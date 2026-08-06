"""模型下载逻辑（供 scripts/download_models.py 复用）。

- 支持代理（--proxy 或环境变量 HTTPS_PROXY）
- 镜像回退：GitHub 直连失败后逐个尝试镜像前缀
- 幂等：目标文件已存在（非空）即跳过
- 仅存在于独立脚本，GUI 运行零网络
"""
from __future__ import annotations

import os
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from meeting_transcriber import paths

_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

MODELS: dict[str, dict] = {
    "asr": {
        "name": "SenseVoice (zh/en/ja/ko/yue)",
        "url": f"{_BASE}/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2",
        "archive": True,
        "subdir": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
        "check": "model.int8.onnx",
    },
    "asr_zipformer": {
        "name": "Zipformer 中英双语 (streaming zipformer bilingual zh-en)",
        "url": f"{_BASE}/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
        "archive": True,
        "subdir": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
        "check": "encoder-epoch-99-avg-1.int8.onnx",
    },
    "embedding": {
        "name": "3D-Speaker eres2net (声纹提取)",
        "url": f"{_BASE}/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        "archive": False,
        "subdir": "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        "check": None,
    },
    "segmentation": {
        "name": "Pyannote segmentation-3.0 (说话人分割)",
        "url": f"{_BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
        "archive": True,
        "subdir": "sherpa-onnx-pyannote-segmentation-3-0",
        "check": "model.int8.onnx",
    },
}

# GitHub 加速镜像（按顺序回退）
MIRROR_PREFIXES = [
    "https://mirror.ghproxy.com/",
    "https://ghproxy.net/",
]


class DownloadError(RuntimeError):
    pass


def _open_url(url: str, proxy: str | None):
    if proxy:
        handler = urllib.request.ProxyHandler(
            {"http": proxy, "https": proxy}
        )
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()
    return opener.open(url, timeout=60)


def download_file(url: str, dest: Path, proxy: str | None = None) -> None:
    """下载 url 到 dest（先写 .part 临时文件，成功后原子 rename；失败抛 DownloadError）。

    Warning 6：直接写 dest 的旧实现中断后会残留半截文件，被 _is_present
    误判为"已存在"而跳过；.part + rename 保证中断不留残件，且与
    Content-Length 比对能发现截断（无 Content-Length 时仅要求非空完整读）。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    urls = [url]
    if url.startswith("https://github.com/"):
        urls += [f"{prefix}{url}" for prefix in MIRROR_PREFIXES]
    last_err: Exception | None = None
    part = dest.with_name(dest.name + ".part")
    try:
        for u in urls:
            part.unlink(missing_ok=True)  # 每轮重试前清理残件
            try:
                with _open_url(u, proxy) as resp:
                    total = int(resp.headers.get("Content-Length") or 0)
                    downloaded = 0
                    with open(part, "wb") as f:
                        while True:
                            chunk = resp.read(1024 * 256)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                _maybe_progress(downloaded, total)
                    if total and downloaded != total:
                        raise DownloadError(f"下载不完整: {downloaded}/{total} 字节")
                    if downloaded == 0:
                        raise DownloadError("下载内容为空")
                part.replace(dest)  # 成功：原子 rename 为目标文件
                return
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, DownloadError) as e:
                last_err = e
                continue
    finally:
        part.unlink(missing_ok=True)
    raise DownloadError(f"下载失败: {url} ({last_err})")


_last_progress = {"pct": -1}


def _maybe_progress(done: int, total: int) -> None:
    pct = int(done * 100 / total / 10) * 10
    if pct != _last_progress["pct"]:
        _last_progress["pct"] = pct
        print(f"\r  下载 {pct}%", end="", flush=True)


def _is_present(spec: dict, target_dir: Path) -> bool:
    if spec["archive"]:
        p = target_dir / spec["subdir"] / spec["check"]
        return p.exists() and p.stat().st_size > 0
    p = target_dir / spec["subdir"]  # 单文件模型名即 subdir 字段存放文件名
    return p.exists() and p.stat().st_size > 0


def download_model(
    key: str,
    target_dir: Path,
    proxy: str | None = None,
    force: bool = False,
) -> Path:
    """下载单个模型到 target_dir；已存在（非空）时幂等跳过。"""
    spec = MODELS[key]
    if not force and _is_present(spec, target_dir):
        print(f"[skip] {spec['name']} 已存在，跳过")
        return target_dir / spec["subdir"]

    print(f"[下载] {spec['name']} ...")
    if spec["archive"]:
        fd, tmp = tempfile.mkstemp(suffix=".tar.bz2")
        os.close(fd)
        try:
            download_file(spec["url"], Path(tmp), proxy)
            target_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tmp, "r:bz2") as tf:
                # Warning 5：filter="data" 拒绝 ../ 越界条目（路径穿越防护，Py3.12+）
                tf.extractall(target_dir, filter="data")
        finally:
            Path(tmp).unlink(missing_ok=True)
        result = target_dir / spec["subdir"]
    else:
        dest = target_dir / spec["subdir"]
        download_file(spec["url"], dest, proxy)
        result = dest
    print()
    print(f"[完成] {spec['name']} -> {result}")
    return result


def download_models(
    target_dir: Path | None = None,
    proxy: str | None = None,
    force: bool = False,
    keys: list[str] | None = None,
) -> dict[str, Path]:
    """下载全部（或指定）模型，返回 {key: 路径}。"""
    target_dir = target_dir or paths.models_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}
    for key in keys or list(MODELS):
        results[key] = download_model(key, target_dir, proxy, force)
    return results
