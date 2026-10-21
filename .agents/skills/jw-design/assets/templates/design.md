---
id: D-YYYYMMDD-HHMM-<slug> # Asia/Singapore minute timestamp plus topic; preserve legacy IDs
title: <一句话特性标题>     # 与下方 H1 保持一致
slug: <kebab-slug>        # 必须等于文件夹名的 slug 段（小写、连字符）
status: draft             # draft|in-review|changes-requested|approved|rejected（proposals 阶段）
stage: proposals          # Relative to the design asset root: proposals|active|archive
owner: "@your-handle"     # 单一负责人（DRI）
reviewers: []             # status 进入 in-review 起必须非空
created: YYYY-MM-DD
updated: YYYY-MM-DD
version: 1                # 每完成一轮评审 +1
domain: core              # memory|scheduler|messaging|protocol|harness|security|observability|core|tooling
tags: []
related: []              # 相关（非替代）设计的 id 列表，如 [SDD-0003]
# supersedes: D-YYYYMMDD-HHMM-<slug>   # 若本设计取代某旧设计
# ↓↓↓ 进入开发 / 归档时按生命周期补充 ↓↓↓
# approved-date: YYYY-MM-DD     # status 变 approved 时
# dev-start-date: YYYY-MM-DD    # 移入 active/ 时
# archived-date: YYYY-MM-DD     # 移入 archive/ 时（归档必填）
# implementation:               # 归档必填——通向代码的桥，AI 参考据此定位实现
#   status: not-started         # not-started|in-progress|shipped|partially-shipped|abandoned
#   repos: []                   # 实现所在仓库名 / URL 列表
#   prs: []                     # 完整 PR URL 列表
#   commits: []                 # commit URL 或 repo@sha
#   tracking:                   # 开发仓 issue / epic URL
---

# <一句话特性标题>

## 1. 背景与问题 (Why)

<为什么要做这个特性？解决什么问题或抓住什么机会？现状的痛点是什么？为何现在做？>

## 2. 目标与非目标

**目标**
- <本次要达成的、可验证的具体目标>

**非目标**
- <明确声明不在本次范围内的事项，防止 scope creep>

## 3. 术语与上下文（可选）

<关键术语、相关系统、读者需要的前置知识。无则可删本节。>

## 4. 方案设计 (What / How)

### 4.1 总体架构

<组件划分与职责；架构图放在 `assets/` 内并相对引用，例如 `![架构](assets/architecture.svg)`。>

### 4.2 数据流与时序

<关键流程的数据流 / 时序图，描述请求经过的组件与状态变化。>

### 4.3 接口与数据模型

<对外接口、消息 / 数据结构、契约。建议沿用 Requirement + Scenario 写法：>

> **Requirement:** 系统 SHALL <能力描述>。
> **Scenario:** WHEN <触发条件> THEN <期望结果>。

### 4.4 关键流程

<核心用例的端到端走查，含异常 / 边界处理。>

### 4.5 配置与开关

<新增 / 变更的配置项及默认值；特性开关（Feature Flag）名称与灰度 / 回退策略。>

## 5. 关键决策与权衡 (ADR)

<逐条记录重大选型。每条建议包含：决策 / 背景 / 备选 / 理由 / 影响。>

### 5.1 <决策标题>
- **决策：** <最终选择>
- **背景：** <约束与前提>
- **备选与理由：** <考虑过的方案及取舍>

### 5.2 被否决的备选与取舍理由
<记录"为何没那样做"——被否决的方案及其原因。归档后这是最珍贵的设计资产之一；
内容不多时，本节可降级为一个三级标题下的一段说明。>

## 6. 影响面与兼容性

<受影响的模块 / 接口 / 数据 / 部署；向后兼容性分析；**BREAKING** 变更与迁移策略。>

## 7. 测试与验证

<验收标准；测试策略（单元 / 集成 / E2E）；可度量的成功指标。>

## 8. 可观测性

<日志 / 指标 / 链路追踪 / 告警；上线后用于判断特性是否健康的关键监控项与 SLI。>

## 9. 风险与回滚

<主要风险与缓解措施；回滚 / 降级方案。>

## 10. 开放问题 (Open Questions)

<待讨论 / 待决定的事项清单，在评审过程中逐步收敛清空。>

- [ ] <开放问题 1>

## 11. 评审记录 (Iteration Log)

<开发前每完成一轮评审追加一行，与 frontmatter 的 `version` 同步。>

| 轮次 | 日期 | 版本 | 评审人 | 结论 | 主要修改/讨论 |
|---|---|---|---|---|---|
| 1 | YYYY-MM-DD | 1 | @reviewer | changes-requested | <要点> |

## 12. 实现记录与偏差

<开发中 / 后填写。归档前本节必须有实质内容。>

### 实际实现
<落地概述。>

### 与设计的偏差
<与本设计不一致之处及原因；无则写"无"。>

### 链接
<PR / commit / issue（亦应同步到 frontmatter 的 implementation 块）。>

### 遗留与后续
<已知遗留项、技术债、后续计划。>

## 13. 参考与关联设计

<按 id 引用关联 SDD（如 SDD-0003）、外部资料、原始需求链接。>
