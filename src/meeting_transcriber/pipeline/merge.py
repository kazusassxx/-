"""双轨时间轴排序合并（E-1）。"""
from __future__ import annotations

from meeting_transcriber.pipeline.segment import Segment


def merge_tracks(
    mic_segs: list[Segment], sys_segs: list[Segment]
) -> list[Segment]:
    """按时间戳排序合并双轨段；同起点时麦克风轨在前（稳定排序）。"""
    merged = list(mic_segs) + list(sys_segs)
    merged.sort(key=lambda s: s.start)
    return merged
