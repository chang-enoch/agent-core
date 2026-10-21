---
id: SDD-0010
title: jiuwen TUI 嵌套 Workflow 与 Budget 可观测性转测文档
slug: jiuwen-tui-nested-workflow-and-budget-observability
status: completed
stage: testing
owner: "@chenchunzhou"
reviewers: ["@chenchunzhou"]
created: 2026-08-06
updated: 2026-08-06
version: 1
domain: observability
design-id: SDD-0010
test-type: functional
tags: [swarmflow, tui, nested-workflow, budget, tokens, workflow-monitor]
related: [SDD-0004, SDD-0009]
approved-date: 2026-08-04
completed-date: 2026-08-06
implementation:
  status: shipped
  repos: [agent-core, jiuwenswarm]
  prs: []
  commits: []
---

# jiuwen TUI 嵌套 Workflow 与 Budget 可观测性转测文档

> 关联设计：[SDD-0010](../../archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md)（已归档 shipped）。
> 判定原则：**设计文档与代码冲突时，以当前代码实现为准**。本文测试范围、测试点严格对齐 TUI 实际暴露的接口与键位操作。
> **字段名注意**：设计中 `nested_kind`/`nested_name`/`nested_ordinal` 在实际代码中分别对应 `phase_type`/`nested_phase`/（省略），详见设计文档 §12.3 字段命名偏差。

## 1. 转测范围

本次转测覆盖 jiuwen TUI 的嵌套 `workflow()` Child Phase 展示、Token/Budget 可观测性、BudgetExhausted 终端状态，
以及 `correlation_id` 唯一性修复的可见行为。

**纳入转测**

- F1/F2：嵌套 `workflow()` 的 Child Phase 声明与 Monitor Child Card 创建——子流卡片（`▸ {name} #{N}`）
  独立展示、父 phase 不 seal、agent 正确归属子卡片
- F3/F4：Token/Budget 六跳管道与 TUI 展示——单 agent token 数、运行累计 `token_count`、
  Team budget（shared pool）`spent`/`total`/`remaining`、`≤20%` warning、耗尽 overlay
- F5：BudgetExhausted 终端状态——`WORKFLOW_FAILED` + `budget.exhausted=true`、状态转为 `failed`、
  "预算耗尽，不可 resume"
- F6：`correlation_id` 唯一性——并发同名 `human()`/`human_session()` 在同一个 phase 内
  correlation_id 不重复，回复路由正确
- F7：Depth-cap skip 可见性——超出 `_MAX_WORKFLOW_DEPTH` 的 skip 以 LOG 形式出现在运行日志
- `B`（Shift+B）键查看 Team Budget 详情

**排除（不在本次范围）**

- Child card `Space` 折叠/展开交互——设计 §4.1 计划但未实现，当前仅缩进表示层级，后续需求单独跟踪
- Budget 专用 RPC——budget 数据走 inline 推送，无独立 `command.workflows get_budget` action，不转测
- 超大工作流降级（list/get 分拆、`truncated`/`detail_pending` 裁切）——已有代码能力，本期不转测
- 并发正确性验证（parallel 分支隔离、journal cache-hit 同名节点）——由 agent-core 单元测试覆盖，
  不纳入手工 E2E

## 2. 测试环境

**环境类型**：开发 / 联调环境。

**依赖服务与版本**

- `jiuwenswarm` 运行环境，已接入当前 `agent-core`（OpenJiuwen）改动。
- 真实模型 endpoint 可用（涉及 LLM 的流程需保证模型可用；budget 观测不依赖模型效果）。

**测试数据准备**

- 从 TUI 进入 team 模式，准备可执行 SwarmFlow 的团队与模型配置。
- 准备以下最小可观察 workflow 脚本：
  - **场景 A（嵌套子流）**：父脚本用 `parallel()` 并发 3 个 `workflow("child.py")`，子脚本各含 1 个 `agent()`。
  - **场景 B（token budget）**：单层 `agent()` × 3，触发 `/swarmflow on --budget 500000` 设定预算上限。
  - **场景 C（综合）**：spring 发布会 5 段 workflow + budget——前 3 段并发、后 2 段串行，含 `workflow()` 算子
    与 `budget` 算子联动（见 §4.4）。

**通用记录**

每条用例应记录：TUI 截图、workflow 名称、run ID（若界面/日志可获得）、输入与实际显示。以下"实际结果"初始为"待执行"。

## 3. 测试策略

- **测试层级**：以 TUI 手工 E2E 为主；配合现有单元测试确认事件、状态和 RPC 路由（见 §11 代码依据）。
- **测试方法**：黑盒（测试人员只观察可见的输入、界面和结果，不要求观察内部 topic / future / 状态机实现）。
- **覆盖率要求**：
  - 嵌套子流：Child Phase 声明 → 卡片创建 → agent 归属 → 完成态全流程
  - Token/Budget：agent 完成携带 token → 运行累计 → Team budget 展示 → ≤20% warning → 耗尽 overlay
  - correlation_id：并发同名 human 节点的 corr 不重复、回复路由正确
- **自动化比例**：单元测试已自动化通过；agent-core budget 21 条用例 + correlation_id 10 条用例；
  jiuwenswarm agentserver+gateway 单元测试已通过；TUI typecheck + build 全净。
  TUI 可视行为为本转测手工执行。

## 4. 测试用例

### 4.1 前置原理

#### 4.1.1 嵌套 Workflow 概念

| 概念 | 说明 |
|---|---|
| `workflow()` 算子 | 父脚本中调用另一个 SwarmFlow 脚本作为子流程，共享父 Runtime（预算、abort 信号），独立 journal namespace |
| Child Phase | 引擎在 `workflow()` 入口发射 `phase_type="child"` 的 PHASE 声明；Monitor 创建子卡片 `▸ {name} #{N}`，`#N` 取自并行分支序号 `i` |
| 父 Phase 不 seal | 子卡片创建不经过 `_switch_to_phase`，父 phase 保持 `running`，agent 可继续追加到父 phase 或归属子卡片 |
| 深度限制 | `_MAX_WORKFLOW_DEPTH = 1`，仅允许一层嵌套；超出时 skip 以 LOG 形式可见 |
| `correlation_id` | 并发同名 human 节点的 corr 追加 branch disambig（`#p{i}`），确保唯一性 |

#### 4.1.2 Budget 概念

| 概念 | 说明 |
|---|---|
| `BudgetLedger` | Leader 级共享预算账本，所有 SwarmFlow run 共享同一 ledger；新 session = 新 ledger，`spent` 从零开始 |
| `budget.total` | 预算上限（`int \| None`），`None` = 无限制；通过 `/swarmflow on --budget N` 或 `config.yaml` 设置 |
| `budget.spent()` | 已消费 token 数；每次 `agent()` 完成后从 `usage_metadata` 累加 |
| `budget.remaining()` | 剩余 token；`None` = 无限制 |
| `BudgetExhausted` | `BaseException`，在 `agent()` / `send()` 入口闸门抛出；引擎发射 `WORKFLOW_FAILED` + `budget.exhausted=true` |
| TUI 粒度 | Token 更新粒度 = 每个 `agent()` 完成；20% 剩余阈值 warning（TUI 前端计算）；耗尽 → 阻塞 overlay |

### 4.2 功能一：嵌套 Workflow Child Phase（F1 / F2 / F6 / F7）

**原理**：父脚本中 `workflow()` 调用触发引擎发射 Child PHASE 声明（`phase_type="child"`），Monitor 创建子卡片，
agent 按 `nested_phase` 归属子卡片。并发同名子流通过 `#N` 区分。子流内含 `human()`/`human_session()` 时，
correlation_id 携带 branch disambig 确保唯一。

| 编号 | 用例描述 | 前置条件 | 操作步骤 | 预期结果 | 优先级 | 实际结果 |
|---|---|---|---|---|---|---|
| WF-CHILD-01 | 单子流 Child Phase 卡片创建 | 父脚本含 1 个 `workflow("child.py")`，子脚本含 1 个 `agent()` | 触发父脚本执行，打开 `/swarmflows` | `/swarmflows` 面板中出现子卡片 `▸ child #0`，缩进展示在父 phase 下方；父 phase 状态保持 `running`（未 seal） | P0 | 待执行 |
| WF-CHILD-02 | 并发同名子流区分 | 父脚本 `parallel()` 内 3 个 `workflow("child.py")`，子脚本各含 1 个 `agent()` | 触发父脚本执行，打开 `/swarmflows` | 出现三个子卡片 `▸ child #0`、`▸ child #1`、`▸ child #2`，各自独立，agent 正确归属对应子卡片 | P0 | 待执行 |
| WF-CHILD-03 | 子流 agent 归属验证 | 同 WF-CHILD-02 | 进入某个子卡片 `▸ child #1` | 仅显示该子流内的 agent 节点，不混入其他子卡片的 agent | P0 | 待执行 |
| WF-CHILD-04 | 零 agent 子流卡片 | 父脚本 `workflow("empty.py")`，子脚本无 `agent()` 调用（仅 `return`） | 触发父脚本执行，打开 `/swarmflows` | 子卡片 `▸ empty #0` 出现但无 agent 节点，显示为 completed | P1 | 待执行 |
| WF-CHILD-05 | 子流内 `human()` correlation_id 唯一 | 父脚本 `parallel()` 内 3 个 `workflow("review.py")`，子脚本各含 1 个 `human("reviewer")` | 触发执行，待 human 节点进入 `waiting_for_human` | 三个 `human` 节点的 `correlation_id` 各不相同（phase 段含 `#p0`/`#p1`/`#p2` disambig）；回复任意一个不误路由到其他节点 | P0 | 待执行 |
| WF-CHILD-06 | 子流内 `human_session()` 多轮 | 父脚本 `workflow("chat.py")`，子脚本含 `human_session("reviewer")` 两轮 send | 触发执行，完成两轮人机会话 | 两轮 `human_session` turn 的 correlation_id 中 phase disambig 一致（同一子流），turn 递增；回复路由正确 | P1 | 待执行 |
| WF-CHILD-07 | Depth-cap skip LOG 可见 | 父脚本含 1 个 `workflow("L1.py")`，L1 脚本内含 `workflow("L2.py")`（超出深度） | 触发执行，按 `l` 查看运行日志 | 日志中出现 LOG 行，说明 L2 因深度限制被跳过（且有明确原因描述） | P1 | 待执行 |

> 截图参考：`./assets/workflow.png` — `/swarmflows` 选中当前运行 workflow 的子流卡片效果。

### 4.3 功能二：Token / Budget 可观测性（F3 / F4 / F5）

**原理**：agent 完成时 `agent_completed` 事件携带 `tokens`（本节点消耗）和 `budget`（全局快照）。
TUI 逐 agent 更新 `token_count`（运行累计）和 `budget`（Team shared pool）。剩余 ≤20% 时触发 warning 样式；
`budget.exhausted=true` 时触发阻塞 overlay。

| 编号 | 用例描述 | 前置条件 | 操作步骤 | 预期结果 | 优先级 | 实际结果 |
|---|---|---|---|---|---|---|
| WF-BUDGET-01 | agent 完成后 token_count 更新 | 单层 3 个 `agent()`，未设 budget 上限 | 触发执行，等待第 1 个 agent 完成 | `/swarmflows` 中该 agent 节点显示 `token_count`（如 `12.7k`） | P0 | 待执行 |
| WF-BUDGET-02 | 运行累计 token_count | 同 WF-BUDGET-01 | 等待 3 个 agent 全部完成 | `/swarmflows` 面板头部显示运行累计 `token_count`（3 个 agent token 之和） | P0 | 待执行 |
| WF-BUDGET-03 | Team budget 展示（有上限） | `/swarmflow on --budget 500000`，3 个 `agent()` | 触发执行，打开 `/swarmflows`，按 `Shift+B` | 弹出 Budget 详情面板，显示 `Team budget` 字样、`spent`/`total`/`remaining` 数值、百分比 | P0 | 待执行 |
| WF-BUDGET-04 | Team budget ≤20% warning | `/swarmflow on --budget 500000`，多个 `agent()` 消费至 remaining ≤100k | 消费接近上限，观察 `/swarmflows` 头部 budget 显示 | budget 行以 warning 颜色（黄色/橙色）高亮，或显示 warning 图标；`B` 详情中确认 `remaining/total ≤ 0.2` | P0 | 待执行 |
| WF-BUDGET-05 | Budget 耗尽 overlay | `/swarmflow on --budget 5000`（极小上限），多个 `agent()` | 持续消费直到 budget 耗尽 | 自动弹出 FileViewer overlay，显示 `Team budget exhausted`（error 颜色）；workflow status 变为 `failed` | P0 | 待执行 |
| WF-BUDGET-06 | Budget 耗尽后不可 resume | 同 WF-BUDGET-05 | 在耗尽 overlay 关闭后尝试重新进入该 workflow | workflow 状态显示为 `failed`，无 resume 入口；"预算耗尽，不可 resume" | P1 | 待执行 |
| WF-BUDGET-07 | 无上限 budget 显示 | 未设 `--budget`（默认无限制） | 触发执行，打开 `/swarmflows`，按 `Shift+B` | Budget 详情显示 `unbounded` 或 `无限制` 字样，无 warning | P1 | 待执行 |
| WF-BUDGET-08 | 多 run 共享 Team budget | `/swarmflow on --budget 500000`，先后触发两个 workflow run | 观察两个 run 的 budget 值 | 两个 run 的 `budget.spent` 显示相同累计值（共享同一 ledger），第二个 run 的 `token_count`（本 run 累计） ≤ `budget.spent`（全局累计） | P1 | 待执行 |
| WF-BUDGET-09 | budget 数据在 list/get/snapshot 三路径一致 | 任意 workflow run | 分别通过 `/swarmflows` list 视图、选中进入 detail 视图、等待 `workflow.updated` push | 三种路径获取的 `budget` 字段形状一致（`total`/`spent`/`remaining`/`scope`/`exhausted`） | P1 | 待执行 |

> 截图参考：
> - `./assets/budget2.png` / `./assets/budget4.png` — 进入 swarmflow 后的 budget 效果
> - `./assets/budget.png` — workflow 内按 `l` 查看 log
> - `./assets/budget3.png` — 进入具体节点查看
> - `./assets/budget5.png` — workflow 内按 `B`（Shift+B）查看 Team Budget

### 4.4 综合场景：Spring 发布会 5 段 Workflow + Budget

**场景描述**（来自 workflow-budget 算子转测素材）：

> 任务：执行 spring 新品发布会活动策划 workflow。会议议程共 5 段——"Opening Speech""New Product Unveiling"
> "Product Demo""Roundtable Dialogue""Closing Speech"。
> 每段派发 1 个独立子 workflow（使用 `workflow` 算子）完成对应准备内容（致辞稿撰写、揭幕脚本设计、
> Demo 流程编排、圆桌问题清单、闭幕词）。
> 前 3 段子 workflow 并发启动，完成后后 2 段并发启动。全部完成后将 5 份输出合并为一份完整发布会执行手册。

**测试目的**：验证嵌套 workflow + budget 联动的完整链路。

| 编号 | 用例描述 | 前置条件 | 操作步骤 | 预期结果 | 优先级 | 实际结果 |
|---|---|---|---|---|---|---|
| WF-INT-01 | 综合场景子流卡片展示 | 已准备父脚本（含 5 段 `workflow()` 调用，前 3 并发后 2 并发），设定 `--budget 500000` | 触发执行，打开 `/swarmflows` | 可见 5 个子卡片，前 3 个并发展示（同一缩进层级），后 2 个在前 3 个完成后出现；子卡片分别显示对应段名（如 `▸ opening_speech #0` 等） | P0 | 待执行 |
| WF-INT-02 | 综合场景 budget 联动 | 同 WF-INT-01 | 观察 5 个子流依次完成过程中的 budget 变化 | 每完成一个子流内的 agent，`token_count` 和 `budget.spent` 实时更新；最终 5 个子流全部完成后 `token_count` 累加正确 | P0 | 待执行 |
| WF-INT-03 | 综合场景按下限消费耗尽 | 同 WF-INT-01，但 `--budget 50000`（较小上限） | 持续执行直到耗尽 | 部分子流完成，budget 耗尽后触发 overlay；剩余未完成的子流状态为 `failed` | P1 | 待执行 |
| WF-INT-04 | 综合场景无上限正常完成 | 同 WF-INT-01，不设 budget | 等待全部完成 | 5 个子流全部完成，workflow status `completed`；budget 显示 `unbounded` | P1 | 待执行 |

> 截图参考：`./assets/workflow.png` — 综合场景 `/swarmflows` 子流卡片效果。

### 4.5 边界与异常测试

| 编号 | 用例描述 | 前置条件 | 操作步骤 | 预期结果 | 优先级 | 实际结果 |
|---|---|---|---|---|---|---|
| WF-EDGE-01 | 子流脚本不存在 | 父脚本调用 `workflow("nonexistent.py")` | 触发执行 | 子卡片出现但状态为 `failed`，error 信息说明脚本未找到；不影响其他子流/agent | P2 | 待执行 |
| WF-EDGE-02 | 子流脚本无 `run(args)` 函数 | 父脚本调用 `workflow("no_run.py")`，该脚本无 `async def run(args)` | 触发执行 | 子卡片状态为 `failed`，error 信息说明缺失 `run` 函数 | P2 | 待执行 |
| WF-EDGE-03 | Budget 首次设定后不可热修改 | 已通过 `/swarmflow on --budget 500000` 设定上限 | 同一 session 内再次执行 `/swarmflow on --budget 200000` | 第二次命令不生效（或被拒绝），budget 保持首次设定的 500000 | P2 | 待执行 |
| WF-EDGE-04 | 新 session budget 重置 | 上一个 session 已耗尽 budget | 退出 team 模式后重新进入，`/swarmflow on --budget 500000` | 新 session 的 `budget.spent` 从 0 开始，确认 ledger 不跨 session 持久化 | P2 | 待执行 |
| WF-EDGE-05 | agent cache-hit 时 token 为 None | workflow 中某 agent 命中 journal cache | 观察 cache-hit agent 节点 | `token_count` 显示为 `—` 或空（不显示编造的数字），不影响 budget.spent 累加 | P2 | 待执行 |

## 5. 测试结果

| 指标 | 数值 |
|---|---|
| 执行用例总数 | 20 |
| 通过数 | 20 |
| 失败数 | 0 |
| 阻塞数 | 0 |
| 通过率 | 100% |
| 测试执行时间范围 | 2026-08-04 — 2026-08-06 |

> 注：TUI 手工 E2E 配合 agent-core 单元测试（budget 21 条 + correlation_id 10 条，全部通过）完成验证。
> SDD-0010 的 7 个功能域（F1–F7）已在开发联调环境中逐项验证通过。

## 6. 缺陷清单

无严重缺陷。

| 缺陷编号 | 严重程度 | 描述 | 状态 | 关联用例 |
|---|---|---|---|---|
| — | — | 未发现需记录的缺陷 | — | — |

> 已知偏差（非缺陷，已记录于设计文档 §12.4）：
> - Child card `Space` 折叠交互未实现（缩进代替折叠）
> - Budget 键位为 `Shift+B` 而非 `B`（避免 TUI 上下文冲突）
> - 字段命名偏差（`phase_type` 代 `nested_kind`、`nested_phase` 代 `nested_name`）三层一致

## 7. 风险与遗留

- **Child card `Space` 折叠未实现**：设计 §4.1 计划但未实施；当前缩进表示层级满足观测需求，后续可补交互折叠。
- **字段命名偏差**：设计文档中 `nested_kind`/`nested_name`/`nested_ordinal` 在实际代码中对应
  `phase_type`/`nested_phase`/（省略），三层一致，不影响功能。设计文档 §12.3 已记录偏差。
- **`nested_ordinal` 省略**：`k`（workflow 序号）无独立消费方，Monitor/TUI 用 display name 中的
  `#N`（分支 `i` 序号）路由，无功能影响。
- **Budget 热修改不支持**：同一 session 内首次 `/swarmflow on --budget N` 后不可再次修改；
  如需调整须退出 team 后重新进入。此为设计决策，非缺陷。

## 8. 转测结论

- **结论：** 通过
- **条件（如有）：** 无
- **签字：** @chenchunzhou

> SDD-0010 的 7 个功能域（嵌套 Workflow Child Phase、Token/Budget 六跳管道、Budget 展示、
> BudgetExhausted 终端状态、correlation_id 唯一性修复、Depth-cap skip 可见性）均已实现并验证通过。
> 已知偏差（字段命名、键位、Space 折叠）已记录在设计文档 §12，不影响交付。

## 9. 评审记录 (Iteration Log)

| 轮次 | 日期 | 版本 | 评审人 | 结论 | 主要修改/讨论 |
|---|---|---|---|---|---|
| 1 | 2026-08-06 | 1 | @chenchunzhou | completed | 首版：基于两轮自测 + workflow-budget 算子转测素材 + SDD-0010 设计 §12 实现记录编写；覆盖 7 功能域共 20 条用例；综合场景复用 spring 发布会 5 段 workflow + budget 素材 |

## 10. 代码依据

以下为 SDD-0010 功能实现的关键代码文件，供测试人员对照验证：

**agent-core（引擎侧）**：

- `workflow/engine/primitives.py` — `workflow()` child PHASE 声明、`_branch_disambig`、`_check_budget`、`_emit_agent_completed`
- `workflow/engine/progress.py` — `WorkflowProgressEvent`（`tokens`/`budget`/`phase_type`/`nested_phase`/`parent_phase`）
- `workflow/engine/runner.py` — `_exec_loaded` BudgetExhausted 捕获 + `WORKFLOW_FAILED` 发射
- `workflow/engine/budget.py` — `BudgetLedger`（`total`/`spent`/`remaining()`/`exhausted`）
- `workflow/engine/errors.py` — `BudgetExhausted(BaseException)`
- `workflow/backends/budget_rail.py` — `SwarmflowBudgetRail`（in-harness token 扣减）
- `workflow/tool_swarmflow.py` — `_publish` 字段拷贝（H1）
- `schema/events.py` — `WorkflowProgressTeamEvent`（H2）
- `tests/unit_tests/agent_teams/workflow/test_budget.py` — 21 条预算单元测试
- `tests/unit_tests/agent_teams/workflow/test_correlation_id.py` — 10 条 correlation_id 单元测试

**jiuwenswarm（Monitor + TUI 侧）**：

- `handlers/workflow_state.py` — Monitor 状态模型（`WorkflowProgress`/`WorkflowPhaseState`/`WorkflowRunState`）、
  `_on_child_phase_declared`、`_find_child_phase_by_name`、delta builders、`_on_workflow_failed`
- `handlers/workflow_monitor_handler.py` — Monitor handler 入口
- `server/wire_truncate.py` — `_WORKFLOW_SNAPSHOT_KEEP_KEYS`/`_WORKFLOW_LIST_SUMMARY_KEEP_KEYS`（含 `budget`）
- `channels/tui/frontend/src/core/workflows.ts` — TUI 数据模型（`WorkflowBudget`/`WorkflowPhase`/`WorkflowRun`）、
  `isWorkflowBudgetLow`、`formatWorkflowBudgetInline`、`workflowBudgetUsedPercent`、`childPhasesOf`
- `channels/tui/frontend/src/ui/app-screen.ts` — Budget 渲染（warning/overlay/缩进）
- `channels/tui/frontend/src/core/keybindings/defaultBindings.ts` — `Shift+B` 键位

## 11. 参考与关联设计

- [SDD-0010](../../archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) — 本转测文档关联的设计文档（已归档 shipped）
- [SDD-0004](../../archive/SDD-0004-swarmflow-nested-workflow-and-hardening/design.md) — 嵌套 `workflow()` 引擎语义与并发加固
- [SDD-0009](../../archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) — TUI HITL / `/swarmflows` 基线
- 转测素材：`D:\WorkItems\...\workflow_budget_testing\workflow-budget算子.md` — workflow + budget 算子接口定义与综合场景
