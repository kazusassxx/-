"""阶段 7.2：CLI 参数契约（H-3）。

WHY：--list-devices / --help 必须成功退出（退出码 0）；--offline 指向
不存在的文件必须非零退出——否则脚本化调用无法感知失败。
"""
from pathlib import Path

import pytest

from meeting_transcriber import cli


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--offline" in out and "--list-devices" in out


def test_list_devices_exit_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "list_input_devices",
        lambda: [{"index": 0, "name": "麦克风 (Realtek Audio)", "channels": 2}],
    )
    code = cli.main(["--list-devices"])
    assert code == 0
    assert "麦克风 (Realtek Audio)" in capsys.readouterr().out


def test_offline_missing_file_exits_nonzero(monkeypatch, capsys):
    missing = Path("绝不存在的会议录音.wav")
    code = cli.main(["--offline", str(missing)])
    assert code != 0
    assert "不存在" in capsys.readouterr().err


def test_no_args_prints_help_and_exits_zero(capsys):
    code = cli.main([])
    assert code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "用法" in out
