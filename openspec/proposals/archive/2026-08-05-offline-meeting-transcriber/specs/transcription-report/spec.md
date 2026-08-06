## ADDED Requirements

### Requirement: Dual-track Chronological Merge
The system SHALL merge the mic-track (labeled "我") and system-track (labeled by role) transcription results sorted by timestamp.

需求含义（E-1）：麦克风轨与系统音轨的转写结果按时间戳排序合并成单一时间线，作为报告正文的数据基础。

#### Scenario: Merge both tracks on one timeline
- **WHEN** both tracks have been transcribed
- **THEN** all segments are sorted by start timestamp into a single ordered list, interleaving "我" and system-speaker utterances correctly

### Requirement: Role-based Markdown Report
The system SHALL generate a role-based Markdown report containing a report title, generation date, and timestamp-sorted body lines in the format `[MM:SS] 角色名 文本`, with the mic track labeled "我 (姓名)" and other speakers labeled by role name.

需求含义（E-2）：报告含标题、生成日期与按时间戳排序的正文；行格式 `[MM:SS] 角色名 文本`（麦克风轨标"我 (姓名)"，未注册发言人标"发言人N"，注册后标真实姓名），时间戳 MM:SS 补零。输出格式与任务书示例逐行一致：

```text
# 会议转写报告
生成日期: 2026-08-04

[00:12] 我 (张三) 今天先同步一下进度
[00:18] 发言人1 那部分我来负责
[00:35] 我 (张三) 好，下周复盘
```

#### Scenario: Generate the Markdown report in the canonical format
- **WHEN** transcription completes
- **THEN** a Markdown report is produced with title, generation date, and `[MM:SS] 角色 文本` lines matching the specification example exactly, with the mic track shown as "我 (姓名)"

#### Scenario: Unknown speakers are numbered sequentially
- **WHEN** a system-track speaker has no database match
- **THEN** they are labeled "发言人N" (N in order of first appearance), and after registration the real name is used instead

### Requirement: Terminology Correction Post-processing
The system SHALL support a user-configured "错词=正确词" mapping table (comma-separated) and apply full-text replacement after transcription completes.

需求含义（E-3）：支持用户配置「错词=正确词」映射表（逗号分隔，如 `腾讯会议=腾讯视频会议`），转写完成后自动全文替换；非法条目（缺 `=`）跳过且不中断整体替换。

#### Scenario: Apply correction mappings across the whole transcript
- **WHEN** transcription finishes and the corrections list contains `错词=正确词` entries
- **THEN** every occurrence of the wrong term is replaced with the correct term across the full text

#### Scenario: A malformed mapping entry is skipped
- **WHEN** one corrections entry lacks the `=` separator
- **THEN** that single entry is skipped while the remaining valid mappings still apply, so one bad configuration line never breaks the whole transcript

### Requirement: Atomic Report Write
The system SHALL write the report to a `.tmp` file first and then rename it into place, so a crash never leaves a half-written report.

需求含义（E-4）：报告先写 `transcript_*.md.tmp` 再 `os.replace` 原子替换；写入失败不静默吞掉——GUI 给出可读错误，不残留半截文件。

#### Scenario: Report is written atomically
- **WHEN** the report file is saved
- **THEN** it is first written to a `.tmp` file and then atomically renamed, so a crash mid-write cannot leave a truncated report at the final path

#### Scenario: Failed write surfaces an error, no partial file
- **WHEN** the report write fails
- **THEN** the user sees a readable error and no half-written file remains at the target path

### Requirement: Transcription Progress Feedback
The system SHALL show a percentage progress bar plus a spinner animation during transcription.

需求含义（E-5）：转写过程中 GUI 显示百分比进度条 + spinner 动画，进度经管线进度回调（段级别）上报，不阻塞 GUI。

#### Scenario: Progress bar and spinner during transcription
- **WHEN** transcription is running
- **THEN** the GUI displays a live percentage progress bar and spinner driven by pipeline progress callbacks, without blocking the UI thread

### Requirement: Cancellable Transcription
The system SHALL let the user cancel an in-progress transcription; cancellation returns silently to the ready state.

需求含义（E-6）：转写进行中用户可取消——取消令牌在段边界检查，取消后不产出报告，GUI 静默回到就绪态，不残留错误状态。

#### Scenario: Cancel mid-transcription
- **WHEN** the user presses cancel while transcription is running
- **THEN** the pipeline stops at the next segment boundary, no report is produced, and the GUI returns silently to the ready state

### Requirement: Single Source of Truth for Formatting
The system SHALL implement report formatting logic in exactly one place, reused by GUI preview, first generation, and rename rewrite.

需求含义（E-7）：报告格式化逻辑只写在一处（`format_report(segments, user_name, generated_at)`）；GUI 预览、首次生成、发言人改名重写三处全部复用同一函数，保证三处输出逐行一致。

#### Scenario: Rename rewrite reuses the same formatter
- **WHEN** the user renames a speaker and the preview and MD file are rewritten
- **THEN** both outputs come from the same single formatting function and stay byte-identical in format to the first generated report
