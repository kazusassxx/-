## ADDED Requirements

### Requirement: Device Listing
The system SHALL provide a `--list-devices` CLI flag that lists all available audio input devices.

需求含义（H-1）：命令行 `--list-devices` 列出所有可用音频输入设备（索引、名称、声道数、默认采样率），复用 GUI 相同的设备枚举逻辑。

#### Scenario: List input devices from the CLI
- **WHEN** the user runs `meeting-transcriber --list-devices`
- **THEN** all available audio input devices are printed and the process exits with code 0

### Requirement: Offline Transcription Mode
The system SHALL provide `--offline <音频文件> [--name <名>] [--lang zh|en|ja|auto] [--threads N]` to run the full transcription pipeline (VAD/diarization/ASR) on an existing audio file and output a Markdown report.

需求含义（H-2）：对已有音频文件离线走完整转写管线（VAD/聚类/ASR/纠错/合并/格式化），输出 Markdown 报告；复用 pipeline 与 storage，不经过 GUI；模型未就绪时同样挂起等待。

#### Scenario: Transcribe an existing file offline
- **WHEN** the user runs `--offline <file>` with valid options
- **THEN** the full pipeline runs on the file and a role-based Markdown report is written

#### Scenario: Missing input file fails with non-zero exit
- **WHEN** `--offline` points to a nonexistent file
- **THEN** the process exits with a non-zero code and a readable error, so scripts can detect the failure

#### Scenario: Language and thread options are honored
- **WHEN** the user passes `--lang zh|en|ja|auto` and `--threads N`
- **THEN** the ASR uses the requested language mode and thread count

### Requirement: Help Output
The system SHALL provide a `--help` flag showing usage information.

需求含义（H-3）：`--help` 显示帮助信息（子命令、参数说明），退出码 0。

#### Scenario: Print help and exit cleanly
- **WHEN** the user runs `meeting-transcriber --help`
- **THEN** usage information is printed and the process exits with code 0
