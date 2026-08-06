"""重采样 + 多声道折叠：统一输出 16kHz 单声道 float32。

下游 VAD / ASR / 声纹提取均以 16k mono f32 为输入契约。
"""
from __future__ import annotations

import numpy as np

TARGET_RATE = 16000


def _fold_to_mono(samples: np.ndarray, channels: int) -> np.ndarray:
    """多声道平均折叠为单声道。"""
    if channels <= 1:
        return samples.astype(np.float32)
    return np.mean(samples, axis=1, dtype=np.float32)


def _resample_linear(x: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """线性插值重采样（免外部依赖）。"""
    if src_rate == dst_rate:
        return x.copy()
    n_out = int(round(len(x) * dst_rate / src_rate))
    src_idx = np.arange(len(x), dtype=np.float64)
    t = np.arange(n_out, dtype=np.float64) * (len(x) - 1) / max(n_out - 1, 1)
    return np.interp(t, src_idx, x.astype(np.float64)).astype(np.float32)


def to_16k_mono_f32(samples: np.ndarray, rate: int, channels: int) -> np.ndarray:
    """任意采样率/声道数的输入 -> 16kHz 单声道 float32。"""
    arr = np.asarray(samples)
    if arr.ndim == 2:
        mono = _fold_to_mono(arr, channels)
    else:
        mono = arr.astype(np.float32)
    return _resample_linear(mono, int(rate), TARGET_RATE)
