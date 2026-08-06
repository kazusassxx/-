"""GUI 入口（8.9）：QApplication + 多语言（中/英/日）+ CJK 字体。

- 语言优先级：config.language（zh/en/ja）→ 系统 locale 检测 → 默认中文（G-8）
- 翻译采用运行时字典表（``DictTranslator``），不依赖 .ts/.qm 文件，
  缺失条目回退原文，绝不出现空串
- 首次启动无 user_name 时强制姓名拦截（G-2），未通过则退出不进入主界面
"""
from __future__ import annotations

import locale
import sys

from PySide6.QtCore import QTranslator
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog

from meeting_transcriber import __appname__
from meeting_transcriber.storage.config import load_config

# 界面字符串翻译表：中文为源语言（空表），en/ja 为映射
TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {},
    "en": {
        "首次使用设置": "First-time Setup",
        "首次使用请先输入您的姓名（用于标记\"我\"）。": "Enter your name to get started (used to mark \"Me\").",
        "请输入您的姓名": "Please enter your name",
        "确定": "OK",
        "设置": "Settings",
        "常规": "General",
        "音频": "Audio",
        "高级纠错": "Corrections",
        "声纹管理": "Voiceprints",
        "姓名": "Name",
        "界面语言": "UI Language",
        "输出目录": "Output Folder",
        "推理线程数": "Inference Threads",
        "浏览": "Browse...",
        "麦克风": "Microphone",
        "系统音开关": "System Audio",
        "系统音设备": "System Audio Device",
        "系统音增益": "System Audio Gain",
        "名词纠错映射": "Term Corrections (wrong=correct)",
        "添加": "Add",
        "删除": "Delete",
        "已注册声纹": "Registered Voiceprints",
        "保存": "Save",
        "取消": "Cancel",
        "开始录音": "Start Recording",
        "停止录音": "Stop Recording",
        "导入音频转写": "Import Audio",
        "录音中": "Recording",
        "转写中": "Transcribing",
        "正在加载推理引擎": "Loading inference engine...",
        "模型就绪": "Models ready",
        "模型加载失败": "Model load failed",
        "重试": "Retry",
        "打开文件": "Open File",
        "会议转写报告": "Meeting Transcript",
        "发言人": "Speakers",
        "本场发言人": "Speakers in this session",
        "命名": "Rename",
        "注册声纹": "Register Voiceprint",
        "首次使用设置 - 请先输入姓名": "First-time Setup - enter your name to continue",
        "姓名不能为空": "Name cannot be empty",
        "转写完成": "Transcription complete",
        "取消转写": "Cancel Transcription",
        "模型未就绪，正在等待...": "Waiting for models...",
        "就绪": "Ready",
        "录音失败": "Recording failed",
        "转写失败": "Transcription failed",
        "「我」无需注册声纹，改名请使用命名按钮。": "\"Me\" needs no voiceprint; use Rename to change the name.",
        "该发言人无声纹样本，无法注册。": "No voiceprint sample available for this speaker.",
        "已注册声纹：": "Voiceprint registered: ",
    },
    "ja": {
        "首次使用设置": "初回セットアップ",
        "首次使用请先输入您的姓名（用于标记\"我\"）。": "初回利用にはお名前の入力が必要です（「私」の表記に使用）。",
        "请输入您的姓名": "お名前を入力してください",
        "确定": "OK",
        "设置": "設定",
        "常规": "一般",
        "音频": "オーディオ",
        "高级纠错": "高度な修正",
        "声纹管理": "声紋管理",
        "姓名": "名前",
        "界面语言": "表示言語",
        "输出目录": "出力フォルダ",
        "推理线程数": "推論スレッド数",
        "浏览": "参照...",
        "麦克风": "マイク",
        "系统音开关": "システム音声",
        "系统音设备": "システム音声デバイス",
        "系统音增益": "システム音声ゲイン",
        "名词纠错映射": "用語修正（誤=正）",
        "添加": "追加",
        "删除": "削除",
        "已注册声纹": "登録済み声紋",
        "保存": "保存",
        "取消": "キャンセル",
        "开始录音": "録音開始",
        "停止录音": "録音停止",
        "导入音频转写": "音声ファイルをインポート",
        "录音中": "録音中",
        "转写中": "文字起こし中",
        "正在加载推理引擎": "推論エンジンを読み込み中...",
        "模型就绪": "モデル準備完了",
        "模型加载失败": "モデルの読み込みに失敗",
        "重试": "再試行",
        "打开文件": "ファイルを開く",
        "会议转写报告": "会議文字起こし",
        "发言人": "発言者",
        "本场发言人": "この会議の発言者",
        "命名": "名前を付ける",
        "注册声纹": "声紋を登録",
        "首次使用设置 - 请先输入姓名": "初回セットアップ - 名前を入力してください",
        "姓名不能为空": "名前は空にできません",
        "转写完成": "文字起こし完了",
        "取消转写": "文字起こしをキャンセル",
        "模型未就绪，正在等待...": "モデル待機中...",
        "就绪": "準備完了",
        "录音失败": "録音に失敗しました",
        "转写失败": "文字起こしに失敗しました",
        "「我」无需注册声纹，改名请使用命名按钮。": "「私」への声紋登録は不要です。名前変更は「名前を付ける」を使用してください。",
        "该发言人无声纹样本，无法注册。": "この発言者の声紋サンプルがありません。",
        "已注册声纹：": "声紋を登録しました：",
    },
}

_CJK_FONT_CANDIDATES = [
    "Microsoft YaHei",  # Windows
    "PingFang SC",  # macOS
    "Hiragino Sans GB",  # macOS
    "Noto Sans CJK SC",  # Linux
    "Noto Sans SC",  # Linux
    "WenQuanYi Micro Hei",  # Linux
    "SimHei",  # Windows 兜底
]


def detect_language(system_lang: str | None) -> str:
    """系统 locale 字符串 → 界面语言；不匹配时默认中文（G-8）。"""
    if not system_lang:
        return "zh"
    lang = system_lang.replace("_", "-").split("-")[0].lower()
    return lang if lang in ("zh", "en", "ja") else "zh"


def effective_language(cfg: dict, system_lang: str | None = None) -> str:
    """最终界面语言：config.language 优先 → 系统检测 → 中文。"""
    cfg_lang = str(cfg.get("language") or "").lower()
    if cfg_lang in ("zh", "en", "ja"):
        return cfg_lang
    if system_lang is None:
        system_lang = locale.getdefaultlocale()[0]
    return detect_language(system_lang)


class DictTranslator(QTranslator):
    """运行时字典翻译：QObject.tr() 自动查询；缺失条目回退原文。"""

    def __init__(self, table: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._table = table

    def translate(  # noqa: N802 - Qt 虚方法签名
        self, context: str, sourceText: str, disambiguation: str = "", n: int = -1
    ) -> str:
        return self._table.get(sourceText, sourceText)


def build_translator(language: str) -> DictTranslator:
    """按语言构建翻译器；未知语言回退中文（源语言空表 = 原文）。"""
    return DictTranslator(TRANSLATIONS.get(language, TRANSLATIONS["zh"]))


def load_cjk_font(app: QApplication) -> str | None:
    """加载系统 CJK 字体（G-10）；返回选中的字体族名，失败返回 None。"""
    families = set(QFontDatabase.families())
    for name in _CJK_FONT_CANDIDATES:
        if name in families:
            app.setFont(QFont(name, 10))
            return name
    return None


def create_app(argv: list[str] | None = None) -> tuple[QApplication, object | None]:
    """构建 QApplication 与主窗口；姓名拦截未通过时返回 (app, None)。"""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(__appname__)

    cfg = load_config()
    app.installTranslator(build_translator(effective_language(cfg)))
    load_cjk_font(app)

    from meeting_transcriber.gui.windows.name_gate import needs_name_gate, NameGateDialog

    if needs_name_gate(cfg):
        gate = NameGateDialog(cfg)
        if gate.exec() != QDialog.Accepted:
            return app, None
        cfg["user_name"] = gate.user_name()

    from meeting_transcriber.gui.windows.main_window import MainWindow

    return app, MainWindow(cfg)


def _install_crash_logging() -> None:
    """崩溃兜底：Python 异常 / C++ 崩溃栈 / Qt 致命消息写入 gui_error.log。

    WHY：打包版 exe 无控制台，崩溃时用户看不到 traceback；且 Qt 层
    abort（0xc0000409）前会打印致命消息，经 qInstallMessageHandler
    落盘后即可定位（如"开始录音后崩溃"的取证路径）。
    """
    from datetime import datetime

    from meeting_transcriber import paths

    log_path = paths.data_dir() / "gui_error.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        import faulthandler

        faulthandler.enable(file=open(log_path, "a"))
    except Exception:  # noqa: BLE001 - 日志不可用不影响主流程
        pass

    def _write(text: str) -> None:
        try:
            with open(log_path, "a") as f:
                f.write(text)
        except OSError:
            pass

    # Qt 层消息（Warning/Critical/Fatal）→ 落盘。abort 前 Qt 必打 fatal 消息。
    try:
        from PySide6.QtCore import qInstallMessageHandler

        def _qt_handler(mode, context, message) -> None:
            _write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] [Qt{int(mode)}] {message}\n")

        qInstallMessageHandler(_qt_handler)
    except Exception:  # noqa: BLE001
        pass

    def _hook(exc_type, exc, tb) -> None:
        import io
        import traceback

        sio = io.StringIO()
        traceback.print_exception(exc_type, exc, tb, file=sio)
        _write(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S} ====\n" + sio.getvalue())
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def main(argv: list[str] | None = None) -> int:
    """GUI 入口：返回进程退出码。"""
    _install_crash_logging()
    app, win = create_app(argv)
    if win is None:
        return 0
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
