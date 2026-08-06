"""双轨采集 Recorder：mic 轨 + 系统音（WASAPI loopback）轨并行采集。

- 独立 PCM 缓存；任一轨缓存超 ``spill_seconds``（默认 5s）即 spill 到
  临时文件，防止长会议 OOM（防 OOM 策略，§4.2）。
- 采集线程与推理零共享：停录后以不可变 ndarray 快照交接。
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from typing import Callable

import numpy as np

from meeting_transcriber.audio.resample import to_16k_mono_f32

DEFAULT_SR = 16000
DEFAULT_SPILL_SECONDS = 5.0
WAVEFORM_MIN_INTERVAL = 0.05  # RMS 节流 ≤50ms
WAVEFORM_POINTS = 32  # 每推送块的峰值包络点数（GUI 滚动波形用）


def _envelope(samples: np.ndarray, n: int = WAVEFORM_POINTS) -> list[float]:
    """峰值包络：把样本块降采样为 ``n`` 个 max|·| 点（音频编辑器风格波形）。

    块内每 ``len//n`` 样本取峰值，保留语音突起的直观形态且数据量恒定。
    """
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        return [0.0] * n
    step = max(1, samples.size // n)
    out: list[float] = []
    for i in range(n):
        seg = samples[i * step : (i + 1) * step]
        out.append(float(np.max(np.abs(seg))) if seg.size else 0.0)
    return out


class _TrackBuffer:
    """单轨 PCM 缓存：超限 spill 到临时文件，续读完整无损。"""

    def __init__(self, sr: int, max_frames: int) -> None:
        self._sr = sr
        self._max_frames = max_frames
        self._chunks: list[np.ndarray] = []
        self._mem_frames = 0
        self._spill_path: str | None = None
        self._spill_frames = 0
        self._lock = threading.Lock()

    def append(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._chunks.append(np.asarray(chunk, dtype=np.float32))
            self._mem_frames += len(chunk)
            if self._mem_frames >= self._max_frames:
                self._spill()

    def _spill(self) -> None:
        data = np.concatenate(self._chunks)
        if self._spill_path is None:
            fd, self._spill_path = tempfile.mkstemp(prefix="mt-spill-", suffix=".f32")
            os.close(fd)
        with open(self._spill_path, "ab") as f:
            f.write(data.tobytes())
        self._spill_frames += len(data)
        self._chunks = []
        self._mem_frames = 0

    def drain(self) -> np.ndarray:
        with self._lock:
            parts: list[np.ndarray] = []
            if self._spill_frames > 0 and self._spill_path:
                with open(self._spill_path, "rb") as f:
                    parts.append(np.frombuffer(f.read(), dtype=np.float32))
            if self._mem_frames > 0:
                parts.append(np.concatenate(self._chunks))
            if not parts:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(parts)

    def cleanup(self) -> None:
        if self._spill_path:
            try:
                os.remove(self._spill_path)
            except OSError:
                pass
            self._spill_path = None


class Recorder:
    """双轨采集器。真实采集经 start()/stop() 启动；核心缓冲逻辑可独立驱动。"""

    def __init__(
        self,
        mic_device: str,
        sys_enabled: bool,
        sys_device: str,
        sr: int = DEFAULT_SR,
        spill_seconds: float = DEFAULT_SPILL_SECONDS,
        mic_gain: float = 1.0,
    ) -> None:
        self._mic_device = mic_device
        self._sys_enabled = sys_enabled
        self._sys_device = sys_device
        self._sr = sr
        self._mic_gain = float(mic_gain)
        self._max_frames = int(sr * spill_seconds)
        self._mic = _TrackBuffer(sr, self._max_frames)
        self._sys = _TrackBuffer(sr, self._max_frames)
        self._running = False
        self._threads: list[threading.Thread] = []
        self._wave_cb: Callable[[dict], None] | None = None
        self._last_wave_ts = 0.0
        # 采集线程失败状态（Critical 1：异常不再被吞，stop() 后可查询上抛）
        self._failures: dict[str, str] = {}
        # 设备实际采样率/声道数（InputStream(samplerate=None) 取设备默认值，常见 48k）
        self._device_sr: dict[str, int] = {}
        self._device_channels: dict[str, int] = {}

    # ---- 波形回调（RMS 节流 ≤50ms）----
    def on_waveform(self, cb: Callable[[dict], None]) -> None:
        self._wave_cb = cb

    def _notify_waveform(self) -> None:
        if self._wave_cb is None:
            return
        now = time.monotonic()
        if now - self._last_wave_ts < WAVEFORM_MIN_INTERVAL:
            return
        self._last_wave_ts = now
        data: dict = {"mic": self._mic_rms(), "sys": self._sys_rms()}
        # 实时波形：最近一回调块的峰值包络（GUI 端累加成滚动波形）
        if self._mic._chunks:
            data["mic_wave"] = _envelope(np.asarray(self._mic._chunks[-1], dtype=np.float32))
        if self._sys._chunks:
            data["sys_wave"] = _envelope(np.asarray(self._sys._chunks[-1], dtype=np.float32))
        self._wave_cb(data)

    def _mic_rms(self) -> float:
        return _rms(self._mic._chunks)

    def _sys_rms(self) -> float:
        return _rms(self._sys._chunks)

    # ---- 数据入口（采集回调 / 测试注入共用）----
    def _feed(
        self,
        track: str,
        chunk: np.ndarray,
        rate: int | None = None,
        channels: int | None = None,
    ) -> None:
        """折叠多声道并重采样到 16k mono。

        rate/channels 为设备实际采样率与声道数（采集回调传入）；
        缺省时按 16k 单声道处理（1D 数据向后兼容）。
        """
        arr = np.asarray(chunk)
        actual_rate = rate if rate is not None else self._sr
        actual_channels = channels if channels is not None else (1 if arr.ndim < 2 else arr.shape[1])
        mono = to_16k_mono_f32(arr, actual_rate, actual_channels)
        if track == "mic":
            # 麦克风增益兜底：系统音频层（如 Nahimic）可能压制第三方应用
            # 的麦克风信号，放大到可转写水平；clip 防饱和爆音
            if self._mic_gain != 1.0:
                mono = np.clip(mono * self._mic_gain, -1.0, 1.0)
            self._mic.append(mono)
        else:
            self._sys.append(mono)
        self._notify_waveform()

    # ---- 真实采集（Windows：WASAPI loopback 经 sounddevice）----
    def start(self) -> None:
        import sounddevice as sd

        self._running = True
        self._threads = []
        self._failures = {}
        self._device_sr = {}
        self._device_channels = {}

        def mic_cb(indata, frames, t, status) -> None:  # noqa: ANN001
            if self._running:
                self._feed(
                    "mic",
                    indata.copy(),
                    rate=self._device_sr.get("mic") or self._sr,
                    channels=indata.shape[1] if indata.ndim > 1 else 1,
                )

        def run_mic() -> None:
            try:
                with sd.InputStream(
                    device=_device_index(self._mic_device),
                    channels=None,  # 设备默认声道数：单声道麦克风不再因强制 2 声道失败
                    samplerate=None,
                    dtype="float32",
                    callback=mic_cb,
                ) as stream:
                    # 设备实际采样率/声道数（samplerate=None 时为设备默认值，常见 48k）
                    self._device_sr["mic"] = int(stream.samplerate)
                    self._device_channels["mic"] = int(stream.channels)
                    while self._running:
                        time.sleep(0.1)
            except Exception as e:  # noqa: BLE001 - 采集失败必须记录，不再静默吞掉
                self._failures["mic"] = f"麦克风轨不可用: {e}"

        def run_sys() -> None:
            if not self._sys_enabled:
                return
            try:
                # 真正的系统音回采：PyAudioWPatch 的 WASAPI loopback
                import pyaudiowpatch as pyaudio

                from meeting_transcriber.audio.devices import loopback_device_index

                idx = loopback_device_index(self._sys_device)
                if idx is None:
                    raise RuntimeError("无可用 WASAPI loopback 设备")
                p = pyaudio.PyAudio()
                try:
                    dev = p.get_device_info_by_index(idx)
                    channels = max(1, int(dev.get("maxInputChannels") or 2))
                    rate = max(1, int(dev.get("defaultSampleRate") or 48000))
                    self._device_sr["sys"] = rate
                    self._device_channels["sys"] = channels

                    def py_cb(in_data, frame_count, time_info, status):  # noqa: ANN001
                        if self._running and in_data:
                            arr = np.frombuffer(in_data, dtype=np.float32)
                            if arr.size:
                                if arr.size % channels == 0:
                                    arr = arr.reshape(-1, channels)
                                self._feed("sys", arr, rate=rate, channels=channels)
                        return (None, pyaudio.paContinue)

                    stream = p.open(
                        format=pyaudio.paFloat32,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=idx,
                        frames_per_buffer=1024,
                        stream_callback=py_cb,
                    )
                    try:
                        while self._running:
                            time.sleep(0.1)
                    finally:
                        stream.stop_stream()
                        stream.close()
                finally:
                    p.terminate()
            except Exception as e:  # noqa: BLE001 - 同上：记录失败轨状态
                self._failures["sys"] = f"系统音轨不可用: {e}"

        t_mic = threading.Thread(target=run_mic, name="rec-mic", daemon=True)
        self._threads.append(t_mic)
        t_mic.start()
        if self._sys_enabled:
            t_sys = threading.Thread(target=run_sys, name="rec-sys", daemon=True)
            self._threads.append(t_sys)
            t_sys.start()

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads = []

    def failures(self) -> dict[str, str]:
        """失败轨状态副本：stop() 后可查询"麦克风轨/系统音轨不可用"信息（GUI 提示用）。"""
        return dict(self._failures)

    def mic_samples(self) -> np.ndarray:
        """16k mono f32（含 spill 续读）。"""
        return self._mic.drain()

    def sys_samples(self) -> np.ndarray:
        return self._sys.drain()

    def cleanup(self) -> None:
        self._mic.cleanup()
        self._sys.cleanup()


def _rms(chunks: list[np.ndarray]) -> float:
    if not chunks:
        return 0.0
    last = chunks[-1]
    if last.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(last))))


def _device_index(name: str) -> int | str:
    """设备名/序号解析：返回 sounddevice 可用的 device 标识。

    麦克风轨经 ``mic_device_index`` 消歧（同名多 hostapi 时优先 MME），
    避免 sounddevice 抛 ``Multiple input devices found``。
    """
    if name == "" or name is None:
        return None  # 系统默认输入设备
    try:
        return int(name)
    except (TypeError, ValueError):
        from meeting_transcriber.audio.devices import mic_device_index

        return mic_device_index(name)
