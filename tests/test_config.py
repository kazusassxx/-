"""阶段 5.6：config 持久化容错（G-9）。

WHY：配置文件损坏/缺失不能阻断启动——回退默认值合并继续运行；
保存后重启必须能恢复用户设置，否则每次启动都重置。
"""
import json

from meeting_transcriber.storage.config import load_config, save_config


def test_corrupt_config_falls_back_to_defaults(monkeypatch, tmp_path):
    d = tmp_path / "home"
    d.mkdir(parents=True)
    (d / "config.json").write_text("{ not valid json !!!", encoding="utf-8")
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(d))

    cfg = load_config()

    assert cfg["user_name"] == ""  # 缺失 → 触发首次启动姓名拦截
    assert cfg["version"] == 1
    assert cfg["num_threads"] == 4
    assert cfg["sys_mix_gain"] == 0.9


def test_missing_config_returns_defaults(monkeypatch, tmp_path):
    d = tmp_path / "home"
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(d))

    cfg = load_config()

    assert cfg["language"] == "zh"
    assert cfg["corrections"] == []


def test_save_then_reload_restores_user_values(monkeypatch, tmp_path):
    d = tmp_path / "home"
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(d))

    save_config(
        {
            "user_name": "张三",
            "num_threads": 2,
            "corrections": ["腾讯会议=腾讯视频会议"],
        }
    )

    cfg = load_config()  # 模拟重启后重新加载
    assert cfg["user_name"] == "张三"
    assert cfg["num_threads"] == 2
    assert cfg["corrections"] == ["腾讯会议=腾讯视频会议"]
    # 未提供字段回填默认值，schema 完整
    assert cfg["version"] == 1
    assert cfg["sys_audio_enabled"] is True


def test_saved_file_is_plain_json_with_version(monkeypatch, tmp_path):
    d = tmp_path / "home"
    monkeypatch.setenv("MEETING_TRANSCRIBER_HOME", str(d))

    save_config({"user_name": "李四"})

    raw = json.loads((d / "config.json").read_text(encoding="utf-8"))
    assert raw["user_name"] == "李四"
    assert raw["version"] == 1
