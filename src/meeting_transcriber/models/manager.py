"""ModelManager：模型定位（exe 同级 ./models/ → ~/.meeting-transcriber/models/）与异步加载。

加载失败明确报错且不联网（决策①：GUI 运行零网络，模型缺失由下载脚本补齐）。
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from meeting_transcriber import paths
from meeting_transcriber.pipeline.asr import make_recognizer

# key -> 相对于 models/ 的路径（SenseVoice / Pyannote 为解压目录，eres2net 为单文件）
MODEL_RELPATHS: dict[str, str] = {
    "asr": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
    "embedding": "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
    "segmentation": "sherpa-onnx-pyannote-segmentation-3-0",
}

# 可选引擎的 asr 目录名（与 MODEL_RELPATHS["asr"] 二选一，按 asr_engine 切换）
ZIPFORMER_ASR_REL = "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"

KEY_FILE = {
    "asr": None,  # asr 是解压目录（引擎识别器内部定位 model/int8 三件套）
    "embedding": None,  # 单文件
    "segmentation": "model.int8.onnx",
}


class ModelNotFoundError(RuntimeError):
    """模型缺失：提示运行 scripts/download_models.py，绝不自动联网。"""


def bundle_models_dir() -> Path | None:
    """打包版（PyInstaller）exe 同级的 ./models/ 目录；开发态返回 None。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "models"
    return None


class ModelManager:
    def __init__(
        self,
        home: Path | None = None,
        num_threads: int = 2,
        lang: str = "auto",
        engine: str = "auto",
        hotwords: str = "",
    ) -> None:
        self._home = home if home is not None else paths.models_dir()
        self._num_threads = num_threads
        self._lang = lang
        self._engine = engine or "auto"
        self._hotwords_file: Path | None = None
        self._write_hotwords(hotwords)
        self._status = "idle"
        self._error: str | None = None
        self._models: dict[str, object] = {}
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    # ---- 引擎与热词 ----
    def _write_hotwords(self, hotwords: str) -> None:
        """把逗号分隔热词写入 home/hotwords.txt（每行一词，UTF-8）。

        空热词时删除旧文件，确保下次加载回退 greedy_search 解码。
        """
        words = [w.strip() for w in (hotwords or "").split(",") if w.strip()]
        self._hotwords_file = None
        if not words:
            (self._home / "hotwords.txt").unlink(missing_ok=True)
            return
        p = self._home / "hotwords.txt"
        p.write_text("\n".join(dict.fromkeys(words)) + "\n", encoding="utf-8")
        self._hotwords_file = p

    def set_engine(self, engine: str) -> None:
        """切换 ASR 引擎；配合 load_async() 重载生效。"""
        self._engine = (engine or "auto") if engine in ("auto", "sensevoice", "zipformer") else "auto"

    def set_hotwords(self, hotwords: str) -> None:
        """更新热词并重写 hotwords.txt（下次 load_async 生效）。"""
        self._write_hotwords(hotwords)

    def _asr_rel(self) -> str:
        """asr 模型相对目录名：auto 时优先 zipformer（存在则用），否则 sensevoice。"""
        if self._engine == "zipformer":
            return ZIPFORMER_ASR_REL
        if self._engine == "sensevoice":
            return MODEL_RELPATHS["asr"]
        # auto：zipformer 目录已存在则优先（用户下载后无需改配置即切换）
        base = bundle_models_dir() or self._home
        return ZIPFORMER_ASR_REL if (base / ZIPFORMER_ASR_REL).exists() else MODEL_RELPATHS["asr"]

    # ---- 定位 ----
    def resolve_path(self, key: str) -> Path:
        """返回模型路径：exe 同级 ./models/ 优先，缺失回退 home 缓存。"""
        rel = self._asr_rel() if key == "asr" else MODEL_RELPATHS[key]
        bundle = bundle_models_dir()
        if bundle is not None:
            candidate = bundle / rel
            if candidate.exists():
                return candidate
        return self._home / rel

    def available(self) -> bool:
        """三个模型是否齐备（幂等检查已下载文件）。"""
        try:
            for key in MODEL_RELPATHS:
                path = self.resolve_path(key)
                file = KEY_FILE[key]
                target = path if file is None else path / file
                if not target.exists() or target.stat().st_size == 0:
                    return False
            return True
        except OSError:
            return False

    def resolve_file(self, key: str) -> Path:
        """返回模型文件（或目录）路径：打包 ./models/ 优先，缺失回退 home 缓存。"""
        path = self.resolve_path(key)
        file = KEY_FILE[key]
        return path if file is None else path / file

    # ---- 异步加载 ----
    @property
    def status(self) -> str:
        """"loading" | "ready" | "error"（未加载时为 "idle"）。"""
        with self._lock:
            return self._status

    @property
    def error(self) -> str | None:
        return self._error

    def set_lang(self, lang: str) -> None:
        """更新识别语言；配合 load_async() 重载使新语言生效（SenseVoice 语言在加载时固定）。"""
        self._lang = lang or "auto"

    def load_async(self, progress_cb=None) -> None:
        """后台线程加载三个模型；进度经 progress_cb(float) 上报。"""
        with self._lock:
            if self._status == "loading":
                return
            self._status = "loading"
            self._error = None
        t = threading.Thread(
            target=self._load_all, args=(progress_cb,), name="model-loader", daemon=True
        )
        self._threads.append(t)
        t.start()

    def _load_all(self, progress_cb) -> None:
        try:
            keys = list(MODEL_RELPATHS)
            for i, key in enumerate(keys):
                if progress_cb:
                    progress_cb(i / len(keys))
                self._models[key] = self._load_component(key)
            if progress_cb:
                progress_cb(1.0)
            with self._lock:
                self._status = "ready"
        except ModelNotFoundError as e:
            with self._lock:
                self._status = "error"
                self._error = str(e)
        except Exception as e:  # noqa: BLE001 - 任何加载失败都进入 error 态
            with self._lock:
                self._status = "error"
                self._error = f"模型加载失败: {e}"

    def _load_component(self, key: str) -> object:
        path = self.resolve_path(key)
        file = KEY_FILE[key]
        target = path if file is None else path / file
        if not target.exists():
            raise ModelNotFoundError(
                f"缺少模型 {key}（{target}）。请先运行 scripts/download_models.py 下载。"
            )
        import sherpa_onnx

        if key == "asr":
            # asr 传整个解压目录，识别器按目录内文件自动分派引擎
            # （zipformer 三件套 / sensevoice model.int8.onnx）
            return make_recognizer(
                str(target),
                num_threads=self._num_threads,
                lang=self._lang,
                hotwords_file=(
                    str(self._hotwords_file) if self._hotwords_file is not None else ""
                ),
            )
        if key == "embedding":
            return sherpa_onnx.SpeakerEmbeddingExtractor(
                sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=str(target), num_threads=self._num_threads
                )
            )
        if key == "segmentation":
            # sherpa-onnx 1.13.4 无 OfflineSpeakerSegmentation 类；Diarizer 内部
            # 用该路径组装 OfflineSpeakerDiarization，故返回模型文件路径字符串。
            return str(target)
        raise KeyError(key)

    def get(self, key: str) -> object:
        """已加载的模型组件；未就绪抛 ModelNotFoundError。"""
        with self._lock:
            model = self._models.get(key)
        if model is None:
            raise ModelNotFoundError(f"模型 {key} 未就绪（status={self._status}）")
        return model
