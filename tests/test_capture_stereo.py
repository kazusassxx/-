"""Critical 1：采集声道折叠/采样率双重错误修复 + 采集线程异常上抛。

WHY（行为意图）：
- 原 _feed 对 2D chunk 硬编码 channels=1 使声道折叠分支永不执行，且源
  采样率被当成 16000 而非设备实际采样率；48k 立体声下 np.interp 对 2D
  数组抛 ValueError，回调异常被 except: pass 吞掉 → 录音线程静默死亡
  产空 WAV。
- 修复后：2D 立体声 48kHz chunk 必须正确折叠为 16k 单声道；采集线程
  异常必须记录失败轨状态，GUI 才能提示"系统音轨/麦克风轨不可用"。
"""
import sys
import types

import numpy as np

from meeting_transcriber.audio.capture import Recorder


def test_feed_mic_gain_amplifies_and_clips():
    """麦克风增益：弱信号放大到可转写水平，clip 防饱和，sys 轨不受影响。

    WHY：系统音频层（如 Nahimic）可能压制第三方应用的麦克风信号，
    增益兜底把弱信号放大；放大不得产生 >1.0 的饱和爆音。
    """
    rec = Recorder("", False, "", sr=16000, mic_gain=10.0)
    rec._feed("mic", np.full(1600, 0.02, dtype=np.float32), rate=16000, channels=1)
    s = rec.mic_samples()
    assert s.size == 1600
    assert np.isclose(float(np.max(np.abs(s))), 0.2, atol=1e-5)  # 0.02 * 10

    rec2 = Recorder("", False, "", sr=16000, mic_gain=50.0)
    rec2._feed("mic", np.full(1600, 0.1, dtype=np.float32), rate=16000, channels=1)
    assert float(np.max(np.abs(rec2.mic_samples()))) <= 1.0  # 饱和保护

    rec3 = Recorder("", True, "", sr=16000, mic_gain=10.0)
    rec3._feed("sys", np.full(1600, 0.5, dtype=np.float32), rate=16000, channels=1)
    assert float(np.max(np.abs(rec3.sys_samples()))) == 0.5  # sys 轨不加增益


def _stereo_48k(seconds=1.0, left=0.5, right=0.25):
    n = int(48000 * seconds)
    return np.stack(
        [np.full(n, left, dtype=np.float32), np.full(n, right, dtype=np.float32)],
        axis=1,
    )


def test_feed_stereo_48k_chunk_produces_16k_mono():
    """2D 立体声 48kHz chunk → 16k 单声道（声道折叠 + 重采样同时生效）。"""
    rec = Recorder("", True, "", sr=16000, spill_seconds=5.0)
    rec._feed("sys", _stereo_48k(), rate=48000, channels=2)

    out = rec.sys_samples()
    assert out.ndim == 1  # 折叠为单声道
    assert len(out) == 16000  # 16k 采样率契约
    # 0.5 与 0.25 均值 0.375，常量信号经重采样应保持
    np.testing.assert_allclose(out, np.full(16000, 0.375), atol=1e-4)
    rec.cleanup()


def test_feed_1d_16k_chunk_without_rate_params_still_works():
    """现有 1D 16k 调用（不传 rate/channels）行为不变（向后兼容）。"""
    rec = Recorder("", True, "", sr=16000, spill_seconds=5.0)
    chunk = np.full(16000, 0.5, dtype=np.float32)
    rec._feed("mic", chunk)

    out = rec.mic_samples()
    assert out.ndim == 1
    assert len(out) == 16000
    rec.cleanup()


class _FailingInputStream:
    """构造即抛异常：模拟声卡打开失败。"""

    def __init__(self, *a, **k):
        raise RuntimeError("无法打开音频设备")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_sounddevice(monkeypatch, stream_cls, loopback_ok=True):
    """mock sounddevice（mic 轨）+ pyaudiowpatch（sys 轨 loopback）。"""
    fake = types.ModuleType("sounddevice")
    fake.InputStream = stream_cls
    fake.query_devices = lambda: [
        {"name": "mic-dev", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000, "hostapi": 0},
        {"name": "Microsoft 声音映射器 - Input", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000, "hostapi": 0},
    ]
    fake.query_hostapis = lambda: [{"name": "MME"}]
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    from meeting_transcriber.audio import devices

    monkeypatch.setattr(devices, "sd", fake)

    pa = types.ModuleType("pyaudiowpatch")

    class _Stream:
        def stop_stream(self):
            pass

        def close(self):
            pass

    class _PyAudio:
        def __init__(self):
            pass

        def terminate(self):
            pass

        def get_device_info_by_index(self, idx):
            return {"name": "扬声器 (Realtek(R) Audio) [Loopback]", "maxInputChannels": 2, "defaultSampleRate": 48000}

        def open(self, *a, **k):
            if not loopback_ok:
                raise RuntimeError("WASAPI loopback 不可用")
            return _Stream()

    pa.PyAudio = _PyAudio
    pa.paFloat32 = 1
    pa.paContinue = 1
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", pa)
    monkeypatch.setattr(devices, "loopback_device_index", lambda name: 5)


def test_capture_thread_failure_recorded_not_swallowed(monkeypatch):
    """双轨采集线程异常不再被吞：失败轨状态可查询（GUI 提示用）。"""
    _install_fake_sounddevice(monkeypatch, _FailingInputStream, loopback_ok=False)
    rec = Recorder("", True, "", sr=16000)
    rec.start()
    rec.stop()  # join 线程后上抛失败轨状态

    failures = rec.failures()
    assert "mic" in failures and "sys" in failures
    assert failures["mic"] and failures["sys"]  # 非空错误信息
    assert "不可用" in failures["mic"]
    rec.cleanup()


def test_partial_failure_records_only_failed_track(monkeypatch):
    """仅系统音轨失败时只记录 sys：降级保留 mic 轨（不因单轨失败放弃双轨）。"""
    _install_fake_sounddevice(monkeypatch, lambda *a, **k: _OkStream(), loopback_ok=False)
    rec = Recorder("mic-dev", True, "sys-dev", sr=16000)
    rec.start()
    rec.stop()

    failures = rec.failures()
    assert "sys" in failures
    assert "mic" not in failures  # mic 轨正常，不误报
    rec.cleanup()


class _OkStream:
    def __enter__(self):
        self.samplerate = 48000
        self.channels = 2
        return self

    def __exit__(self, *a):
        return False
