## ADDED Requirements

### Requirement: Speaker Diarization Clustering
The system SHALL automatically cluster the system audio track into multiple speaker segments using a speaker segmentation model (Pyannote ONNX, loaded via sherpa-onnx).

需求含义（C-1）：系统音频通过说话人分割模型（Pyannote 等）自动聚类为多个 Speaker 区间，每个区间带 (start, end, label)；聚类结果中的超长段由 VAD 二次切分后送 ASR（D-3）。

#### Scenario: Cluster system audio into speaker segments
- **WHEN** the system track reaches the diarization stage after stop
- **THEN** it is clustered into labeled speaker intervals, one label per detected distinct voice

#### Scenario: Diarization model missing
- **WHEN** the Pyannote segmentation model is not present locally
- **THEN** the system reports an explicit error pointing to the download script, without any attempt to fetch the model over the network at runtime

### Requirement: Voiceprint Embedding Extraction
The system SHALL extract a voiceprint feature vector (512-dimensional) for each clustered speaker.

需求含义（C-2）：为每个聚类出的 Speaker 提取声纹特征向量（3D-Speaker eres2net，512 维）；维度契约固定为 512，维度不齐将破坏声纹库持久化与匹配。

#### Scenario: Extract a 512-dim embedding per speaker
- **WHEN** the diarizer has produced speaker clusters
- **THEN** each cluster yields a 512-dimensional voiceprint vector, ready for cosine matching against the local speaker database

#### Scenario: Embedding dimension contract
- **WHEN** the embedding extractor returns a vector
- **THEN** its dimension is exactly 512, so stored voiceprints remain compatible with the database schema across sessions
