"""storage/config.py：config.json 读写（version:1 兼容，原子写，损坏容错）。

解析失败/缺失 → 按默认值合并，绝不崩溃（G-9 配置持久化）。
"""
from __future__ import annotations

import json
from pathlib import Path

from meeting_transcriber import paths
from meeting_transcriber.report.atomicio import write_atomic

DEFAULT_CONFIG: dict = {
    "user_name": "",
    "language": "zh",
    "asr_lang": "zh",
    "asr_engine": "auto",  # auto | sensevoice | zipformer（auto=按模型目录自动识别）
    "hotwords": "",  # 逗号分隔热词，仅 zipformer 引擎生效
    "output_dir": str(Path.home() / "Documents" / "MeetingTranscripts"),
    "num_threads": 4,
    "mic_device": "",
    "mic_gain": 10.0,
    "sys_audio_enabled": True,
    "sys_audio_device": "",
    "sys_mix_gain": 0.9,
    "corrections": [],
    "version": 1,
}


def load_config() -> dict:
    """读取配置；缺失/损坏 → 默认值合并（user_name 缺失触发首次姓名拦截）。"""
    path = paths.config_path()
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config 根节点不是对象")
    except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError):
        return dict(DEFAULT_CONFIG)
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in raw.items() if k in DEFAULT_CONFIG})
    return cfg


def save_config(cfg: dict) -> None:
    """合并默认值后原子写入 config.json。"""
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    data = json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(paths.config_path(), data)
