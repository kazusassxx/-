"""声纹提取（3D-Speaker eres2net，512 维）。

模型实例经 set_model() 注入（pipeline 从 ModelManager 获取）；
未注入时懒加载默认 ModelManager 的 embedding 组件。
"""
from __future__ import annotations

import numpy as np

EMBEDDING_DIM = 512

_model = None


def set_model(model: object) -> None:
    """注入声纹提取模型（供 pipeline / 测试使用）。"""
    global _model
    _model = model


def _get_model() -> object:
    global _model
    if _model is None:
        from meeting_transcriber.models.manager import ModelManager

        _model = ModelManager().get("embedding")
    return _model


def extract_embedding(samples: np.ndarray, sr: int = 16000) -> np.ndarray:
    """提取 512 维声纹向量；维度不齐显式报错（C-2 向量契约）。

    sherpa-onnx 1.13.4 的 SpeakerEmbeddingExtractor.compute() 接收
    OnlineStream：先 create_stream() 喂波形，再 compute() 取 512 维向量。
    """
    model = _get_model()
    samples = np.asarray(samples, dtype=np.float32)
    if hasattr(model, "compute") and hasattr(model, "create_stream"):
        stream = model.create_stream()
        stream.accept_waveform(int(sr), samples.tolist())
        result = model.compute(stream)
    else:  # 兼容旧 API compute(samples, sr)
        result = model.compute(samples, int(sr))
    if hasattr(result, "data"):
        vec = np.asarray(result.data, dtype=np.float32)
    else:
        vec = np.asarray(result, dtype=np.float32)
    vec = vec.reshape(-1)
    if vec.size != EMBEDDING_DIM:
        raise ValueError(
            f"声纹向量维度 {vec.size} != {EMBEDDING_DIM}，拒绝入库（防破坏声纹库）"
        )
    return vec
