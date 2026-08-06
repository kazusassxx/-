"""WASAPI loopback 系统音设备解析（系统音修复）。

WHY：旧实现系统音轨打开"输入设备"（实际录的是麦克风），系统播放声音
从未被采集；修复后系统音 = PyAudioWPatch WASAPI loopback 回采，
无效/旧配置（输入设备名）自动回退默认输出对应的 loopback 设备。
"""
import sys
import types

from meeting_transcriber.audio import devices

DEFAULT_OUT = "扬声器 (Realtek(R) Audio)"
LB1 = "扬声器 (Realtek(R) Audio) [Loopback]"
LB2 = "扬声器 (网易虚拟音频设备) [Loopback]"


def _install_pa(monkeypatch, loopbacks, default_out_name=DEFAULT_OUT):
    pa = types.ModuleType("pyaudiowpatch")

    class _PyAudio:
        def __init__(self):
            pass

        def terminate(self):
            pass

        def get_loopback_device_info_generator(self):
            for d in loopbacks:
                yield d

        def get_host_api_info_by_type(self, t):
            return {"defaultOutputDevice": 0}

        def get_device_info_by_index(self, idx):
            return {"name": default_out_name, "index": idx}

    pa.PyAudio = _PyAudio
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", pa)


def _install(monkeypatch, infos, hostapis):
    """mock sounddevice 设备表（mic 设备解析用）。"""
    fake = types.ModuleType("sounddevice")
    fake.query_devices = lambda: infos
    fake.query_hostapis = lambda: hostapis
    fake.default = types.SimpleNamespace(device=(0, 0))
    monkeypatch.setattr(devices, "sd", fake)


def _loopbacks():
    return [
        {"index": 7, "name": LB1, "maxInputChannels": 2, "defaultSampleRate": 48000},
        {"index": 8, "name": LB2, "maxInputChannels": 2, "defaultSampleRate": 48000},
    ]


def test_loopback_device_index_falls_back_to_default(monkeypatch):
    """旧配置存输入设备名/空配置 -> 回退默认输出对应 loopback。"""
    _install_pa(monkeypatch, _loopbacks())

    assert devices.loopback_device_index("Microsoft 声音映射器 - Input") == 7
    assert devices.loopback_device_index("") == 7
    # 有效 loopback 名 / index 入参 -> 原样返回
    assert devices.loopback_device_index(LB1) == 7
    assert devices.loopback_device_index("8") == 8


def test_loopback_device_index_no_devices_returns_none(monkeypatch):
    """完全无 loopback 设备 -> None（GUI 提示系统音轨不可用并降级）。"""
    _install_pa(monkeypatch, [])

    assert devices.loopback_device_index("anything") is None


def test_loopback_device_index_library_missing_returns_none(monkeypatch):
    """PyAudioWPatch 未安装 -> None（不崩溃）。"""
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", None)

    assert devices.loopback_device_index("") is None
    assert devices.list_loopback_devices() == []


def test_mic_device_index_resolves_ambiguous_name_to_mme(monkeypatch):
    """同名设备出现在多个 hostapi（MME/DS/WASAPI）→ 消歧优先 MME。

    WHY：sounddevice 按名字打开会抛 ``Multiple input devices found``
    导致"麦克风轨不可用"；实测 MME 输入有信号，故必须消歧到 MME。
    """
    infos = [
        {"name": "麦克风阵列", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000, "hostapi": 0},
        {"name": "麦克风阵列", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000, "hostapi": 1},
        {"name": "麦克风阵列", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000, "hostapi": 2},
    ]
    hostapis = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}]
    _install(monkeypatch, infos, hostapis)

    assert devices.mic_device_index("麦克风阵列") == 0  # MME 优先
    assert devices.mic_device_index("1") == 1  # index 入参原样
    assert devices.mic_device_index("不存在的设备") is None


def test_list_loopback_devices_enum_failure_returns_empty(monkeypatch):
    """loopback 枚举失败 -> 空列表（不崩溃）。"""

    class _Boom:
        def get_loopback_device_info_generator(self):
            raise RuntimeError("no wasapi")

    pa = types.ModuleType("pyaudiowpatch")
    pa.PyAudio = _Boom
    monkeypatch.setitem(__import__("sys").modules, "pyaudiowpatch", pa)

    assert devices.list_loopback_devices() == []
