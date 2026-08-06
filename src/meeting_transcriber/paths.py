"""数据路径解析（平台抽象）。

数据根目录为 ``~/.meeting-transcriber/``，可通过环境变量
``MEETING_TRANSCRIBER_HOME`` 覆盖（测试与多环境场景使用）。
"""
from __future__ import annotations

import os
from pathlib import Path

from meeting_transcriber import __appname__


def data_dir() -> Path:
    """数据根目录：默认 ``~/.meeting-transcriber/``。"""
    override = os.environ.get("MEETING_TRANSCRIBER_HOME")
    if override:
        return Path(override)
    return Path.home() / f".{__appname__}"


def config_path() -> Path:
    """用户配置 config.json 路径。"""
    return data_dir() / "config.json"


def speakers_path() -> Path:
    """声纹数据库 speakers.json 路径。"""
    return data_dir() / "speakers.json"


def models_dir() -> Path:
    """模型缓存目录。"""
    return data_dir() / "models"
