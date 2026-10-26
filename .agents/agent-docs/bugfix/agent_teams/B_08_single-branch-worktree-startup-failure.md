# 单分支仓库的 worktree 基线失效导致调查成员未启动

## 元信息

| 项 | 值 |
|---|---|
| 日期 | 2026-10-26 |
| 严重程度 | 高：隔离成员无法启动，任务显示进行中但无实际执行 |
| 范围 | Harness worktree Git 基线解析、TeamAgent 启动失败通知 |
| 关联 spec | `S_05_member-spawn-and-stream.md`、Harness `S_05_tools-contract.md` |
| 测试基线 | 扩展回归 240 PASS，3 项已确认基线失败另列排除；不等同真实模型迁移完成 |

## 现象与根因

2026-10-23 的专家团迁移会话中，三项调查任务进入 `in_progress`，对应成员却回滚到
`unstarted`；日志为 `fatal: invalid reference: origin/main`。Leader 约六分钟后等待
不存在的调查产出。本次不是 worker 心跳超时。

仓库仅跟踪 develop，且未设置 origin/HEAD。旧默认分支检测只探测 main/master，误选
main；`git fetch origin main` 可成功但仅更新 FETCH_HEAD，不受 develop 专用 refspec
跟踪。后端未验证 origin/main 是否可解析便返回它，最终 worktree add 失败。
调度器已先将任务置为进行中；启动异常只被记录，Leader 无法据此发现假性运行。

## 决策

1. 验证 origin/HEAD；回退识别当前已跟踪分支及 main/master/develop。
2. fetch 后再次确认引用，未生成则使用既有本地 HEAD 回退，不使用 FETCH_HEAD 偷换基线。
3. 创建时固定已解析 SHA，避免引用在解析和 checkout 间移动。
4. 保留注册/启动分离和 CAS 回滚；真实启动异常以双语通知交给 Leader，同错误去重，
   成功后解除抑制。通知失败不破坏原 best-effort 启动/对账路径。

## 拒绝的方案与边界

- 不伪造 origin/main，不强制 fetch 全分支，也不修改用户 remote 配置。
- 不关闭独立 worktree 或改成共享写入，不调整心跳时限。
- 不把每个 auto_start_member 返回 False 都当故障：已启动/并发抢占同样可返回 False。
- 不将远端默认基线策略全局替换为最新 HEAD；成员后续同步已发布候选仍依工程协议执行。
- 不恢复、重启、清理原实验，不改迁移专家团/Skill/Query。

## 验证

回归覆盖 develop-only、悬空默认引用、自定义跟踪分支、fetch 成功但引用缺失、创建时
SHA 固定，以及单成员/批量/idle 对账失败的通知去重与成功后重新告警。
真实 Git 场景仅使用 pytest 临时仓库，不触碰用户工程或网络远端。

在独立 Python 进程中从 Git HEAD 加载修复前的 `git.py/backend.py`，两项真实 Git
复现均报 `invalid reference: origin/main`；修复后两项均通过。
扩展回归首轮为 238 PASS / 3 FAIL，三项失败均已在修复前代码上复现：Windows
路径分隔符断言两项、缺失目录异常类型断言一项，未为本修复修改这些无关测试。
补充双语及错误变化测试后，显式排除上述三项的最终复验为 240 PASS / 3 deselected。
其余告警为既有 Pydantic 废弃提示及 scheduler 测试 AsyncMock 未 await 提示，未扩大本次修复范围。

### 更新上游后的复核

2026-10-26 同步实验分支到 agent-core `9949b44a4`、JiuwenSwarm `b040cafc9`。
上游新增调度成员子任务和专家团空名册按需加载；本故障涉及的 Git 基线解析、后端
worktree 创建及 TeamAgent 启动错误处理未改动，因此本修复仍须保留。

更新后扩展覆盖专家创建、成员子任务和 policy rail，结果为 426 PASS / 5 FAIL /
3 deselected。五项失败均为外部 Claude 成员用例所需的可选 `claude-agent-sdk`
未安装，不是 worktree 回归；本次原生模型专家团未因此安装外部 CLI 依赖。
JiuwenSwarm 对应配置、调度与专家团装配测试 109 PASS / 2 SKIPPED；前端生产构建成功。
设置页测试 62 PASS / 1 FAIL，失败为未变动的 success toast 样式精确匹配断言，
与本次修复及新增调度开关无关；未修改无关样式或测试来隐藏该结果。

复验命令（仓库根目录；Python 使用 JiuwenSwarm 当前虚拟环境）：

```text
python -m pytest -o addopts= -q tests/system_tests/harness/tools/worktree/test_single_branch_baseline.py
python -m pytest -o addopts= -q tests/unit_tests/agent_teams/agent/test_member_startup_reconcile.py
```
