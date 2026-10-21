# 设计与交付生命周期

设计资产根目录为 `.agents/agent-docs/designs/`。本文件统一定义字段与状态；
`jw-design` 负责方案形成和评审，`jw-dev` 负责实际开发后的记录、转测与归档。
本规则不改变用户指令或仓库的提交、PR 权限。

## 标识与文档结构

新设计目录及 frontmatter `id` 均为 `D_YYYYMMDD_HHMM_<slug>`，例如
`D_20261021_1530_message-routing`。使用 Asia/Singapore、精确到分钟，slug 为小写英文短横线主题。
同一分钟不同主题各自独立；完整标识重名时确认是否同一设计，不能覆盖、分配递增号或修改历史编号。
已有 `SDD-NNNN` 继续有效，文件名与引用保持不变，`REGISTRY.md` 仅保留旧编号台账。
按完整标识引用，索引提供当前路径，不以阶段路径作为永久标识。

每个阶段目录下的设计文件夹含 `design.md` 和可选 `assets/`。
转测资料位于 `testing/<设计标识>/testing.md`，与其关联设计共享标识；
设计文件之间标识唯一，转测文件通过 `design-id` 指向对应设计，不作为另一篇设计重复登记。
旧格式散落资料保留原位置，见 designs 的 `legacy-documents.md`，不伪造状态或补造历史审批。

## Frontmatter

| 字段 | 约定 |
|---|---|
| `id` | 新分钟时间标识，或历史 SDD 标识 |
| `title`、`slug` | 中文标题与英文主题；slug 对应目录主题 |
| `stage` | 相对设计资产根目录的阶段：proposals / active / archive / testing |
| `status` | 与阶段对应的状态，见下表 |
| `owner` | 真实负责人；未知时明确待确认，不使用示例值冒充 |
| `reviewers` | 真实参与者；进入评审时填写，未知时不得冒充已评审 |
| `created`、`updated` | YYYY-MM-DD；updated 不早于 created |
| `version` | 正整数；每轮实质评审增加版本并记录结论 |
| `domain` | memory / scheduler / messaging / protocol / harness / security / observability / core / tooling |
| `tags`、`related` | 可选主题标签、相关但不替代的完整设计标识 |
| `supersedes`、`superseded-by` | 可选替代关系；确认替代后双向关联 |
| `approved-date` | 实际批准日期；不能以生成文档或开始编码推断批准 |
| `dev-start-date`、`archived-date` | 实际开工、归档日期 |
| `implementation` | 实现事实：status、repos、prs、commits，可选 tracking；无证据时不填已交付 |

`implementation.status`：not-started / in-progress / shipped / partially-shipped / abandoned。
设计中的 PR、commit 定位用于追溯实际实现；spec / feature / bugfix 元信息不需要提交后回填 hash。

## 状态与阶段

| 阶段 | 合法状态 | 维护阶段 |
|---|---|---|
| proposals | draft / in-review / changes-requested / approved / rejected | jw-design |
| active | in-development / on-hold | jw-dev |
| archive | shipped / superseded / abandoned | jw-dev；方向替代交回 jw-design |
| testing | draft / in-review / in-testing / completed / failed / rejected | jw-dev |

- `draft → in-review ⇄ changes-requested`，评审后进入 approved 或 rejected。
- 用户或实际评审者明确确认后记录 approved、approved-date 和评审结论。
- 实际开工后 `approved → in-development`，移动 proposals → active，同步 stage 与开工日期。
- `in-development ⇄ on-hold`；交付确认后进入 shipped，移动 active → archive。
- 开发终止可进入 abandoned，移动 active → archive，说明原因和未完成部分。
- 已交付方案改变方向时创建新设计，以 supersedes / superseded-by 关联；旧设计标为 superseded。
- rejected 留在 proposals，不冒充已交付归档。

移动时同步状态、stage、日期和索引；已跟踪路径使用 `git mv`，未跟踪路径使用普通移动，
这不代表已经获准提交。附件随设计移动，标识不变。

## 开发记录、冻结与转测

开发过程中持续记录真实实现、设计偏差、验证结果及遗留。正文结构按选用模板组织，
不要求固定的章节编号；批准结论不代表已实现，代码合并不代表验收通过。
归档前补齐实现定位、偏差、验证结论和 archived-date。
归档后保留历史决策，允许修复坏链接、追加替代指针；方向变化另建设计。

转测流程为 `draft → in-review ⇄ changes-requested → in-testing → completed / failed`，
failed 经修复后可回到 in-review；明确否决则 rejected，completed / rejected 为该次转测终态。
转测额外记录 `design-id`、`test-type`（functional / integration / e2e / performance / security / regression），
实际转测时记录 approved-date，完成时记录 completed-date。没有真实测试证据不写 completed。

## 内容归属与工具

设计记录问题、方案和决策依据；specs 维护当前契约；features 记录特性落地过程；bugfix 留存故障证据。
开发计划维护依赖、进展与交付条件。相互引用，不复制多份状态或契约。
所有新文档以分钟时间标识为准，模板中的历史编号示例不构成新取号要求。

索引生成器在 `.agents/skills/jw-design/scripts/generate_index.py`，支持显式 `--root`。
复用 core 的 `.venv` 与 PyYAML，不安装钩子或增加 CI 门禁。
可选 frontmatter 工具保留为参考，不要求自动执行；禁止静态检查时不执行。
