# Design: offline-meeting-transcriber

## Architecture Overview
分层单体桌面应用，五层 + 两入口：

```
┌─────────────────────────────────────────────────────────────┐
│ 入口层: gui（PySide6）                      cli（argparse）  │
├─────────────────────────────────────────────────────────────┤
│ pipeline 转写层: pipeline.py 编排（VAD → 聚类/声纹 → ASR →   │
│                 纠错 → 合并 → 格式化），进度回调 + 取消令牌   │
├───────────────────────────────┬─────────────────────────────┤
│ audio 采集层                   │ model 管理层                │
│ devices/capture/resample/mix   │ manager（定位+异步加载）    │
│ import_audio                   │ download（下载脚本）        │
├───────────────────────────────┴─────────────────────────────┤
│ storage 持久化层: config.py / speakers.py / atomicio.py      │
└─────────────────────────────────────────────────────────────┘
```

- **audio 采集层**：设备枚举（平台抽象）、双轨采集（mic + WASAPI loopback）、重采样/单声道、混音落盘、防 OOM spill、外部音频解码导入
- **pipeline 转写层**：纯函数式处理单元（VAD / 聚类 / 声纹提取 / 匹配 / ASR 调用 / 纠错 / 合并 / 格式化）+ 单一编排器，不感知 GUI/CLI
- **model 管理层**：模型定位优先级、异步加载、缺模型报错（零网络）；下载逻辑仅存在于独立脚本与打包脚本
- **storage 层**：config.json / speakers.json / 报告的原子读写，schema 版本化
- **gui 层**：状态机驱动（就绪/录音/转写/完成/导入转写），QThread 承载录音与转写工作线程
- **cli 入口**：`--list-devices` / `--offline` / `--help`，复用 pipeline 与 storage

代码位置：仓库根目录新增 `src/meeting_transcriber/`（与 `.trae/`、`openspec/` 并列，决策④）。

## Module Boundaries

```
src/meeting_transcriber/
├── __init__.py            # __appname__ = "meeting-transcriber", __version__
├── paths.py               # 数据目录 ~/.meeting-transcriber/、config/speakers/models 路径（平台抽象）
├── audio/
│   ├── devices.py         # list_input_devices()（sounddevice；平台抽象）
│   ├── capture.py         # Recorder：mic 轨 + sys 轨并行采集、独立 PCM 缓存、spill
│   ├── resample.py        # to_16k_mono_f32()、声道平均
│   ├── mix.py             # mix_and_save()、防 OOM spill
│   └── import_audio.py    # decode_to_16k_mono()（soundfile）
├── pipeline/
│   ├── vad.py             # EnergyVAD.segment() / merge_adjacent()
│   ├── diarize.py         # Diarizer.segment()（Pyannote ONNX）
│   ├── embedding.py       # extract_embedding()（eres2net，512 维）
│   ├── asr.py             # SenseVoiceASR.transcribe() + clean_output()
│   ├── merge.py           # 双轨时间轴合并、长段二次切分
│   └── pipeline.py        # TranscriptionPipeline.run()（编排 + 进度 + 取消）
├── report/
│   ├── corrections.py     # apply_corrections()（错词=正确词映射）
│   ├── formatter.py       # format_report() —— 单一真相源（E-7）
│   └── atomicio.py        # write_atomic() / write_text_atomic()
├── storage/
│   ├── config.py          # load_config() / save_config()（原子写）
│   └── speakers.py        # SpeakerDB：load/save/register/delete/match（原子写 + 损坏容错）
├── models/
│   ├── manager.py         # ModelManager：resolve_path()/load_async()/status
│   └── download.py        # 下载逻辑（供 scripts/download_models.py 复用）
├── gui/
│   ├── app.py             # QApplication 入口 + 语言检测（QTranslator）
│   ├── state_machine.py   # 就绪/录音/转写/完成/导入转写 状态迁移
│   ├── windows/
│   │   ├── main_window.py # 主窗口（录音态/转写态/完成态 + 发言人面板）
│   │   ├── mini_window.py # 录音小窗（置顶）
│   │   ├── settings_dialog.py  # 四 Tab 设置
│   │   └── name_gate.py   # 首次启动姓名强拦截
│   └── workers.py         # RecordingWorker / TranscriptionWorker（QThread）
└── cli.py                 # argparse 入口
scripts/
├── download_models.py     # 独立下载脚本（代理/镜像回退，幂等）
└── build_windows.ps1      # PyInstaller 单目录打包 + 模型内置 + 压缩分发
tests/                     # pytest（见 tasks.md）
```

## Data Model Changes

### config.json（现有 schema，version:1，保持兼容，不新增字段）
```json
{
  "user_name": "张三",
  "language": "zh",
  "asr_lang": "zh",
  "output_dir": "C:/Users/me/Documents/MeetingTranscripts",
  "num_threads": 4,
  "mic_device": "麦克风 (Realtek Audio)",
  "sys_audio_enabled": true,
  "sys_audio_device": "WASAPI Loopback",
  "sys_mix_gain": 0.9,
  "corrections": ["腾讯会议=腾讯视频会议"],
  "version": 1
}
```
- 写入一律经 `write_atomic()`；解析失败时按默认值合并（`user_name` 缺失 → 触发首次启动姓名拦截），不崩溃。

### speakers.json（现有 schema，version:1）
```json
{
  "version": 1,
  "speakers": [
    {
      "id": "uuid4-hex",
      "name": "张三",
      "embedding": [0.0123, -0.0456, "…共 512 维…"],
      "created_at": "2026-08-05T10:00:00+08:00"
    }
  ]
}
```
- 损坏容错：解析失败 → 原文件改名备份 `speakers.json.corrupt-<UTC时间戳>.bak` → 以空库继续（C-8）。

### Segment（转写管线内部数据模型）
```python
@dataclass(frozen=True)
class Segment:
    start: float          # 秒，时间轴起点
    end: float            # 秒
    track: str            # "mic" | "sys" | "import"
    speaker_ref: str      # "me"（麦克风轨）| 声纹库 id | "speaker_N"（未注册聚类）
    speaker_name: str     # 显示名："我 (张三)" / "张三" / "发言人N"
    text: str             # ASR 纯文本（纠错前）；未转写时为 ""
    skipped: bool         # 静音跳过标记（B-4）
```

### 报告格式（format_report 唯一输出，对应 E-2）
```markdown
# 会议转写报告
生成日期: 2026-08-04

[00:12] 我 (张三) 今天先同步一下进度
[00:18] 发言人1 那部分我来负责
[00:35] 我 (张三) 好，下周复盘
```
- `format_report(segments: list[Segment], user_name: str, generated_at: date) -> str`
- GUI 预览、首次生成、改名重写三处全部调用该函数（E-7）。

### 文件路径约定（对应 §五，`<appname>` = `meeting-transcriber`）
| 数据 | 路径 |
|:---|:---|
| 模型缓存 | `~/.meeting-transcriber/models/`（运行时定位：exe 同级 `./models/` 优先） |
| 用户配置 | `~/.meeting-transcriber/config.json` |
| 声纹数据库 | `~/.meeting-transcriber/speakers.json` |
| 录音文件 | `<output_dir>/record_YYYYMMDD_HHMMSS.wav` |
| 转写报告 | `<output_dir>/transcript_YYYYMMDD_HHMMSS.md` |

## API / Interface Contract（函数签名级）

### audio 层
```python
# audio/devices.py
def list_input_devices() -> list[dict]      # [{index, name, channels, default_samplerate}]

# audio/capture.py
class Recorder:
    def __init__(self, mic_device: str, sys_enabled: bool, sys_device: str) -> None
    def start(self) -> None                  # 启动 mic/sys 双轨采集线程
    def stop(self) -> None
    def mic_samples(self) -> np.ndarray      # 16k mono f32（含 spill 续读）
    def sys_samples(self) -> np.ndarray
    def on_waveform(self, cb: Callable[[dict], None]) -> None   # RMS 节流 ≤50ms

# audio/resample.py
def to_16k_mono_f32(samples: np.ndarray, rate: int, channels: int) -> np.ndarray

# audio/mix.py
def mix_and_save(mic: np.ndarray, sys: np.ndarray,
                 out_path: Path, sys_gain: float = 0.9) -> None   # 16k/16bit/mono WAV

# audio/import_audio.py
def decode_to_16k_mono(path: Path) -> np.ndarray                  # F-2
```

### pipeline 层
```python
# pipeline/vad.py
class EnergyVAD:
    def __init__(self, sr: int = 16000, min_len: float = 4.0,
                 max_len: float = 15.0, merge_gap: float = 1.5) -> None
    def segment(self, samples: np.ndarray) -> list[tuple[float, float]]     # (start, end) 秒

# pipeline/diarize.py
class Diarizer:
    def segment(self, samples: np.ndarray) -> list[tuple[float, float, str]]  # (start, end, label)

# pipeline/embedding.py
def extract_embedding(samples: np.ndarray, sr: int = 16000) -> np.ndarray    # 512 维

# pipeline/asr.py
class SenseVoiceASR:
    def transcribe(self, samples: np.ndarray) -> str      # 返回清洗后纯文本（B-7）
    @staticmethod
    def clean_output(raw: str) -> str                     # 剥离 special token

# pipeline/merge.py
def merge_tracks(mic_segs: list[Segment], sys_segs: list[Segment]) -> list[Segment]  # 时间轴排序（E-1）

# pipeline/pipeline.py
class TranscriptionPipeline:
    def __init__(self, models: ModelManager, config: dict) -> None
    def run(self, samples: np.ndarray, track: str,
            progress: Callable[[float], None] | None = None,
            cancelled: threading.Event) -> list[Segment]    # 编排 VAD/聚类/ASR/纠错（E-5/E-6）
```

### report / storage / models 层
```python
# report/corrections.py
def apply_corrections(text: str, corrections: list[str]) -> str     # "错=正" 逗号分隔

# report/formatter.py
def format_report(segments: list[Segment], user_name: str,
                  generated_at: date) -> str                        # 单一真相源（E-7）

# report/atomicio.py
def write_atomic(path: Path, data: bytes) -> None                   # .tmp + os.replace

# storage/config.py
def load_config() -> dict                                           # 缺失/损坏→默认值
def save_config(cfg: dict) -> None                                  # 原子写

# storage/speakers.py
class SpeakerDB:
    @classmethod
    def load(cls, path: Path) -> "SpeakerDB"                        # 损坏→备份+空库（C-8）
    def save(self) -> None                                          # 原子写（P4）
    def register(self, name: str, embedding: np.ndarray) -> str     # 返回 id（C-5）
    def delete(self, speaker_id: str) -> None                       # C-6
    def match(self, embedding: np.ndarray, threshold: float = 0.65) -> str | None  # 返回姓名或 None（C-4）

# models/manager.py
class ModelManager:
    def resolve_path(self, key: str) -> Path                        # ./models/ → ~/.models/ 优先级
    def load_async(self, progress_cb) -> None                       # 后台线程加载（B-6）
    @property
    def status(self) -> str                                         # "loading" | "ready" | "error"
```

### CLI 入口
```
meeting-transcriber --list-devices
meeting-transcriber --offline <file> [--name 姓名] [--lang zh|en|ja|auto] [--threads N]
meeting-transcriber --help
```

## Concurrency Model
- **录音线程**（`RecordingWorker`，QThread）：纯采集 + 混音落盘 + 波形节流推送（≤50ms）。与转写线程零共享可变状态——停录瞬间以不可变 `np.ndarray` 快照交接 PCM（§8.3 解耦要求）。
- **转写线程**（`TranscriptionWorker`，QThread）：消费录音快照 / 导入音频，跑 pipeline；通过 `progress` 回调与 `cancelled` 事件与 GUI 通信；模型未就绪时挂起任务等待（F-4）。
- **模型加载**：`ModelManager.load_async()` 后台加载三个 sherpa-onnx 模型；状态（loading/ready/error）经 Qt 信号广播，GUI 显示模型状态指示（G-14）；加载完成触发挂起的转写任务自动续转（P3）。
- **取消语义**：`cancelled` Event 在段边界检查；取消后不产出报告，GUI 静默回就绪态（E-6）。
- **防 OOM**：双轨 PCM 独立缓存；任一轨单路失衡超 5s 即 spill 到临时文件，停录后续读（§4.2）。

## Atomic Write Strategy
- 统一 `write_atomic(path, data)`：同目录写 `path.tmp` → 写入并 `flush` + `os.fsync` → `os.replace` 原子替换 → 失败清理 `.tmp`。
- 适用对象：config.json、speakers.json、transcript_*.md（E-4/P4）。
- 报告/配置写入失败不静默吞掉：GUI 给出可读错误，不残留半截文件。

## Migration Strategy
- 现有 config.json / speakers.json 均为 version:1，新功能不加字段即兼容，仅新增字段时按缺省值合并写入。
- speakers.json 未来模型升级（如向量维度变化）时，靠 `version` 字段触发迁移逻辑（C-7），本轮不引入迁移代码，仅保留版本校验。
- 代码仓库内既有 `src/user_registration.py`（前序项目残留）与本 feature 无关，不修改、不影响本 proposal 交付。

## Key Design Decisions
| # | 决策 | 依据 |
|:---:|:---|:---|
| 1 | Pyannote 分割模型经下载脚本获取、sherpa-onnx 加载 | 决策①：GUI 零网络，模型缺失时明确报错 |
| 2 | 录音线程与推理线程完全解耦 | P2/P3：录音零推理、模型未就绪也能先录 |
| 3 | 报告格式化单一真相源 `format_report()` | E-7：GUI 预览/生成/改名重写三处复用 |
| 4 | 全量原子写 | P4：config/speakers/报告均 .tmp + rename |
| 5 | 声纹损坏容错（备份 + 空库继续） | C-8：可用性优先，生物特征数据防损坏阻断 |
| 6 | 运行时模型定位 ./models/ → ~/.models/ | §4.4：打包版内置优先，开发态复用缓存 |
