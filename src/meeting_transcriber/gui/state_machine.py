"""GUI 状态机（§七 状态机契约，任务 8.1）。

五态：就绪 / 录音 / 转写 / 完成 / 导入转写。

迁移表（唯一合法边）::

    就绪 --record--> 录音 --stop--> 转写 --finish--> 完成 --reset--> 就绪
    就绪 --import_audio--> 导入转写 --finish--> 完成
    转写 --cancel--> 就绪
    导入转写 --cancel--> 就绪
    完成 --record--> 录音           （连续开会：无需先复位）
    完成 --import_audio--> 导入转写

- 非法迁移抛 ``IllegalTransitionError`` 且状态不变（无副作用）
- ``can(action)`` 纯查询：录音按钮启用规则 = can("record")（G-4 防并发）

本模块刻意不依赖 Qt，保持纯 Python 可单测。
"""
from __future__ import annotations

from enum import Enum


class State(str, Enum):
    READY = "ready"  # 就绪
    RECORDING = "recording"  # 录音
    TRANSCRIBING = "transcribing"  # 转写
    COMPLETED = "completed"  # 完成
    IMPORTING = "importing"  # 导入转写


class IllegalTransitionError(RuntimeError):
    """状态迁移非法：调用方（GUI）应先以 can() 查询。"""


# action -> 允许迁移的前置状态集合
_TRANSITIONS: dict[str, frozenset[State]] = {
    "record": frozenset({State.READY, State.COMPLETED}),
    "stop": frozenset({State.RECORDING}),
    "finish": frozenset({State.TRANSCRIBING, State.IMPORTING}),
    "cancel": frozenset({State.TRANSCRIBING, State.IMPORTING}),
    "import_audio": frozenset({State.READY, State.COMPLETED}),
    "reset": frozenset({State.COMPLETED}),
}

# action -> 迁移后的目标状态
_NEXT: dict[str, State] = {
    "record": State.RECORDING,
    "stop": State.TRANSCRIBING,
    "finish": State.COMPLETED,
    "cancel": State.READY,
    "import_audio": State.IMPORTING,
    "reset": State.READY,
}


class StateMachine:
    def __init__(self, initial: State = State.READY) -> None:
        self._state = initial

    @property
    def state(self) -> State:
        return self._state

    def can(self, action: str) -> bool:
        """查询某动作在当前状态下是否合法（无副作用，供按钮禁用轮询）。"""
        return self._state in _TRANSITIONS.get(action, frozenset())

    def _do(self, action: str) -> None:
        if not self.can(action):
            raise IllegalTransitionError(
                f"非法迁移: {self._state.value} --{action}--> ?"
            )
        self._state = _NEXT[action]

    # ---- 动作（与设计文档命名一致，供 GUI 直接调用）----
    def record(self) -> None:
        """开始录音：就绪/完成 → 录音。"""
        self._do("record")

    def stop(self) -> None:
        """停录并进入转写：录音 → 转写。"""
        self._do("stop")

    def finish(self) -> None:
        """转写完成：转写/导入转写 → 完成。"""
        self._do("finish")

    def cancel(self) -> None:
        """取消：转写/导入转写 → 就绪（静默，不产出报告，E-6）。"""
        self._do("cancel")

    def import_audio(self) -> None:
        """导入音频转写：就绪/完成 → 导入转写。"""
        self._do("import_audio")

    def reset(self) -> None:
        """完成 → 就绪（新会话准备）。"""
        self._do("reset")
