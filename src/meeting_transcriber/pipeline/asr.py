"""ASR 引擎集成：初始化 + 转写 + 输出清洗（B-7）+ 静音跳过（B-4）。

双引擎（config["asr_engine"] 切换）：
- SenseVoiceASR：多语言（zh/en/ja/ko/yue），无热词（CTC 系）
- ZipformerASR：中英双语 transducer（sherpa-onnx streaming-zipformer-bilingual-zh-en），
  支持热词 boosting（decoding_method=modified_beam_search）
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|]*\|>")
_XML_TAG_RE = re.compile(r"<[^>]+>")

# CJK 统一表意文字区段（用于 zipformer BPE 输出的中文空格合并）
_CJK_RE = re.compile(
    r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]"
)


def is_silent(samples: np.ndarray, threshold: float = 0.01) -> bool:
    """RMS 峰值过低判定静音段（不送 ASR）。"""
    arr = np.asarray(samples, dtype=np.float32)
    if arr.size == 0:
        return True
    return float(np.sqrt(np.mean(np.square(arr)))) < threshold


class SenseVoiceASR:
    def __init__(
        self,
        model: str,
        tokens: str,
        num_threads: int = 2,
        lang: str = "auto",
    ) -> None:
        import sherpa_onnx

        # sherpa-onnx：language="" 表示自动检测；显式 lang 传具体语言代码
        language = "" if lang in ("", "auto") else lang
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=tokens,
            num_threads=num_threads,
            language=language,
        )

    def transcribe(self, samples: np.ndarray) -> str:
        """返回清洗后纯文本；静音段跳过直接返回空串（B-4）。"""
        arr = np.asarray(samples, dtype=np.float32)
        if is_silent(arr):
            return ""
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, arr.tolist())
        self._recognizer.decode_stream(stream)
        return self.clean_output(stream.result.text)

    @staticmethod
    def clean_output(raw: str) -> str:
        """剥离 <|zh|> 等 special token 与 XML 标签。"""
        text = _SPECIAL_TOKEN_RE.sub("", raw)
        text = _XML_TAG_RE.sub("", text)
        return text.strip()


class ZipformerASR:
    """中英双语 streaming zipformer transducer 识别（支持热词）。

    sherpa-onnx 的 streaming zipformer **只能经 OnlineRecognizer 在线解码**
    （issue #235 官方确认：OfflineRecognizer 加载会报 encoder chunk 维度错）。
    我们对每个 VAD 语音段模拟流式：accept_waveform + 尾部补静音 + input_finished
    + is_ready 循环 decode（官方 online-decode-files.py 流程）。

    hotwords_file：每行一个词的 UTF-8 文本；非空时自动改用
    modified_beam_search 解码（sherpa-onnx 热词仅在该解码方式下生效），
    否则用更快的 greedy_search。bpe_vocab：bilingual 模型为 BPE 建模，
    需传 bpe.vocab 并置 modeling_unit="bpe"，否则 token 映射错乱。
    """

    # streaming 模型尾部需补静音以 flush 完整结果（官方 0.66s）
    _TAIL_SECONDS = 0.66

    def __init__(
        self,
        encoder: str,
        decoder: str,
        joiner: str,
        tokens: str,
        num_threads: int = 2,
        hotwords_file: str = "",
        hotwords_score: float = 1.5,
        bpe_vocab: str = "",
    ) -> None:
        import sherpa_onnx

        hotwords_file = hotwords_file or ""
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=tokens,
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            num_threads=num_threads,
            decoding_method=(
                "modified_beam_search" if hotwords_file else "greedy_search"
            ),
            hotwords_file=hotwords_file,
            hotwords_score=hotwords_score,
            modeling_unit="bpe" if bpe_vocab else "cjkchar",
            bpe_vocab=bpe_vocab,
        )

    def transcribe(self, samples: np.ndarray) -> str:
        """模拟流式解码单段音频；静音段跳过（B-4）。"""
        arr = np.asarray(samples, dtype=np.float32)
        if is_silent(arr):
            return ""
        stream = self._recognizer.create_stream()
        stream.accept_waveform(16000, arr.tolist())
        # 尾部补静音 flush 完整假设（streaming 模型必需）
        tail = np.zeros(int(self._TAIL_SECONDS * 16000), dtype=np.float32)
        stream.accept_waveform(16000, tail.tolist())
        stream.input_finished()
        while self._recognizer.is_ready(stream):
            self._recognizer.decode_stream(stream)
        return self.clean_output(self._recognizer.get_result(stream))

    @staticmethod
    def clean_output(raw: str) -> str:
        """合并 zipformer BPE 输出的中文 token 空格，保留英文/数字空格。

        zipformer 是 BPE 模型，输出形如 " 你 好 世 界 API 的 设 计"：
        中文字符按 token 拆分带空格，英文/数字是完整 BPE 子词。
        WHY：直接把空格剥掉会拼坏英文（"API" 需保留），不处理则中文
        变成 "你 好 世 界" 可读性差。规则：CJK 之间不加空格（合并），
        CJK 与 非CJK 之间加空格（"API 的" 不粘连）。
        """
        text = _SPECIAL_TOKEN_RE.sub("", raw)
        text = _XML_TAG_RE.sub("", text)
        tokens = text.split()
        out: list[str] = []
        prev_cjk = False
        for tok in tokens:
            if not tok:
                continue
            is_cjk = _CJK_RE.match(tok) is not None
            if is_cjk:
                # CJK 之间直接拼接；前一 token 是非 CJK（英文/数字）时补空格
                if out and not prev_cjk:
                    out.append(" ")
                out.append(tok)
                prev_cjk = True
            else:
                # 非 CJK 前补空格（与中文或上一个英文 token 分隔）
                if out:
                    out.append(" ")
                out.append(tok)
                prev_cjk = False
        return "".join(out).strip()


def make_recognizer(
    model_dir: str,
    num_threads: int = 2,
    lang: str = "auto",
    hotwords_file: str = "",
) -> object:
    """按模型目录识别引擎类型并构造识别器（manager 复用，热词仅 zipformer 生效）。

    model_dir 指向解压目录，内含 encoder/decoder/joiner（zipformer）或
    model.onnx（sensevoice）。按文件存在性自动分派，避免 config 字段与
    实际模型不匹配。
    """
    d = Path(model_dir)
    if (d / "encoder-epoch-99-avg-1.int8.onnx").exists() or (
        d / "encoder.onnx"
    ).exists() or (d / "encoder-epoch-99-avg-1.onnx").exists():
        return ZipformerASR(
            encoder=str(_first_existing(d, ("encoder-epoch-99-avg-1.int8.onnx", "encoder.onnx", "encoder-epoch-99-avg-1.onnx"))),
            decoder=str(_first_existing(d, ("decoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.onnx", "decoder.onnx"))),
            joiner=str(_first_existing(d, ("joiner-epoch-99-avg-1.int8.onnx", "joiner.onnx", "joiner-epoch-99-avg-1.onnx"))),
            tokens=str(d / "tokens.txt"),
            num_threads=num_threads,
            hotwords_file=hotwords_file,
            bpe_vocab=str(d / "bpe.vocab") if (d / "bpe.vocab").exists() else "",
        )
    return SenseVoiceASR(
        str(d / "model.int8.onnx"),
        str(d / "tokens.txt"),
        num_threads=num_threads,
        lang=lang,
    )


def _first_existing(d: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        p = d / name
        if p.exists():
            return p
    raise FileNotFoundError(f"{d} 中缺少 {names[0]}")
