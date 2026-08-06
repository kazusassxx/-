## ADDED Requirements

### Requirement: Mic Track Energy VAD
The system SHALL segment the mic track using a lightweight RMS-energy VAD: RMS is computed over fixed blocks, and consecutive blocks below the threshold are treated as silence that splits segments.

需求含义（D-1）：基于 RMS 能量的轻量 VAD，按固定块大小计算 RMS，连续多块低于阈值判定为静音并断句；该 VAD 只用于麦克风轨，运行在停录后的离线管线中。

#### Scenario: Segment mic track at silence gaps
- **WHEN** the mic track contains speech separated by sustained low-RMS silence
- **THEN** the VAD splits the track into speech segments at the silence boundaries

### Requirement: Segment Length Constraints
The system SHALL enforce a minimum segment length of 4s and a maximum of 15s, hard-cutting longer segments.

需求含义（D-2）：最短语音段 ≥ 4s（避免超短段送 ASR），最长 ≤ 15s（强制切断，防单段过长导致模型退化）；超短段直接丢弃不送 ASR，超长段在 15s 处强制切断。

#### Scenario: Drop segments shorter than 4 seconds
- **WHEN** the VAD produces a speech segment under 4 seconds
- **THEN** the segment is dropped from the ASR queue, so the ASR never receives degenerate ultra-short clips

#### Scenario: Hard-cut segments longer than 15 seconds
- **WHEN** a speech segment exceeds 15 seconds
- **THEN** it is forcibly cut at the 15-second boundary, keeping every ASR input inside the healthy 4–15s window

### Requirement: Secondary Segmentation for Long Diarization Segments
The system SHALL re-segment diarization segments longer than 15s with a secondary VAD pass before sending them to ASR.

需求含义（D-3）：声纹聚类的某些段可能很长（说话人连续说几分钟），对 > 15s 的聚类段复用能量 VAD 做二次切分后再送 ASR，防止单段过长导致模型退化。

#### Scenario: A long speaker turn is split before ASR
- **WHEN** the diarizer returns a segment where one speaker talks continuously for over 15 seconds
- **THEN** the segment is re-segmented by the energy VAD, so every ASR input respects the 15s upper bound

### Requirement: Adjacent Short Segment Merging
The system SHALL merge adjacent segments of the same speaker when the gap is ≤ 1.5s and the combined length is ≤ 15s.

需求含义（D-4）：同角色相邻段间隔 ≤ 1.5s 且累计 ≤ 15s 的合并为一段，避免语气词、停顿被切成碎句送 ASR，也防止碎句导致转写上下文丢失。

#### Scenario: Merge fragmented utterances of the same speaker
- **WHEN** two adjacent segments of the same speaker are separated by at most 1.5s and their combined length is at most 15s
- **THEN** they are merged into one segment before ASR, so filler words are not transcribed as isolated fragments

#### Scenario: Do not merge beyond the length budget
- **WHEN** merging would push the combined segment past 15 seconds
- **THEN** the merge is refused and the segments stay separate, preserving the ASR segment-length contract
