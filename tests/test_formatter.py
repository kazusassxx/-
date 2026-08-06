"""阶段 6.4：format_report() 单一真相源（E-7）。

WHY：GUI 预览 / 首次生成 / 改名重写三处必须输出逐行一致；麦克风轨
固定显示 "我 (姓名)"，未注册发言人称 "发言人N"。
"""
from datetime import date

from meeting_transcriber.pipeline.segment import Segment
from meeting_transcriber.report.formatter import format_report


def _seg(start, end, track, ref, name, text="", skipped=False):
    return Segment(
        start=start,
        end=end,
        track=track,
        speaker_ref=ref,
        speaker_name=name,
        text=text,
        skipped=skipped,
    )


def test_format_matches_taskbook_example():
    segments = [
        _seg(12, 16, "mic", "me", "我 (张三)", "今天先同步一下进度"),
        _seg(18, 22, "sys", "张三", "张三", "那部分我来负责"),
        _seg(35, 39, "mic", "me", "我 (张三)", "好，下周复盘"),
    ]
    out = format_report(segments, "张三", date(2026, 8, 4))
    expected = (
        "# 会议转写报告\n"
        "生成日期: 2026-08-04\n"
        "\n"
        "[00:12] 我 (张三) 今天先同步一下进度\n"
        "[00:18] 张三 那部分我来负责\n"
        "[00:35] 我 (张三) 好，下周复盘\n"
    )
    assert out == expected


def test_mic_track_always_rendered_as_me_with_user_name():
    """麦克风轨无论 speaker_name 为何值，一律显示 "我 (姓名)"。"""
    segs = [_seg(12, 16, "mic", "me", "任意旧名", "测试内容")]
    out = format_report(segs, "张三", date(2026, 8, 4))
    assert "[00:12] 我 (张三) 测试内容" in out


def test_unregistered_speaker_uses_speaker_name():
    segs = [_seg(18, 22, "sys", "speaker_1", "发言人1", "那部分我来负责")]
    out = format_report(segs, "张三", date(2026, 8, 4))
    assert "[00:18] 发言人1 那部分我来负责" in out


def test_timestamp_zero_padding():
    """时间戳 MM:SS 补零：0→00:00，5→00:05，65→01:05。"""
    segs = [
        _seg(0, 4, "sys", "speaker_1", "发言人1", "a"),
        _seg(5, 9, "sys", "speaker_1", "发言人1", "b"),
        _seg(65, 69, "sys", "speaker_1", "发言人1", "c"),
    ]
    out = format_report(segs, "张三", date(2026, 8, 4))
    lines = [l for l in out.splitlines() if l.startswith("[")]
    assert lines[0].startswith("[00:00]")
    assert lines[1].startswith("[00:05]")
    assert lines[2].startswith("[01:05]")


def test_rename_rewrite_consistency():
    """改名后重写：同一组段仅 user_name 变化，输出随之更新。"""
    segs = [_seg(12, 16, "mic", "me", "", "你好")]
    out_a = format_report(segs, "张三", date(2026, 8, 4))
    out_b = format_report(segs, "李四", date(2026, 8, 4))
    assert "[00:12] 我 (张三) 你好" in out_a
    assert "[00:12] 我 (李四) 你好" in out_b


def test_skipped_segment_renders_without_text():
    segs = [_seg(5, 9, "sys", "speaker_1", "发言人1", text="", skipped=True)]
    out = format_report(segs, "张三", date(2026, 8, 4))
    assert "[00:05] 发言人1" in out
    assert "[00:05] 发言人1 " not in out  # 无尾随空格
