"""原子写：.tmp + flush + fsync + os.replace + 失败清理（P4）。

适用：config.json / speakers.json / transcript_*.md。
"""
from __future__ import annotations

from pathlib import Path


def write_atomic(path: Path, data: bytes) -> None:
    """原子写入 bytes：同目录 .tmp → fsync → os.replace；失败清理 .tmp。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            _fsync(f)
        os_replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    write_atomic(path, text.encode(encoding))


def _fsync(f) -> None:  # noqa: ANN001
    import os

    try:
        os.fsync(f.fileno())
    except OSError:
        pass  # 个别文件系统不支持 fsync 时降级


def os_replace(src: Path, dst: Path) -> None:
    import os

    os.replace(src, dst)
