"""录音小窗（G-6，任务 8.4）：录音时缩为屏幕右上角置顶小窗。

仅含停止键 + 双轨波形；停录/转写开始后由 MainWindow 隐藏并恢复主窗。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from meeting_transcriber.gui.windows.waveform import WaveformWidget


class MiniWindow(QWidget):
    """右上角置顶录音小窗：仅停止键 + 波形。"""

    stop_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setObjectName("miniWindow")

        self._wave = WaveformWidget()
        self._wave.setMinimumSize(320, 120)
        self._time_label = QLabel("00:00")
        self._time_label.setObjectName("miniTime")

        stop_btn = QPushButton(self.tr("停止录音"))
        stop_btn.setObjectName("miniStop")
        stop_btn.clicked.connect(self.stop_requested.emit)

        top = QHBoxLayout()
        top.addWidget(self._wave, 1)
        top.addWidget(self._time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addLayout(top)
        layout.addWidget(stop_btn)

    def show_at_top_right(self) -> None:
        """置于主屏幕右上角（留 16px 边距）并显示。"""
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else self.screen().availableGeometry()
        self.adjustSize()
        x = geo.right() - self.width() - 16
        y = geo.top() + 16
        self.move(x, y)
        self.show()
        self.raise_()

    def set_wave(self, data: dict) -> None:
        self._wave.set_wave(data)

    def clear_wave(self) -> None:
        self._wave.clear()

    def set_elapsed(self, seconds: int) -> None:
        self._time_label.setText(f"{seconds // 60:02d}:{seconds % 60:02d}")
