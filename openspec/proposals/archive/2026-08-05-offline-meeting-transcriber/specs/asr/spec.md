## ADDED Requirements

### Requirement: Offline SenseVoice Recognition
The system SHALL perform offline speech recognition with the SenseVoice model (primary Chinese, auxiliary English/Japanese) via a local ONNX runtime (sherpa-onnx).

需求含义（B-1）：集成 SenseVoice（FunAudioLLM 开源模型，中文为主，兼具多语言/情感/声学事件识别）的本地推理能力，全程离线，数据不出本机。

#### Scenario: Transcribe a speech segment offline
- **WHEN** a VAD/diarization segment is submitted to the ASR
- **THEN** SenseVoice transcribes it locally without any network access

### Requirement: Multi-language Support
The system SHALL support at least four recognition modes: Chinese, English, Japanese, and auto-detect.

需求含义（B-2）：语言模式至少覆盖中文、英文、日文、自动识别四种，由用户在设置中选定并持久化。

#### Scenario: Recognize Chinese, English, and Japanese modes
- **WHEN** the user selects zh / en / ja as the recognition language
- **THEN** the ASR is configured for that language, and segments are transcribed accordingly

#### Scenario: Auto-detect language
- **WHEN** the user selects the auto-detect mode
- **THEN** the ASR infers the language per segment without explicit language hints

### Requirement: Segment-based Inference
The system SHALL never feed the whole long recording into the ASR in one pass — the mic track goes through VAD segmentation and the system track through diarization before each segment is transcribed individually.

需求含义（B-3）：不对整段长音频直接推理；麦克风轨经 VAD 断句后逐段送 ASR，系统音轨经声纹分割后逐段送 ASR，保证段长健康与模型输出稳定。

#### Scenario: Long audio is transcribed segment by segment
- **WHEN** a long recording reaches the ASR stage
- **THEN** only VAD/diarization-segmented clips (4–15s) are transcribed, one at a time, never the full file at once

### Requirement: Silence Segment Skipping
The system SHALL skip segments whose peak level is too low (near silence) without sending them to the ASR.

需求含义（B-4）：段内峰值过低（接近静音）的片段跳过 ASR，节省算力；被跳过的段不产生文本，在管线中保留 `skipped` 标记。

#### Scenario: Skip a near-silent segment
- **WHEN** a segment's peak RMS is below the silence threshold
- **THEN** the ASR is skipped for that segment, saving compute, and the segment is marked as skipped instead of producing garbage text

### Requirement: Configurable Inference Threads
The system SHALL let the user configure the number of inference threads (1–8), with a recommended value of CPU cores / 2 capped at 4.

需求含义（B-5）：推理线程数可在 GUI 中调整（1-8），系统给出推荐值（CPU 核数 / 2，上限 4），并持久化到配置。

#### Scenario: Adjust thread count in settings
- **WHEN** the user changes the inference thread count within the 1–8 range
- **THEN** the ASR uses the configured thread count, and the GUI shows the recommended default (cores/2, capped at 4)

#### Scenario: Clamp out-of-range thread values
- **WHEN** a persisted or user-supplied thread count falls outside 1–8
- **THEN** the system clamps it into the valid range rather than failing

### Requirement: Asynchronous Model Loading
The system SHALL load models on a background thread without blocking GUI rendering, showing "正在加载推理引擎" while loading.

需求含义（B-6）：模型加载放在后台线程，不阻塞 GUI 渲染；加载期间显示"正在加载推理引擎"提示，加载完成自动触发挂起的转写任务续转（P3）。

#### Scenario: GUI stays responsive while models load
- **WHEN** the app starts and models begin loading
- **THEN** the GUI remains interactive and shows a "loading inference engine" status instead of freezing

#### Scenario: Suspended tasks resume when loading completes
- **WHEN** a transcription task is suspended waiting for models
- **THEN** the task resumes automatically the moment loading reports ready

### Requirement: Output Cleaning
The system SHALL strip special tokens (language markers, emotion markers, XML control tags) from the raw model output, keeping only plain text.

需求含义（B-7）：清除模型输出中夹带的 special token 标签（如 `<|zh|>` 语言标记、情绪标记、XML 控制标签等），只保留纯文本，防止报告出现噪声标签。

#### Scenario: Clean special tokens from raw output
- **WHEN** the ASR returns raw text containing language/emotion/event tokens and XML tags
- **THEN** the tokens are stripped and only plain text is handed to the report pipeline, so no control noise ever appears in the transcript
