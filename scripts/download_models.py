"""独立模型下载脚本（幂等，支持代理与镜像回退）。

用法:
    python scripts/download_models.py [--target DIR] [--proxy URL] [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meeting_transcriber import paths
from meeting_transcriber.models import download


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载 meeting-transcriber 三个模型")
    parser.add_argument(
        "--target",
        default=str(paths.models_dir()),
        help=f"模型存放目录（默认 {paths.models_dir()}）",
    )
    parser.add_argument("--proxy", default=None, help="HTTP/HTTPS 代理，如 http://127.0.0.1:7890")
    parser.add_argument("--force", action="store_true", help="强制重新下载（默认幂等跳过）")
    parser.add_argument(
        "--models",
        nargs="*",
        choices=list(download.MODELS),
        default=None,
        help="仅下载指定模型：asr / embedding / segmentation",
    )
    args = parser.parse_args(argv)

    try:
        results = download.download_models(
            target_dir=Path(args.target),
            proxy=args.proxy,
            force=args.force,
            keys=args.models,
        )
    except download.DownloadError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    print("\n全部完成：")
    for key, path in results.items():
        print(f"  {key}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
