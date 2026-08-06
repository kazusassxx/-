# Tasks: offline-meeting-transcriber

> 按依赖顺序分阶段实施，每项 2–5 分钟。标记 🧪 的为 pytest 单元测试任务（对应 §8.3 代码质量要求：VAD 分段、名词纠错、声纹匹配、报告格式化、原子写等核心逻辑）。所有文件写入须用原子写。

## 阶段 0：项目脚手架
- [x] 0.1 创建 `src/meeting_transcriber/` 包结构（audio/pipeline/report/storage/models/gui 子包 + `__init__.py` 定义 `__appname__ = "meeting-transcriber"`）
- [x] 0.2 创建 `pyproject.toml`：Python 3.12.10，依赖 sherpa-onnx==1.13.4 / PySide6==6.11.1 / sounddevice / PyAudioWPatch / soundfile / numpy，dev 依赖 pytest
- [x] 0.3 创建 `paths.py`：数据目录 `~/.meeting-transcriber/`、config/speakers/models 路径解析（平台抽象）
- [x] 0.4 更新 `.gitignore`：排除 `~/.meeting-transcriber/`、声纹库、录音/转写输出、`models/`、build/dist（§4.5 敏感数据不入库）
- [x] 0.5 添加 MIT License 与 README 骨架（构建/使用说明，§4.5）

## 阶段 1：audio 采集层
- [x] 1.1 `audio/devices.py`：`list_input_devices()` 枚举输入设备（sounddevice）
- [x] 1.2 🧪 `tests/test_resample.py`：`to_16k_mono_f32()` 将 48kHz 立体声转 16kHz 单声道（断言采样率与声道数）
- [x] 1.3 `audio/resample.py`：重采样 + 多声道平均实现
- [x] 1.4 `audio/mix.py`：`mix_and_save()` 双轨时间轴对齐混音（sys 轨 ×0.9 衰减）写 16k/16bit/mono WAV
- [x] 1.5 🧪 `tests/test_mix.py`：混音后 WAV 采样率/位深/声道断言 + 系统音 0.9 衰减幅度断言（WHY：验证 A-7 防盖过人声）
- [x] 1.6 `audio/capture.py`：`Recorder` 双轨采集（mic + WASAPI loopback，PyAudioWPatch），独立 PCM 缓存
- [x] 1.7 `audio/capture.py`：波形回调（RMS 节流 ≤50ms）+ 单路失衡超 5s spill 到临时文件（防 OOM）
- [x] 1.8 🧪 `tests/test_spill.py`：模拟单路失衡触发 spill，断言内存不无限增长且续读完整（WHY：长会议不 OOM）
- [x] 1.9 `audio/import_audio.py`：`decode_to_16k_mono()`（soundfile 解码 WAV/MP3/FLAC）

## 阶段 2：model 管理层 + 下载脚本
- [x] 2.1 `models/manager.py`：`resolve_path()` 模型定位（exe 同级 `./models/` → `~/.meeting-transcriber/models/`）
- [x] 2.2 `models/download.py` + `scripts/download_models.py`：下载 SenseVoice / eres2net / Pyannote 三模型，支持代理、镜像回退、幂等跳过已存在文件
- [x] 2.3 `models/manager.py`：`load_async()` 后台线程加载 + status（loading/ready/error），缺模型明确报错不联网
- [x] 2.4 🧪 `tests/test_model_resolution.py`：模拟 exe 同级 models/ 优先、缺失回退 home 缓存（WHY：打包版内置优先契约 §4.4）

## 阶段 3：pipeline 核心（VAD / 聚类 / 声纹）
- [x] 3.1 `pipeline/vad.py`：`EnergyVAD.segment()` 按块 RMS 静音断句
- [x] 3.2 `pipeline/vad.py`：段长约束（≥4s / ≤15s 强制切断）
- [x] 3.3 `pipeline/vad.py`：`merge_adjacent()` 同角色相邻短段合并（间隔 ≤1.5s 且累计 ≤15s）
- [x] 3.4 🧪 `tests/test_vad.py`：合成音频断言断句边界、超短段丢弃、超长段切断、碎句合并（WHY：D-2/D-4 保证送 ASR 段长在 4–15s 健康区间）
- [x] 3.5 `pipeline/diarize.py`：`Diarizer.segment()`（Pyannote ONNX via sherpa-onnx）聚类 Speaker 区间
- [x] 3.6 `pipeline/diarize.py`：>15s 聚类段二次 VAD 切分（复用 EnergyVAD）
- [x] 3.7 `pipeline/embedding.py`：`extract_embedding()`（3D-Speaker eres2net，512 维）
- [x] 3.8 🧪 `tests/test_embedding.py`：提取结果维度 = 512（WHY：C-2 向量契约，维度不齐将破坏声纹库持久化）
- [x] 3.9 🧪 `tests/test_speaker_match.py`：`SpeakerDB.match()` 余弦相似度阈值 0.65——同人 ≥0.65 命中、异人 <0.65 返回 None（WHY：C-4 自动标注与误报边界）
- [x] 3.10 `pipeline/merge.py`：`merge_tracks()` 双轨按时间戳排序合并

## 阶段 4：ASR 集成
- [x] 4.1 `pipeline/asr.py`：`SenseVoiceASR` 初始化 + `transcribe()`（sherpa-onnx，num_threads 传入）
- [x] 4.2 `pipeline/asr.py`：`clean_output()` 剥离 `<|zh|>` 等 special token 与 XML 标签
- [x] 4.3 🧪 `tests/test_asr_clean.py`：含语言/情绪/事件 token 的原始输出清洗为纯文本（WHY：B-7 防报告噪声）
- [x] 4.4 `pipeline/asr.py`：静音段跳过（RMS 峰值过低不送 ASR）

## 阶段 5：storage 持久化层
- [x] 5.1 `report/atomicio.py`：`write_atomic()`（.tmp + flush + fsync + os.replace + 失败清理）
- [x] 5.2 🧪 `tests/test_atomicio.py`：原子写不残留 .tmp、写入成功可读、失败时原文件完好（WHY：P4 防半截文件）
- [x] 5.3 `storage/config.py`：`load_config()`（缺失/损坏→默认值合并）+ `save_config()`（原子写）
- [x] 5.4 `storage/speakers.py`：`SpeakerDB.load/save/register/delete` + 版本校验（version:1）
- [x] 5.5 🧪 `tests/test_speaker_db.py`：损坏 JSON 时备份原文件（带时间戳 .bak）并以空库继续（WHY：C-8 可用性优先，不因声纹库损坏阻断启动）
- [x] 5.6 🧪 `tests/test_config.py`：损坏 config 回退默认值 + 保存后重启可恢复（WHY：G-9 配置持久化）

## 阶段 6：report 转写报告
- [x] 6.1 `report/corrections.py`：`apply_corrections()` 错词=正确词映射替换（逗号分隔）
- [x] 6.2 🧪 `tests/test_corrections.py`：多条映射全文替换 + 非法条目（缺"="）跳过不中断（WHY：E-3 专有名词纠错且单条坏配置不拖垮全流程）
- [x] 6.3 `report/formatter.py`：`format_report()` 单一真相源（标题/日期/`[MM:SS] 角色名 文本`，麦克风轨"我 (姓名)"，未注册"发言人N"）
- [x] 6.4 🧪 `tests/test_formatter.py`：格式化输出与任务书 §3.5 示例逐行一致 + 时间戳 MM:SS 补零 + 改名后重写一致性（WHY：E-7 单一真相源保证三处消费输出一致）
- [x] 6.5 `pipeline/pipeline.py`：`TranscriptionPipeline.run()` 编排（VAD→聚类/声纹→匹配→ASR→纠错→合并→格式化）+ 进度回调 + `cancelled` 事件
- [x] 6.6 🧪 `tests/test_pipeline_cancel.py`：取消令牌置位后管线在段边界停止且不产出报告（WHY：E-6 取消静默回就绪）

## 阶段 7：CLI 入口
- [x] 7.1 `cli.py`：argparse 三子命令（--list-devices / --offline / --help），复用 pipeline
- [x] 7.2 🧪 `tests/test_cli.py`：`--list-devices` 与 `--help` 退出码 0；`--offline` 指向不存在文件非零退出（WHY：H-3 参数契约）

## 阶段 8：GUI（PySide6）
- [x] 8.1 `gui/state_machine.py`：状态机（就绪/录音/转写/完成/导入转写）迁移 + 录音按钮禁用规则
- [x] 8.2 `gui/windows/name_gate.py`：首次启动姓名强拦截（config 无 user_name 时）
- [x] 8.3 `gui/windows/main_window.py`：录音态（停止键/双轨波形/计时）、转写态（进度条 + spinner + 取消）、完成态（预览 + 打开文件按钮）
- [x] 8.4 `gui/windows/mini_window.py`：录音小窗（右上角置顶，仅停止键 + 波形），停录/转写后恢复
- [x] 8.5 `gui/windows/settings_dialog.py`：四 Tab 设置（常规/音频/高级纠错/声纹管理），修改持久化到 config
- [x] 8.6 `gui/workers.py`：RecordingWorker / TranscriptionWorker（QThread），录音零推理（P2）
- [x] 8.7 `gui/windows/main_window.py`：发言人面板——命名/改名即时刷新预览与 MD（复用 format_report）+ 声纹注册
- [x] 8.8 `gui/windows/main_window.py`：模型状态指示（就绪/加载中/错误 + 重试按钮）；导入音频按钮与文件对话框
- [x] 8.9 `gui/app.py`：多语言（中/英/日 QTranslator + 系统语言检测）+ CJK 字体加载
- [x] 8.10 🧪 `tests/test_state_machine.py`：状态迁移合法性（录音→转写→完成→就绪；转写→就绪取消；导入转写→取消）（WHY：§七 状态机契约，防非法迁移）

## 阶段 9：打包与验收联调
- [x] 9.1 `scripts/build_windows.ps1`：PyInstaller 单目录打包，模型内置 exe 同级 `./models/`，检测缺失自动调用下载脚本
- [x] 9.2 压缩分发：打包产物生成 zip 分发包
- [x] 9.3 🧪 全量回归：`pytest` 全部通过（VAD/纠错/声纹匹配/格式化/原子写/损坏容错/状态机）—— 134 passed
- [ ] 9.4 验收：Windows 双击启动、首次姓名拦截、双轨录音波形、停录转写出 MD、声纹注册后二次识别、抓包零网络、配置重启不丢失（§8.1/8.2 清单）—— **需实机执行**
- [x] 9.5 仓库收尾：README 完整构建/使用说明、License、.gitignore 复核（无敏感数据/模型入库）

## 测试清单汇总（对应 §8.3）
- [x] 🧪 test_resample.py / test_mix.py / test_spill.py（audio 层）
- [x] 🧪 test_model_resolution.py（模型定位优先级）
- [x] 🧪 test_vad.py（VAD 分段/段长/合并）
- [x] 🧪 test_embedding.py / test_speaker_match.py（声纹提取维度 / 余弦匹配阈值）
- [x] 🧪 test_asr_clean.py（special token 清洗）
- [x] 🧪 test_atomicio.py / test_config.py / test_speaker_db.py（原子写 / 配置 / 声纹库容错）
- [x] 🧪 test_corrections.py / test_formatter.py（纠错 / 报告格式化单一真相源）
- [x] 🧪 test_pipeline_cancel.py / test_state_machine.py（取消语义 / GUI 状态机）
- [x] 🧪 test_cli.py（CLI 退出码契约）
