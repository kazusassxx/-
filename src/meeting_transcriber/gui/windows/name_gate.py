"""首次启动姓名强拦截（G-2，任务 8.2）。

config.json 无有效 user_name 时，启动必须输入姓名才能进入主界面；
确认后经 ``save_config`` 原子持久化，后续启动直接跳过。
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from meeting_transcriber.storage.config import save_config


def needs_name_gate(cfg: dict) -> bool:
    """config 无有效 user_name（缺失/空白）时需拦截（G-2）。"""
    return not str(cfg.get("user_name") or "").strip()


class NameGateDialog(QDialog):
    """姓名输入强拦截：未输入姓名时确定按钮不可用；确认后原子持久化。"""

    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowTitle(self.tr("首次使用设置"))

        tip = QLabel(self.tr("首次使用请先输入您的姓名（用于标记\"我\"）。"))
        tip.setWordWrap(True)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(self.tr("请输入您的姓名"))

        self._ok = QPushButton(self.tr("确定"))
        self._ok.setEnabled(False)
        cancel = QPushButton(self.tr("取消"))
        cancel.clicked.connect(self.reject)

        self._edit.textChanged.connect(self._on_text)
        self._ok.clicked.connect(self._confirm)

        form = QFormLayout()
        form.addRow(self.tr("姓名"), self._edit)

        layout = QVBoxLayout(self)
        layout.addWidget(tip)
        layout.addLayout(form)
        btns = QVBoxLayout()
        btns.addWidget(self._ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def _on_text(self, text: str) -> None:
        self._ok.setEnabled(bool(text.strip()))

    def _confirm(self) -> None:
        name = self._edit.text().strip()
        if not name:
            return
        self._cfg["user_name"] = name
        save_config(self._cfg)
        self.accept()

    def user_name(self) -> str:
        """已确认的姓名（对话框未通过时返回空串）。"""
        return self._edit.text().strip()
