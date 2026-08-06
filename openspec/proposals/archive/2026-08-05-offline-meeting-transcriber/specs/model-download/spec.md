## ADDED Requirements

### Requirement: Standalone Download Script
The system SHALL provide a standalone model download script (not built into the GUI) that fetches the SenseVoice, eres2net, and Pyannote models.

需求含义（§4.4）：提供独立的模型下载脚本（`scripts/download_models.py`，非 GUI 内置），下载 SenseVoice ASR / 3D-Speaker eres2net 声纹提取 / Pyannote 说话人分割三个模型到默认缓存路径；模型文件不入库，README 注明获取方式。

#### Scenario: Download all three models to the cache
- **WHEN** the user runs the download script
- **THEN** the SenseVoice, eres2net, and Pyannote models are fetched into `~/.<appname>/models/`, with already-present files skipped (idempotent)

### Requirement: Proxy and Mirror Fallback
The system SHALL support proxy configuration and mirror fallback in the download script.

需求含义（§4.4）：下载脚本支持代理（环境变量/参数配置）与镜像回退（主源失败自动切换镜像源），保证模型在受限网络下可获取。

#### Scenario: Primary source fails and mirror is used
- **WHEN** the primary download source is unreachable
- **THEN** the script falls back to a mirror source and still completes the download

#### Scenario: Proxy is honored
- **WHEN** the user configures a proxy
- **THEN** the download requests are routed through the proxy

### Requirement: Automatic Download During Packaging
The system SHALL have the packaging script detect missing model caches and automatically invoke the download script.

需求含义（§4.4）：Windows 打包脚本（`scripts/build_windows.ps1`）检测模型缓存缺失时自动调用下载脚本，并将模型内置到分发包 exe 同级 `./models/`，保证双击即用。

#### Scenario: Packaging bundles models automatically
- **WHEN** the Windows build script runs and a model cache is missing
- **THEN** the script invokes the download script automatically, then bundles all models into the distribution's `./models/` directory

#### Scenario: Packaged app ships with bundled models
- **WHEN** the packaged distribution is unpacked
- **THEN** all required models are present next to the exe, so the app works with zero network access

### Requirement: Model Cache Path Convention
The system SHALL use `~/.<appname>/models/` as the default model cache path.

需求含义（§4.4/§五）：模型默认缓存路径为 `~/.meeting-transcriber/models/`（开发态预下载 / 打包时内置），与配置、声纹库同属应用数据目录。

#### Scenario: Models resolve to the home cache by default
- **WHEN** the app looks up a model in a development environment
- **THEN** it finds it under `~/.meeting-transcriber/models/`

### Requirement: Runtime Model Resolution Priority
The system SHALL resolve models at runtime in this priority order: `./models/` next to the exe first, then `~/.<appname>/models/`.

需求含义（§4.4）：运行时模型定位优先级：exe 同级 `./models/`（打包版内置）→ 用户 Home `~/.<appname>/models/`（开发态缓存）；打包版内置优先，开发态复用缓存。

#### Scenario: Bundled models next to the exe win
- **WHEN** the packaged app runs and `./models/` exists next to the exe
- **THEN** those models are used with priority over the home cache

#### Scenario: Fallback to the home cache
- **WHEN** `./models/` is absent (e.g. development)
- **THEN** the app resolves models from `~/.<appname>/models/` instead

### Requirement: Zero Network Error on Missing Models
The system SHALL report an explicit error when a required model is missing at runtime, and SHALL never attempt to download models over the network from the app.

需求含义（§4.4/P1）：运行时缺模型直接报错并引导用户运行下载脚本，绝不静默联网下载——GUI 零网络是强制契约；下载逻辑仅存在于独立脚本与打包脚本。

#### Scenario: Missing model produces an explicit offline error
- **WHEN** a required model cannot be found at either resolution path
- **THEN** the app reports a readable error telling the user to run the download script, and makes zero network requests
