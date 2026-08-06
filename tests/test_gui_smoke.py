"""阶段 8 离屏冒烟（9.4 无头验证，QT_QPA_PLATFORM=offscreen）。

WHY（行为意图）：
- GUI 层模块可导入、主窗口可构造、状态页切换不崩溃（纯 UI 无法离屏交互的部分）
- 模型未就绪时转写任务挂起等待、就绪后自动续转并落盘 MD（P3/F-4）
- 录音 worker 零推理：只采集+混音落盘 WAV（P2）
"""
from __future__ import annotations

import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SR = 16000


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _tone(seconds, rms=0.5):
    return np.full(int(seconds * SR), rms, dtype=np.float32)


def _make_config(tmp_path) -> dict:
    return {
        "user_name": "张三",
        "language": "zh",
        "output_dir": str(tmp_path),
        "num_threads": 2,
        "mic_device": "",
        "sys_audio_enabled": False,
        "sys_audio_device": "",
        "sys_mix_gain": 0.9,
        "corrections": [],
    }


class _ReadyModels:
    """已就绪的假模型：不真实加载 sherpa，GUI 冒烟用。"""

    status = "ready"
    error = None

    def load_async(self, progress_cb=None) -> None:
        pass

    def get(self, key):
        raise RuntimeError(f"冒烟测试不应使用模型组件: {key}")


class _ErrorModels:
    status = "error"
    error = "缺少模型 asr"

    def load_async(self, progress_cb=None) -> None:
        pass


class _LoadingThenReady:
    """前 0.25s 为 loading，之后 ready；就绪前被 get() 即断言失败。

    WHY：验证 TranscriptionWorker 必须挂起等待模型就绪才使用组件（P3）。
    """

    def __init__(self):
        self._ready_at = time.monotonic() + 0.25

    @property
    def status(self):
        return "ready" if time.monotonic() >= self._ready_at else "loading"

    @property
    def error(self):
        return None

    def get(self, key):
        assert self.status == "ready", "模型未就绪即被转写线程使用（未挂起等待）"
        if key == "asr":
            return _FakeRecognizer()
        if key == "embedding":
            return _FakeExtractor()
        raise KeyError(key)


class _FakeStream:
    result = type("R", (), {"text": "<|zh|>测试文本<|end|>"})()

    def accept_waveform(self, sr, samples):
        pass


class _FakeRecognizer:
    """模拟 SenseVoiceASR：pipeline 经 transcribe() 调用。"""

    def transcribe(self, samples):
        return "测试文本"


class _FakeExtractor:
    def compute(self, samples, sr):
        return np.random.default_rng(0).standard_normal(512).astype(np.float32)


# ---------------- 主窗口冒烟 ----------------
def test_main_window_constructs_in_ready_state(qapp, tmp_path):
    from meeting_transcriber.gui.state_machine import State
    from meeting_transcriber.gui.windows.main_window import MainWindow
    from meeting_transcriber.storage.speakers import SpeakerDB

    win = MainWindow(
        _make_config(tmp_path),
        models=_ReadyModels(),
        speaker_db=SpeakerDB(tmp_path / "speakers.json"),
    )
    try:
        assert win._sm.state is State.READY
        assert win._stack.count() == 4  # 就绪/录音/转写/完成 四页
        assert win._stack.currentIndex() == 0
        # 就绪态：录音与导入可用（can("record") 契约）
        assert win._record_btn.isEnabled() is True
        assert win._import_btn.isEnabled() is True
        assert win._retry_btn.isHidden() is True
    finally:
        win._model_timer.stop()
        win.close()


def test_main_window_has_settings_entry(qapp, tmp_path, monkeypatch):
    """G-7（任务 8.5）：主窗口必须暴露设置入口，点击打开 SettingsDialog。

    WHY：设置对话框此前已实现但未接入主窗口（只有 import 无按钮），
    导致打包后 GUI 里找不到"设置"。此测试锁定入口存在且可打开。
    """
    from meeting_transcriber.gui.windows.main_window import MainWindow
    from meeting_transcriber.storage.speakers import SpeakerDB

    win = MainWindow(
        _make_config(tmp_path),
        models=_ReadyModels(),
        speaker_db=SpeakerDB(tmp_path / "speakers.json"),
    )
    try:
        assert win._settings_btn.isHidden() is False
        opened: list[object] = []
        monkeypatch.setattr(
            "meeting_transcriber.gui.windows.settings_dialog.SettingsDialog.exec",
            lambda self: opened.append(self),
        )
        win._open_settings()
        assert len(opened) == 1  # 按钮连接已生效，点击确实打开设置对话框
    finally:
        win._model_timer.stop()
        win.close()


def test_worker_released_only_after_finished(qapp, tmp_path):
    """QThread 必须在线程真正结束后才释放引用。

    WHY：原实现在 finished_ok/error 槽里直接 ``self._rec_worker = None``，
    引用归零立即析构 QThread，但线程收尾未完成 → Qt fatal
    "QThread: Destroyed while thread is still running" → 录音即崩溃。
    修复：释放只发生在 finished 信号触发的 *_worker_finished 槽。
    """
    from PySide6.QtCore import QThread

    from meeting_transcriber.gui.windows.main_window import MainWindow
    from meeting_transcriber.storage.speakers import SpeakerDB

    win = MainWindow(
        _make_config(tmp_path),
        models=_ReadyModels(),
        speaker_db=SpeakerDB(tmp_path / "speakers.json"),
    )
    try:
        # 模拟录音线程仍在收尾：finished 未到达 → 引用必须保留（不提前析构）
        rec = QThread()
        win._rec_worker = rec
        assert win._rec_worker is not None
        # finished 信号到达 → 统一释放
        win._on_rec_worker_finished()
        assert win._rec_worker is None

        # 转写 worker 同样契约
        tx = QThread()
        win._tx_worker = tx
        assert win._tx_worker is not None
        win._on_tx_worker_finished()
        assert win._tx_worker is None
    finally:
        win._model_timer.stop()
        win.close()


def test_state_pages_switch_without_crash(qapp, tmp_path):
    from meeting_transcriber.gui.windows.main_window import MainWindow
    from meeting_transcriber.storage.speakers import SpeakerDB

    win = MainWindow(
        _make_config(tmp_path),
        models=_ReadyModels(),
        speaker_db=SpeakerDB(tmp_path / "speakers.json"),
    )
    try:
        # 录音态：停止页；录音按钮禁用（防重复触发）
        win._sm.record()
        win._apply_state()
        assert win._stack.currentIndex() == 1
        assert win._record_btn.isEnabled() is False

        # 转写态：进度页；spinner 进入动画态（range 0,0）；录音按钮仍禁用（G-4）
        win._sm.stop()
        win._apply_state()
        assert win._stack.currentIndex() == 2
        assert win._spinner.maximum() == 0
        assert win._record_btn.isEnabled() is False

        # 完成态：预览页
        win._sm.finish()
        win._apply_state()
        assert win._stack.currentIndex() == 3

        # 复位回就绪
        win._sm.reset()
        win._apply_state()
        assert win._stack.currentIndex() == 0
        assert win._record_btn.isEnabled() is True
    finally:
        win._model_timer.stop()
        win.close()


def test_model_error_shows_retry_button(qapp, tmp_path):
    from meeting_transcriber.gui.windows.main_window import MainWindow
    from meeting_transcriber.storage.speakers import SpeakerDB

    win = MainWindow(
        _make_config(tmp_path),
        models=_ErrorModels(),
        speaker_db=SpeakerDB(tmp_path / "speakers.json"),
    )
    try:
        win._poll_models()  # G-14：错误状态显示重试按钮
        assert win._retry_btn.isHidden() is False
        assert "缺少模型" in win._model_label.text()
    finally:
        win._model_timer.stop()
        win.close()


# ---------------- 对话框冒烟 ----------------
def test_create_app_skips_gate_when_name_set(qapp, tmp_path, monkeypatch):
    """G-2：config 已有 user_name 时启动直接进入主界面（跳过拦截）。"""
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(tmp_path))
    from meeting_transcriber.gui.app import create_app
    from meeting_transcriber.storage.config import save_config

    save_config({"user_name": "张三"})

    app, win = create_app([])
    try:
        assert win is not None  # 姓名已配置 → 无拦截 → 主窗口就绪
    finally:
        win._model_timer.stop()
        win.close()


def test_settings_dialog_constructs_with_four_tabs(qapp, tmp_path):
    from meeting_transcriber.gui.windows.settings_dialog import SettingsDialog
    from meeting_transcriber.storage.speakers import SpeakerDB

    dlg = SettingsDialog(_make_config(tmp_path), SpeakerDB(tmp_path / "speakers.json"))
    try:
        assert dlg.windowTitle() == "设置"
        from PySide6.QtWidgets import QTabWidget

        assert dlg.findChild(QTabWidget).count() == 4  # 常规/音频/高级纠错/声纹管理
    finally:
        dlg.close()


def test_name_gate_dialog_blocks_empty_name(qapp, tmp_path, monkeypatch):
    """G-2：姓名未输入时确定按钮禁用，输入后才可继续。"""
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(tmp_path))  # 防写真实配置
    from meeting_transcriber.gui.windows.name_gate import NameGateDialog

    dlg = NameGateDialog({"user_name": ""})
    try:
        assert dlg._ok.isEnabled() is False
        dlg._edit.setText("张三")
        assert dlg._ok.isEnabled() is True
        dlg._edit.setText("   ")
        assert dlg._ok.isEnabled() is False  # 纯空白不算有效姓名
    finally:
        dlg.close()


# ---------------- 工作线程（P2/P3 契约）----------------
def test_recording_worker_records_and_mixes_without_inference(qapp, tmp_path):
    """录音零推理（P2）：worker 只采集+混音落盘 WAV，不触碰模型。"""
    from meeting_transcriber.gui.workers import RecordingWorker

    class _FakeRecorder:
        def __init__(self, *a, **k):
            self._stopped = False

        def on_waveform(self, cb):
            pass

        def start(self):
            pass

        def stop(self):
            self._stopped = True

        def failures(self):
            return {}  # 无失败轨（Critical 1：失败信息经 track_failed 上抛）

        def mic_samples(self):
            return np.full(SR, 0.2, dtype=np.float32)

        def sys_samples(self):
            return np.zeros(SR, dtype=np.float32)

        def cleanup(self):
            pass

    out = tmp_path / "record_test.wav"
    worker = RecordingWorker(
        mic_device="",
        sys_enabled=False,
        sys_device="",
        out_path=out,
        recorder_cls=_FakeRecorder,
    )
    worker.request_stop()  # 同步冒烟：先置停止位，run 立即完成一轮
    worker.run()

    import soundfile as sf

    data, rate = sf.read(str(out))
    assert rate == 16000
    assert data.shape[1] == 1 if data.ndim > 1 else data.ndim == 1  # mono


def test_transcription_worker_waits_for_models_then_writes_md(qapp, tmp_path):
    """模型未就绪时任务挂起、就绪后自动续转并产出 MD（P3/F-4）。"""
    from meeting_transcriber.gui.workers import TranscriptionWorker

    audio = np.concatenate([_tone(4.0, 0.5), _tone(2.0, 0.0)])  # 1 段语音
    out = tmp_path / "transcript_test.md"
    worker = TranscriptionWorker(
        _LoadingThenReady(),
        {"user_name": "张三", "corrections": []},
        audio,
        np.zeros(0, dtype=np.float32),
        out,
        track_sys="sys",
    )
    worker.run()  # 同步执行：内部等待模型 loading→ready 后转写

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "会议转写报告" in text
    assert "测试文本" in text  # ASR 文本贯通到报告（完整链路）


def test_cancel_before_report_write_skips_md(qapp, tmp_path, monkeypatch):
    """Info 1：sys 轨完成后、写盘前取消 → 不产出报告（取消竞态）。"""
    from meeting_transcriber.gui import workers as workers_mod
    from meeting_transcriber.gui.workers import TranscriptionWorker

    audio = np.concatenate([_tone(4.0, 0.5), _tone(2.0, 0.0)])
    out = tmp_path / "cancelled.md"
    worker = TranscriptionWorker(
        _LoadingThenReady(),
        {"user_name": "张三", "corrections": []},
        audio,
        audio,
        out,
        track_sys="sys",
    )

    def _cancel_then_merge(mic, sys):
        worker._cancelled.set()  # 恰在双轨完成、写盘前被取消
        return []

    monkeypatch.setattr(workers_mod, "merge_tracks", _cancel_then_merge)
    worker.run()

    assert not out.exists()  # 取消后不产出（半截）报告（E-6）


def test_worker_forwards_speaker_db_to_pipeline(qapp, tmp_path, monkeypatch):
    """Critical 2：TranscriptionWorker 把 speaker_db 显式传给 pipeline（C-4 生效前提）。"""
    from meeting_transcriber.gui import workers as workers_mod
    from meeting_transcriber.gui.workers import TranscriptionWorker
    from meeting_transcriber.storage.speakers import SpeakerDB

    captured = {}

    class _SpyPipeline:
        def __init__(self, models, config, speaker_db=None):
            captured["db"] = speaker_db

        def run(self, samples, track, progress=None, cancelled=None):
            return []

    monkeypatch.setattr(workers_mod, "TranscriptionPipeline", _SpyPipeline)
    db = SpeakerDB(tmp_path / "speakers.json")
    worker = TranscriptionWorker(
        _ReadyModels(),
        {"user_name": "张三", "corrections": []},
        np.zeros(0, dtype=np.float32),
        np.zeros(0, dtype=np.float32),
        tmp_path / "o.md",
        speaker_db=db,
    )
    worker.run()

    assert captured["db"] is db


def test_settings_threads_range_1_to_8_with_recommendation(qapp, tmp_path):
    """Warning 4：推理线程数范围 1..8（任务书 B-5），并显示推荐值说明。"""
    from meeting_transcriber.gui.windows.settings_dialog import SettingsDialog
    from meeting_transcriber.storage.speakers import SpeakerDB

    dlg = SettingsDialog(_make_config(tmp_path), SpeakerDB(tmp_path / "speakers.json"))
    try:
        assert dlg._threads.minimum() == 1
        assert dlg._threads.maximum() == 8  # 原 32 上限不符合 B-5
        assert "推荐" in dlg._threads_tip.text()
    finally:
        dlg.close()


def test_dual_track_progress_never_exceeds_100_percent(qapp, tmp_path, monkeypatch):
    """修复：sys 轨进度 span 误传 1.0 → 双轨进度冲到 150%；必须封顶 1.0。

    WHY：进度条 label 显示 p*100，p>1 会显示"150%"等溢出值，给用户
    造成"进度异常/超过 100%"的错误感知（模型其实还在正常加载）。
    """
    from meeting_transcriber.gui import workers as workers_mod
    from meeting_transcriber.gui.workers import TranscriptionWorker

    events: list[float] = []

    class _SpyPipeline:
        def __init__(self, models, config, speaker_db=None):
            pass

        def run(self, samples, track, progress=None, cancelled=None):
            progress(0.0)
            progress(1.0)
            return []

    monkeypatch.setattr(workers_mod, "TranscriptionPipeline", _SpyPipeline)
    audio = np.ones(16000, dtype=np.float32) * 0.5
    worker = TranscriptionWorker(
        _ReadyModels(),
        {"user_name": "张三", "corrections": []},
        audio,
        audio,
        tmp_path / "o.md",
        track_sys="sys",
    )
    worker.progress.connect(events.append)
    worker.run()

    assert events, "双轨转写必须发射进度"
    assert max(events) <= 1.0, f"进度不得超过 100%（出现 {max(events):.2f}）"
    assert round(events[-1], 6) == 1.0  # 双轨完成恰好到达 100%


def test_waveform_widget_buffers_wave_and_falls_back_to_bars(qapp):
    """录音实时波形：注入包络点 → 滚动 buffer 增长/截断；无波形数据回退电平条。

    WHY：用户要求"录音时有音频波形显示更直观"——波形数据缺失时
    必须回退 RMS 条显示，任何情况下 paint 不得崩溃。
    """
    from meeting_transcriber.gui.windows.waveform import WaveformWidget

    widget = WaveformWidget()
    widget.show()
    try:
        # 无波形数据：电平条模式不崩
        widget.set_levels(0.5, 0.3)
        widget.grab()  # 触发 paintEvent

        # 注入波形：buffer 增长
        frame = {"mic": 0.5, "sys": 0.2, "mic_wave": [0.1] * 32, "sys_wave": [0.05] * 32}
        widget.set_wave(frame)
        assert len(widget._buf["mic"]) == 32
        assert len(widget._buf["sys"]) == 32
        widget.grab()  # 波形绘制不崩

        # 缓冲截断：超过上限后保留最近点
        big = {"mic": 0.5, "sys": 0.2, "mic_wave": [0.1] * 32}
        for _ in range(300):  # 300*32 = 9600 > 6000
            widget.set_wave(big)
        assert len(widget._buf["mic"]) <= 6000
        widget.grab()

        # clear 后回到电平条模式
        widget.clear()
        assert len(widget._buf["mic"]) == 0
        widget.grab()
    finally:
        widget.close()


def test_recorder_waveform_push_includes_envelope(qapp):
    """Recorder 波形推送：dict 含 mic_wave/sys_wave 峰值包络（32 点）。

    WHY：实时波形显示的数据源——只有包络随 RMS 一起推送，GUI 才能滚动画图。
    """
    from meeting_transcriber.audio.capture import Recorder

    rec = Recorder("", False, "", sr=16000)
    captured: dict = {}
    rec.on_waveform(captured.update)
    rec._feed("mic", np.full(3200, 0.5, dtype=np.float32), rate=16000, channels=1)

    assert "mic" in captured
    assert len(captured.get("mic_wave", [])) == 32
    assert max(captured["mic_wave"]) == 0.5


def test_waveform_paints_track_labels_and_grid(qapp):
    """波形增强：双轨必须带轨名标签（麦克风/系统音）+ 时间刻度绘制不崩。

    WHY：增强后的波形用标签区分双轨来源，否则双色波形无法辨识谁是谁；
    网格与标签绘制在 paintEvent 内，注入数据后 grab() 即触发，崩溃即测试失败。
    """
    from meeting_transcriber.gui.windows import waveform as wave_mod
    from meeting_transcriber.gui.windows.waveform import WaveformWidget

    # 双轨标签元数据齐全（键名与数据入口一致）
    keys = {k for k, _l, _c in wave_mod._TRACK_LABELS}
    assert keys == {"mic", "sys"}

    widget = WaveformWidget()
    widget.show()
    try:
        widget.resize(400, 220)
        frame = {"mic": 0.5, "sys": 0.2, "mic_wave": [0.1] * 32, "sys_wave": [0.05] * 32}
        widget.set_wave(frame)
        # 完整 paintEvent 渲染（含轨标签 + 网格），崩溃即测试失败
        widget.grab()
    finally:
        widget.close()


def test_mini_window_waveform_large_enough(qapp):
    """录音小窗波形放大：最小尺寸保证波形可辨识（否则小窗波形看不清）。"""
    from meeting_transcriber.gui.windows.mini_window import MiniWindow

    mini = MiniWindow()
    try:
        assert mini._wave.minimumSize().width() >= 320
        assert mini._wave.minimumSize().height() >= 120
    finally:
        mini.close()


def test_settings_dialog_has_asr_lang_and_correction_hint(qapp, tmp_path):
    """准确率优化：设置里必须能改「识别语言(ASR)」且纠错 Tab 有格式说明。

    WHY：SenseVoice 不支持热词（官方仅 transducer 支持），固定识别语言是
    真实有效且零成本的准确率提升手段——必须可从设置界面配置，否则用户
    无法利用该能力。
    """
    from PySide6.QtWidgets import QLabel, QTabWidget

    from meeting_transcriber.gui.windows.settings_dialog import SettingsDialog
    from meeting_transcriber.storage.speakers import SpeakerDB

    dlg = SettingsDialog(_make_config(tmp_path), SpeakerDB(tmp_path / "speakers.json"))
    try:
        # 识别语言下拉存在，默认取配置 asr_lang（未配置 → auto）
        assert dlg._asr_lang.count() >= 6  # auto/zh/en/yue/ja/ko
        assert dlg._asr_lang.currentData() in ("auto", "zh")

        # ASR 引擎下拉存在（auto/sensevoice/zipformer）且含双语推荐项
        assert dlg._asr_engine.count() == 3
        assert dlg._asr_engine.itemData(2) == "zipformer"
        # 热词输入框存在且初始值来自 config
        assert dlg._hotwords.text() == ""

        # 纠错 Tab 有格式说明（错词=正确词）
        tabs = dlg.findChild(QTabWidget)
        tabs.setCurrentIndex(2)  # 高级纠错
        labels = [w for w in dlg.findChildren(QLabel) if "错词=正确词" in w.text()]
        assert labels, "高级纠错 Tab 必须展示映射格式说明"
    finally:
        dlg.close()


def test_settings_save_persists_asr_settings(qapp, tmp_path, monkeypatch):
    """保存设置：asr_lang / asr_engine / hotwords 全部写回 config。

    WHY：三项 ASR 参数（语言、引擎、热词）都是用户可见的准确率配置，
    保存不写回 = 重启后设置丢失，功能失效。
    """
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(tmp_path))  # 防写真实配置
    from meeting_transcriber.gui.windows.settings_dialog import SettingsDialog
    from meeting_transcriber.storage.speakers import SpeakerDB

    cfg = _make_config(tmp_path)
    cfg["asr_lang"] = "auto"
    cfg["asr_engine"] = "auto"
    cfg["hotwords"] = ""
    dlg = SettingsDialog(cfg, SpeakerDB(tmp_path / "speakers.json"))
    try:
        idx = dlg._asr_lang.findData("zh")
        dlg._asr_lang.setCurrentIndex(idx)
        idx = dlg._asr_engine.findData("zipformer")
        dlg._asr_engine.setCurrentIndex(idx)
        dlg._hotwords.setText("API,Transformer")
        dlg._on_save()
    finally:
        dlg.close()
    assert cfg["asr_lang"] == "zh"
    assert cfg["asr_engine"] == "zipformer"
    assert cfg["hotwords"] == "API,Transformer"


def test_setting_asr_changes_reload_models(qapp, tmp_path, monkeypatch):
    """识别语言 / ASR 引擎 / 热词任一变更 → 模型重载。

    WHY：这三项参数都在模型加载时固定（SenseVoice 语言、zipformer 热词
    modified_beam_search 解码），直接改 config 不重载 = 新设置无效，
    功能失效。此测试锁定「变更触发 set_* + load_async」契约。
    """
    from meeting_transcriber.gui.windows import main_window as mw_mod
    from meeting_transcriber.gui.windows.main_window import MainWindow
    from meeting_transcriber.storage.speakers import SpeakerDB

    class _LangModels:
        status = "ready"
        error = None
        langs: list[str] = []
        engines: list[str] = []
        hotwords: list[str] = []

        def load_async(self, progress_cb=None) -> None:
            pass

        def set_lang(self, lang: str) -> None:
            self.langs.append(lang)

        def set_engine(self, engine: str) -> None:
            self.engines.append(engine)

        def set_hotwords(self, hotwords: str) -> None:
            self.hotwords.append(hotwords)

    models = _LangModels()
    cfg = _make_config(tmp_path)
    cfg["asr_lang"] = "auto"
    cfg["asr_engine"] = "auto"
    cfg["hotwords"] = ""

    win = MainWindow(cfg, models=models, speaker_db=SpeakerDB(tmp_path / "sp.json"))

    class _FakeDlg:
        def __init__(self, cfg, db, parent):
            pass

        def exec(self):
            cfg["asr_lang"] = "zh"  # 用户在对话框里改成了中文
            cfg["asr_engine"] = "zipformer"
            cfg["hotwords"] = "API,Transformer"  # 并切引擎 + 加热词
            return mw_mod.QDialog.DialogCode.Accepted

    try:
        monkeypatch.setattr(mw_mod, "SettingsDialog", _FakeDlg)
        win._open_settings()

        assert models.langs == ["zh"], "识别语言变更后必须 set_lang + 重载模型"
        assert models.engines == ["zipformer"], "引擎变更后必须 set_engine + 重载"
        assert models.hotwords == ["API,Transformer"], "热词变更后必须 set_hotwords + 重载"
    finally:
        win._model_timer.stop()
        win.close()
