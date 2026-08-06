"""阶段 8.9/8.2：GUI 入口纯逻辑（语言检测 / 翻译表 / 姓名拦截判定）。

WHY：G-8 系统语言不匹配时默认中文，避免界面语言错乱；G-2 姓名缺失时
首次启动必须拦截，空白姓名不视为已配置；翻译表缺失条目回退原文，
防止界面出现空串或乱码。
"""
import pytest

from meeting_transcriber.gui.app import DictTranslator, detect_language
from meeting_transcriber.gui.windows.name_gate import needs_name_gate


# ---- 8.9 语言检测 ----
@pytest.mark.parametrize(
    "sys_lang,expected",
    [
        ("zh_CN.UTF-8", "zh"),
        ("zh_TW", "zh"),
        ("en_US", "en"),
        ("en_GB.UTF-8", "en"),
        ("ja_JP", "ja"),
        ("fr_FR", "zh"),  # 不匹配 → 默认中文
        ("", "zh"),
        (None, "zh"),
    ],
)
def test_detect_language_maps_system_locale(sys_lang, expected):
    assert detect_language(sys_lang) == expected


# ---- 8.9 运行时翻译表（不依赖 .qm 文件）----
def test_translator_returns_known_entry():
    tr = DictTranslator({"开始录音": "Start Recording"})
    assert tr.translate(None, "开始录音") == "Start Recording"


def test_translator_falls_back_to_source_when_missing():
    """缺失条目回退原文——不认识的字符串绝不返回空串。"""
    tr = DictTranslator({"开始录音": "Start Recording"})
    assert tr.translate(None, "停止录音") == "停止录音"


def test_zh_translation_table_is_identity():
    """中文为源语言，空表即原文，无需映射。"""
    tr = DictTranslator({})
    assert tr.translate(None, "开始录音") == "开始录音"


# ---- 8.2 首次启动姓名拦截判定 ----
@pytest.mark.parametrize(
    "cfg,expected",
    [
        ({}, True),  # 无 user_name → 拦截
        ({"user_name": ""}, True),
        ({"user_name": "   "}, True),  # 纯空白不算已配置
        ({"user_name": "张三"}, False),
    ],
)
def test_needs_name_gate_blocks_only_missing_or_blank(cfg, expected):
    assert needs_name_gate(cfg) is expected
