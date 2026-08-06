## ADDED Requirements

### Requirement: Cross-platform Desktop GUI
The system SHALL provide a native cross-platform desktop GUI (macOS / Windows / Linux), with Windows as the primary delivery target.

需求含义（G-1）：跨平台原生桌面应用，Windows 为首要交付平台（WASAPI Loopback 系统音），音频采集、文件路径、系统字体等做平台抽象，预留 macOS / Linux 移植能力。

#### Scenario: App launches as a native desktop window
- **WHEN** the packaged app is started by double-clicking
- **THEN** a native desktop window opens with no external dependencies or network access

### Requirement: First-launch User Name Gate
The system SHALL force the user to enter their name on first launch before entering the main window (used to label "我").

需求含义（G-2）：首次打开必须输入使用者姓名才能进入主界面（config 无 `user_name` 时触发），用于在报告中标记麦克风轨"我 (姓名)"；姓名持久化后不再重复拦截。

#### Scenario: First launch blocks the main window until a name is given
- **WHEN** the app starts with no saved user name
- **THEN** a name gate is shown and the main window stays locked until the user enters and confirms their name

#### Scenario: Returning users skip the gate
- **WHEN** the app starts with a persisted user name
- **THEN** the gate is skipped and the main window opens directly

### Requirement: Recording State
The system SHALL show, in the recording state: start/stop buttons, real-time dual-track waveforms (mic + system), and a recording duration timer.

需求含义（G-3）：主界面录音态显示开始/停止录音按钮、双轨实时波形（麦克风 + 系统音）、录音时长计时；波形 RMS 更新节流 ≤ 50ms，不堆积不卡顿。

#### Scenario: Recording UI shows controls, waveforms, and timer
- **WHEN** recording is active
- **THEN** the GUI shows the stop button, dual-track live waveforms, and an updating duration timer

### Requirement: Transcription State
The system SHALL show, in the transcription state: a progress percentage plus spinner, and a cancel button; the record button is disabled to prevent misoperation.

需求含义（G-4）：主界面转写态显示转写进度百分比 + spinner、取消按钮；禁用录音按钮防误操作。

#### Scenario: Transcription UI with disabled record button
- **WHEN** transcription is running
- **THEN** the GUI shows progress percentage, spinner, and a cancel button, while the record button is disabled

### Requirement: Completion State
The system SHALL show, in the completion state: a transcript preview and an "open file" button that locates the output directory in the system file manager.

需求含义（G-5）：主界面完成态显示转写文本预览与"打开文件"按钮（在系统文件管理器中定位输出目录）。

#### Scenario: Completed transcription shows preview and open-file
- **WHEN** transcription finishes
- **THEN** the GUI shows the transcript preview and an "open file" button that opens the output directory in the system file manager

### Requirement: Recording Mini Window
The system SHALL shrink to a top-right always-on-top mini window (stop button + waveform only) when recording starts, and restore the full window after stop/transcription.

需求含义（G-6）：开始录音后自动缩为屏幕右上角置顶小窗（仅停止键 + 波形），停录/转写后恢复完整窗口，便于录音期间操作其他应用。

#### Scenario: Recording switches to the pinned mini window
- **WHEN** recording starts
- **THEN** the GUI shrinks to a top-right always-on-top mini window showing only the stop button and waveform

#### Scenario: Mini window restores after stop
- **WHEN** recording stops (or transcription completes)
- **THEN** the full main window is restored

### Requirement: Settings Dialog
The system SHALL provide a tabbed settings page: General (name, language, output dir, inference threads), Audio (mic selection, system audio switch), Advanced corrections (term mapping), and Speaker management (register/delete).

需求含义（G-7）：设置页面分 Tab：常规（姓名、语言、输出目录、推理线程数）、音频（麦克风选择、系统音开关）、高级纠错（名词映射）、声纹管理（注册/删除）；修改持久化到 config。

#### Scenario: Four tabs persist their settings
- **WHEN** the user edits settings in any of the four tabs (General / Audio / Advanced corrections / Speaker management) and confirms
- **THEN** the changes are persisted to the local config, and speaker management operates on the voiceprint database

### Requirement: Multi-language UI
The system SHALL support at least Chinese, English, and Japanese UI languages, auto-detecting the system language.

需求含义（G-8）：界面至少支持中文、英文、日文三种语言，启动时自动检测系统语言并应用对应翻译（QTranslator），语言可在设置中切换并持久化。

#### Scenario: UI language auto-detects from the system
- **WHEN** the app starts
- **THEN** the UI language is chosen from the system locale among zh / en / ja

#### Scenario: UI language is switchable and persisted
- **WHEN** the user switches the language in settings
- **THEN** the whole UI immediately reflects the new language, and the choice is restored on next launch

### Requirement: Configuration Persistence
The system SHALL save all user settings (name, language, device selection, thread count, output dir, etc.) to the local config file and restore them on next launch.

需求含义（G-9）：所有用户设置保存到 `~/.meeting-transcriber/config.json`，下次启动自动恢复；写入一律原子写，解析失败时按默认值合并（user_name 缺失 → 触发首次启动姓名拦截），不崩溃。

#### Scenario: Settings survive restart
- **WHEN** the user changes settings and restarts the app
- **THEN** all saved settings are restored from the local config file

#### Scenario: Corrupted config falls back to defaults
- **WHEN** `config.json` fails to parse
- **THEN** the app merges defaults and continues, and a missing `user_name` re-triggers the first-launch name gate instead of crashing

### Requirement: CJK Font Support
The system SHALL load system CJK fonts across platforms to fully avoid CJK mojibake.

需求含义（G-10）：跨平台加载系统中文字体，彻底解决 CJK 乱码问题；字体加载做平台抽象。

#### Scenario: CJK text renders correctly
- **WHEN** the UI displays Chinese/Japanese text
- **THEN** system CJK fonts are loaded and all characters render without mojibake

### Requirement: Audio Import Button
The system SHALL provide an "import audio for transcription" button on the main window that opens a file picker dialog.

需求含义（G-11）：主界面提供"导入音频转写"按钮，弹出文件选择对话框（支持 WAV/MP3/FLAC），导入后进入转写态。

#### Scenario: Import audio via the file dialog
- **WHEN** the user clicks the import button and picks a supported audio file
- **THEN** a file dialog opens, the file is accepted, and the app enters the import-transcription flow

### Requirement: Speaker Panel
The system SHALL show, after transcription completes, a left panel listing the speakers detected in this session, each with the ability to be named/renamed and registered as a voiceprint.

需求含义（G-12）：转写完成后左栏显示本场检测到的发言人列表，可为每个人命名/改名并注册声纹到本地库。

#### Scenario: Name and register a detected speaker
- **WHEN** the user names a detected speaker in the left panel
- **THEN** the speaker's voiceprint is registered to the local database and the panel reflects the new name

### Requirement: Immediate Rename Effect
The system SHALL refresh the transcript preview and the MD file immediately when a speaker is renamed, supporting repeated renames.

需求含义（G-13）：给发言人改名后立即刷新转写文本预览和 MD 文件（支持多次重命名），重写复用同一格式化函数（E-7），保证一致性。

#### Scenario: Renaming a speaker rewrites preview and MD at once
- **WHEN** the user renames a speaker
- **THEN** the preview and the MD file are immediately rewritten with the new name, and repeated renames keep working

### Requirement: Model Status Indicator
The system SHALL display the inference engine status (ready / loading / error) on the main window, with a retry button on error.

需求含义（G-14）：主界面显示推理引擎就绪/加载中/错误状态，错误时提供重试按钮（重新触发 `load_async`）；状态经 Qt 信号广播。

#### Scenario: Loading and ready states are shown
- **WHEN** models are loading or ready
- **THEN** the main window shows the corresponding status indicator

#### Scenario: Error state offers a retry button
- **WHEN** model loading fails (e.g. missing model files)
- **THEN** the GUI shows an error status with a retry button that re-triggers loading

### Requirement: Zero Network Contract
The system SHALL make no network requests while the GUI is running — models must be bundled at packaging time or pre-cached in development; a missing model reports an error and never silently downloads.

需求含义（P1，零网络强制契约）：GUI 运行时严禁发起任何网络请求（可通过抓包/防火墙验证）；所有模型在打包时内置或开发态预先缓存，运行时缺模型直接报错，绝不静默联网下载。下载逻辑仅存在于独立脚本与打包脚本。

#### Scenario: No network traffic while the GUI runs
- **WHEN** the GUI is running in any state (recording, transcribing, idle)
- **THEN** zero network requests are made, verifiable by packet capture

#### Scenario: Missing model never triggers silent download
- **WHEN** a required model is absent at runtime
- **THEN** the GUI reports an explicit model error pointing to the download script, with no network attempt
