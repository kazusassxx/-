"""阶段 2.4：模型定位优先级契约。

WHY：§4.4 打包版内置模型优先（exe 同级 ./models/），缺失时回退
~/.meeting-transcriber/models/ 缓存——若优先级颠倒，打包版会绕过
内置模型去读用户缓存，导致分发不可移植。
"""
import sys

import pytest

from meeting_transcriber.models.manager import ModelManager

SENSE_DIR = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"


@pytest.fixture
def frozen_exe(monkeypatch, tmp_path):
    """模拟 PyInstaller 打包环境：exe 位于 tmp_path/bundle/。"""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "meeting-transcriber.exe"))
    return bundle


def test_bundle_models_take_priority(frozen_exe, tmp_path):
    """exe 同级 models/ 存在时优先于 home 缓存。"""
    (frozen_exe / "models" / SENSE_DIR).mkdir(parents=True)
    mgr = ModelManager(home=tmp_path / "home" / "models")

    resolved = mgr.resolve_path("asr")

    assert resolved == frozen_exe / "models" / SENSE_DIR


def test_missing_bundle_falls_back_to_home_cache(frozen_exe, tmp_path):
    """exe 同级缺失时回退 home 缓存（打包漏模型也可用缓存兜底）。"""
    home = tmp_path / "home" / "models"
    (home / SENSE_DIR).mkdir(parents=True)
    mgr = ModelManager(home=home)

    resolved = mgr.resolve_path("asr")

    assert resolved == home / SENSE_DIR


def test_dev_mode_resolves_home_cache(tmp_path, monkeypatch):
    """开发态（非 frozen）不查 exe 同级，直接使用 home 缓存路径。"""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    home = tmp_path / "home" / "models"
    mgr = ModelManager(home=home)

    resolved = mgr.resolve_path("embedding")

    assert resolved == home / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
