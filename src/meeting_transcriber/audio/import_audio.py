"""外部音频导入：解码任意支持格式为 16kHz 单声道 f32（F-2）。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from meeting_transcriber.audio.resample import to_16k_mono_f32


def decode_to_16k_mono(path: Path) -> np.ndarray:
    """解码 WAV / MP3 / FLAC 为 16k mono f32（libsndfile 实际支持；M4A/AAC 不支持）。"""
    data, rate = sf.read(str(path), dtype="float32", always_2d=False)
    channels = 2 if data.ndim > 1 else 1
    return to_16k_mono_f32(np.asarray(data), int(rate), channels)
