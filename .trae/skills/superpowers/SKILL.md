---
name: superpowers
description: TDD 驱动实施与归档阶段。桥接 OpenSpec proposal → 工程级 RED-GREEN-REFACTOR 循环 → 归档闭环。触发条件：OpenSpec Proposal 已批准。
disable-model-invocation: true
---

# Superpowers：TDD 驱动与归档

## 目标

将 OpenSpec 阶段产出的 proposal + tasks.md，以 TDD（测试驱动开发）方式完成代码编写并归档。

## 核心理念

### 测试哲学

- **测试行为，不测实现**: 通过公共接口验证行为，不测内部实现细节
- **好测试**: 读起来像规格说明书 — "用户可以用有效购物车结账" 告诉你系统有什么能力
- **坏测试**: 耦合实现 — 重构后测试挂了但行为没变 = 测试测的是实现，不是行为

### 垂直切片（严禁水平切片）

```
错误（水平切片）:
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

正确（垂直切片）:
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
  ...
```

一次一个测试 → 一次一个实现 → 每次循环都从上一个循环学到东西。

## TDD 工作流

### Step 1: 桥接转化（Proposal → 测试计划）

1. 解析 `openspec/proposals/<feature-id>/propose.md` 和 specs/
2. 提取所有 ADDED/MODIFIED 需求中的 Scenario
3. 将每个 Scenario 转化为对应的测试用例
4. 输出测试计划（在对话中展示，无需单独文件）

### Step 2: TDD 循环

对每个测试用例执行 RED-GREEN-REFACTOR：

```
RED:   写测试 → 确认失败（断言的是行为意图）
GREEN: 写最少代码让测试通过 → 确认通过
REFACTOR: 重构优化 → 确认所有测试仍通过
```

**规则**:
- Never refactor while RED — 必须先绿
- 不写超过当前测试需要的代码（YAGNI）
- 不预判未来测试
- 每个循环完成后再开下一个
- 使用 `code-review-graph` 定位影响范围

### Step 3: 代码审查

实现完成后，使用 `code-review-graph` MCP 工具：
- `get_review_context_tool` 获取变更文件的 blast radius
- 检查是否有遗漏的依赖影响
- 运行全部相关测试

### Step 4: 归档闭环

```
1. 移动 proposal 到 archive:
   openspec/proposals/<feature-id>/
   → openspec/proposals/archive/<YYYY-MM-DD>-<feature-id>/

2. 更新 code-review-graph 索引（如有变更触发增量更新）

3. Commit 提交信息格式:
   feat(<scope>): <description>
   
   OpenSpec: <feature-id>
```

## 检查清单（每周期）

```
[ ] 测试描述的是行为，不是实现
[ ] 测试只使用公共接口
[ ] 测试在内部重构后仍然有效
[ ] 代码仅满足当前测试的最小量
[ ] 没有预判性功能
[ ] 所有测试通过后再重构
```

## 测试反模式（Avoid）

| 反模式 | 示例 | 问题 |
|--------|------|------|
| 测私有方法 | `testCalculateTax()` 直接调 private | 重构内部实现 → 测试失效 |
| Mock 一切 | 连自己的模块都 mock | 测试与现实脱节 |
| 测数据结构 | `expect(user).toHaveProperty('name')` | 测的是形状不是行为 |
| 过度断言 | 一个测试 10 个 `expect()` | 难以定位失败原因 |
| 外部验证 | 直接查 DB 验证而非通过接口 | 破坏封装 |

## 衔接

归档完成后，一次完整重度开发闭环结束。
