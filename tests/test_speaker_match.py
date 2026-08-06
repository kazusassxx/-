"""阶段 3.9：SpeakerDB.match() 余弦相似度阈值 0.65（C-4）。

WHY：自动标注与误报的边界——同人向量必须 ≥0.65 命中姓名，异人必须
<0.65 返回 None；若阈值失效，声纹库要么谁都认不出要么张冠李戴。
"""
import numpy as np
import pytest

from meeting_transcriber.storage.speakers import SpeakerDB


def _unit_vec(seed):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512)
    return v / np.linalg.norm(v)


def test_same_speaker_matches_above_threshold(tmp_path):
    db = SpeakerDB(tmp_path / "speakers.json")
    db.register("张三", _unit_vec(1))

    query = 0.95 * _unit_vec(1) + 0.05 * _unit_vec(2)
    assert db.match(query) == "张三"


def test_different_speaker_below_threshold_returns_none(tmp_path):
    db = SpeakerDB(tmp_path / "speakers.json")
    db.register("张三", _unit_vec(1))

    assert db.match(-_unit_vec(1)) is None  # 余弦 -1


def test_empty_db_returns_none(tmp_path):
    db = SpeakerDB(tmp_path / "speakers.json")
    assert db.match(_unit_vec(1)) is None


def test_best_match_name_returned_not_id(tmp_path):
    """命中时返回注册的显示姓名（供报告直接使用），而非内部 id。"""
    db = SpeakerDB(tmp_path / "speakers.json")
    db.register("李四", _unit_vec(10))
    db.register("王五", _unit_vec(20))

    query = 0.9 * _unit_vec(10) + 0.1 * _unit_vec(20)
    assert db.match(query) == "李四"
