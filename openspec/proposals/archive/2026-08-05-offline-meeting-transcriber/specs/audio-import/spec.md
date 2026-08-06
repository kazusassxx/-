## ADDED Requirements

### Requirement: Import External Audio Files
The system SHALL import external audio files in WAV, MP3, and FLAC formats for transcription.

需求含义（F-1）：支持导入 WAV / MP3 / FLAC 常见格式。M4A / AAC 不在支持范围——解码基于 libsndfile（soundfile）的能力边界，导入此类格式时明确报错并提示支持的格式列表，而非静默失败或产生空结果。

#### Scenario: Import a WAV file
- **WHEN** the user picks a WAV file via the import dialog
- **THEN** the file is accepted and enters the transcription pipeline

#### Scenario: Import MP3 and FLAC files
- **WHEN** the user picks an MP3 or FLAC file
- **THEN** the file is decoded and enters the same pipeline as WAV imports

#### Scenario: Unsupported format is rejected with a clear message
- **WHEN** the user picks an M4A or AAC file
- **THEN** the import fails with an explicit "unsupported format" error listing WAV/MP3/FLAC, so the user knows the format limitation (libsndfile constraint) instead of getting a broken transcription

### Requirement: Automatic Decode and Resample
The system SHALL decode any sample rate and codec automatically into 16kHz mono f32 PCM.

需求含义（F-2）：任意采样率、任意支持的编解码格式，导入后自动解码并重采样为 16kHz 单声道 f32 PCM，与录音双轨同一输入契约，后续管线完全复用。

#### Scenario: Decode and resample a 48kHz stereo MP3
- **WHEN** a 48kHz stereo MP3 is imported
- **THEN** it is decoded and resampled to 16kHz mono f32 before entering the pipeline

### Requirement: Unified Speaker Diarization Pipeline
The system SHALL treat an imported file as a multi-speaker mixed recording and route it through the same diarization pipeline, with no mic/sys physical separation.

需求含义（F-3）：导入音频视为一场多人混合录音，统一走声纹聚类分角色（无 mic/sys 物理分离），不做本端/他端区分；导入转写结果与录音转写共用同一报告格式。

#### Scenario: Imported audio is diarized by voice
- **WHEN** an imported file reaches the pipeline
- **THEN** it is segmented by speaker diarization, and each detected speaker is labeled (registered name or "发言人N") in the report

#### Scenario: No track separation on imports
- **WHEN** the pipeline processes an imported file
- **THEN** no mic/sys distinction is applied — all audio is treated as one mixed meeting track

### Requirement: Deferred Transcription Until Model Ready
The system SHALL suspend an import task when models are not ready, and resume it automatically once models finish loading.

需求含义（F-4）：导入时若模型未加载完成，任务挂起等待；模型就绪后自动续转，与录音转写的 P3 解耦原则一致——导入不因模型未就绪而失败或丢失。挂起期间用户仍可取消任务。

#### Scenario: Import while models are still loading
- **WHEN** the user imports audio before the inference models are ready
- **THEN** the task is suspended, and transcription resumes automatically once the models report ready

#### Scenario: Cancel a suspended import
- **WHEN** the user cancels while an import task is suspended waiting for models
- **THEN** the task is cancelled cleanly and the GUI returns to the ready state without a stuck task
