"""阶段 3.8：声纹提取维度契约（C-2）。

WHY：3D-Speaker eres2net 输出固定 512 维向量；维度不齐将污染声纹库
持久化（不同维度向量混存导致 cosine 匹配崩溃），因此必须在源头拦截。
"""
import numpy as np
import pytest

from meeting_transcriber.pipeline import embedding


class _FakeExtractor:
    def compute(self, samples, sr):
        return np.random.default_rng(0).standard_normal(512).astype(np.float32)


def test_extract_embedding_is_512_dim_float32(monkeypatch):
    embedding.set_model(_FakeExtractor())
    vec = embedding.extract_embedding(np.zeros(16000, dtype=np.float32))
    assert vec.shape == (512,)
    assert vec.dtype == np.float32


def test_wrong_dimension_is_rejected():
    """模型输出非 512 维必须显式报错，绝不静默入库。"""

    class _BadExtractor(_FakeExtractor):
        def compute(self, samples, sr):
            return np.zeros(128, dtype=np.float32)

    embedding.set_model(_BadExtractor())
    with pytest.raises(ValueError):
        embedding.extract_embedding(np.zeros(16000, dtype=np.float32))
