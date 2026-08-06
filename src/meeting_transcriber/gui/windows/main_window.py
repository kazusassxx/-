"""主窗口（8.3/8.7/8.8）：四状态页 + 发言人面板 + 模型状态指示 + 导入音频。

- 状态驱动：QStackedWidget 按 StateMachine 切换（就绪/录音/转写/完成/导入转写）
- 录音态：双轨波形 + 计时 + 停止键；转写态：进度条 + spinner + 取消（G-3/G-4）
- 完成态：预览 + 打开文件（G-5）；左栏发言人面板命名/改名即时刷新（G-12/G-13，E-7）
- 模型状态指示 + 重试（G-14）；导入音频转写（G-11）
"""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from meeting_transcriber import paths
from meeting_transcriber.gui.state_machine import State, StateMachine
from meeting_transcriber.gui.workers import (
    RecordingWorker,
    TranscriptionResult,
    TranscriptionWorker,
)
from meeting_transcriber.gui.windows.mini_window import MiniWindow
from meeting_transcriber.gui.windows.settings_dialog import SettingsDialog
from meeting_transcriber.gui.windows.waveform import WaveformWidget
from meeting_transcriber.models.manager import ModelManager
from meeting_transcriber.pipeline import embedding
from meeting_transcriber.report.atomicio import write_text_atomic
from meeting_transcriber.report.formatter import format_report
from meeting_transcriber.storage.config import save_config
from meeting_transcriber.storage.speakers import SpeakerDB

SR = 16000


class MainWindow(QMainWindow):
    """主窗口：状态机驱动 + QThread 工作线程（录音零推理，P2）。"""

    def __init__(
        self,
        config: dict,
        models: ModelManager | None = None,
        speaker_db: SpeakerDB | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._models = models or ModelManager(
            num_threads=int(self._config.get("num_threads") or 4),
            lang=str(self._config.get("asr_lang") or "auto"),
        )
        self._db = speaker_db or SpeakerDB.load(paths.speakers_path())
        self._sm = StateMachine()
        self._rec_worker: RecordingWorker | None = None
        self._tx_worker: TranscriptionWorker | None = None
        self._result: TranscriptionResult | None = None
        self._report_date = date.today()
        self._elapsed = 0

        self._mini = MiniWindow()
        self._mini.stop_requested.connect(self._on_stop_recording)

        self._build_ui()
        self._start_model_load()
        self._apply_state()

    # ================= UI 构建 =================
    def _build_ui(self) -> None:
        self.setWindowTitle("Meeting Transcriber")
        self.resize(880, 620)

        # 顶部：模型状态指示（G-14）+ 设置入口（G-7，任务 8.5）
        self._model_label = QLabel()
        self._retry_btn = QPushButton(self.tr("重试"))
        self._retry_btn.hide()
        self._retry_btn.clicked.connect(self._retry_models)
        self._settings_btn = QPushButton(self.tr("设置"))
        self._settings_btn.clicked.connect(self._open_settings)
        top = QHBoxLayout()
        top.addWidget(self._model_label)
        top.addStretch(1)
        top.addWidget(self._retry_btn)
        top.addWidget(self._settings_btn)

        # 中央：左发言人面板 + 右状态页
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_ready_page())  # 0 就绪
        self._stack.addWidget(self._build_recording_page())  # 1 录音
        self._stack.addWidget(self._build_transcribing_page())  # 2 转写
        self._stack.addWidget(self._build_completed_page())  # 3 完成

        splitter = QSplitter()
        splitter.addWidget(self._build_speaker_panel())
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 660])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # 计时器：录音计时 + 模型状态轮询（ModelManager 无 Qt 信号，GUI 侧轮询广播）
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._tick)

        self._model_timer = QTimer(self)
        self._model_timer.setInterval(300)
        self._model_timer.timeout.connect(self._poll_models)
        self._model_timer.start()

    def _build_ready_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addStretch(1)
        self._record_btn = QPushButton(self.tr("开始录音"))
        self._record_btn.setMinimumHeight(56)
        self._record_btn.clicked.connect(self._on_start_recording)
        self._import_btn = QPushButton(self.tr("导入音频转写"))
        self._import_btn.setMinimumHeight(40)
        self._import_btn.clicked.connect(self._on_import_audio)
        layout.addWidget(self._record_btn)
        layout.addWidget(self._import_btn)
        layout.addStretch(1)
        return w

    def _build_recording_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addStretch(1)
        self._rec_wave = WaveformWidget()
        self._rec_wave.setMinimumSize(400, 220)  # 主窗录音页：更大的波形区域
        self._time_label = QLabel("00:00")
        self._time_label.setAlignment(Qt.AlignCenter)
        stop_btn = QPushButton(self.tr("停止录音"))
        stop_btn.clicked.connect(self._on_stop_recording)
        layout.addWidget(self._rec_wave)
        layout.addWidget(self._time_label)
        layout.addWidget(stop_btn)
        layout.addStretch(1)
        return w

    def _build_transcribing_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addStretch(1)

        self._wait_label = QLabel(self.tr("模型未就绪，正在等待..."))
        self._wait_label.setAlignment(Qt.AlignCenter)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress_label = QLabel("0%")
        self._progress_label.setAlignment(Qt.AlignCenter)

        self._spinner = QProgressBar()  # indeterminate 动画条（spinner）
        self._spinner.setRange(0, 0)
        self._spinner.setFixedHeight(6)

        cancel_btn = QPushButton(self.tr("取消转写"))
        cancel_btn.clicked.connect(self._on_cancel_transcription)

        layout.addWidget(self._wait_label)
        layout.addWidget(self._progress)
        layout.addWidget(self._progress_label)
        layout.addWidget(self._spinner)
        layout.addWidget(cancel_btn)
        layout.addStretch(1)
        return w

    def _build_completed_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._new_record_btn = QPushButton(self.tr("开始录音"))
        self._new_record_btn.clicked.connect(self._on_start_recording)
        self._new_import_btn = QPushButton(self.tr("导入音频转写"))
        self._new_import_btn.clicked.connect(self._on_import_audio)
        open_btn = QPushButton(self.tr("打开文件"))
        open_btn.clicked.connect(self._open_report)

        btns = QHBoxLayout()
        btns.addWidget(self._new_record_btn)
        btns.addWidget(self._new_import_btn)
        btns.addWidget(open_btn)
        layout.addLayout(btns)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        layout.addWidget(self._preview, 1)
        return w

    def _build_speaker_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        title = QLabel(self.tr("本场发言人"))
        self._speaker_list = QListWidget()
        self._speaker_list.currentRowChanged.connect(lambda _r: self._sync_name_input())

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self.tr("命名"))
        rename_btn = QPushButton(self.tr("命名"))
        rename_btn.clicked.connect(self._rename_speaker)
        reg_btn = QPushButton(self.tr("注册声纹"))
        reg_btn.clicked.connect(self._register_speaker)

        btns = QHBoxLayout()
        btns.addWidget(rename_btn)
        btns.addWidget(reg_btn)

        layout.addWidget(title)
        layout.addWidget(self._speaker_list, 1)
        layout.addWidget(self._name_edit)
        layout.addLayout(btns)
        return w

    # ================= 设置（G-7，任务 8.5）=================
    def _open_settings(self) -> None:
        if self._sm.state in (State.TRANSCRIBING, State.IMPORTING):
            QMessageBox.information(
                self, self.tr("设置"), self.tr("转写进行中，请完成后再修改设置。")
            )
            return
        old_lang = str(self._config.get("asr_lang") or "auto")
        dlg = SettingsDialog(self._config, self._db, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_lang = str(self._config.get("asr_lang") or "auto")
            # 识别语言变更 → 重载模型使新语言生效（SenseVoice 语言在模型加载时固定）
            if new_lang != old_lang and self._models.status in ("ready", "error"):
                self._models.set_lang(new_lang)
                self._models.load_async()

    # ================= 模型状态（G-14）=================
    def _start_model_load(self) -> None:
        self._models.load_async()

    def _retry_models(self) -> None:
        self._models.load_async()

    def _poll_models(self) -> None:
        status = self._models.status
        if status == "ready":
            self._model_label.setText(self.tr("模型就绪"))
            self._retry_btn.hide()
        elif status == "loading":
            self._model_label.setText(self.tr("正在加载推理引擎"))
            self._retry_btn.hide()
        elif status == "error":
            self._model_label.setText(
                self.tr("模型加载失败") + f": {self._models.error or ''}"
            )
            self._retry_btn.show()
        else:  # idle
            self._model_label.setText(self.tr("正在加载推理引擎"))
            self._retry_btn.hide()

    # ================= 录音（P2 零推理）=================
    def _on_start_recording(self) -> None:
        if not self._sm.can("record"):
            return
        self._sm.record()
        self._elapsed = 0
        self._time_label.setText("00:00")
        self._rec_timer.start()
        self._apply_state()

        out = self._output_path("record")
        self._rec_wave.clear()
        self._mini.clear_wave()
        self._rec_worker = RecordingWorker(
            mic_device=str(self._config.get("mic_device") or ""),
            sys_enabled=bool(self._config.get("sys_audio_enabled", True)),
            sys_device=str(self._config.get("sys_audio_device") or ""),
            out_path=out,
            sys_gain=float(self._config.get("sys_mix_gain", 0.9)),
            mic_gain=float(self._config.get("mic_gain", 10.0)),
        )
        self._rec_worker.waveform.connect(self._on_waveform)
        self._rec_worker.track_failed.connect(self._on_track_failed)
        self._rec_worker.finished_ok.connect(self._on_recording_finished)
        self._rec_worker.error.connect(self._on_recording_error)
        self._rec_worker.finished.connect(self._on_rec_worker_finished)
        self._rec_worker.start()

        self.hide()
        self._mini.show_at_top_right()

    def _on_rec_worker_finished(self) -> None:
        """录音线程真正结束后才释放引用（防 QThread 运行中析构崩溃）。"""
        if self._rec_worker is not None:
            self._rec_worker.deleteLater()
            self._rec_worker = None

    def _on_stop_recording(self) -> None:
        if self._sm.state is not State.RECORDING:
            return
        self._mini.hide()
        self.show()
        self._rec_timer.stop()
        self._sm.stop()  # 录音 → 转写
        self._apply_state()
        if self._rec_worker is not None:
            self._rec_worker.request_stop()

    def _on_waveform(self, data: dict) -> None:
        self._rec_wave.set_wave(data)
        self._mini.set_wave(data)

    def _tick(self) -> None:
        self._elapsed += 1
        text = f"{self._elapsed // 60:02d}:{self._elapsed % 60:02d}"
        self._time_label.setText(text)
        self._mini.set_elapsed(self._elapsed)

    def _on_recording_finished(self, mic, sys, wav_path) -> None:  # noqa: ANN001
        if self._sm.state is not State.TRANSCRIBING:
            return
        out = self._output_path("transcript")
        self._tx_worker = TranscriptionWorker(
            self._models, self._config, mic, sys, out, track_sys="sys",
            speaker_db=self._db,  # Critical 2：声纹库注入转写管线（C-4）
        )
        self._connect_tx()
        self._tx_worker.start()

    def _on_recording_error(self, msg: str) -> None:
        self._mini.hide()
        self.show()
        self._rec_timer.stop()
        QMessageBox.warning(self, self.tr("录音失败"), msg)
        # 录音态无直接回退边：走 停止→取消 合法路径回就绪
        if self._sm.state is State.RECORDING:
            self._sm.stop()
        if self._sm.can("cancel"):
            self._sm.cancel()
        self._apply_state()

    def _on_track_failed(self, msg: str) -> None:
        """Critical 1：某采集轨失败不再静默——提示用户，另一轨仍降级产出。"""
        QMessageBox.information(self, self.tr("录音提示"), msg)

    # ================= 转写 =================
    def _on_import_audio(self) -> None:
        if not self._sm.can("import_audio"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("导入音频转写"), "", "Audio (*.wav *.mp3 *.flac)"
        )
        if not path:
            return
        self._sm.import_audio()
        self._apply_state()
        out = self._output_path("transcript")
        self._tx_worker = TranscriptionWorker(
            self._models,
            self._config,
            np.zeros(0, dtype=np.float32),
            np.zeros(0, dtype=np.float32),
            out,
            track_sys="import",
            import_path=Path(path),
            speaker_db=self._db,  # Critical 2：声纹库注入转写管线（C-4）
        )
        self._connect_tx()
        self._tx_worker.start()

    def _connect_tx(self) -> None:
        assert self._tx_worker is not None
        self._tx_worker.progress.connect(self._on_tx_progress)
        self._tx_worker.finished_ok.connect(self._on_tx_finished)
        self._tx_worker.cancelled.connect(self._on_tx_cancelled)
        self._tx_worker.error.connect(self._on_tx_error)
        self._tx_worker.finished.connect(self._on_tx_worker_finished)

    def _on_tx_worker_finished(self) -> None:
        """转写线程真正结束后才释放引用（防 QThread 运行中析构崩溃）。"""
        if self._tx_worker is not None:
            self._tx_worker.deleteLater()
            self._tx_worker = None

    def _on_tx_progress(self, p: float) -> None:
        pct = max(0.0, min(1.0, float(p)))  # 钳制到 [0, 100%]：双轨进度映射异常时不再溢出显示
        self._progress.setValue(int(pct * 100))
        self._progress_label.setText(f"{int(pct * 100)}%")

    def _on_tx_finished(self, result: TranscriptionResult) -> None:
        self._result = result
        self._report_date = date.today()
        self._sm.finish()
        self._load_speaker_panel()
        self._refresh_report()
        self._apply_state()
        if result.notes:  # 降级提示（如说话人分割模型未下载）
            self.statusBar().showMessage("；".join(result.notes), 8000)

    def _on_tx_cancelled(self) -> None:
        if self._sm.can("cancel"):
            self._sm.cancel()
        self._progress.setValue(0)
        self._progress_label.setText("0%")
        self._apply_state()

    def _on_tx_error(self, msg: str) -> None:
        QMessageBox.critical(self, self.tr("转写失败"), msg)
        if self._sm.can("cancel"):
            self._sm.cancel()
        self._progress.setValue(0)
        self._apply_state()

    def _on_cancel_transcription(self) -> None:
        if self._tx_worker is not None:
            self._tx_worker.cancel()

    # ================= 发言人面板（G-12/G-13，E-7）=================
    def _load_speaker_panel(self) -> None:
        self._speaker_list.clear()
        if self._result is None:
            return
        seen: dict[str, str] = {}
        for seg in self._result.segments:
            seen.setdefault(seg.speaker_ref, seg.speaker_name)
        for ref, name in seen.items():
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, ref)
            self._speaker_list.addItem(item)

    def _selected_ref(self) -> str | None:
        item = self._speaker_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _sync_name_input(self) -> None:
        item = self._speaker_list.currentItem()
        self._name_edit.setText(item.text() if item is not None else "")

    def _rename_speaker(self) -> None:
        ref = self._selected_ref()
        new_name = self._name_edit.text().strip()
        if ref is None or not new_name or self._result is None:
            return
        if ref == "me":
            # "我"的名字 = 用户姓名：改配置并持久化（format_report 单一真相源）
            self._config["user_name"] = new_name
            save_config(self._config)
        else:
            self._result.segments = [
                replace(seg, speaker_name=new_name) if seg.speaker_ref == ref else seg
                for seg in self._result.segments
            ]
        self._load_speaker_panel()
        self._refresh_report()  # E-7：预览与 MD 立即刷新为新名称

    def _register_speaker(self) -> None:
        ref = self._selected_ref()
        if ref is None or self._result is None:
            return
        if ref == "me":
            QMessageBox.information(self, self.tr("注册声纹"), self.tr("「我」无需注册声纹，改名请使用命名按钮。"))
            return
        new_name = self._name_edit.text().strip()
        seg = next((s for s in self._result.segments if s.speaker_ref == ref), None)
        if seg is None:
            return
        track_samples = (
            self._result.mic_samples if seg.track == "mic" else self._result.sys_samples
        )
        sl = track_samples[int(seg.start * SR) : int(seg.end * SR)]
        if sl.size == 0:
            QMessageBox.warning(self, self.tr("注册声纹"), self.tr("该发言人无声纹样本，无法注册。"))
            return
        try:
            embedding.set_model(self._models.get("embedding"))
            vec = embedding.extract_embedding(sl)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, self.tr("注册声纹"), str(e))
            return
        if new_name:
            self._result.segments = [
                replace(seg2, speaker_name=new_name) if seg2.speaker_ref == ref else seg2
                for seg2 in self._result.segments
            ]
        self._db.register(new_name or seg.speaker_name, vec)
        self._db.save()
        self._load_speaker_panel()
        self._refresh_report()
        QMessageBox.information(
            self, self.tr("注册声纹"), self.tr("已注册声纹：") + (new_name or seg.speaker_name)
        )

    def _refresh_report(self) -> None:
        """预览与 MD 文件同时刷新（E-7 单一真相源 format_report）。"""
        if self._result is None:
            return
        text = format_report(
            self._result.segments,
            str(self._config.get("user_name") or ""),
            self._report_date,
        )
        self._result.report_text = text
        try:
            write_text_atomic(Path(self._result.report_path), text)
        except OSError as e:  # Info 3：写盘异常不再静默吞掉
            QMessageBox.critical(self, self.tr("报告保存失败"), str(e))
        self._preview.setPlainText(text)

    # ================= 完成态动作（G-5）=================
    def _open_report(self) -> None:
        if self._result is None:
            return
        p = Path(self._result.report_path)
        if sys.platform == "win32":
            import subprocess

            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    # ================= 状态应用 =================
    def _apply_state(self) -> None:
        s = self._sm.state
        page = {
            State.READY: 0,
            State.RECORDING: 1,
            State.TRANSCRIBING: 2,
            State.IMPORTING: 2,
            State.COMPLETED: 3,
        }[s]
        self._stack.setCurrentIndex(page)

        # 录音按钮启用规则（G-4）：仅就绪/完成态可开始录音
        enabled = self._sm.can("record")
        self._record_btn.setEnabled(enabled)
        self._new_record_btn.setEnabled(enabled)
        self._import_btn.setEnabled(self._sm.can("import_audio"))
        self._new_import_btn.setEnabled(self._sm.can("import_audio"))

        transcribing = s in (State.TRANSCRIBING, State.IMPORTING)
        self._spinner.setRange(0, 0 if transcribing else 1)
        self._wait_label.setVisible(transcribing)

        status = {
            State.READY: self.tr("就绪"),
            State.RECORDING: self.tr("录音中"),
            State.TRANSCRIBING: self.tr("转写中"),
            State.IMPORTING: self.tr("转写中"),
            State.COMPLETED: self.tr("转写完成"),
        }[s]
        self.statusBar().showMessage(status)

    # ================= 工具 =================
    def _output_path(self, kind: str) -> Path:
        out_dir = Path(self._config.get("output_dir") or "")
        if not out_dir.is_absolute():
            out_dir = Path.home() / "Documents" / "MeetingTranscripts"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "record" if kind == "record" else "transcript"
        return out_dir / f"{prefix}_{stamp}.wav" if kind == "record" else out_dir / f"{prefix}_{stamp}.md"
