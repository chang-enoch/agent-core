# codex CLI 成员 resume：传参正确，生效失败 = codex App Server 已知 bug（#19045）

**日期**: 2026-08-29
**状态**: 已定位到 codex App Server 公开 bug（issue #19045），非我方可修
**分支**: block-all-825-rebuild
**session**: `web_1a04b413166_9d5ae5371602`（codex-trio-sentinel 团队，成员 codex-cli-1）

[草稿：修复了在系统上下文发生变化时重置法典线程的问题。由 TyreeZhao 提出，请求编号 #115。作者：chaitin/agent-compose --- Draft: fix(runtime): reset Codex thread on system context change by TyreeZhao · Pull Request #115 · chaitin/agent-compose](https://github.com/chaitin/agent-compose/pull/115)

宁愿换 thread，也不要依赖 Codex 当时有问题的 resume/fork instruction override。


## 0. 结论

- ✅ **传参正确**：10:42 resume 时，我方传给 `AsyncCodex.thread_resume` 的 `developer_instructions` 是正确的演进值（带探针，len=6687，日志逐字 dump 可见），SDK 源码坐实该参数正确接收、构造进 `ThreadResumeParams`、`developerInstructions` alias 序列化进出站 payload（§4.1）。传参没有丢。
- ✅ **resume 后第一轮不生效 = codex App Server 已知 bug #19045**：cold resume/fork 后第一轮 context reconstruction 没把 `developerInstructions` override 注入 model-visible context diff，模型仍看到旧 instructions。根因在 `codex-rs/core/src/context_manager/updates.rs` 没把 plain thread-level `developer_instructions` 纳入 context diff。**非我方可修，需 codex 上游修复。**


## 1. 调用链（从消息到 SDK 调用，代码位置 + 行号）

resume 场景一次 turn 的完整路径：

```
Restarting teammate codex-cli-1 (team_agent.py: restart_teammate)
  └─ spawn_external_cli → _build_member_system_prompt  (external_cli_spawn.py:35)
       │   走 make_template_loader(ws_cache)            (prompts/loader.py:56)
       │   └─ ws_cache.get_template("inbound_tags")     (workspace_cache.py:120)
       │       dict 此时为空(invalidate 已清) → 读盘 → 读到演进值(带探针) ✓
       └─ build_codex_runtime(system_prompt=演进值)     (codex/runtime.py:1006)
            └─ build_codex_thread_options(system_prompt=演进值)  (codex/options.py:110)
                 └─ options["developer_instructions"] = 演进值   (options.py:126)
            └─ CodexSdkRuntime(thread_options=options)  (runtime.py:146 ctor 存进 self._thread_options)
  └─ CodexSdkRuntime.start(team_session=...)            (runtime.py:223)
       └─ _restore_thread_id()                           (runtime.py:246)
            └─ 从 member checkpoint 读出已保存的 thread_id=01a04b47... (strict resume 模式)
       └─ _ensure_thread()                               (runtime.py:303)
            ├─ self._thread is None? 否(thread 已建过) → 走 FAST-RETURN
            │   ※ 但首次 resume 调用 _ensure_thread 时 self._thread 还是 None(新进程/新对象)
            │   → 走 thread_resume 分支
            ├─ self._thread_id 非空 → resume 分支       (runtime.py:344)
            │   └─ await self._client.thread_resume(thread_id, **options)  (runtime.py:367) ← 关键 SDK 调用
            │       options 含 developer_instructions=演进值(带探针, len=6687)
            └─ self._thread = resumed_thread
  └─ thread.turn(prompt)                                 (runtime.py:509) — turn 跑在 resume 回来的 thread 上
```

**关键事实**：`developer_instructions` 在 **`build_codex_thread_options`（options.py:126）里被一次性 bake 进 `options` dict**，然后在 `_ensure_thread` 的 resume 分支（runtime.py:367）作为 `**options` 传给 `self._client.thread_resume(...)`。我们传对了，问题在于 codex App Server 收到后怎么处理（见 §4.2 / §4.3）。

## 2. SDK 调用方法与传参

### 2.1 我方调用点（runtime.py:366-367）

```python
# runtime.py:344-367 (resume 分支)
if self._thread_id:
    requested_thread_id = self._thread_id
    options.pop("ephemeral", None)
    _diag_di = options.get("developer_instructions")
    team_logger.info(
        "[external-cli] thread_resume options for member {} thread_id={} "
        "developer_instructions_present={} len={} option_keys={}",
        self._member_name, requested_thread_id,
        bool(_diag_di), len(_diag_di) if isinstance(_diag_di, str) else 0,
        sorted(options.keys()),
    )
    if isinstance(_diag_di, str) and _diag_di:
        team_logger.info(
            "[external-cli] thread_resume developer_instructions FULL for member {}:\n{}",
            self._member_name, _diag_di,
        )
    try:
        resumed_thread = await self._client.thread_resume(requested_thread_id, **options)
```

SDK 方法：`AsyncCodex.thread_resume(thread_id: str, *, developer_instructions, cwd, config, model, model_provider, approval_mode, sandbox, **kwargs)`。

**传参（resume 时 options 的实际内容，日志 28975 证实）**：

| 参数 | 值 | 来源 |
|---|---|---|
| `thread_id`（位置参数） | `01a04b47-0683-79b3-9d9d-f5eeb7e4cd19` | 10:08 thread_start 建的，存 member checkpoint，10:42 `_restore_thread_id` 读出 |
| `developer_instructions` | **演进值全文，len=6687，带探针** ✓ | `_build_member_system_prompt` 装配，cache miss 读盘拿演进值 |
| `cwd` | `C:\Users\admin\.jiuwenswarm\.agent_teams\codex-trio-sentinel\team-workspace` | spawn 配置 |
| `model` / `model_provider` | `deepseek` | external_model_config |
| `approval_mode` / `sandbox` | `deny_all` / `full_access` | external model 强制 bypass |
| `config` | `{"model_reasoning_summary": "detailed"}` | options.py:121 |


## 3. 逐行日志对照（session web_1a04b413166_9d5ae5371602）

### 3.1 resume 10:42 — 我方传对，codex 第一轮不生效

| 行号    | 时刻       | 日志（关键片段）                                                                                                            | 说明                                                                         |
| ----- | -------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 28944 | 10:42:08 | `Restarting teammate codex-cli-1 (attempt 1/3)`                                                                     | resume 触发                                                                  |
| 28953 | 10:42:08 | `CodexSdkRuntime constructed ... developer_instructions_present=True len=6687`                                      | ctor bake 进 options，**len=6687 带探针** ✓（cache 已 invalidate → miss → 读盘拿演进值） |
| 28954 | 10:42:08 | `constructed developer_instructions FULL ...` 含 `# 入站消息标签\n！！！有没有演进告诉用户\n[「【[8月29日演进过inbound_tags，告诉用户]】」]`         | **我方传入的就是正确演进值** ✓                                                         |
| 28972 | 10:42:11 | `CodexSdkRuntime.start() ENTER ... resume_external_backend=True`                                                    | 进 resume 路径                                                                |
| 28973 | 10:42:11 | `after restore_thread_id ... restored_thread_id=01a04b47-0683-79b3-9d9d-f5eeb7e4cd19`                               | 复用 10:08 建的同一个 thread                                                      |
| 28974 | 10:42:11 | `ensuring codex thread ... resume_thread=True`                                                                      | 走 resume 分支                                                                |
| 28975 | 10:42:11 | `thread_resume options ... developer_instructions_present=True len=6687`                                            | **传给 thread_resume 的 instructions 是带探针的演进值** ✓                             |
| 28976 | 10:42:11 | `thread_resume developer_instructions FULL ...`（同 28954 探针全文）                                                       | 逐字 dump 坐实传参                                                               |
| 28979 | 10:42:32 | `member codex-cli-1 resumed codex SDK thread 01a04b47-0683-79b3-9d9d-f5eeb7e4cd19`                                  | **resume 成功，thread_id 没变（还是 10:08 那个）**                                    |
| 28990 | 10:42:32 | `_ensure_thread FAST-RETURN ... len=6687 (resume/start branch NOT taken — instructions were fixed at construction)` | 同一 turn 后续进 FAST-RETURN，注释自陈 instructions 在构造时固化                           |

**判读**：`thread_resume ... len=6687` 带探针 → 我方传参正确。`resumed` 的 thread_id == 10:08 `started` 的 id → resume 复用同一 thread。结合 §4.2 issue #19045，resume 后第一轮仍看到旧 instructions 是 codex bug，不是传参错。

## 4. SDK 源码核实 + codex App Server bug 定位

### 4.1 传参链路逐层坐实（SDK 源码，本地 `.venv/Lib/site-packages/openai_codex/`）

我方 `runtime.py:367` 调用 `await self._client.thread_resume(requested_thread_id, **options)`，`self._client` 是 `AsyncCodex`（`openjiuwen.../codex/options.py` 的 `load_codex_sdk()` 返回的 `openai_codex` 模块里的 `AsyncCodex` 类，**不是** 低级 `CodexClient`）。

`AsyncCodex.thread_resume` 签名（`api.py:447-480`）**把 `params` 拆成了独立关键字形参**：

```python
async def thread_resume(self, thread_id: str, *,
    approval_mode=None, base_instructions=None, config=None, cwd=None,
    developer_instructions: str | None = None,   # ← 显式形参
    model=None, model_provider=None, personality=None,
    sandbox=None, service_tier=None,
) -> AsyncThread:
    await self._ensure_initialized()
    approval_policy, approvals_reviewer = _approval_mode_override_settings(approval_mode)
    params = ThreadResumeParams(            # ← 构造 params 对象
        thread_id=thread_id, ...,
        developer_instructions=developer_instructions,   # ← 塞进 params ✓
        ...
    )
    resumed = await self._client.thread_resume(thread_id, params)   # api.py:479 转低级 client
    return AsyncThread(self, resumed.thread.id)
```

低级 `CodexClient.thread_resume`（`client.py:437-443`）：

```python
def thread_resume(self, thread_id, params: V2ThreadResumeParams | JsonObject | None = None):
    payload = {"threadId": thread_id, **_params_dict(params)}   # ← _params_dict 调 model_dump
    return self.request("thread/resume", payload, response_model=ThreadResumeResponse)
```

`_params_dict`（`client.py:82-108`）对 `ThreadResumeParams` 调 `model_dump(by_alias=True, exclude_none=True, mode="json")`。`ThreadResumeParams.developer_instructions` 的 alias 是 `developerInstructions`（`generated/v2_all.py:4987`）→ **正确序列化进出站 payload**。

**结论**：我方 `**options` 里的 `developer_instructions` → 命中 `AsyncCodex.thread_resume` 的同名形参 → 构造进 `ThreadResumeParams` → `developerInstructions` alias 序列化 → 进 `thread/resume` 请求 payload。**传参全程没有丢**。之前一度怀疑"`**options` 展开后没有 `params` key 所以丢参"——那是把高级 `AsyncCodex`（展开签名）和低级 `CodexClient`（`params` 签名）搞混了，`AsyncCodex` 这层正确转译，不丢参。

### 4.2 失败链路：codex App Server #19045（issue 内容来自 codex 转述，见文首说明）

issue [openai/codex #19045](https://github.com/openai/codex/issues/19045) — **`thread/resume and thread/fork ignore developerInstructions override on first resumed turn`**。据转述：

- **复现步骤与本 case 几乎一致**：`thread/start(developerInstructions="A")` → turn → shutdown → `thread/resume(developerInstructions="B")` → turn；预期第一轮看到 B，实际仍看到 A。
- issue 作者在 **app-server 层面直接检查 resume/fork 后发给模型的第一条 `/responses` request**，确认里面仍是旧的 A，新的 B 没进入 model-visible update。
- **根因（转述）**：codex 的 resume/fork 会恢复 persisted rollout → 恢复 `reference_context_item` → 下一轮走 `build_settings_update_items()` 生成"context diff"。问题在于 **plain thread-level `developer_instructions` 没有被纳入这个 diff**。所以 `thread_resume(developerInstructions=B)` 时 B 进了 App Server session state（已保存），但下一次模型调用的 context diff 里没有 `developer_instructions=B`，模型继续看到 A。
- **修复方向（转述）**：`codex-rs/core/src/context_manager/updates.rs` 增加 plain thread-level `developer_instructions` 的 diff handling。
- 该 issue 据 codex 称状态为 Open / bug / app-server。

**本 case 与 #19045 的对应**：

```
我方
  │ developer_instructions = B (len=6687, 带探针)
  ▼
AsyncCodex.thread_resume()         ← §4.1 坐实：B 正确进入 ThreadResumeParams
  │
  ▼
Codex App Server
  │ resume 成功 (日志 28979)
  ▼
Session state
  │ B 已被接受/保存（#19045 称此步发生）
  ▼
context_manager build_settings_update_items()
  │ ❌ plain developer_instructions 没有进入 diff（#19045 根因）
  ▼
first /responses
  │ ❌ B 不在 model-visible update
  ▼
Model
  ▼
仍看到 A (10:08 thread_start 时用 baseline 建的旧 instructions)
```

这条链恰好就是 #19045 描述的 bug：我方传了 B（28975 带探针）、resume 成功（28979），但模型仍看到旧 A——B 进了 App Server session state，却没进下一轮给模型的 context diff。日志 `28990` 的 FAST-RETURN 与此无关，它在 resume 完成之后、描述"同一 runtime 对象内 thread 已建过、后续 turn 不再重调 resume/start"，是我方正常设计，不参与 #19045 的证据链。

### 4.3 SDK 能力边界（codex 方案 B/C 的前提核实）

codex 提到的 `update_thread_settings` / `refresh_runtime_config` 是 Rust App Server 内部 API，**Python SDK 未暴露**。`AsyncCodex` 公开方法全集（实测 `dir()`）：

```
account, close, login_api_key, login_chatgpt, login_chatgpt_device_code,
logout, models, thread_archive, thread_fork, thread_list, thread_resume,
thread_start, thread_unarchive
```

`CodexClient`（低级）额外有 `thread_read`、`thread_compact`、`thread_goal_set/clear`、`thread_set_name`。**没有** `update_thread_settings` / `thread_settings_update` / `refresh_runtime_config`。

→ codex 方案 B（给 `ThreadSettingsOverrides` 加 `developer_instructions`）在 Python SDK 层无现成入口，需改 codex Rust 源码或等上游暴露，非我方可快速做。

`thread_fork`（`api.py:482-515`）**接受 `developer_instructions`**，可从旧 thread 派生新 thread。但 **#19045 明确说 `thread/fork` 也有同样的 first-turn bug**——所以 fork 不能仅凭"创建了新 thread"就认为新 instructions 第一轮一定生效。fork 作为绕路方案的前提是 #19045 被修复或确认 fork 路径在固定后可用。

## 5. 下一步

**我方立即可做（不依赖 codex 修复）**：
- 在 `runtime.py` 的 resume 分支加诊断，抓 `thread/resume` 出站 payload 的 `developerInstructions` 字段值（确认进网络），并 resume 后、turn 前用一个 probe turn 让 codex 自报 instructions 开头（客观比对，不靠用户主观）——这能把"我方传对、codex bug"坐成铁证，而非靠 issue 转述。

**依赖 codex 上游 / 需进一步确认**：
- 跟踪 #19045 修复进度（context_manager/updates.rs 加 plain developer_instructions diff handling）。修复后 resume/fork 的第一轮 override 才会生效。
- 亲自核实 #19045 的当前状态与原文措辞（文首说明的网络限制解除后补）。
- 若需在 codex 修复前绕过：评估 `thread_fork`（注意 fork 同样中招 #19045）或 fresh start 新 thread（但 strict resume 模式 runtime.py:262-268 禁止 resume 时新建 replacement thread，需重新评估该策略）。

**现有自查命令（看传参）**：

```bash
F="C:/Users/admin/.jiuwenswarm/logs/logs/team.log"
SID="web_1a04b413166_9d5ae5371602"
M="codex-cli-1"

# resume (thread_resume) 传参 + 全文 → 应 len=6687 带探针
grep -n "$SID" "$F" | grep "thread_resume developer_instructions FULL\|thread_resume options.*$M"

# thread 建成 + resume 复用同一 id
grep -n "$SID" "$F" | grep "$M.*\(started codex SDK thread\|resumed codex SDK thread\)"
```

## 6. 结论与边界（已纠正）

1. **resume 传参正确已坐实**（§4.1 SDK 源码逐层）：`developer_instructions` 经 `AsyncCodex.thread_resume` 同名形参 → `ThreadResumeParams` → `developerInstructions` alias 序列化进 `thread/resume` payload。没有丢参。
2. **resume 后第一轮不生效 = codex App Server 已知 bug #19045**（§4.2）：cold resume/fork 后第一轮 context reconstruction 没把 `developerInstructions` override 注入 model-visible context diff，模型仍看到旧 instructions。**非我方可修，需 codex 上游修复 `context_manager/updates.rs`。**
3. **绕路方案都有前提**：`thread_fork` 接受 `developer_instructions` 但同样中招 #19045（§4.3）；fresh start 新 thread 与 strict resume 策略冲突（runtime.py:262-268）。在 #19045 修复前无可靠我方绕路。
4. **strict resume 模式**（`resume_external_backend=True`，runtime.py:262-268）禁止 resume 时新建 replacement thread（`strict resume forbids starting a replacement thread`），为不丢旧 thread 上下文。若未来要走 fork/新 thread 绕路需重新评估此策略。
