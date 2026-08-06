"""阶段 3.4：EnergyVAD 分段 / 段长约束 / 碎句合并。

WHY：D-2/D-4 保证送 ASR 的段长落在 4–15s 健康区间——过短浪费推理、
过长超出 ASR 上下文产生截断错误；静音碎句若不合并在最终报告里会变成
一屏碎片。
"""
import numpy as np
import pytest

from meeting_transcriber.pipeline.vad import EnergyVAD, merge_adjacent

SR = 16000
TOL = 0.2


def _tone(seconds, rms=0.5):
    return np.full(int(seconds * SR), rms, dtype=np.float32)


def test_silence_gap_splits_segments():
    audio = np.concatenate([_tone(4.0), _tone(2.0, 0.0), _tone(4.0)])
    segs = EnergyVAD().segment(audio)
    assert len(segs) == 2
    assert segs[0][0] == pytest.approx(0.0, abs=TOL)
    assert segs[0][1] == pytest.approx(4.0, abs=TOL)
    assert segs[1][0] == pytest.approx(6.0, abs=TOL)
    assert segs[1][1] == pytest.approx(10.0, abs=TOL)


def test_short_segment_is_dropped():
    """<4s 的超短段丢弃（不送 ASR）。"""
    audio = np.concatenate([_tone(1.0), _tone(2.0, 0.0), _tone(5.0)])
    segs = EnergyVAD().segment(audio)
    assert len(segs) == 1
    assert segs[0][0] == pytest.approx(3.0, abs=TOL)
    assert segs[0][1] == pytest.approx(8.0, abs=TOL)


def test_overlong_segment_force_split():
    """连续 20s 语音强制切断为 ≤15s 的段。"""
    segs = EnergyVAD().segment(_tone(20.0))
    assert len(segs) >= 2
    for s, e in segs:
        assert e - s <= 15.0 + TOL
    assert segs[0] == pytest.approx((0.0, 15.0), abs=TOL)
    assert segs[-1][1] == pytest.approx(20.0, abs=TOL)


def test_fragments_within_gap_are_merged():
    """间隔 ≤1.5s 的碎句合并为一句（累计 ≤15s）。"""
    audio = np.concatenate([_tone(4.0), _tone(1.0, 0.0), _tone(4.0)])
    segs = EnergyVAD().segment(audio)
    assert len(segs) == 1
    assert segs[0][0] == pytest.approx(0.0, abs=TOL)
    assert segs[0][1] == pytest.approx(9.0, abs=TOL)


def test_merge_adjacent_gap_and_length_contract():
    # 间隔 ≤ gap 且合并后 ≤ max_len → 合并
    assert merge_adjacent([(0.0, 2.0), (2.5, 4.0)], gap=1.5, max_len=15.0) == [
        (0.0, 4.0)
    ]
    # 间隔 > gap → 不合并
    assert merge_adjacent([(0.0, 2.0), (4.0, 6.0)], gap=1.5, max_len=15.0) == [
        (0.0, 2.0),
        (4.0, 6.0),
    ]
    # 合并后累计超 max_len → 不合并
    assert merge_adjacent([(0.0, 10.0), (10.5, 16.0)], gap=1.5, max_len=15.0) == [
        (0.0, 10.0),
        (10.5, 16.0),
    ]


def test_all_silence_produces_no_segments():
    assert EnergyVAD().segment(_tone(10.0, 0.0)) == []
