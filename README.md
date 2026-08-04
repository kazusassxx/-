# Basic

基于 Trae AI IDE 的全栈工程师 Agent 协作项目，集成需求拷问（Grill-me）、领域规格定义（OpenSpec）、TDD 驱动（Superpowers）和代码图谱分析（code-review-graph）的完整工程闭环。

## 快速开始

```bash
git clone <repo-url>
cd basic
```

在 Trae IDE 中打开此项目，Agent 将自动遵循 `.trae/rules/AGENTS.md` 中的规范。

## 开发流程

### 轻重分流

收到任何开发请求时，Agent 首先判定任务类型：

| 类型 | 流程 | 耗时 |
|------|------|------|
| **轻量**（文案/样式/单文件 <30行） | 意图确认 → 外科手术修改 → 验证 → Commit | 分钟级 |
| **重度**（新功能/模块变更/跨层改动） | Grill → OpenSpec → TDD → Archive | 小时级 |

### 重度流程 4 卡口（Subagent 自动调度）

1. **Grill-me** — `@requirement-griller` 高压逼问所有隐含假设与边缘场景
2. **OpenSpec** — `@spec-writer` 输出 `propose.md` + specs + design + tasks
3. **Superpowers** — `@tdd-implementer` RED-GREEN-REFACTOR TDD 循环驱动实施
4. **Code Review** — `@code-reviewer` 基于 code-review-graph 图谱审查变更影响面

详见 [DEVELOPMENT_SOP.md](DEVELOPMENT_SOP.md)。

## 工具链

| 工具 | 类型 | 用途 |
|------|------|------|
| AGENTS.md | Rule | 全局纪律、分流路由、4卡口流程 |
| requirement-griller | Subagent | 需求拷问卡口 |
| spec-writer | Subagent | 领域规格定义 |
| tdd-implementer | Subagent | TDD 驱动实施 |
| code-reviewer | Subagent | 代码审查（图谱驱动） |
| grill-me / openspec / superpowers | Skill | 各卡口操作手册 |
| code-review-graph | MCP | 代码符号图谱与 blast radius 分析 |

## 项目结构

```
.
├── .trae/
│   ├── rules/AGENTS.md          # Agent 全局行为规范
│   ├── agents/                  # 可复用 Subagent
│   │   ├── requirement-griller.md
│   │   ├── spec-writer.md
│   │   ├── tdd-implementer.md
│   │   └── code-reviewer.md
│   ├── mcp.json                 # 项目级 MCP 配置
│   └── skills/                  # Skill 定义
│       ├── grill-me/SKILL.md
│       ├── openspec/SKILL.md
│       └── superpowers/SKILL.md
├── openspec/
│   └── proposals/
│       └── archive/             # 已完成并归档的提案
├── src/                         # 源代码
├── README.md
└── DEVELOPMENT_SOP.md
```
