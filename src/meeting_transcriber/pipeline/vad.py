"""能量 VAD：按块 RMS 静音断句，段长约束 1.5–15s。

最短 1.5s：真实会议短句（1–3s）常见，4s 下限会丢弃大量真实语音
（D-4 原 4s 下限放宽，SenseVoice 转写 1.5s 短句无问题）。
"""
from __future__ import annotations

import numpy as np


def merge_adjacent(
    segments: list[tuple[float, float]],
    gap: float = 1.5,
    max_len: float = 15.0,
) -> list[tuple[float, float]]:
    """合并间隔 ≤gap 且合并后长度 ≤max_len 的相邻段。"""
    if not segments:
        return []
    merged: list[list[float]] = [list(segments[0])]
    for s, e in segments[1:]:
        ps, pe = merged[-1]
        if s - pe <= gap and (e - ps) <= max_len:
            merged[-1][1] = max(pe, e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


class EnergyVAD:
    def __init__(
        self,
        sr: int = 16000,
        min_len: float = 1.5,
        max_len: float = 15.0,
        merge_gap: float = 1.5,
        block: float = 0.1,
        rms_threshold: float = 0.01,
    ) -> None:
        self._sr = sr
        self._min_len = min_len
        self._max_len = max_len
        self._merge_gap = merge_gap
        self._block = block
        self._rms_threshold = rms_threshold

    def segment(self, samples: np.ndarray) -> list[tuple[float, float]]:
        """按块 RMS 断句，返回 (start, end) 秒列表（健康区间 4–15s）。"""
        samples = np.asarray(samples, dtype=np.float32)
        block_n = max(1, int(self._sr * self._block))
        n_blocks = len(samples) // block_n
        if n_blocks == 0:
            return []

        speech = np.zeros(n_blocks, dtype=bool)
        for i in range(n_blocks):
            seg = samples[i * block_n : (i + 1) * block_n]
            speech[i] = bool(np.sqrt(np.mean(np.square(seg))) > self._rms_threshold)

        # 连续语音块区间
        runs: list[tuple[int, int]] = []
        start = None
        for i, s in enumerate(speech):
            if s and start is None:
                start = i
            elif not s and start is not None:
                runs.append((start, i))
                start = None
        if start is not None:
            runs.append((start, n_blocks))

        segs = [(s * self._block, e * self._block) for s, e in runs]
        segs = merge_adjacent(segs, gap=self._merge_gap, max_len=self._max_len)

        # 超长强制切断
        result: list[tuple[float, float]] = []
        for s, e in segs:
            if e - s > self._max_len:
                cur = s
                while cur + self._max_len < e:
                    result.append((cur, cur + self._max_len))
                    cur += self._max_len
                result.append((cur, e))
            else:
                result.append((s, e))

        # 超短丢弃
        return [(s, e) for s, e in result if e - s >= self._min_len - 1e-9]
