"""Critical 2 + Warning 1：声纹库注入转写管线 + Diarizer 接入。

WHY（行为意图）：
- Critical 2：pipeline._match_or_anon 读 config["_speaker_db"] 但全仓库
  无人写入 → db 恒为 None → C-4"下次会议自动识别已知人声"完全失效。
  注册已知声纹后，下次转写必须自动标注姓名。
- Warning 1：sys/import 轨应接入 Pyannote 分割聚类；缺分割模型时优雅
  降级为 VAD 段级编号且明确提示，不能因缺分割模型整条转写报错。
"""
import numpy as np
import pytest

from meeting_transcriber.pipeline.pipeline import TranscriptionPipeline
from meeting_transcriber.storage.speakers import SpeakerDB

SR = 16000


def _tone(seconds, rms=0.5):
    return np.full(int(seconds * SR), rms, dtype=np.float32)


def _build_audio(segments=3):
    parts = []
    for _ in range(segments):
        parts.append(_tone(4.0))
        parts.append(_tone(2.0, 0.0))
    return np.concatenate(parts)


class _FakeRecognizer:
    """模拟 SenseVoiceASR：transcribe 计数 + 固定文本。"""

    def __init__(self):
        self.calls = 0

    def transcribe(self, samples):
        self.calls += 1
        return "测试文本"


class _FakeExtractor:
    """确定性声纹向量：同 RMS 音频 → 同一向量（声纹匹配可复现）。"""

    def compute(self, samples, sr):
        arr = np.asarray(samples, dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(arr)))) if arr.size else 0.0
        if rms <= 0.0:
            return np.zeros(512, dtype=np.float32)
        v = np.random.default_rng(int(round(rms * 10000))).standard_normal(512)
        return (v / float(np.linalg.norm(v))).astype(np.float32)


class _FakeModels:
    def __init__(self, recognizer, has_segmentation=False):
        self._rec = recognizer
        self._ext = _FakeExtractor()
        self._has_seg = has_segmentation

    def get(self, key):
        if key == "asr":
            return self._rec
        if key == "embedding":
            return self._ext
        if key == "segmentation" and self._has_seg:
            return object()
        raise KeyError(key)

    def resolve_file(self, key):
        """模拟 ModelManager.resolve_file()（1.13.4 下 Diarizer 需模型文件路径）。"""
        if key == "segmentation" and self._has_seg:
            return "/fake/segmentation/model.onnx"
        return "/fake/embedding/model.onnx"


class _FakeDiarizer:
    """固定两段说话人区间：覆盖 0–8s，同 label。"""

    def __init__(self, seg_model, emb_model):
        self._seg = seg_model
        self._emb = emb_model

    def segment(self, samples):
        return [(0.0, 4.0, "speaker_00"), (4.0, 8.0, "speaker_00")]


# ---------------- Critical 2：声纹库注入 ----------------
def test_registered_voiceprint_auto_labels_next_transcription(tmp_path):
    """C-4：注册已知声纹 → 下次转写自动标注姓名（而非"发言人N"）。"""
    vec = _FakeExtractor().compute(_tone(4.0), SR)  # 与转写段同款音频 → 同向量
    db = SpeakerDB(tmp_path / "speakers.json")
    db.register("张三", vec)
    models = _FakeModels(_FakeRecognizer())
    pipe = TranscriptionPipeline(models, {"user_name": "我", "corrections": []}, speaker_db=db)

    result = pipe.run(_build_audio(), "sys")

    assert result
    assert all(seg.speaker_name == "张三" for seg in result)
    assert all(not seg.speaker_name.startswith("发言人") for seg in result)


def test_unregistered_voiceprint_stays_anonymous(tmp_path):
    """未注册向量 → 仍按会话内"发言人N"编号（不误报姓名）。"""
    rng = np.random.default_rng(7)
    vec = (rng.standard_normal(512) / np.linalg.norm(rng.standard_normal(512))).astype(np.float32)
    db = SpeakerDB(tmp_path / "speakers.json")
    db.register("张三", vec)
    models = _FakeModels(_FakeRecognizer())
    pipe = TranscriptionPipeline(models, {"user_name": "我", "corrections": []}, speaker_db=db)

    result = pipe.run(_build_audio(), "sys")

    assert result
    assert all(seg.speaker_name.startswith("发言人") for seg in result)


# ---------------- Warning 1：Diarizer 接入与优雅降级 ----------------
def test_sys_track_uses_diarizer_segments_when_available(monkeypatch):
    """有分割模型时 sys 轨按说话人区间转写（2 区间 → 2 次 ASR，而非 VAD 段数）。"""
    monkeypatch.setattr("meeting_transcriber.pipeline.pipeline.Diarizer", _FakeDiarizer)
    rec = _FakeRecognizer()
    models = _FakeModels(rec, has_segmentation=True)
    pipe = TranscriptionPipeline(models, {"user_name": "我", "corrections": []})

    result = pipe.run(_build_audio(), "sys")

    assert rec.calls == 2
    assert [seg.speaker_name for seg in result] == ["发言人1", "发言人1"]  # 同 label 稳定编号


def test_missing_segmentation_model_falls_back_to_vad(monkeypatch):
    """缺分割模型 → 降级 VAD 段级编号，转写不报错且明确提示。"""
    rec = _FakeRecognizer()
    models = _FakeModels(rec)
    pipe = TranscriptionPipeline(models, {"user_name": "我", "corrections": []})

    result = pipe.run(_build_audio(), "sys")

    assert rec.calls == 3  # 仍按 VAD 段数完成转写
    assert len(result) == 3
    assert pipe.segmentation_note  # 明确提示已降级


def test_diarizer_construction_failure_falls_back_to_vad(monkeypatch):
    """分割模型损坏/加载失败 → 同样降级 VAD，不整条转写报错。"""

    class _BrokenDiarizer:
        def __init__(self, seg, emb):
            raise RuntimeError("分割模型损坏")

    monkeypatch.setattr("meeting_transcriber.pipeline.pipeline.Diarizer", _BrokenDiarizer)
    rec = _FakeRecognizer()
    models = _FakeModels(rec, has_segmentation=True)
    pipe = TranscriptionPipeline(models, {"user_name": "我", "corrections": []})

    result = pipe.run(_build_audio(), "sys")

    assert len(result) == 3
    assert pipe.segmentation_note


def test_mic_track_always_uses_vad_even_with_segmentation(monkeypatch):
    """mic 轨固定走 VAD（design：mic 轨 speaker_ref="me"，无需分割）。"""
    monkeypatch.setattr("meeting_transcriber.pipeline.pipeline.Diarizer", _FakeDiarizer)
    rec = _FakeRecognizer()
    models = _FakeModels(rec, has_segmentation=True)
    pipe = TranscriptionPipeline(models, {"user_name": "我", "corrections": []})

    result = pipe.run(_build_audio(), "mic")

    assert rec.calls == 3  # mic 轨仍按 VAD 段数
    assert all(seg.speaker_ref == "me" for seg in result)
