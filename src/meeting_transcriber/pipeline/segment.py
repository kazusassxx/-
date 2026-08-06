"""转写管线内部数据模型 Segment。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float  # 秒，时间轴起点
    end: float  # 秒
    track: str  # "mic" | "sys" | "import"
    speaker_ref: str  # "me"（麦克风轨）| 声纹库 id | "speaker_N"（未注册聚类）
    speaker_name: str  # 显示名："我 (张三)" / "张三" / "发言人N"
    text: str = ""  # ASR 纯文本（纠错前）；未转写时为 ""
    skipped: bool = False  # 静音跳过标记（B-4）
