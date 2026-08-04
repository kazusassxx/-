---
name: openspec
description: 领域规格定义阶段。将 grill-me 产出转化为结构化 proposal + 领域契约文档。触发条件：Grill-me 完成且用户确认进入 OpenSpec。
disable-model-invocation: true
---

# OpenSpec：领域规格定义

## 目标

将 grill-me 阶段的无歧义需求约束清单，转化为结构化的领域规格文档（propose.md）及契约定义。这是**人类与 AI 就"要构建什么"达成一致的卡口**。

## 产物结构

在 `openspec/proposals/<feature-id>/` 下生成以下文件：

```
openspec/proposals/<feature-id>/
├── propose.md       # 核心提案文档
├── specs/
│   └── <capability>/
│       └── spec.md  # 领域契约 delta（ADDED/MODIFIED/REMOVED 需求）
├── design.md        # 技术设计方案
└── tasks.md         # 实施任务清单
```

### propose.md 模板

```markdown
# <feature-name>

## Purpose
<一句话描述为什么要做这个变更>

## Scope
### In Scope
- <包含的内容>

### Out of Scope
- <明确不包含的内容>

## Background
<必要的背景上下文>

## Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| ...  | ...    | ...        |

## Dependencies
- <前置依赖项>
```

### specs/<capability>/spec.md 模板

```markdown
## ADDED Requirements

### Requirement: <Requirement Name>
The system SHALL <requirement description>.

#### Scenario: <Scenario Name>
- **WHEN** <condition>
- **THEN** <expected outcome>

## MODIFIED Requirements

### Requirement: <Existing Requirement Name>
<updated description with changes highlighted>

## REMOVED Requirements

### Requirement: <Removed Requirement Name>
**Reason**: <为什么移除>
```

### design.md 模板

```markdown
# Design: <feature-name>

## Architecture Overview
<高层架构决策>

## Data Model Changes
<涉及的数据模型变更>

## API / Interface Contract
<对外接口契约变更>

## Migration Strategy
<数据迁移/兼容性方案>
```

### tasks.md 模板

```markdown
# Tasks: <feature-name>

## 1. <Phase Name>
- [ ] 1.1 <Task description>
- [ ] 1.2 <Task description>

## 2. <Phase Name>
- [ ] 2.1 <Task description>
```

## 执行步骤

1. **确定 feature-id**: kebab-case 命名（如 `add-user-auth`, `refactor-payment-flow`）
2. **创建目录结构**: 在 `openspec/proposals/<feature-id>/` 下创建上述文件
3. **填充 propose.md**: 基于 grill-me 需求约束清单
4. **填充 specs/**: 定义领域契约 delta，使用 ADDED/MODIFIED/REMOVED 标记
5. **填充 design.md**: 技术方案（如涉及架构变更则必须）
6. **填充 tasks.md**: 拆解为可执行的实施任务，每个任务 2-5 分钟可完成

## 出口条件

- propose.md + specs/ + design.md + tasks.md 均已完成
- 用户明确回复"批准 Proposal"
- 产物提交到 `openspec/proposals/<feature-id>/`

## 衔接

此阶段结束后，自动触发 `superpowers` Skill 进入 TDD 驱动实施阶段。
