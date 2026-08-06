"""双通道实时波形控件（主窗与小窗共用，G-3/G-6）。

录音时显示真实波形：``set_wave(data)`` 注入最近块的峰值包络点
（上游已按 ≤50ms 节流），内部环形缓冲 → paintEvent 画双轨滚动波形；
无波形数据时回退 RMS 电平条（兼容旧注入路径）。
"""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

_BG = QColor("#1e1e2e")
_MIC = QColor("#4cc9f0")
_SYS = QColor("#f72585")
_GRID = QColor("#2a2a3a")
_LABEL_BG = QColor(30, 30, 46, 200)
_BUF_MAX = 6000  # 每轨包络点上限（20 块/s × 32 点 ≈ 9s）

# 双轨标签：轨键 -> (显示名, 颜色)
_TRACK_LABELS = [("mic", "麦克风", _MIC), ("sys", "系统音", _SYS)]
_LABEL_BY_KEY = {k: (name, color) for k, name, color in _TRACK_LABELS}


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class WaveformWidget(QWidget):
    """双轨（麦克风 / 系统音）实时波形，缺数据时回退 RMS 条。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._levels = [0.0, 0.0]
        self._buf: dict[str, deque] = {"mic": deque(maxlen=_BUF_MAX), "sys": deque(maxlen=_BUF_MAX)}
        self.setMinimumSize(160, 56)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

    # ---- 数据入口 ----
    def set_levels(self, mic: float, sys: float) -> None:
        """仅更新 RMS 电平（无波形数据时的回退显示）。"""
        self._levels = [_clamp(mic), _clamp(sys)]
        self.update()

    def set_wave(self, data: dict) -> None:
        """注入一帧波形：``mic_wave``/``sys_wave`` 包络点（追加滚动），
        同时更新 RMS 电平。数据缺失的轨保持旧波形不补零。"""
        for track, key in (("mic", "mic_wave"), ("sys", "sys_wave")):
            wave = data.get(key)
            if wave:
                self._buf[track].extend(float(v) for v in wave)
        self._levels = [_clamp(data.get("mic", 0.0)), _clamp(data.get("sys", 0.0))]
        self.update()

    def clear(self) -> None:
        """清空波形与电平（新一次录音前调用）。"""
        self._buf["mic"].clear()
        self._buf["sys"].clear()
        self._levels = [0.0, 0.0]
        self.update()

    # ---- 绘制 ----
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 事件
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BG)
        has_mic = bool(self._buf["mic"])
        has_sys = bool(self._buf["sys"])
        if has_mic or has_sys:
            self._paint_wave(painter)
        else:
            self._paint_bars(painter)
        painter.end()

    def _paint_bars(self, painter: QPainter) -> None:
        """回退模式：双轨 RMS 电平条。"""
        w = self.width()
        h = self.height()
        bar_h = max(4, (h - 12) // 2)
        colors = (_MIC, _SYS)
        for i, level in enumerate(self._levels):
            y = 6 + i * (bar_h + 8)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#3a3a4a"))
            painter.drawRoundedRect(4, y, w - 8, bar_h, 3, 3)
            width = max(2, int((w - 8) * level))
            painter.setBrush(colors[i])
            painter.drawRoundedRect(4, y, width, bar_h, 3, 3)

    def _paint_wave(self, painter: QPainter) -> None:
        """双轨滚动波形：上下两半，各轨中点为零线，包络折线填充 + 轨标签 + 时间刻度。"""
        w = self.width()
        h = self.height()
        track_h = max(16, (h - 6) // 2)
        labels = (("mic", _MIC, 3), ("sys", _SYS, 3 + track_h + 6))

        # 时间刻度：按缓冲最长时长等分 5 格垂直虚线（约每 2s 一格）
        self._paint_grid(painter, w, h)

        for key, color, y0 in labels:
            pts = self._buf[key]
            painter.setPen(QColor("#3a3a4a"))
            painter.drawLine(0, y0 + track_h // 2, w, y0 + track_h // 2)  # 零线
            if not pts:
                continue
            painter.setPen(QPen(color, 1))
            n = len(pts)
            step_x = w / max(1, n - 1)
            amp_h = track_h / 2 - 3
            path = QPainterPath()
            path.moveTo(QPointF(0.0, y0 + track_h / 2 - min(amp_h, pts[0] * amp_h)))
            for i, v in enumerate(pts):
                x = i * step_x
                y = y0 + track_h / 2 - min(amp_h, v * amp_h)
                path.lineTo(QPointF(x, y))
            painter.drawPath(path)
            # 轨标签：左上角半透明底 + 轨名
            self._paint_track_label(painter, key, y0)

    def _paint_grid(self, painter: QPainter, w: int, h: int) -> None:
        """垂直时间刻度虚线（5 等分）。"""
        pen = QPen(_GRID, 1, Qt.DashLine)
        painter.setPen(pen)
        for i in range(1, 5):
            x = w * i / 5
            painter.drawLine(int(x), 0, int(x), h)

    def _paint_track_label(self, painter: QPainter, key: str, y0: int) -> None:
        """轨名标签（麦克风/系统音），覆盖在最上层。"""
        label, color = _LABEL_BY_KEY[key]
        painter.save()
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(label) + 8
        th = metrics.height() + 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(_LABEL_BG)
        painter.drawRoundedRect(2, y0 + 1, tw, th, 2, 2)
        painter.setPen(color)
        painter.drawText(6, y0 + 1 + metrics.ascent() + 1, label)
        painter.restore()
