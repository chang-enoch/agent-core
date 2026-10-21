---
id: SDD-0011
title: 可演进 Team 工作区转测文档
slug: evolvable-team-workspace
status: draft
stage: testing
owner: "@xiajing"
reviewers: ["@xiajing"]
created: 2026-08-28
updated: 2026-08-31
version: 1
domain: core
design-id: SDD-0011
test-type: e2e
tags: [agent-teams, workspace, evolution, prompt-template, tool-desc, frontmatter, lazy-cache, path-truth, file-data-store, topology]
related: [SDD-0002, SDD-0003]
---

# 可演进 Team 工作区转测文档

> 关联设计：[SDD-0011](../../archive/SDD-0011-evolvable-team-workspace/design.md)（已归档 shipped）。
> 判定原则：**设计文档与代码冲突时，以当前代码实现为准**。本文测试范围、测试点严格对齐 workspace 实际暴露的接口与文件布局，不保留已被重构 / 废弃的用例。

## 0. 文档导航

本转测由 3 份正文 + 1 份旁证组成，按可演进 workspace 的三类「模型可见文本」分篇：

| 文档 | 覆盖范围 |
|---|---|
| [01-evolvable-workspace.md](./01-evolvable-workspace.md) | Block A/C/B 类演进覆盖：A 类提示词模板（inbound_tags / leader_bootstrap）、B 类成员 / 团队字段（member_prompt / team_card）、C 类 tool 描述（send_message desc + content）的统一落盘与演进生效 |
| [02-message-task-content-spill.md](./02-message-task-content-spill.md) | Block B 正文外置：message / task content 写入 session 文件夹的读写时序与回收 |
| [03-member-directory-linker.md](./03-member-directory-linker.md) | Block C 成员目录链接器：成员 workspace 目录的建链 / 恢复 / 清理 / 迁移拓扑 |
| [2026-08-29-codex-resume-not-our-bug-evidence.md](./2026-08-29-codex-resume-not-our-bug-evidence.md) | 旁证：codex resume 后首轮不生效为 codex App Server 已知 bug（#19045），非本仓回归 |

> 验证截图统一存放于 [`./assets/`](./assets/)。

## 1. 转测范围

本次转测覆盖可演进 Team 工作区的三类「模型可见文本」统一落盘与演进生效机制。

**纳入转测**
- A 类提示词模板演进：`inbound_tags`、`leader_bootstrap`（leader 唯一可见的 A 类系统提示词演进点）。
- B 类成员 / 团队字段演进：`member_prompt`、`team_card`（DB 读取层 overlay）。
- C 类 tool 描述演进：`send_message` desc + `send_message.content`（构造期 + lazy 扫描）。
- 演进生效端到端：pause → 改 md → resume 全链路（含 in-process teammate 共享 cache）。
- Block B 正文外置：message / task content 的写入 / 读取 / 回收时序。
- Block C 成员拓扑：成员 workspace 目录的建链 / 恢复 / 清理 / 迁移。

**排除（不在本次范围）**
- codex 外部 CLI 成员 A 类系统提示词不演进——经旁证认定为 codex App Server 已知 bug（#19045），非本仓回归，不纳入用例。
- 跨 session 预定义成员在其他 team 首次创建用新值——已纳入 01 §5 验证流程，但需真实模型 endpoint。

> **串行优先**：warm resume 场景（同 session）与跨 session 场景分别验证；并行场景不在本版用例。

## 2. 测试环境

**环境类型**：开发 / 联调环境。

**依赖服务与版本**
- `agent-core` 运行环境，`openjiuwen` 改 path editable 联调。
- 真实模型 endpoint 可用（claude `ANTHROPIC_*` / codex `CODEX_API_KEY` env）。

**测试数据准备**
- 准备可执行 Team（test401 报数小队），开启 `evolution_enabled`。
- 使用 `evolve_team_mark.py` 一键标记全部演进点为 evolved 基线。

## 3. 测试点速查

详细用例见各正文文档，此处仅列演进点矩阵速查：

| 演进点 | 类 | 读取路径 | 验证文档 |
|---|---|---|---|
| inbound_tags | A | teammate 系统提示词 section（leader 无此 section） | 01 §4 |
| leader_bootstrap | A | leader 系统提示词唯一 team section | 01 §3.2 / §5 |
| member_prompt | B | _identity / worker 进程 | 01 §4-5 |
| team_card | B | leader roster | 01 §4-5 |
| send_message desc | C | tool 构造期 | 01 §4 |
| send_message.content | C | tool.param | 01 §4 |
| message/task content | B | session 文件夹 | 02 |
| 成员目录链接 | C | 软链接拓扑 | 03 |

> **已知非本仓 bug**：codex 外部 CLI 成员 A 类系统提示词不演进（codex App Server #19045），详见旁证文档。

## 4. 测试策略

**测试层级**：E2E（端到端）。真实 Team + 真实模型 endpoint，按 stop → 改 md → session 恢复全链路验证演进值是否进入模型可见上下文。

**测试方法**：灰盒——以模型实际输出为验收信号（向成员发问核对系统提示词/工具/team-context 里有无演进暗号），辅以磁盘目录与 frontmatter 核对。

**用例分布**：见 §3 演进点矩阵与各正文文档的验证流程章节。

## 5. 测试结果

> status 尚为 draft，尚未执行完整一轮转测；以下为 01/02/03 各文档验证流程中已实跑的 ST 基线（详见各正文文档）。

## 6. 缺陷清单

| 缺陷编号 | 严重程度 | 描述 | 状态 | 关联用例 |
|---|---|---|---|---|
| BUG-001 | 一般 | codex 外部 CLI 成员 A 类系统提示词（inbound_tags）stop→resume 后不演进 | 延期 | 01 §4.1 / §5.4 |

> **根因**：codex App Server 已知 bug #19045（cold resume/fork 后首轮 context diff 未纳入 developer_instructions），非本仓回归。详见 [旁证文档](./2026-08-29-codex-resume-not-our-bug-evidence.md)。本仓不修复；codex 端修复后回归。

## 7. 风险与遗留

- **真实模型 endpoint 依赖**：ST 需 claude `ANTHROPIC_*` / codex `CODEX_API_KEY`，未在 CI 自动化。
- **evolve_team_mark.py 版本**：随 8/29 验证版本归档，后续若接口变动需同步更新脚本。
- **design.md 未收录此缺陷**：SDD-0011 design.md §10/§12 未记录 codex 已知缺陷，建议后续同步补入。

## 8. 转测结论

> status 变为 completed/failed 时填写。

## 9. 评审记录 (Iteration Log)

| 轮次 | 日期 | 版本 | 评审人 | 结论 | 主要修改/讨论 |
|---|---|---|---|---|---|
| 1 | 2026-08-31 | 1 | @xiajing | draft | 3 份正文 + 旁证归档，6 张验证截图入 assets/ |

## 10. 参考与关联设计

- **关联设计**：[SDD-0011](../../archive/SDD-0011-evolvable-team-workspace/design.md)（可演进 Team 工作区，已归档 shipped）
- **关联**：SDD-0002（SwarmFlow 有状态 session 与人机）、SDD-0003（SwarmFlow 中断恢复与持久状态）——`RESUME_FROM_PAUSE` 复用 agent 是演进生效的关键链路。
- **外部**：agent-core `docs/features/F_82_evolvable-workspace.md`、`docs/specs/S_24_evolvable-workspace.md`。
