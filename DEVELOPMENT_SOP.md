# 团队开发 SOP（标准操作流程）

## 1. 总则

本 SOP 定义了在 Trae AI IDE 中，全栈工程师日常开发的标准化流程。核心原则：**先判定轻重，再选择流程**。

## 2. 任务分类（轻重分流）

Agent 收到开发请求后，**必须先根据以下矩阵判定任务类型**，不得跳过：

| 维度 | 轻量级 | 重度级 |
|------|--------|--------|
| 影响范围 | 单文件、UI样式、文案、注释 | 多模块、DB变更、接口契约 |
| 逻辑风险 | 不改变核心业务断言 | 状态机、权限、金流、一致性 |
| 代码量 | < 30 行 | ≥ 30 行 |
| 示例 | padding调整、Null保护、日志 | 新API、支付重构、中间件变更 |

判定完成后，严格按照对应流程执行。

## 3. 轻量开发流程

```
意图确认 → 外科手术修改 → 验证 → Commit
```

### 3.1 意图确认
在对话框中一句话声明修改意图与评估范围。

### 3.2 外科手术修改
- 利用 `code-review-graph` MCP 定位目标代码符号
- 仅修改目标代码段，**严禁顺手重构**相邻代码

### 3.3 验证
- 运行现有相关单元测试
- 或进行本地简易验证（浏览器/API 调用）

### 3.4 Commit
- 格式：`fix(scope): <简短描述>`
- 例：`fix(ui): 修正登录按钮 padding`

## 4. 重度开发流程（4 卡口）

### 卡口 1: Grill-me 需求拷问

**触发**: `/grill-me` 或 Agent 判定为重度任务

Agent 按以下 6 大维度逐条逼问，一次一问：

1. 功能边界（做什么/不做什么 / 输入输出范围）
2. 异常与边界（空值/非法输入/并发/降级）
3. 数据一致性（状态变更/回滚/补偿/迁移兼容）
4. 安全与权限（权限模型/审计日志/敏感数据）
5. 性能与规模（QPS/数据量级/瓶颈/缓存）
6. 测试与验证（正确性验证/关键场景/回归范围）

**出口条件**: 用户明确回复"可以进入 OpenSpec"

### 卡口 2: OpenSpec 领域规格定义

**触发**: Grill 完成

生成 `openspec/proposals/<feature-id>/` 目录，包含：

| 文件 | 内容 |
|------|------|
| `propose.md` | 目的、范围、背景、风险 |
| `specs/<capability>/spec.md` | ADDED/MODIFIED/REMOVED 需求 + Scenario |
| `design.md` | 架构、数据模型、接口契约、迁移策略 |
| `tasks.md` | 按阶段拆解的实施任务清单 |

**出口条件**: 用户明确回复"批准 Proposal"

### 卡口 3: Superpowers TDD 驱动

**触发**: Proposal 批准

核心纪律：
- **垂直切片**: 一次一个测试 → 一次一个实现
- **不测实现**: 通过公共接口验证行为
- **不绿不重构**: 测试没绿，不准重构

```
循环:
  RED:   写一个测试 → 确认失败（断言行为意图）
  GREEN: 写最少代码 → 确认通过
  REFACTOR: 优化 → 确认全量测试仍绿
```

### 卡口 4: 归档闭环

- 移动 `openspec/proposals/<feature-id>/` 到 `openspec/proposals/archive/<YYYY-MM-DD>-<feature-id>/`
- 触发 `code-review-graph` 增量索引更新
- Commit: `feat(scope): description`

## 5. Commit 规范

| 类型 | 前缀 | 示例 |
|------|------|------|
| 新功能 | `feat` | `feat(auth): 添加邮箱注册` |
| Bug修复 | `fix` | `fix(payment): 修复金额精度丢失` |
| 重构 | `refactor` | `refactor(db): 提取连接池配置` |
| 轻量改动 | `fix` 或 `chore` | `fix(ui): 调整按钮间距` |

## 6. 代码审查（Code Review）

使用 `code-review-graph` MCP 工具：
- `get_review_context_tool`: 获取变更的 blast radius
- `get_impact_radius_tool`: 分析上下游依赖影响
- `semantic_search_nodes_tool`: 语义搜索相关代码

原则：**先查图谱，再读文件**。

## 7. 检查清单

### 每日开发前
- [ ] Agent 已读取 `.trae/rules/AGENTS.md`
- [ ] 理解今天的任务属于轻量还是重度

### 轻度任务
- [ ] 一句话声明意图
- [ ] 未顺手重构相邻代码
- [ ] 验证通过

### 重度任务
- [ ] Grill 完成，所有维度无遗漏
- [ ] Proposal 已批准
- [ ] TDD 垂直切片执行
- [ ] 已归档
