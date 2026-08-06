"""阶段 1.2：to_16k_mono_f32() 重采样 + 多声道平均契约。

WHY：下游 VAD/ASR 均要求 16kHz 单声道 float32；48kHz 立体声必须正确
折叠为单声道，否则声道数/采样率不齐会静默产出错位转写。
"""
import numpy as np

from meeting_transcriber.audio.resample import to_16k_mono_f32


def test_48k_stereo_folds_to_16k_mono_average():
    rate = 48000
    n = rate  # 1 秒
    left = np.full(n, 0.5, dtype=np.float32)
    right = np.full(n, 0.25, dtype=np.float32)
    stereo = np.stack([left, right], axis=1)

    mono = to_16k_mono_f32(stereo, rate, 2)

    assert mono.dtype == np.float32
    assert mono.ndim == 1  # 单声道
    assert len(mono) == 16000  # 16k 采样率契约
    # 多声道平均：0.5 与 0.25 的均值 0.375，常量信号经重采样应保持
    np.testing.assert_allclose(mono, np.full(16000, 0.375), atol=1e-4)


def test_16k_mono_passthrough_unchanged():
    rng = np.random.default_rng(42)
    mono = rng.standard_normal(16000).astype(np.float32)

    out = to_16k_mono_f32(mono, 16000, 1)

    assert out.shape == (16000,)
    np.testing.assert_allclose(out, mono, atol=1e-6)


def test_mono_input_ndarray_shape_1_is_accepted():
    # 部分解码器返回 shape (N,) 的 16k 单声道，须直接可用
    rng = np.random.default_rng(7)
    mono = rng.standard_normal(8000).astype(np.float32)
    out = to_16k_mono_f32(mono, 16000, 1)
    assert len(out) == 8000
