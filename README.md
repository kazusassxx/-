# Basic

基于 Trae AI IDE 的全栈工程师 Agent 协作项目，集成需求拷问（Grill-me）、领域规格定义（OpenSpec）、TDD 驱动（Superpowers）和代码图谱分析（code-review-graph）的完整工程闭环。

## 快速开始

```bash
git clone <repo-url>
cd basic
```

在 Trae IDE 中打开此项目，Agent 将自动遵循 `.trae/rules/AGENTS.md` 中的规范。

## 开发流程

### 轻重分流

收到任何开发请求时，Agent 首先判定任务类型：

| 类型 | 流程 | 耗时 |
|------|------|------|
| **轻量**（文案/样式/单文件 <30行） | 意图确认 → 外科手术修改 → 验证 → Commit | 分钟级 |
| **重度**（新功能/模块变更/跨层改动） | Grill → OpenSpec → TDD → Archive | 小时级 |

### 重度流程 4 卡口（Subagent 自动调度）

1. **Grill-me** — `@requirement-griller` 高压逼问所有隐含假设与边缘场景
2. **OpenSpec** — `@spec-writer` 输出 `propose.md` + specs + design + tasks
3. **Superpowers** — `@tdd-implementer` RED-GREEN-REFACTOR TDD 循环驱动实施
4. **Code Review** — `@code-reviewer` 基于 code-review-graph 图谱审查变更影响面

详见 [DEVELOPMENT_SOP.md](DEVELOPMENT_SOP.md)。

## 工具链

| 工具 | 类型 | 用途 |
|------|------|------|
| AGENTS.md | Rule | 全局纪律、分流路由、4卡口流程 |
| requirement-griller | Subagent | 需求拷问卡口 |
| spec-writer | Subagent | 领域规格定义 |
| tdd-implementer | Subagent | TDD 驱动实施 |
| code-reviewer | Subagent | 代码审查（图谱驱动） |
| grill-me / openspec / superpowers | Skill | 各卡口操作手册 |
| code-review-graph | MCP | 代码符号图谱与 blast radius 分析 |

## 项目结构

```
.
├── .trae/                          # Agent 协作配置
│   ├── rules/AGENTS.md             # Agent 全局行为规范
│   ├── agents/                     # 可复用 Subagent（重度流程 4 卡口）
│   │   ├── requirement-griller.md
│   │   ├── spec-writer.md
│   │   ├── tdd-implementer.md
│   │   └── code-reviewer.md
│   ├── skills/                     # Skill 定义
│   │   ├── grill-me/SKILL.md
│   │   ├── openspec/SKILL.md
│   │   └── superpowers/SKILL.md
│   └── mcp.json                    # 项目级 MCP 配置
├── openspec/
│   └── proposals/archive/          # 已完成并归档的规格提案
├── scripts/                        # 工具脚本
│   ├── download_models.py          # 模型下载（SenseVoice / eres2net / Pyannote）
│   └── build_windows.ps1           # Windows 打包（PyInstaller onedir + 模型内置）
├── src/meeting_transcriber/        # 产品源码
│   ├── audio/                      # 音频层
│   │   ├── capture.py              #   双轨采集（mic + WASAPI loopback）+ 波形包络
│   │   ├── devices.py              #   设备枚举与消歧（多 hostapi 同名）
│   │   ├── resample.py             #   重采样到 16kHz 单声道
│   │   ├── mix.py                  #   双轨混音（系统音衰减）
│   │   └── import_audio.py         #   外部音频解码
│   ├── pipeline/                   # 转写管线
│   │   ├── vad.py                  #   能量 VAD 断句
│   │   ├── diarize.py              #   Pyannote 说话人分割
│   │   ├── embedding.py            #   512 维声纹提取
│   │   ├── asr.py                  #   SenseVoice 离线识别
│   │   ├── merge.py                #   短段合并 / 长段切分
│   │   ├── segment.py              #   段落模型
│   │   └── pipeline.py             #   编排：VAD→聚类→ASR→声纹匹配
│   ├── report/                     # 报告输出
│   │   ├── formatter.py            #   分角色 Markdown（单一真相源）
│   │   ├── corrections.py          #   名词纠错映射
│   │   └── atomicio.py             #   原子写
│   ├── storage/                    # 持久化
│   │   ├── config.py               #   用户配置（原子写）
│   │   └── speakers.py             #   声纹库（版本化 / 损坏容错）
│   ├── gui/                        # 桌面 GUI（PySide6）
│   │   ├── app.py                  #   应用入口
│   │   ├── state_machine.py        #   四状态机
│   │   ├── workers.py              #   录音 / 转写工作线程
│   │   └── windows/                #   主窗 / 小窗 / 波形 / 设置 / 姓名拦截
│   ├── cli.py                      # 命令行入口（--offline / --list-devices）
│   └── paths.py                    # 数据路径约定
├── tests/                          # 150 项测试（合成数据 + mock，不触真实数据）
├── pyproject.toml                  # 项目元数据与依赖（PEP 621）
├── LICENSE                         # MIT 开源协议
├── README.md                       # 本文件
├── 产品介绍.md                      # 产品介绍文档
├── 离线会议转写工具开发任务说明书.md   # 开发任务规格书
└── DEVELOPMENT_SOP.md              # 开发流程规范
```

## 文档索引

| 文档 | 说明 |
|------|------|
| [产品介绍.md](产品介绍.md) | 产品定位、功能特性、架构与隐私承诺（面向使用者） |
| [离线会议转写工具开发任务说明书.md](离线会议转写工具开发任务说明书.md) | 完整需求规格 A~H 与验收标准（面向开发者） |
| [DEVELOPMENT_SOP.md](DEVELOPMENT_SOP.md) | Agent 开发流程操作规范 |

## Meeting Transcriber（离线会议转写工具）

纯离线双轨会议转写桌面工具：麦克风 + 系统音频双轨录音，停录后自动完成声纹分角色 + SenseVoice 转写，输出分角色 Markdown 会议纪要。全程脱网，数据不出本机。

### 数据与隐私

- 用户数据目录：`~/.meeting-transcriber/`（config.json / speakers.json / 模型缓存）
- 模型文件不入库，由下载脚本获取；敏感数据（声纹/录音/姓名）已被 `.gitignore` 排除。

### 安装与开发

```bash
# Python 3.12.10
pip install -e ".[dev]"          # 安装运行时依赖 + pytest
python scripts/download_models.py  # 下载三个模型（SenseVoice / eres2net / Pyannote）
```

### 运行

```bash
meeting-transcriber --list-devices          # 枚举输入设备
meeting-transcriber --offline input.wav --name 张三 --lang zh --threads 4  # 离线转写
meeting-transcriber --help
```

#### 桌面 GUI

```bash
python -m meeting_transcriber.gui.app      # 启动图形界面
```

- 首次启动强制输入姓名（写入 `~/.meeting-transcriber/config.json`）
- 界面语言自动跟随系统（中/英/日），可在「设置 → 常规」手动切换
- 录音后自动缩为右上角置顶小窗；停录进入转写，完成后可预览报告、命名/注册发言人声纹
- 支持导入 WAV/M4A/MP3/AAC/FLAC 离线转写
- 模型缺失时界面显示错误并提供重试；GUI 运行全程零网络请求

### 打包（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# 模型缺失时脚本会自动调用 scripts/download_models.py；产物 zip 位于 dist/
```

- PyInstaller 单目录打包，入口 `gui/app.py`；`sherpa_onnx`/`soundfile` 全量收集
- 模型内置到 exe 同级 `./models/`（运行时定位：exe 同级优先，回退 `~/.meeting-transcriber/models/`）
- `-SkipModels` 跳过模型内置；`-Version` 自定义 zip 版本号

### 测试

```bash
python -m pytest tests/ -v
```

（测试使用合成数据与 mock，不触碰用户真实数据目录；可用环境变量 `MEETING_TRANSCRIBER_HOME` 指向临时数据目录。GUI 层测试在 Qt offscreen 平台运行。）

