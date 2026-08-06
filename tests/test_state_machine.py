"""阶段 8.10：GUI 状态机迁移合法性（§七 状态机契约）。

WHY：录音→转写→完成→就绪是唯一合法主链路；转写/导入转写态可取消
静默回就绪；录音按钮仅在就绪/完成态可用——若允许非法迁移（如就绪
直接转写、录音态直接完成），会造成录音与转写并发（G-4）等状态错乱。
"""
import pytest

from meeting_transcriber.gui.state_machine import (
    IllegalTransitionError,
    State,
    StateMachine,
)


def _to(sm: StateMachine, target: State) -> None:
    """把状态机驱动到指定前置状态（合法路径）。"""
    if target is State.RECORDING:
        sm.record()
    elif target is State.TRANSCRIBING:
        sm.record()
        sm.stop()
    elif target is State.IMPORTING:
        sm.import_audio()
    elif target is State.COMPLETED:
        sm.import_audio()
        sm.finish()


def test_full_chain_record_stop_finish_reset():
    """主链路：就绪→录音→转写→完成→就绪。"""
    sm = StateMachine()
    assert sm.state is State.READY

    sm.record()
    assert sm.state is State.RECORDING

    sm.stop()
    assert sm.state is State.TRANSCRIBING

    sm.finish()
    assert sm.state is State.COMPLETED

    sm.reset()
    assert sm.state is State.READY


def test_cancel_transcribing_returns_ready():
    """转写态取消 → 静默回就绪（E-6），不产出报告。"""
    sm = StateMachine()
    _to(sm, State.TRANSCRIBING)

    sm.cancel()

    assert sm.state is State.READY


def test_cancel_importing_returns_ready():
    """导入转写态取消 → 回就绪。"""
    sm = StateMachine()
    _to(sm, State.IMPORTING)

    sm.cancel()

    assert sm.state is State.READY


def test_import_finish_reaches_completed():
    """导入转写正常完成 → 完成态（与录音转写共用完成态 UI）。"""
    sm = StateMachine()
    sm.import_audio()
    assert sm.state is State.IMPORTING

    sm.finish()

    assert sm.state is State.COMPLETED


def test_completed_can_start_new_recording():
    """完成态可直接开始新录音（连续开会场景无需先复位）。"""
    sm = StateMachine()
    _to(sm, State.COMPLETED)

    sm.record()

    assert sm.state is State.RECORDING


@pytest.mark.parametrize(
    "pre,action",
    [
        # 就绪态只能 record / import_audio
        (State.READY, "stop"),
        (State.READY, "finish"),
        (State.READY, "cancel"),
        (State.READY, "reset"),
        # 录音态只能 stop
        (State.RECORDING, "record"),
        (State.RECORDING, "finish"),
        (State.RECORDING, "cancel"),
        (State.RECORDING, "import_audio"),
        (State.RECORDING, "reset"),
        # 转写态只能 finish / cancel
        (State.TRANSCRIBING, "record"),
        (State.TRANSCRIBING, "stop"),
        (State.TRANSCRIBING, "import_audio"),
        (State.TRANSCRIBING, "reset"),
        # 导入转写态只能 finish / cancel
        (State.IMPORTING, "record"),
        (State.IMPORTING, "stop"),
        (State.IMPORTING, "import_audio"),
        (State.IMPORTING, "reset"),
        # 完成态只能 record / import_audio / reset（连续开会或导入新音频）
        (State.COMPLETED, "stop"),
        (State.COMPLETED, "finish"),
        (State.COMPLETED, "cancel"),
    ],
)
def test_illegal_transitions_raise(pre, action):
    """非法迁移必须显式报错，绝不静默改变状态。"""
    sm = StateMachine()
    _to(sm, pre)
    before = sm.state

    with pytest.raises(IllegalTransitionError):
        getattr(sm, action)()

    assert sm.state is before  # 报错后状态不变（无副作用）


@pytest.mark.parametrize(
    "pre,expected",
    [
        (State.READY, True),
        (State.RECORDING, False),  # 录音态显示停止键
        (State.TRANSCRIBING, False),  # G-4：转写态禁用录音按钮
        (State.IMPORTING, False),
        (State.COMPLETED, True),
    ],
)
def test_record_button_enabled_only_in_ready_or_completed(pre, expected):
    """录音按钮启用规则：仅就绪/完成态可开始录音，防录音与转写并发。"""
    sm = StateMachine()
    _to(sm, pre)

    assert sm.can("record") is expected


def test_can_is_query_without_side_effect():
    """can() 仅查询不改变状态（按钮状态轮询安全）。"""
    sm = StateMachine()
    _to(sm, State.TRANSCRIBING)

    assert sm.can("cancel") is True
    assert sm.can("record") is False
    assert sm.state is State.TRANSCRIBING
