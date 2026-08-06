"""阶段 4.3：ASR 输出清洗契约。

WHY：B-7 防报告噪声——SenseVoice 原始输出夹带语言/情绪/事件 special
token（<|zh|> <|NEUTRAL|> <|Speech|> <|end|>）与 XML 标签，若不剥离，
报告会被标签淹没。
"""
import numpy as np
import pytest

from meeting_transcriber.pipeline.asr import SenseVoiceASR, is_silent


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<|zh|><|NEUTRAL|><|Speech|>今天天气真不错<|end|>", "今天天气真不错"),
        ("<|en|><|Speech|>Hello world<|end|>", "Hello world"),
        ("<|zh|><|HAPPY|>会议结束了<|end|>", "会议结束了"),
        ("<unk>你好</unk>", "你好"),  # 通用 XML 标签
        ("<|zh|><|end|>", ""),  # 纯标签 → 空文本
    ],
)
def test_clean_output_strips_special_tokens(raw, expected):
    assert SenseVoiceASR.clean_output(raw) == expected


def test_clean_output_keeps_punctuation_and_whitespace():
    raw = "<|zh|><|Speech|>  好，下周复盘！  <|end|>"
    assert SenseVoiceASR.clean_output(raw) == "好，下周复盘！"


def test_is_silent_rejects_low_rms():
    """RMS 峰值过低（静音段）不送 ASR（B-4）。"""
    silent = np.zeros(16000, dtype=np.float32)
    assert is_silent(silent) is True
    loud = np.full(16000, 0.5, dtype=np.float32)
    assert is_silent(loud) is False
