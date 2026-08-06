"""阶段 6.6：转写管线取消语义（E-6）。

WHY：用户在转写中途取消时必须静默回就绪——若管线继续吞完所有段，
取消按钮形同虚设；取消点必须在段边界，且不产出（剩余）报告内容。
"""
import threading

import numpy as np

from meeting_transcriber.pipeline import embedding
from meeting_transcriber.pipeline.pipeline import TranscriptionPipeline

SR = 16000


def _tone(seconds, rms=0.5):
    return np.full(int(seconds * SR), rms, dtype=np.float32)


class _FakeRecognizer:
    """模拟 SenseVoiceASR：pipeline 经 transcribe() 调用（含清洗后文本）。"""

    def __init__(self):
        self.calls = 0

    def transcribe(self, samples):
        self.calls += 1
        return "测试文本"


class _FakeExtractor:
    def compute(self, samples, sr):
        return np.random.default_rng(0).standard_normal(512).astype(np.float32)


class _FakeModels:
    def __init__(self, recognizer):
        self._rec = recognizer
        self._ext = _FakeExtractor()

    def get(self, key):
        if key == "asr":
            return self._rec
        if key == "embedding":
            return self._ext
        raise KeyError(key)


def _build_audio():
    # 5 段 4s 语音，间隔 2s 静音 → 5 个 VAD 段
    parts = []
    for _ in range(5):
        parts.append(_tone(4.0))
        parts.append(_tone(2.0, 0.0))
    return np.concatenate(parts)


def test_cancel_stops_pipeline_at_segment_boundary():
    rec = _FakeRecognizer()
    models = _FakeModels(rec)
    pipe = TranscriptionPipeline(models, {"user_name": "张三", "corrections": []})
    cancelled = threading.Event()

    def progress(p):
        if p >= 0.2:  # 第 2 段处置位取消
            cancelled.set()

    result = pipe.run(_build_audio(), "sys", progress=progress, cancelled=cancelled)

    # 在段边界停止：未消费完所有段（ASR 调用 < 总段数 5）
    assert rec.calls < 5
    assert rec.calls == 2  # 当前段完成后才检查取消
    # 取消后不产出完整报告：返回段数少于完整转写
    assert len(result) < 5


def test_no_cancel_processes_all_segments():
    rec = _FakeRecognizer()
    models = _FakeModels(rec)
    pipe = TranscriptionPipeline(models, {"user_name": "张三", "corrections": []})

    result = pipe.run(_build_audio(), "sys")

    assert rec.calls == 5
    assert len(result) == 5


def test_mic_track_assigns_me_speaker():
    rec = _FakeRecognizer()
    models = _FakeModels(rec)
    pipe = TranscriptionPipeline(models, {"user_name": "张三", "corrections": []})

    result = pipe.run(_build_audio(), "mic")

    for seg in result:
        assert seg.speaker_ref == "me"
        assert seg.speaker_name == "我 (张三)"


def test_unregistered_sys_track_speakers_numbered_consistently():
    """未注册发言人会话内编号稳定：同人相邻段共享 speaker_1。"""
    rec = _FakeRecognizer()
    models = _FakeModels(rec)
    pipe = TranscriptionPipeline(models, {"user_name": "张三", "corrections": []})

    result = pipe.run(_build_audio(), "sys")

    names = [seg.speaker_name for seg in result]
    assert all(name.startswith("发言人") for name in names)
    # 相同向量 → 同一编号（embedding 相同）
    assert len(set(names)) == 1
