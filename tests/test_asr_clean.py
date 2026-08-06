"""阶段 4.3：ASR 输出清洗契约。

WHY：B-7 防报告噪声——SenseVoice 原始输出夹带语言/情绪/事件 special
token（<|zh|> <|NEUTRAL|> <|Speech|> <|end|>）与 XML 标签，若不剥离，
报告会被标签淹没。

ZipformerASR.clean_output：zipformer 是 BPE 模型，中文按 token 拆分
带空格（"你 好 世 界"），英文/数字保留空格；WHY=中文不合并则报告
可读性差，英文不保留则拼坏英文词（"API"→"A PI"）。
"""
import numpy as np
import pytest

from meeting_transcriber.pipeline.asr import (
    SenseVoiceASR,
    ZipformerASR,
    is_silent,
    make_recognizer,
)


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


# ---------------- ZipformerASR（中英双语，BPE 输出清洗）----------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # BPE 中文 token 带空格 → 合并为连续中文
        (" 你 好 世 界", "你好世界"),
        # 中文 + 英文/数字：英文保留空格，中文合并
        (" 我 们 要 讨论 API 的 设计", "我们要讨论 API 的设计"),
        (" 项 目 数 量 是 100 个", "项目数量是 100 个"),
        # 英文 BPE 子词（续段不带空格前缀）
        (" 请 查 看 Transformer 文 档", "请查看 Transformer 文档"),
        # 特殊 token 同样剥离
        ("<|zh|> 今 天 天气 不错<|end|>", "今天天气不错"),
    ],
)
def test_zipformer_clean_output_merges_cjk_keeps_latin(raw, expected):
    """BPE 中文 token 空格合并，英文/数字空格保留。

    WHY：zipformer 输出 " 你 好 世 界 API"——中文不合并则报告
    "你 好 世 界"，英文不保留则 "API" 被拆坏；两者都是用户可见的质量缺陷。
    """
    assert ZipformerASR.clean_output(raw) == expected


def test_make_recognizer_dispatches_zipformer_by_encoder_file(tmp_path, monkeypatch):
    """make_recognizer 按目录内 encoder 文件自动分派 ZipformerASR。

    WHY：manager 不感知引擎细节，仅凭模型目录内容分派；zipformer
    目录含 encoder-*.int8.onnx 即走 transducer 路径（热词生效前提）。
    """
    from meeting_transcriber.pipeline import asr as asr_mod

    d = tmp_path / "zipformer"
    d.mkdir()
    (d / "encoder-epoch-99-avg-1.int8.onnx").write_bytes(b"e")
    (d / "decoder-epoch-99-avg-1.onnx").write_bytes(b"d")
    (d / "joiner-epoch-99-avg-1.int8.onnx").write_bytes(b"j")
    (d / "tokens.txt").write_text("▁\n", encoding="utf-8")

    captured: dict = {}

    def _spy_init(self, encoder, decoder, joiner, tokens, num_threads=2, hotwords_file="", hotwords_score=1.5, bpe_vocab=""):
        captured["engine"] = "zipformer"
        captured["hotwords_file"] = hotwords_file
        captured["encoder"] = encoder

    monkeypatch.setattr(asr_mod.ZipformerASR, "__init__", _spy_init)
    recognizer = make_recognizer(str(d), num_threads=1)
    assert isinstance(recognizer, asr_mod.ZipformerASR)
    assert captured["engine"] == "zipformer"
    assert captured["encoder"] == str(d / "encoder-epoch-99-avg-1.int8.onnx")


def test_make_recognizer_forwards_hotwords_to_zipformer(tmp_path, monkeypatch):
    """热词文件必须传给 ZipformerASR（modified_beam_search 解码前提）。

    WHY：manager 把 home/hotwords.txt 传下来，识别器据此切换解码方式；
    热词不传 = 设置界面输入的热词完全不生效。
    """
    from meeting_transcriber.pipeline import asr as asr_mod

    d = tmp_path / "zipformer"
    d.mkdir()
    (d / "encoder-epoch-99-avg-1.int8.onnx").write_bytes(b"e")
    (d / "decoder-epoch-99-avg-1.onnx").write_bytes(b"d")
    (d / "joiner-epoch-99-avg-1.int8.onnx").write_bytes(b"j")
    (d / "tokens.txt").write_text("▁\n", encoding="utf-8")
    hw = tmp_path / "hotwords.txt"
    hw.write_text("API\nTransformer\n", encoding="utf-8")

    captured: dict = {}

    def _spy_init(self, encoder, decoder, joiner, tokens, num_threads=2, hotwords_file="", hotwords_score=1.5, bpe_vocab=""):
        captured["hotwords_file"] = hotwords_file

    monkeypatch.setattr(asr_mod.ZipformerASR, "__init__", _spy_init)
    make_recognizer(str(d), num_threads=1, hotwords_file=str(hw))
    assert captured["hotwords_file"] == str(hw)


def test_make_recognizer_dispatches_sensevoice_without_encoder(tmp_path, monkeypatch):
    """目录仅有 model.int8.onnx（SenseVoice）→ 分派 SenseVoiceASR。"""
    from meeting_transcriber.pipeline import asr as asr_mod

    d = tmp_path / "sensevoice"
    d.mkdir()
    (d / "model.int8.onnx").write_bytes(b"m")
    (d / "tokens.txt").write_text("▁\n", encoding="utf-8")

    captured: dict = {}

    def _spy_init(self, model, tokens, num_threads=2, lang="auto"):
        captured["engine"] = "sensevoice"
        captured["model"] = model

    monkeypatch.setattr(asr_mod.SenseVoiceASR, "__init__", _spy_init)
    recognizer = make_recognizer(str(d), num_threads=1, lang="zh")
    assert isinstance(recognizer, asr_mod.SenseVoiceASR)
    assert captured["engine"] == "sensevoice"
    assert captured["model"] == str(d / "model.int8.onnx")
