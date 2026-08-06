"""CLI 入口：--list-devices / --offline <file> / --help。"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

from meeting_transcriber import paths
from meeting_transcriber.audio.devices import list_input_devices
from meeting_transcriber.audio.import_audio import decode_to_16k_mono
from meeting_transcriber.models.manager import ModelManager
from meeting_transcriber.pipeline import embedding
from meeting_transcriber.pipeline.pipeline import TranscriptionPipeline
from meeting_transcriber.report.atomicio import write_text_atomic
from meeting_transcriber.report.formatter import format_report
from meeting_transcriber.storage.config import load_config
from meeting_transcriber.storage.speakers import SpeakerDB


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meeting-transcriber",
        description="纯离线双轨会议转写工具：声纹分角色 + SenseVoice 转写 + Markdown 报告",
    )
    parser.add_argument("--list-devices", action="store_true", help="枚举输入设备")
    parser.add_argument("--offline", metavar="FILE", help="离线转写音频文件 (WAV/MP3/FLAC)")
    parser.add_argument("--name", metavar="姓名", default=None, help="当前用户姓名")
    parser.add_argument(
        "--lang", choices=["zh", "en", "ja", "auto"], default=None, help="ASR 语言"
    )
    parser.add_argument("--threads", type=int, default=None, help="推理线程数")
    return parser


def _list_devices_cmd() -> int:
    devices = list_input_devices()
    if not devices:
        print("未找到可用的输入设备。", file=sys.stderr)
        return 1
    print("可用的输入设备：")
    for d in devices:
        name = d.get("name", "")
        hostapi = d.get("hostapi", "")
        tag = f" [{hostapi}]" if hostapi else ""
        print(f"  [{d['index']}] {name}{tag} ({d['channels']} ch)")
    return 0


def _offline_cmd(args: argparse.Namespace) -> int:
    src = Path(args.offline)
    if not src.exists():
        print(f"错误: 文件不存在: {src}", file=sys.stderr)
        return 1

    cfg = load_config()
    if args.name:
        cfg["user_name"] = args.name
    if args.lang:
        cfg["asr_lang"] = args.lang  # Warning 3：--lang 真正生效（传给 ASR）
    if args.threads:
        cfg["num_threads"] = args.threads

    print(f"解码音频: {src}")
    samples = decode_to_16k_mono(src)

    mgr = ModelManager(
        num_threads=int(cfg.get("num_threads") or 4),
        lang=str(cfg.get("asr_lang") or "auto"),
    )
    mgr.load_async()
    while mgr.status in ("idle", "loading"):
        time.sleep(0.05)
    if mgr.status != "ready":
        print(f"错误: {mgr.error}", file=sys.stderr)
        return 1

    embedding.set_model(mgr.get("embedding"))
    db = SpeakerDB.load(paths.speakers_path())  # Critical 2：CLI 同样接入声纹库（C-4）
    pipe = TranscriptionPipeline(mgr, cfg, speaker_db=db)
    print("转写中 ...")
    segs = pipe.run(samples, "import", cancelled=threading.Event())
    if pipe.segmentation_note:
        print(pipe.segmentation_note, file=sys.stderr)

    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"transcript_{stamp}.md"
    report_text = format_report(segs, cfg["user_name"], date.today())
    write_text_atomic(out_path, report_text)
    print(f"转写完成: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_devices:
        return _list_devices_cmd()
    if args.offline:
        return _offline_cmd(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
