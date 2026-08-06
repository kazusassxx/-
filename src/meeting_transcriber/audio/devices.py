"""音频设备枚举（sounddevice + pyaudiowpatch，平台抽象）。

- ``list_input_devices``：麦克风等输入设备（sounddevice）。
- ``list_loopback_devices``：WASAPI loopback 设备（PyAudioWPatch），
  系统音回采专用；名字形如 "扬声器 (Realtek(R) Audio) [Loopback]"。
- ``loopback_device_index``：系统音设备解析；无效/空配置自动回退
  默认输出的 loopback 设备。
"""
from __future__ import annotations

import sounddevice as sd


def list_input_devices() -> list[dict]:
    """枚举可用的输入设备。

    返回: ``[{index, name, channels, default_samplerate, hostapi}]``，仅含
    ``max_input_channels > 0`` 的设备；枚举失败时返回空列表（不崩溃）。
    """
    return _list_devices(max_channels_key="max_input_channels")


def mic_device_index(name: str) -> int | None:
    """麦克风设备解析：返回唯一的 sounddevice index。

    WHY：同一设备名常出现在多个 hostapi（MME/DirectSound/WASAPI），
    sounddevice 按名字打开会抛 ``ValueError: Multiple input devices found``
    导致麦克风轨不可用；实测本机 MME 输入有信号、WASAPI 输入采不到数据，
    故多匹配时优先 MME，保证开箱可用。
    """
    ins = list_input_devices()
    if not ins:
        return None
    if name:
        try:
            idx = int(name)
            for d in ins:
                if d["index"] == idx:
                    return idx
            return None
        except (TypeError, ValueError):
            matches = [d for d in ins if d["name"] == name]
            if not matches:
                return None
            if len(matches) == 1:
                return matches[0]["index"]
            # 多 hostapi 同名：优先 MME（实测有信号），否则取第一个
            for d in matches:
                if d["hostapi"] == "MME":
                    return d["index"]
            return matches[0]["index"]
    # 空配置：返回默认输入设备 index（sounddevice 的 default.device[0]）
    try:
        return int(sd.default.device[0])
    except (TypeError, ValueError, Exception):  # noqa: BLE001
        return None


def _list_devices(max_channels_key: str) -> list[dict]:
    devices: list[dict] = []
    try:
        infos = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:
        return devices
    hostapi_names = {i: h.get("name", "") for i, h in enumerate(hostapis)}
    for idx, info in enumerate(infos):
        max_ch = int(info.get(max_channels_key) or 0)
        if max_ch <= 0:
            continue
        devices.append(
            {
                "index": idx,
                "name": info.get("name", ""),
                "channels": max_ch,
                "default_samplerate": float(info.get("default_samplerate") or 0),
                "hostapi": hostapi_names.get(info.get("hostapi", -1), ""),
            }
        )
    return devices


def list_loopback_devices() -> list[dict]:
    """枚举 WASAPI loopback 设备（PyAudioWPatch）。

    返回: ``[{index, name, channels, default_samplerate}]``；库缺失/枚举
    失败时返回空列表（不崩溃）。
    """
    try:
        import pyaudiowpatch as pyaudio
    except Exception:
        return []
    try:
        p = pyaudio.PyAudio()
    except Exception:
        return []
    out: list[dict] = []
    try:
        for dev in p.get_loopback_device_info_generator():
            out.append(
                {
                    "index": int(dev.get("index", -1)),
                    "name": dev.get("name", ""),
                    "channels": int(dev.get("maxInputChannels") or 0),
                    "default_samplerate": float(dev.get("defaultSampleRate") or 0),
                }
            )
    except Exception:
        out = []
    finally:
        try:
            p.terminate()
        except Exception:
            pass
    return out


def loopback_device_index(name: str) -> int | None:
    """系统音回采设备解析：返回可用 loopback 设备的 PyAudioWPatch index。

    WHY：旧配置存的可能是输入设备名（如 "Microsoft 声音映射器 - Input"），
    直接打开必失败；本函数将无效/空配置重定向到默认输出的 loopback 设备
    （开箱即可回采系统播放声音）。无任何 loopback 设备 → None（GUI 提示
    "系统音轨不可用"并降级，不整条转写报错）。
    """
    devs = list_loopback_devices()
    if not devs:
        return None
    if name:
        try:
            idx = int(name)
            for d in devs:
                if d["index"] == idx:
                    return idx
        except (TypeError, ValueError):
            for d in devs:
                if d["name"] == name:
                    return d["index"]
    # 默认回退：默认输出设备对应的 loopback（名字含默认输出名）
    try:
        import pyaudiowpatch as pyaudio

        p = pyaudio.PyAudio()
        try:
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
            default_name = default_out.get("name", "")
            for d in devs:
                if default_name and default_name in d["name"]:
                    return d["index"]
        finally:
            p.terminate()
    except Exception:
        pass
    return devs[0]["index"] if devs else None
