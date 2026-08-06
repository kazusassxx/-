# offline-meeting-transcriber

## Purpose
从零实现一款**纯离线**的双轨会议转写桌面工具（Windows 为首要交付平台）：同时录制麦克风与系统音频，停录后自动完成声纹分角色 + 语音转写，输出分角色 Markdown 会议纪要。全程脱网，数据不出本机。

## Scope

### In Scope
- **双轨录音**：麦克风采集 + Windows WASAPI Loopback 系统音捕获，时间轴对齐混音落盘（16kHz/16bit/单声道 WAV）
- **离线转写管线**：能量 VAD 断句 → Pyannote 声纹聚类分割（sherpa-onnx 加载）→ 512 维声纹提取（3D-Speaker eres2net）→ 余弦匹配本地声纹库 → SenseVoice 逐段 ASR → 名词纠错 → 双轨时间轴合并 → 分角色 Markdown 报告
- **声纹库**：本地 `~/.meeting-transcriber/speakers.json`（带版本号、原子写、损坏容错），支持注册/删除/自动识别
- **配置持久化**：`~/.meeting-transcriber/config.json`（version:1 现有 schema），首次启动强制用户名
- **桌面 GUI**：PySide6 主界面（录音态/转写态/完成态）+ 录音小窗置顶模式 + 设置面板（常规/音频/高级纠错/声纹管理）+ 多语言（中/英/日）
- **导入音频转写**：WAV/MP3/FLAC 解码重采样后统一走声纹聚类管线
- **CLI 模式**：`--list-devices` / `--offline <file>` / `--help`
- **模型管理**：独立下载脚本（代理、镜像回退）；打包脚本检测模型缺失自动调用下载；运行时模型定位 `./models/` → `~/.meeting-transcriber/models/`
- **打包交付**：PyInstaller 单目录 + 模型内置 + 压缩分发；GitHub 公开仓库（License + .gitignore 排除敏感数据与模型 + README）

### Out of Scope
- 联网功能：无云端同步、无在线翻译、无在线模型下载（GUI 运行时零网络）
- 实时字幕/实时转写（录音期间不做任何 AI 推理）
- 会议录音文件的云端存储与分享
- 通话软件内置集成（如 Teams/Zoom 插件化）
- 手机端 / Web 端
- 视频会议录制与画面分析
- 导入音频中分离本端/他端（导入音频统一按多人混合录音处理，无 mic/sys 物理分离）

## Background
- 需求来源：《离线会议转写工具开发任务说明书》（仓库根目录），产品行为与功能规格见其 §三 A–H、非功能需求 §四、数据路径约定 §五。
- 已确认约束（Grill-me 产物）：技术栈 Python 3.12.10 + sherpa-onnx 1.13.4（ASR=SenseVoice ONNX、声纹提取=3D-Speaker eres2net ONNX、说话人分割=Pyannote ONNX）+ PySide6 6.11.1 + sounddevice/PyAudioWPatch（WASAPI loopback）+ soundfile + numpy；appname=`meeting-transcriber`。
- 模型缓存现状：ASR 与声纹模型已存在于 `~/.meeting-transcriber/models/`；**Pyannote 分割模型缺失，需下载脚本获取**。
- 决策①：声纹分割采用下载 Pyannote 分割模型、sherpa-onnx 加载，GUI 运行零网络。
- 决策④：代码放当前仓库根目录（新增 `src/` 等，与 `.trae/`、`openspec/` 并列）。

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pyannote 分割模型缺失且下载源不可达 | 系统音轨无法分角色 | 下载脚本支持代理与镜像回退；模型缺失时明确报错并引导下载，绝不静默联网 |
| WASAPI Loopback 在部分声卡/驱动上不可用或无声 | 系统音轨空采 | 提供系统音开关与设备选择；录音前可先试听/电平显示；异常时降级仅麦克风轨并提示 |
| 长会议录音内存堆积 OOM | 录音崩溃丢数据 | 双轨分轨缓存 + 单路失衡超 5s 直写磁盘 spill，混音落盘后释放 |
| 声纹库损坏/版本不兼容 | 应用启动崩溃、声纹丢失 | 解析失败自动备份原文件（带损坏时间戳）并以空库继续；版本号字段留迁移空间 |
| 模型未就绪即停录 | 转写卡死或丢任务 | 转写任务挂起，模型就绪后自动续转（P3 解耦原则） |
| 报告/配置文件写盘中断 | 半截文件、配置丢失 | 全量原子写（临时文件 + rename），含 config/speakers/报告 |
| 打包后模型路径找不到 | 双击启动即报错 | 运行时模型定位优先级：exe 同级 `./models/` → `~/.meeting-transcriber/models/`；打包脚本自动内置并校验 |
| 敏感数据（声纹/录音/姓名/绝对路径）误入公开仓库 | 隐私事故且难彻底清除 | .gitignore 强制排除；模型不入库（下载脚本获取）；README 明示 |
| ASR 输出夹带 special token | 报告含噪声标签 | 输出清洗层统一剥离语言/情绪/XML 标签 |

## Dependencies
- **运行时依赖（Python 3.12.10）**：sherpa-onnx 1.13.4、PySide6 6.11.1、sounddevice、PyAudioWPatch、soundfile、numpy
- **模型（下载脚本获取，GUI 运行时零网络）**：
  - ASR：SenseVoice ONNX（已缓存 `~/.meeting-transcriber/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/`）
  - 声纹提取：3D-Speaker eres2net ONNX（已缓存 `~/.meeting-transcriber/models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx`）
  - 说话人分割：Pyannote ONNX（**缺失，需下载脚本获取**）
- **平台**：Windows（首要交付，WASAPI Loopback）；macOS/Linux 预留扩展
- **构建**：PyInstaller（单目录打包）；pytest（单元测试）
- **仓库**：GitHub 公开仓库 + MIT License + .gitignore + README
