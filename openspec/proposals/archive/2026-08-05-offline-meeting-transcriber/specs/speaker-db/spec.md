## ADDED Requirements

### Requirement: Local Speaker Database
The system SHALL maintain a local voiceprint database at `~/.<appname>/speakers.json`, storing registered speaker names and their voiceprint features.

需求含义（C-3）：应用维护一个本地声纹数据库（`~/.meeting-transcriber/speakers.json`），存储已注册发言人的姓名与声纹特征（512 维向量），采用原子写（P4）。

#### Scenario: Persist registered speakers across sessions
- **WHEN** a speaker is registered and the app is restarted
- **THEN** the registered names and embeddings are still loaded from `speakers.json`, so the same person is recognized again in later meetings

#### Scenario: Database writes are atomic
- **WHEN** `speakers.json` is saved
- **THEN** it is written via a temp file followed by rename, so a crash mid-write never leaves a half-written database

### Requirement: Cosine Similarity Matching
The system SHALL match a session's extracted voiceprints against the local database using cosine similarity, auto-labeling a known name when the score reaches the threshold of 0.65.

需求含义（C-4）：转写时将本场提取的声纹与本地库做余弦相似度匹配，阈值 0.65；超过阈值自动标注已知姓名，未超过则标记为"发言人N"（N 按检测顺序编号）。

#### Scenario: Match a known speaker above threshold
- **WHEN** a session voiceprint scores ≥ 0.65 against a database entry
- **THEN** the corresponding registered name is automatically assigned to the speaker's segments

#### Scenario: Unknown voice stays below threshold
- **WHEN** the best cosine similarity against every database entry is below 0.65
- **THEN** the speaker is labeled "发言人N" instead of being mis-attributed to a known name, keeping the auto-labeling false-positive boundary intact

### Requirement: New Speaker Registration
The system SHALL let the user name and register an unknown speaker detected in a session, so the next meeting recognizes them automatically.

需求含义（C-5）：转写完成后，用户可在 GUI 中为本场检测到的未知发言人命名并注册到声纹库（写入姓名 + 512 维向量），下次会议自动识别。

#### Scenario: Register an unknown speaker with a name
- **WHEN** the user names an unregistered "发言人N" in the speaker panel
- **THEN** a new database entry (id, name, embedding, created_at) is created atomically, and future sessions match against it

### Requirement: Speaker Database Management
The system SHALL let the user view the registered speaker list and delete any entry one by one from the GUI.

需求含义（C-6）：GUI 中可查看已注册声纹列表并逐个删除，删除后立即原子写回磁盘。

#### Scenario: Delete a registered speaker
- **WHEN** the user deletes a speaker from the management list
- **THEN** the entry is removed from the database and persisted atomically, and the deleted name is no longer auto-labeled

### Requirement: Database Versioning
The system SHALL include a version field in the persisted format so future model upgrades can migrate data.

需求含义（C-7）：持久化格式包含版本号字段（`version: 1`）；未来模型升级（如向量维度变化）时靠版本号触发迁移逻辑——本轮仅保留版本校验，不引入迁移代码。

#### Scenario: Persist a version field
- **WHEN** `speakers.json` is saved
- **THEN** it contains a `version` field, providing a migration hook for future embedding dimension changes

### Requirement: Corruption Tolerance
The system SHALL back up a corrupted speaker database file and continue with an empty database instead of crashing.

需求含义（C-8）：声纹库文件解析失败（JSON 损坏、版本不兼容等）时自动将原文件改名备份为 `speakers.json.corrupt-<UTC时间戳>.bak`，并以空库继续运行，不崩溃——可用性优先，生物特征数据防损坏阻断启动。

#### Scenario: Corrupted speakers.json is backed up and service continues
- **WHEN** `speakers.json` fails to parse at load time
- **THEN** the original file is renamed to a timestamped `.corrupt-*.bak` backup, the app starts with an empty speaker database, and the user can re-register speakers instead of being blocked by a crashed startup
