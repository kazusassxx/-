"""阶段 1.8：单路失衡 spill 防 OOM。

WHY：长会议中若某一路（如系统音）持续有声而另一路静音，PCM 若全部
驻留内存会 OOM 崩溃丢数据；spill 后内存受限且续读数据必须完整无损。
"""
import numpy as np

from meeting_transcriber.audio.capture import Recorder

ONE_SEC = 16000
SPILL_SECONDS = 5.0


def test_sys_track_spill_bounds_memory_and_drains_fully(tmp_path):
    rec = Recorder("", True, "", sr=16000, spill_seconds=SPILL_SECONDS)
    chunk = np.full(ONE_SEC, 0.5, dtype=np.float32)
    total = 0
    for _ in range(30):  # 模拟 30s 系统音持续有声
        rec._feed("sys", chunk)
        total += ONE_SEC

    # 内存中保留帧数不超过 spill 阈值，其余已写临时文件（不 OOM）
    assert rec._sys._mem_frames <= int(SPILL_SECONDS * 16000)

    # 续读完整：30s 数据无损还原
    samples = rec.sys_samples()
    assert len(samples) == total
    np.testing.assert_allclose(samples, np.full(total, 0.5), atol=1e-6)

    rec.cleanup()


def test_balanced_tracks_no_spill_under_threshold(tmp_path):
    """短于阈值的双轨录音全部驻留内存，不产生 spill 文件。"""
    rec = Recorder("", True, "", sr=16000, spill_seconds=SPILL_SECONDS)
    for _ in range(3):  # 3s < 5s
        rec._feed("mic", np.zeros(ONE_SEC, dtype=np.float32))
        rec._feed("sys", np.zeros(ONE_SEC, dtype=np.float32))

    assert rec._mic._spill_path is None
    assert rec._sys._spill_path is None
    assert len(rec.mic_samples()) == 3 * ONE_SEC
    assert len(rec.sys_samples()) == 3 * ONE_SEC
    rec.cleanup()


def test_spill_keeps_mic_track_intact(tmp_path):
    """sys 轨 spill 不污染 mic 轨数据（双轨独立缓存）。"""
    rec = Recorder("", True, "", sr=16000, spill_seconds=SPILL_SECONDS)
    mic_chunk = np.full(ONE_SEC, 0.25, dtype=np.float32)
    sys_chunk = np.full(ONE_SEC, 0.5, dtype=np.float32)
    for _ in range(6):  # 仅 sys 超过阈值
        rec._feed("mic", mic_chunk)
        rec._feed("sys", sys_chunk)

    mic = rec.mic_samples()
    sys = rec.sys_samples()
    assert len(mic) == 6 * ONE_SEC
    assert len(sys) == 6 * ONE_SEC
    np.testing.assert_allclose(np.unique(mic), np.array([0.25]), atol=1e-6)
    np.testing.assert_allclose(np.unique(sys), np.array([0.5]), atol=1e-6)
    rec.cleanup()
