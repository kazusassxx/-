"""设置面板（G-7，任务 8.5）：常规 / 音频 / 高级纠错 / 声纹管理 四 Tab。

修改经 ``save_config`` 原子持久化（G-9），声纹删除直接作用于 SpeakerDB。
"""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from meeting_transcriber.audio.devices import list_input_devices, list_loopback_devices
from meeting_transcriber.storage.config import save_config

LANG_LABELS = [("zh", "中文"), ("en", "English"), ("ja", "日本語")]

# SenseVoice 支持的识别语言（asr_lang）；auto = 自动检测
ASR_LANG_LABELS = [
    ("auto", "自动检测"),
    ("zh", "中文"),
    ("en", "English"),
    ("yue", "粤语"),
    ("ja", "日本語"),
    ("ko", "한국어"),
]

# ASR 引擎（asr_engine）；auto = 模型目录自动识别（zipformer 优先）
ASR_ENGINE_LABELS = [
    ("auto", "自动识别"),
    ("sensevoice", "SenseVoice（多语言）"),
    ("zipformer", "Zipformer 中英双语（推荐）"),
]

# 推理线程数范围 1..8（任务书 B-5）；推荐值 = CPU 核数/2，上限 4
THREADS_MIN = 1
THREADS_MAX = 8


class SettingsDialog(QDialog):
    """四 Tab 设置对话框；accept 时原子写盘 config.json。"""

    def __init__(self, config: dict, speaker_db, parent=None) -> None:
        super().__init__(parent)
        self._cfg = config  # 引用 MainWindow 的 config，accept 后同步生效
        self._db = speaker_db
        self.setWindowTitle(self.tr("设置"))
        self.setMinimumWidth(480)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_general(), self.tr("常规"))
        tabs.addTab(self._build_audio(), self.tr("音频"))
        tabs.addTab(self._build_corrections(), self.tr("高级纠错"))
        tabs.addTab(self._build_voiceprints(), self.tr("声纹管理"))

        btn_save = QPushButton(self.tr("保存"))
        btn_cancel = QPushButton(self.tr("取消"))
        btn_save.clicked.connect(self._on_save)
        btn_cancel.clicked.connect(self.reject)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addLayout(btns)

    # ---- 常规 ----
    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._name = QLineEdit(str(self._cfg.get("user_name") or ""))
        self._lang = QComboBox()
        for code, label in LANG_LABELS:
            self._lang.addItem(label, code)
        idx = self._lang.findData(str(self._cfg.get("language") or "zh"))
        self._lang.setCurrentIndex(max(idx, 0))

        self._out_dir = QLineEdit(str(self._cfg.get("output_dir") or ""))
        browse = QPushButton(self.tr("浏览..."))
        browse.clicked.connect(self._pick_output_dir)

        self._threads = QSpinBox()
        self._threads.setRange(THREADS_MIN, THREADS_MAX)  # 任务书 B-5：1..8
        self._threads.setValue(int(self._cfg.get("num_threads") or 4))
        recommended = max(THREADS_MIN, min(4, (os.cpu_count() or 4) // 2))
        self._threads_tip = QLabel(
            self.tr(f"推荐 {recommended}（CPU 核数/2，上限 4）")
        )
        self._threads_tip.setStyleSheet("color: gray;")

        self._asr_lang = QComboBox()
        for code, label in ASR_LANG_LABELS:
            self._asr_lang.addItem(label, code)
        idx = self._asr_lang.findData(str(self._cfg.get("asr_lang") or "auto"))
        self._asr_lang.setCurrentIndex(max(idx, 0))
        self._asr_lang_tip = QLabel(
            self.tr("识别语言 = 指定固定语言可避免跨语言误判，显著提升该语言准确率")
        )
        self._asr_lang_tip.setStyleSheet("color: gray;")

        self._asr_engine = QComboBox()
        for code, label in ASR_ENGINE_LABELS:
            self._asr_engine.addItem(label, code)
        idx = self._asr_engine.findData(str(self._cfg.get("asr_engine") or "auto"))
        self._asr_engine.setCurrentIndex(max(idx, 0))
        self._asr_engine_tip = QLabel(
            self.tr("Zipformer = 中英混杂专用（需下载双语模型）；SenseVoice = 多语言通用")
        )
        self._asr_engine_tip.setStyleSheet("color: gray;")

        self._hotwords = QLineEdit(str(self._cfg.get("hotwords") or ""))
        self._hotwords_tip = QLabel(
            self.tr("热词（仅 Zipformer 引擎生效）：英文/专名用逗号分隔，如 API,Transformer,张三丰")
        )
        self._hotwords_tip.setWordWrap(True)
        self._hotwords_tip.setStyleSheet("color: gray;")

        form.addRow(self.tr("姓名"), self._name)
        form.addRow(self.tr("界面语言"), self._lang)
        form.addRow(self.tr("识别语言"), self._asr_lang)
        form.addRow("", self._asr_lang_tip)
        form.addRow(self.tr("ASR 引擎"), self._asr_engine)
        form.addRow("", self._asr_engine_tip)
        form.addRow(self.tr("热词"), self._hotwords)
        form.addRow("", self._hotwords_tip)
        row = QHBoxLayout()
        row.addWidget(self._out_dir, 1)
        row.addWidget(browse)
        form.addRow(self.tr("输出目录"), row)
        form.addRow(self.tr("推理线程数"), self._threads)
        form.addRow("", self._threads_tip)
        return w

    def _pick_output_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr("输出目录"), self._out_dir.text())
        if d:
            self._out_dir.setText(d)

    # ---- 音频 ----
    def _build_audio(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        devices = list_input_devices()
        # 同名设备常出现在多个 hostapi（MME/DirectSound/WASAPI）：
        # 下拉去重，运行时 mic_device_index 自动消歧优先 MME
        names = []
        for d in devices:
            if d["name"] not in names:
                names.append(d["name"])

        self._mic = QComboBox()
        self._mic.addItems(names)
        self._set_combo_by_text(self._mic, str(self._cfg.get("mic_device") or ""))

        self._mic_gain = QDoubleSpinBox()
        self._mic_gain.setRange(1.0, 50.0)
        self._mic_gain.setSingleStep(1.0)
        self._mic_gain.setDecimals(0)
        self._mic_gain.setValue(float(self._cfg.get("mic_gain") or 10.0))
        self._mic_gain_tip = QLabel(
            self.tr("麦克风增益 = 软件放大被系统压弱的麦克风信号（Nahimic 等增强软件常见）")
        )
        self._mic_gain_tip.setStyleSheet("color: gray;")

        self._sys_enabled = QCheckBox(self.tr("系统音开关"))
        self._sys_enabled.setChecked(bool(self._cfg.get("sys_audio_enabled")))
        self._sys_enabled.toggled.connect(self._sys_enabled_changed)

        # 系统音 = WASAPI loopback 回采（录电脑播放的声音）
        lb_devices = list_loopback_devices()
        lb_names = [d["name"] for d in lb_devices]
        self._sys_device = QComboBox()
        self._sys_device.addItems(lb_names)
        # 旧配置可能存输入设备名：找不到时保持空项 → 运行自动回退默认 loopback
        self._set_combo_by_text(self._sys_device, str(self._cfg.get("sys_audio_device") or ""))
        self._sys_loopback_tip = QLabel(self.tr("系统音 = 播放设备 loopback 回采（录制电脑播放的声音）"))
        self._sys_loopback_tip.setStyleSheet("color: gray;")

        self._sys_gain = QDoubleSpinBox()
        self._sys_gain.setRange(0.0, 1.0)
        self._sys_gain.setSingleStep(0.05)
        self._sys_gain.setValue(float(self._cfg.get("sys_mix_gain") or 0.9))

        form.addRow(self.tr("麦克风"), self._mic)
        form.addRow(self.tr("麦克风增益"), self._mic_gain)
        form.addRow("", self._mic_gain_tip)
        form.addRow("", self._sys_enabled)
        form.addRow(self.tr("系统音设备"), self._sys_device)
        form.addRow("", self._sys_loopback_tip)
        form.addRow(self.tr("系统音增益"), self._sys_gain)
        return w

    def _sys_enabled_changed(self, checked: bool) -> None:
        self._sys_device.setEnabled(checked)

    # ---- 高级纠错 ----
    def _build_corrections(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._corr_list = QListWidget()
        for item in self._cfg.get("corrections") or []:
            self._corr_list.addItem(str(item))

        self._corr_tip = QLabel(
            self.tr("格式：错词=正确词（如 张三丰=张三）。"
                    "多条用英文逗号分隔。ASR 常把生僻词/人名识别成同音字，在此纠正。")
        )
        self._corr_tip.setWordWrap(True)
        self._corr_tip.setStyleSheet("color: gray;")

        add_btn = QPushButton(self.tr("添加"))
        del_btn = QPushButton(self.tr("删除"))
        add_btn.clicked.connect(self._add_correction)
        del_btn.clicked.connect(self._del_correction)

        btns = QHBoxLayout()
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        layout.addWidget(self._corr_list)
        layout.addLayout(btns)
        layout.addWidget(self._corr_tip)
        return w

    def _add_correction(self) -> None:
        text, ok = QInputDialog.getText(self, self.tr("高级纠错"), self.tr("名词纠错映射"))
        if ok and text.strip():
            self._corr_list.addItem(text.strip())

    def _del_correction(self) -> None:
        for item in self._corr_list.selectedItems():
            self._corr_list.takeItem(self._corr_list.row(item))

    # ---- 声纹管理 ----
    def _build_voiceprints(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self._vp_list = QListWidget()
        self._reload_voiceprints()

        del_btn = QPushButton(self.tr("删除"))
        del_btn.clicked.connect(self._del_voiceprint)

        layout.addWidget(self._vp_list)
        layout.addWidget(del_btn)
        return w

    def _reload_voiceprints(self) -> None:
        self._vp_list.clear()
        for sp in self._db.speakers():
            self._vp_list.addItem(QListWidgetItem(f"{sp['name']}  ({sp['id'][:8]}…)"))

    def _del_voiceprint(self) -> None:
        item = self._vp_list.currentItem()
        if item is None:
            return
        row = self._vp_list.row(item)
        speakers = self._db.speakers()
        if 0 <= row < len(speakers):
            self._db.delete(speakers[row]["id"])
            self._db.save()
            self._reload_voiceprints()

    # ---- 保存 ----
    def _on_save(self) -> None:
        self._cfg["user_name"] = self._name.text().strip()
        self._cfg["language"] = self._lang.currentData()
        self._cfg["output_dir"] = self._out_dir.text().strip()
        self._cfg["num_threads"] = self._threads.value()
        self._cfg["asr_lang"] = self._asr_lang.currentData()
        self._cfg["asr_engine"] = self._asr_engine.currentData()
        self._cfg["hotwords"] = self._hotwords.text().strip()
        self._cfg["mic_device"] = self._mic.currentText()
        self._cfg["mic_gain"] = self._mic_gain.value()
        self._cfg["sys_audio_enabled"] = self._sys_enabled.isChecked()
        self._cfg["sys_audio_device"] = self._sys_device.currentText()
        self._cfg["sys_mix_gain"] = self._sys_gain.value()
        self._cfg["corrections"] = [
            self._corr_list.item(i).text() for i in range(self._corr_list.count())
        ]
        save_config(self._cfg)
        self.accept()

    @staticmethod
    def _set_combo_by_text(combo: QComboBox, text: str) -> None:
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
