"""GUI 工作线程（任务 8.6）：录音 / 转写 QThread，与 GUI 线程解耦。

并发模型（design.md）：
- ``RecordingWorker``：纯采集 + 混音落盘 + 波形节流推送（≤50ms），
  录音期间零 AI 推理（P2）；停录瞬间以不可变 ndarray 快照交接 PCM。
- ``TranscriptionWorker``：消费录音快照 / 导入音频，跑 pipeline；
  模型未就绪时挂起等待，就绪后自动续转（P3/F-4）；取消经 Event
  段边界检查，取消后不产出报告（E-6）。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

from meeting_transcriber.audio.capture import Recorder
from meeting_transcriber.audio.import_audio import decode_to_16k_mono
from meeting_transcriber.audio.mix import mix_and_save
from meeting_transcriber.pipeline.merge import merge_tracks
from meeting_transcriber.pipeline.pipeline import TranscriptionPipeline
from meeting_transcriber.pipeline.segment import Segment
from meeting_transcriber.report.atomicio import write_text_atomic
from meeting_transcriber.report.formatter import format_report

POLL_INTERVAL = 0.1  # 等待模型就绪的轮询间隔（秒）


@dataclass
class TranscriptionResult:
    """转写完成产物：段列表 + 双轨快照（声纹注册切片用）+ 报告。"""

    segments: list[Segment]
    mic_samples: np.ndarray
    sys_samples: np.ndarray
    report_text: str
    report_path: str
    notes: tuple[str, ...] = ()  # 降级/提示信息（如分割模型未下载）


class RecordingWorker(QThread):
    """录音线程：纯采集 + 混音落盘，不做任何推理（P2）。

    信号: waveform(dict{mic, sys}) / finished_ok(mic, sys, wav_path) / error(str)
    """

    waveform = Signal(dict)
    finished_ok = Signal(object, object, str)
    error = Signal(str)
    track_failed = Signal(str)  # Critical 1：失败轨状态（"麦克风轨/系统音轨不可用"）

    def __init__(
        self,
        mic_device: str,
        sys_enabled: bool,
        sys_device: str,
        out_path: Path,
        sys_gain: float = 0.9,
        mic_gain: float = 1.0,
        recorder_cls=Recorder,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._mic_device = mic_device
        self._sys_enabled = sys_enabled
        self._sys_device = sys_device
        self._out_path = Path(out_path)
        self._sys_gain = sys_gain
        self._mic_gain = mic_gain
        self._recorder_cls = recorder_cls
        self._stop_evt = threading.Event()

    def request_stop(self) -> None:
        """GUI 线程调用：请求停录，worker 完成收尾后发 finished_ok。"""
        self._stop_evt.set()

    def run(self) -> None:  # noqa: D102 - QThread.run
        rec = self._recorder_cls(
            self._mic_device,
            self._sys_enabled,
            self._sys_device,
            mic_gain=self._mic_gain,
        )
        try:
            rec.on_waveform(self.waveform.emit)  # RMS 节流已由 Recorder 保证 ≤50ms
            rec.start()
            while not self._stop_evt.wait(POLL_INTERVAL):
                pass
            rec.stop()
            # Critical 1：失败轨状态上抛（不再静默吞掉），另一轨仍降级产出
            for track, msg in rec.failures().items():
                label = "系统音轨" if track == "sys" else "麦克风轨"
                self.track_failed.emit(f"{label}不可用: {msg}")
            mic = np.asarray(rec.mic_samples(), dtype=np.float32)
            sys = np.asarray(rec.sys_samples(), dtype=np.float32)
            self._out_path.parent.mkdir(parents=True, exist_ok=True)
            mix_and_save(mic, sys, self._out_path, self._sys_gain)
            self.finished_ok.emit(mic, sys, str(self._out_path))
        except Exception as e:  # noqa: BLE001 - 采集异常必须反馈给 GUI
            self.error.emit(str(e))
        finally:
            rec.cleanup()


class TranscriptionWorker(QThread):
    """转写线程：双轨（mic/sys）或导入（单轨）跑 pipeline → 合并 → 落盘。

    信号: progress(float) / finished_ok(TranscriptionResult) / cancelled / error(str)
    """

    progress = Signal(float)
    finished_ok = Signal(object)
    cancelled = Signal()
    error = Signal(str)

    def __init__(
        self,
        models,
        config: dict,
        mic_samples: np.ndarray,
        sys_samples: np.ndarray,
        out_path: Path,
        track_sys: str = "sys",
        import_path: Path | None = None,
        speaker_db=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._models = models
        self._config = config
        self._mic = np.asarray(mic_samples, dtype=np.float32)
        self._sys = np.asarray(sys_samples, dtype=np.float32)
        self._out_path = Path(out_path)
        self._track_sys = track_sys  # "sys"（双轨录音）| "import"（导入音频）
        self._import_path = Path(import_path) if import_path is not None else None
        self._speaker_db = speaker_db  # Critical 2：声纹库注入 pipeline（C-4）
        self._cancelled = threading.Event()
        self._pipeline: TranscriptionPipeline | None = None

    def cancel(self) -> None:
        """GUI 线程调用：置取消令牌，pipeline 在段边界停止（E-6）。"""
        self._cancelled.set()

    def _wait_models_ready(self) -> bool:
        """模型未就绪时挂起等待；error 或用户取消返回 False（P3/F-4）。"""
        while self._models.status == "loading":
            if self._cancelled.is_set():
                return False
            time.sleep(POLL_INTERVAL)
        return self._models.status == "ready"

    def run(self) -> None:  # noqa: D102 - QThread.run
        try:
            if self._import_path is not None:
                # 导入音频：worker 内解码，避免阻塞 GUI 线程（F-2）
                samples = decode_to_16k_mono(self._import_path)
                self._mic = np.zeros(0, dtype=np.float32)
                self._sys = samples
                self._track_sys = "import"
            if not self._wait_models_ready():
                if self._cancelled.is_set():
                    self.cancelled.emit()
                else:
                    self.error.emit(str(self._models.error or "模型未就绪"))
                return
            self._pipeline = TranscriptionPipeline(
                self._models, self._config, speaker_db=self._speaker_db
            )

            mic_segs: list[Segment] = []
            if self._mic.size > 0:
                mic_segs = self._run_track(self._mic, "mic", 0.0, 0.5)
                if self._cancelled.is_set():
                    self.cancelled.emit()
                    return

            sys_segs: list[Segment] = []
            if self._sys.size > 0:
                sys_segs = self._run_track(self._sys, self._track_sys, 0.5, 0.5)
                if self._cancelled.is_set():
                    self.cancelled.emit()
                    return

            segments = merge_tracks(mic_segs, sys_segs)
            # Info 1：写盘前再查取消——双轨完成瞬间用户取消不得产出（半截）报告
            if self._cancelled.is_set():
                self.cancelled.emit()
                return

            notes = []
            if self._pipeline.segmentation_note:
                notes.append(self._pipeline.segmentation_note)
            report_text = format_report(
                segments, str(self._config.get("user_name") or ""), date.today()
            )
            self._out_path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(self._out_path, report_text)
            self.finished_ok.emit(
                TranscriptionResult(
                    segments=segments,
                    mic_samples=self._mic,
                    sys_samples=self._sys,
                    report_text=report_text,
                    report_path=str(self._out_path),
                    notes=tuple(notes),
                )
            )
        except Exception as e:  # noqa: BLE001 - 转写异常必须反馈给 GUI
            self.error.emit(str(e))

    def _run_track(self, samples: np.ndarray, track: str, lo: float, span: float) -> list[Segment]:
        """单轨转写；进度映射到 [lo, lo+span] 区间，段边界检查取消。"""
        pipe = self._pipeline
        assert pipe is not None

        def cb(p: float) -> None:
            self.progress.emit(lo + span * p)

        return pipe.run(samples, track, progress=cb, cancelled=self._cancelled)
