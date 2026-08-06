"""阶段 5.5：声纹库损坏容错 + 持久化 roundtrip。

WHY：C-8 可用性优先——声纹库损坏绝不能阻断应用启动；必须备份损坏
文件（带时间戳 .bak）并以空库继续，否则用户连应用都打不开。
"""
import json

import numpy as np

from meeting_transcriber.storage.speakers import SpeakerDB


def test_corrupt_json_backed_up_and_empty_db_continues(tmp_path):
    p = tmp_path / "speakers.json"
    p.write_text("{broken json", encoding="utf-8")

    db = SpeakerDB.load(p)

    backups = list(tmp_path.glob("speakers.json.corrupt-*.bak"))
    assert len(backups) == 1  # 损坏原文件已备份，可人工恢复
    assert db.match(np.zeros(512, dtype=np.float32)) is None  # 空库继续


def test_version_mismatch_backed_up(tmp_path):
    """未来版本（version != 1）同样备份并以空库继续（C-7 仅校验，不迁移）。"""
    p = tmp_path / "speakers.json"
    p.write_text('{"version": 2, "speakers": []}', encoding="utf-8")

    SpeakerDB.load(p)

    assert len(list(tmp_path.glob("speakers.json.corrupt-*.bak"))) == 1


def test_register_save_reload_roundtrip(tmp_path):
    p = tmp_path / "speakers.json"
    db = SpeakerDB(p)
    rng = np.random.default_rng(1)
    vec = rng.standard_normal(512).astype(np.float32)

    db.register("张三", vec)
    db.save()

    db2 = SpeakerDB.load(p)
    assert db2.match(vec) == "张三"  # 重启后声纹仍可识别

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert len(raw["speakers"][0]["embedding"]) == 512


def test_delete_removes_speaker_and_match_none(tmp_path):
    p = tmp_path / "speakers.json"
    db = SpeakerDB(p)
    vec = np.ones(512, dtype=np.float32)
    sid = db.register("张三", vec)

    db.delete(sid)

    assert db.match(vec) is None


def test_created_at_uses_local_timezone_offset(tmp_path):
    """Info 5：created_at 与 design 示例一致为本地时区（带偏移），而非 UTC。

    WHY：design 示例 "2026-08-05T10:00:00+08:00" 是本地时间；若写成 UTC
    （Z 后缀），用户看到的注册时间会比本地晚 8 小时，语义不一致。
    """
    from datetime import datetime

    p = tmp_path / "speakers.json"
    db = SpeakerDB(p)
    db.register("张三", np.ones(512, dtype=np.float32))
    db.save()

    raw = json.loads(p.read_text(encoding="utf-8"))
    ts = raw["speakers"][0]["created_at"]
    dt = datetime.fromisoformat(ts)
    assert dt.utcoffset() is not None  # 必须带时区偏移
    # 偏移应与机器本地时区一致（当前实现为 UTC 会在此失败）
    assert dt.utcoffset() == datetime.now().astimezone().utcoffset()
