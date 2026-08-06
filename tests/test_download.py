"""Warning 5/6：tar 解包路径穿越防护 + 单文件下载幂等修复。

WHY（行为意图）：
- extractall 无 filter 时，恶意 tar 条目（如 ../evil）可越界写盘；
  filter="data" 必须拒绝越界路径。
- 直接写目标文件的下载中断会残留半截文件，下次被 _is_present 误判为
  "已存在"而跳过（幂等缺陷）；.part + rename 保证中断不留残件，
  且与 Content-Length 比对能发现截断。
"""
import io
import tarfile

import pytest

from meeting_transcriber.models import download


class _FakeResponse:
    def __init__(self, data: bytes, content_length: int | None):
        self._buf = io.BytesIO(data)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_extractall_rejects_path_traversal(tmp_path):
    """tar 条目含 ../ 越界路径 → filter="data" 拒绝且不产生越界文件。"""
    archive = tmp_path / "evil.tar.bz2"
    with tarfile.open(archive, "w:bz2") as tf:
        info = tarfile.TarInfo(name="../evil.txt")
        info.size = 6
        tf.addfile(info, io.BytesIO(b"pwned!"))

    target = tmp_path / "out"
    target.mkdir()
    with pytest.raises(tarfile.OutsideDestinationError):
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(target, filter="data")

    assert not (tmp_path / "evil.txt").exists()  # 越界文件未写出


def test_interrupted_download_leaves_no_partial_file(monkeypatch, tmp_path):
    """下载中断（长度不符）→ 目标与 .part 均不残留（幂等不被半截文件欺骗）。"""
    monkeypatch.setattr(
        download,
        "_open_url",
        lambda url, proxy=None: _FakeResponse(b"x" * 256, content_length=1000),
    )
    dest = tmp_path / "model.onnx"
    with pytest.raises(download.DownloadError):
        download.download_file("https://example.com/model.onnx", dest)
    assert not dest.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_successful_download_renames_part_to_dest(monkeypatch, tmp_path):
    """下载成功 → .part 原子 rename 为目标文件，无残留。"""
    monkeypatch.setattr(
        download,
        "_open_url",
        lambda url, proxy=None: _FakeResponse(b"abcdef", content_length=6),
    )
    dest = tmp_path / "model.onnx"
    download.download_file("https://example.com/model.onnx", dest)
    assert dest.read_bytes() == b"abcdef"
    assert list(tmp_path.glob("*.part")) == []


def test_download_without_content_length_skips_strict_check(monkeypatch, tmp_path):
    """无 Content-Length → 跳过长度严格校验，仅要求完整读到非空内容。"""
    monkeypatch.setattr(
        download,
        "_open_url",
        lambda url, proxy=None: _FakeResponse(b"data", content_length=None),
    )
    dest = tmp_path / "m.onnx"
    download.download_file("https://example.com/m.onnx", dest)
    assert dest.read_bytes() == b"data"
