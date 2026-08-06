"""声纹库 SpeakerDB（version:1 schema，原子写 + 损坏容错）。

- match() 余弦相似度阈值 0.65（C-4）
- register/delete 修改内存；save() 原子持久化（P4）
- load() 损坏时备份 ``speakers.json.corrupt-<UTC时间戳>.bak`` 并以空库继续（C-8）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from meeting_transcriber.report.atomicio import write_atomic

SCHEMA_VERSION = 1
MATCH_THRESHOLD = 0.65


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SpeakerDB:
    def __init__(self, path: Path, speakers: list[dict] | None = None) -> None:
        self.path = Path(path)
        self._speakers: list[dict] = list(speakers) if speakers else []

    # ---- 加载 / 保存 ----
    @classmethod
    def load(cls, path: Path) -> "SpeakerDB":
        import json

        p = Path(path)
        if not p.exists():
            return cls(p)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if raw.get("version") != SCHEMA_VERSION or not isinstance(
                raw.get("speakers"), list
            ):
                raise ValueError(f"不支持的 schema 版本: {raw.get('version')}")
            return cls(p, raw["speakers"])
        except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError):
            _backup_corrupt(p)
            return cls(p)

    def save(self) -> None:
        import json

        payload = {
            "version": SCHEMA_VERSION,
            "speakers": self._speakers,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        write_atomic(self.path, data)

    # ---- 增删 ----
    def register(self, name: str, embedding: np.ndarray) -> str:
        sid = uuid.uuid4().hex
        self._speakers.append(
            {
                "id": sid,
                "name": name,
                "embedding": np.asarray(embedding, dtype=np.float32).tolist(),
                # Info 5：本地时区带偏移（与 design 示例 "2026-08-05T10:00:00+08:00" 一致）
                "created_at": datetime.now().astimezone().isoformat(),
            }
        )
        return sid

    def delete(self, speaker_id: str) -> None:
        self._speakers = [s for s in self._speakers if s["id"] != speaker_id]

    def speakers(self) -> list[dict]:
        """只读访问声纹列表（GUI 展示/设置面板用，不可写）。"""
        return list(self._speakers)

    # ---- 匹配 ----
    def match(self, embedding: np.ndarray, threshold: float = MATCH_THRESHOLD) -> str | None:
        """余弦匹配：≥threshold 返回注册姓名，否则 None（C-4 误报边界）。"""
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        best: str | None = None
        best_sim = threshold
        for sp in self._speakers:
            ref = np.asarray(sp["embedding"], dtype=np.float32).reshape(-1)
            sim = _cosine(vec, ref)
            if sim >= best_sim:
                best, best_sim = sp["name"], sim
        return best


def _backup_corrupt(path: Path) -> None:
    """损坏文件改名备份（带 UTC 时间戳），随后以空库继续。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = path.with_name(f"{path.name}.corrupt-{ts}.bak")
    try:
        path.replace(bak)
    except OSError:
        pass
