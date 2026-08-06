"""阶段 1.5：mix_and_save() 混音落盘契约。

WHY：A-7 要求系统音以 0.9 衰减避免盖过人声——若衰减缺失，会后系统
提示音会淹没说话人；WAV 必须为 16k/16bit/mono 供 ASR 直接消费。
"""
import numpy as np
import soundfile as sf

from meeting_transcriber.audio.mix import mix_and_save


def test_wav_format_contract(tmp_path):
    out = tmp_path / "mix.wav"
    mix_and_save(
        np.zeros(16000, dtype=np.float32),
        np.zeros(16000, dtype=np.float32),
        out,
    )
    info = sf.info(out)
    assert info.samplerate == 16000
    assert info.channels == 1
    assert info.subtype == "PCM_16"


def test_sys_track_attenuated_by_09(tmp_path):
    """系统音 0.5 经 0.9 衰减后混音幅度为 0.45（防盖过人声 A-7）。"""
    mic = np.zeros(16000, dtype=np.float32)
    sys = np.full(16000, 0.5, dtype=np.float32)
    out = tmp_path / "mix.wav"

    mix_and_save(mic, sys, out)

    data, _ = sf.read(out, dtype="float32")
    np.testing.assert_allclose(np.abs(data), np.full(16000, 0.45), atol=0.01)


def test_uneven_tracks_aligned_to_longest(tmp_path):
    """双轨时长不一致时对齐到最长轨，短轨补零不截断。"""
    mic = np.zeros(8000, dtype=np.float32)  # 0.5s
    sys = np.full(16000, 0.5, dtype=np.float32)  # 1s
    out = tmp_path / "mix.wav"

    mix_and_save(mic, sys, out)

    data, _ = sf.read(out, dtype="float32")
    assert len(data) == 16000
    np.testing.assert_allclose(data, np.full(16000, 0.45), atol=0.01)


def test_clip_is_clamped_not_wrapped(tmp_path):
    """极端输入混音后必须钳制在 [-1, 1]，绝不环绕产生爆音。"""
    mic = np.full(16000, 0.9, dtype=np.float32)
    sys = np.full(16000, 0.9, dtype=np.float32)  # 0.9 + 0.9*0.9 = 1.71 > 1
    out = tmp_path / "mix.wav"

    mix_and_save(mic, sys, out)

    data, _ = sf.read(out, dtype="float32")
    assert float(np.max(data)) <= 1.0
    assert float(np.min(data)) >= -1.0
