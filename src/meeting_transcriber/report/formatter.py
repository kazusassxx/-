"""报告格式化单一真相源 format_report()（E-7）。

GUI 预览 / 首次生成 / 改名重写三处均调用此函数，保证输出逐行一致。
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from meeting_transcriber.pipeline.segment import Segment


def _fmt_ts(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def format_report(
    segments: Iterable[Segment],
    user_name: str,
    generated_at: date,
) -> str:
    """格式化 Markdown 报告：

    ``# 会议转写报告`` / ``生成日期: YYYY-MM-DD`` / ``[MM:SS] 角色名 文本``
    """
    lines = ["# 会议转写报告", f"生成日期: {generated_at:%Y-%m-%d}", ""]
    for seg in segments:
        if seg.speaker_ref == "me":
            name = f"我 ({user_name})"
        else:
            name = seg.speaker_name
        line = f"[{_fmt_ts(seg.start)}] {name}"
        if seg.text and not seg.skipped:
            line += f" {seg.text}"
        lines.append(line)
    return "\n".join(lines) + "\n"
