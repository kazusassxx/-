"""说话人分割聚类（Pyannote ONNX via sherpa-onnx）。

>15s 的聚类段用 EnergyVAD 二次切分，避免超长段送 ASR 截断。
"""
from __future__ import annotations

import numpy as np

from meeting_transcriber.pipeline.vad import EnergyVAD


class Diarizer:
    def __init__(
        self,
        segmentation_model: object,
        embedding_model: object,
        cluster_threshold: float = 0.5,
        max_len: float = 15.0,
        sr: int = 16000,
    ) -> None:
        import sherpa_onnx

        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=segmentation_model
                ),
                num_threads=2,
            ),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=embedding_model, num_threads=2
            ),
            clustering=sherpa_onnx.FastClusteringConfig(
                threshold=cluster_threshold, num_clusters=-1
            ),
            min_duration_on=0.3,
            min_duration_off=0.5,
        )
        self._sd = sherpa_onnx.OfflineSpeakerDiarization(config)
        self._max_len = max_len
        self._sr = sr

    def segment(self, samples: np.ndarray) -> list[tuple[float, float, str]]:
        """返回 (start, end, label) 列表；label 形如 "speaker_00"。"""
        samples = np.asarray(samples, dtype=np.float32)
        result = self._sd.process(samples)
        raw = result.sort_by_start_time()
        segs = [
            (float(s.start), float(s.end), str(s.speaker)) for s in raw
        ]
        return self._resplit_long(segs, samples)

    def _resplit_long(
        self, segments: list[tuple[float, float, str]], samples: np.ndarray
    ) -> list[tuple[float, float, str]]:
        """>15s 聚类段二次 VAD 切分（复用 EnergyVAD）。"""
        out: list[tuple[float, float, str]] = []
        vad = EnergyVAD(sr=self._sr, max_len=self._max_len)
        for start, end, label in segments:
            if end - start <= self._max_len:
                out.append((start, end, label))
                continue
            seg = samples[int(start * self._sr) : int(end * self._sr)]
            for s, e in vad.segment(seg):
                out.append((start + s, start + e, label))
        return sorted(out, key=lambda t: t[0])
