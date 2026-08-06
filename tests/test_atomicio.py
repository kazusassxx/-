"""阶段 5.2：原子写契约（P4）。

WHY：报告/配置写盘中断若残留半截文件，下次启动会读到损坏内容；
.tmp + os.replace 保证要么全写成功要么原文件分毫不动。
"""
import pytest

from meeting_transcriber.report import atomicio
from meeting_transcriber.report.atomicio import write_atomic, write_text_atomic


def test_success_leaves_no_tmp_and_content_readable(tmp_path):
    p = tmp_path / "a.json"
    write_atomic(p, b'{"ok": 1}')
    assert p.read_bytes() == b'{"ok": 1}'
    assert list(tmp_path.glob("*.tmp")) == []


def test_failure_keeps_original_and_cleans_tmp(monkeypatch, tmp_path):
    """写入失败时原文件完好且 .tmp 被清理（不残留半截文件）。"""
    p = tmp_path / "a.json"
    p.write_bytes(b"original")
    monkeypatch.setattr(
        atomicio,
        "os_replace",
        lambda s, d: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        write_atomic(p, b"new content")
    assert p.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_failure_without_existing_target_leaves_nothing(monkeypatch, tmp_path):
    p = tmp_path / "new.json"
    monkeypatch.setattr(
        atomicio,
        "os_replace",
        lambda s, d: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        write_atomic(p, b"x")
    assert not p.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_text_atomic_roundtrip(tmp_path):
    p = tmp_path / "r.md"
    write_text_atomic(p, "# 标题\n正文内容")
    assert p.read_text(encoding="utf-8") == "# 标题\n正文内容"
