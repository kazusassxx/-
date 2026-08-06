"""SenseVoice ASR 集成：初始化 + 转写 + 输出清洗（B-7）+ 静音跳过（B-4）。"""
from __future__ import annotations

import re

import numpy as np

_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|]*\|>")
_XML_TAG_RE = re.compile(r"<[^>]+>")


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
