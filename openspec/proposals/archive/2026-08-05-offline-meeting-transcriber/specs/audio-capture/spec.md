## ADDED Requirements

### Requirement: Microphone Device Selection
The system SHALL enumerate all available input devices and let the user select the microphone used for recording.

需求含义（A-1）：GUI 下拉列表枚举系统所有可用输入设备（设备索引、名称、声道数、默认采样率），用户可选择任一麦克风开始录音；所选设备持久化到配置，下次启动自动恢复。

#### Scenario: Enumerate and select a microphone
- **WHEN** the user opens the device dropdown on the recording page
- **THEN** the system lists every available input device with its index and name, and the user's selection becomes the mic track source

#### Scenario: No input device available
- **WHEN** the system finds zero usable input devices
- **THEN** the start-recording action is blocked and the GUI shows a readable error, so the user is never left recording a silent mic track

### Requirement: System Audio Capture
The system SHALL capture system audio (the far-end voice) via Windows WASAPI loopback, with platform abstraction reserved for macOS and Linux.

需求含义（A-2）：Windows 通过 WASAPI Loopback 系统回环捕获对方声音；架构上预留跨平台扩展能力（macOS 虚拟音频设备 BlackHole、Linux PulseAudio Monitor），采集层不做平台硬编码。

#### Scenario: Capture system audio over WASAPI loopback
- **WHEN** recording starts and system audio capture is enabled
- **THEN** the system audio track is captured in parallel with the mic track on the same timeline

#### Scenario: Loopback unavailable on the current device
- **WHEN** WASAPI loopback fails or returns silence on the active audio device
- **THEN** the system degrades to mic-only recording and shows a warning, instead of failing the whole session

### Requirement: Dual-track Time-Aligned Mixing
The system SHALL align the mic and system tracks on a shared timeline and mix them into a single WAV file (16kHz / 16bit / mono).

需求含义（A-3）：麦克风与系统音频按时间轴对齐，混合后写入单个 `record_YYYYMMDD_HHMMSS.wav`（16kHz / 16bit / 单声道），作为录音存档与后续转写的物理依据。

#### Scenario: Mix both tracks into one WAV
- **WHEN** recording stops
- **THEN** the aligned mic and system samples are mixed and written to a 16kHz / 16-bit / mono WAV file at the configured output directory

### Requirement: Independent Per-track Buffering
The system SHALL cache the raw PCM of each track separately in memory during recording, so each track feeds its own analysis pipeline after stop.

需求含义（A-4）：录音期间麦克风与系统音频的原始 PCM 分别独立缓存，互不污染；停录后麦克风轨送入能量 VAD 断句管线，系统音轨送入声纹聚类管线，各自独立处理。

#### Scenario: Separate buffers feed separate pipelines
- **WHEN** recording stops
- **THEN** mic samples are handed to the VAD pipeline while system samples are handed to the diarization pipeline, without the two ever sharing mutable state

### Requirement: Hardware Sample Rate Adaptation
The system SHALL resample any device-native sample rate (44.1kHz / 48kHz, etc.) to 16kHz automatically.

需求含义（A-5）：无论设备原生采样率是多少，采集后统一重采样到 16kHz，保证与 ASR / VAD / 声纹模型的输入契约一致。

#### Scenario: Resample a 48kHz device to 16kHz
- **WHEN** the selected device runs at 48kHz
- **THEN** the captured samples are resampled to 16kHz before buffering, so downstream analysis always sees 16kHz input

### Requirement: Multi-channel Downmix to Mono
The system SHALL downmix multi-channel devices to mono by averaging all channels.

需求含义（A-6）：多声道设备自动取各声道平均转为单声道，避免声道叠加产生削波或相位抵消，同时满足 16kHz 单声道模型输入契约。

#### Scenario: Downmix a stereo device to mono
- **WHEN** the selected device delivers two or more channels
- **THEN** the channels are averaged into a single mono stream without clipping or channel cancellation

### Requirement: System Track Mix Attenuation
The system SHALL attenuate the system track (recommended 0.9) when mixing, so far-end audio does not drown out the local voice.

需求含义（A-7）：混音时系统音轨适度衰减（建议 0.9），避免对方声音盖过本端人声；衰减系数可在设置中调整并持久化。

#### Scenario: Apply 0.9 gain to the system track before mixing
- **WHEN** the mixer combines mic and system samples
- **THEN** the system samples are multiplied by 0.9 first, keeping the local voice dominant in the mixed WAV

### Requirement: Recording Zero-inference Contract
The system SHALL perform no AI inference during recording — only audio capture, mixing, disk writing, and real-time waveform display.

需求含义（P2，录音零开销）：录音期间不做任何 ASR / 声纹分析；所有推理在停录后离线执行。录音线程与推理线程完全解耦，不共享可变状态（停录瞬间以不可变数组快照交接 PCM）。

#### Scenario: No inference while recording
- **WHEN** a recording session is active
- **THEN** no ASR or voiceprint analysis runs; the recording thread only captures, mixes, persists, and streams waveform RMS

#### Scenario: Model still loading during recording
- **WHEN** the user starts recording before the inference models finish loading
- **THEN** recording proceeds normally and transcription only starts after stop, once the models are ready (P3 decoupling)

### Requirement: Anti-OOM Spill
The system SHALL spill an unbalanced track to disk when one track grows without bound for more than 5 seconds, preventing memory exhaustion in long meetings.

需求含义（§4.2 防 OOM）：双轨 PCM 独立缓存；任一轨单路失衡（另一轨持续静音）超 5s 时，将该轨数据直写临时文件而非无限堆积内存，停录后从临时文件续读完整数据。

#### Scenario: Unbalanced track spills to disk
- **WHEN** one track keeps accumulating while the other is silent for more than 5 seconds
- **THEN** the accumulating track is spilled to a temporary file so memory does not grow without bound, and the full samples are readable after stop

#### Scenario: Spilled data is fully recovered
- **WHEN** recording stops after a spill occurred
- **THEN** the spilled track's complete samples are re-read from the temporary file, so downstream analysis receives lossless audio
