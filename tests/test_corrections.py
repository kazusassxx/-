"""阶段 6.2：名词纠错契约（E-3）。

WHY：专有名词（人名/产品名）ASR 常识别错误；映射须全文替换；
单条坏配置（缺 "="）绝不能拖垮整个流程。
"""
import pytest

from meeting_transcriber.report.corrections import apply_corrections


def test_multiple_mappings_replace_across_text():
    text = "我们下周在腾讯会议开会，腾讯会议连接发群里"
    out = apply_corrections(text, ["腾讯会议=腾讯视频会议", "下周=下周三"])
    assert out == "我们下周三在腾讯视频会议开会，腾讯视频会议连接发群里"


def test_bad_entries_skipped_without_aborting():
    """缺 "=" / 空错词等非法条目跳过，不中断后续有效映射。"""
    text = "测试abc项目正确完工"
    out = apply_corrections(
        text,
        ["abc", "=坏映射", "正确=修复", ""],
    )
    assert out == "测试abc项目修复完工"  # abc 未被替换（非法跳过），但后续映射仍生效


def test_comma_separated_mappings_in_one_entry():
    text = "苹果和橙子都好吃"
    out = apply_corrections(text, ["苹果=苹果汁, 橙子=橙汁"])
    assert out == "苹果汁和橙汁都好吃"


def test_no_corrections_returns_original():
    assert apply_corrections("原文", []) == "原文"
