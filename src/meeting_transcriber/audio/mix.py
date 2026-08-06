"""双轨混音落盘：16kHz / 16bit / mono WAV。

系统音轨以 ``sys_gain``（默认 0.9）衰减，避免系统提示音盖过人声（A-7）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

DEFAULT_SYS_GAIN = 0.9


def _align(mic: np.ndarray, sys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """按最长轨对齐，短轨补零。"""
    n = max(len(mic), len(sys))
    if len(mic) < n:
        mic = np.concatenate([mic, np.zeros(n - len(mic), dtype=mic.dtype)])
    if len(sys) < n:
        sys = np.concatenate([sys, np.zeros(n - len(sys), dtype=sys.dtype)])
    return mic, sys


def mix_and_save(
    mic: np.ndarray,
    sys: np.ndarray,
    out_path: Path,
    sys_gain: float = DEFAULT_SYS_GAIN,
) -> None:
    """混音并写 16k/16bit/mono WAV（PCM_16）。"""
    mic = np.asarray(mic, dtype=np.float32)
    sys = np.asarray(sys, dtype=np.float32)
    mic, sys = _align(mic, sys)
    mixed = np.clip(mic + sys * sys_gain, -1.0, 1.0)
    sf.write(str(out_path), mixed, 16000, subtype="PCM_16")
