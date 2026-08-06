"""TranscriptionPipeline：编排 VAD/分割 → 声纹匹配 → ASR → 纠错 → Segment。

- 进度回调 progress(float) 与取消令牌 cancelled（段边界检查，E-5/E-6）
- 麦克风轨固定 speaker_ref="me"；系统/导入轨经 Pyannote 分割聚类（缺模型
  时降级 VAD 段级）→ 声纹库匹配或会话内匿名编号（C-4）
"""
from __future__ import annotations

import threading
from typing import Callable

import numpy as np

from meeting_transcriber.pipeline import embedding
from meeting_transcriber.pipeline.asr import is_silent
from meeting_transcriber.pipeline.diarize import Diarizer
from meeting_transcriber.pipeline.segment import Segment
from meeting_transcriber.pipeline.vad import EnergyVAD
from meeting_transcriber.report.corrections import apply_corrections


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class TranscriptionPipeline:
    def __init__(self, models, config: dict, speaker_db=None) -> None:
        self._models = models
        self._config = config
        self._speaker_db = speaker_db  # Critical 2：声纹库显式注入（C-4 生效前提）
        self._anon: list[tuple[str, np.ndarray]] = []  # 会话内未注册聚类
        self.segmentation_note: str | None = None  # 分割模型降级提示（GUI/CLI 可读）

    def run(
        self,
        samples: np.ndarray,
        track: str,
        progress: Callable[[float], None] | None = None,
        cancelled: threading.Event = None,  # type: ignore[assignment]
    ) -> list[Segment]:
        """单轨转写编排；取消后返回已处理部分（调用方检测 cancelled 不产报告）。"""
        if cancelled is None:
            cancelled = threading.Event()
        samples = np.asarray(samples, dtype=np.float32)
        self._anon = []
        self.segmentation_note = None
        embedding.set_model(self._models.get("embedding"))

        corrections = list(self._config.get("corrections") or [])
        user_name = str(self._config.get("user_name") or "")

        # 段来源：mic 轨固定 VAD；sys/import 轨优先 Pyannote 分割聚类（Warning 1）
        if track == "mic":
            segs = [(s, e, None) for s, e in EnergyVAD().segment(samples)]
        else:
            segs = self._diarize_or_vad(samples)

        total = max(len(segs), 1)
        results: list[Segment] = []

        for i, (s, e, label) in enumerate(segs):
            if cancelled.is_set():
                break
            if progress:
                progress(i / total)
            seg_audio = samples[int(s * 16000) : int(e * 16000)]
            skipped = is_silent(seg_audio)
            text = "" if skipped else self._transcribe(seg_audio)
            text = apply_corrections(text, corrections)
            results.append(self._build_segment(s, e, track, seg_audio, text, skipped, user_name, label))

        if progress:
            progress(1.0)
        return results

    # ---- 内部 ----
    def _transcribe(self, seg_audio: np.ndarray) -> str:
        """经 SenseVoiceASR.transcribe 转写并清洗（实例方法，B-7）。"""
        return self._models.get("asr").transcribe(seg_audio)

    def _diarize_or_vad(self, samples: np.ndarray) -> list[tuple[float, float, str | None]]:
        """sys/import 轨段来源：有分割模型走 Pyannote 聚类，否则降级 VAD 段级。

        缺分割模型时优雅降级（不整条转写报错）并通过 segmentation_note 明确提示。
        """
        try:
            seg_model = self._models.get("segmentation")
        except Exception:  # noqa: BLE001 - 模型未下载/未就绪均降级
            seg_model = None
        if seg_model is None:
            self.segmentation_note = (
                "说话人分割模型未下载，已降级为 VAD 分段编号"
                "（可运行 scripts/download_models.py 补齐）"
            )
            return [(s, e, None) for s, e in EnergyVAD().segment(samples)]
        try:
            diarizer = Diarizer(
                str(self._models.resolve_file("segmentation")),
                str(self._models.resolve_file("embedding")),
            )
            return diarizer.segment(samples)
        except Exception:  # noqa: BLE001 - 分割模型加载/推理失败同样降级
            self.segmentation_note = "说话人分割不可用，已降级为 VAD 分段编号"
            return [(s, e, None) for s, e in EnergyVAD().segment(samples)]
    def _build_segment(
        self,
        s: float,
        e: float,
        track: str,
        seg_audio: np.ndarray,
        text: str,
        skipped: bool,
        user_name: str,
        label: str | None = None,
    ) -> Segment:
        if track == "mic":
            return Segment(s, e, track, "me", f"我 ({user_name})", text, skipped)

        vec = embedding.extract_embedding(seg_audio)
        name = self._match_or_anon(vec, label)
        ref = name if not name.startswith("发言人") else f"speaker_{name[3:]}"
        return Segment(s, e, track, ref, name, text, skipped)

    def _match_or_anon(self, vec: np.ndarray, label: str | None = None) -> str:
        """声纹库匹配；未注册时按分割 label 稳定编号或会话内余弦聚类（发言人N）。"""
        db = self._speaker_db or self._config.get("_speaker_db")
        if db is not None:
            hit = db.match(vec)
            if hit is not None:
                return hit
        if label is not None:
            return self._diarized_label_name(label)
        for plabel, ref in self._anon:
            if _cosine(vec, ref) >= 0.65:
                return plabel
        n = len(self._anon) + 1
        plabel = f"发言人{n}"
        self._anon.append((plabel, vec))
        return plabel

    @staticmethod
    def _diarized_label_name(label: str) -> str:
        """分割 label（speaker_00）→ 会话内稳定显示名（发言人1）。"""
        try:
            n = int(label.rsplit("_", 1)[-1]) + 1
        except (ValueError, AttributeError):
            return label or "发言人1"
        return f"发言人{n}"
