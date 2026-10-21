# Team 模式 Permissions 功能串讲

## 1. 这个功能解决什么问题

原来 team 模式下不支持DeepAgent的权限管理。本方案复用已有的 `PermissionInterruptRail` + `ToolPermissionHost` 宿主注入机制，给 teammate 加上工具调用权限管控，并把需要审批（ASK）的工具调用路由到 leader 审批，而不是走前端用户交互。

一句话：**teammate 调工具 → 按规则判 ALLOW/ASK/DENY → ASK 的暂停 teammate 等 leader 审批**。

## 2. 权限三态

teammate 每次调工具前，`PermissionEngine` 评估出三态之一：

- **ALLOW**：直接执行，不暂停。
- **DENY**：直接拒绝，工具结果返回 `[PERMISSION_DENIED]`（后附 reason），不暂停、不发消息。
- **ASK**：暂停 teammate（进入 interrupt），发消息给 leader；leader 用 `approve_tool` 审批后 teammate 才继续。

## 3. 双开关（生效前提）

权限要生效，配置里**两个开关必须同时打开**，缺一不可：

| 开关 | 配置位置 | 作用 |
|---|---|---|
| 全局 `permissions.enabled` | `permissions:` 段 | 控制 `PermissionEngine` 是否工作 |
| team `enable_permissions` | `modes.team.<team>.enable_permissions` | 控制 team 模式是否启用权限 rail |

任一关闭，`TeamPermissionRail` 都不挂载。

配置参考（`jiuwenswarm/resources/config.yaml` 风格）：

```yaml
permissions:
  enabled: true
  schema: tiered_policy
  tools:
    bash: ask
    write_file: deny
    todo_list: allow
  ...

modes:
  team:
    jiuwen_team:
      team_name: jiuwen_team
      enable_permissions: true
      ...
```

注意 `enable_permissions` 在 `config.yaml` 默认是 `false`。两个开关分属不同配置段，职责不同：全局开关是引擎前提，team 开关控制是否在 team 模式下启用权限 rail 替代简单审批。

## 4. ASK 审批流程（最核心的路径）

整条链路：

1. teammate 调用某工具（如 `bash`）。
2. `PermissionEngine` 评估 → ASK。
3. `TeamApprovalOrchestrator.handle_approval_request` 给 leader 发一条消息，返回字符串 `"interrupt"`。
4. teammate 进入 interrupt 暂停。
5. leader 收到消息，消息内容包含：`permission: ASK`、`Member:`、`Tool call ID:`、`Tool:`、`Matched rule:`、`Arguments:`，结尾提示 `Please review and call approve_tool.`
6. leader 调用 `approve_tool(approved=..., auto_confirm=..., feedback=...)`。
7. 审批结果通过**两条通道**送达 teammate（见第 6 节）。
8. teammate 唤醒 → `parse_confirm_payload` → 决定执行或拒绝。

### 4.1 leader 审批不写盘（关键差异）

- leader 审批是 **session 级**，不落盘：`TeamPermissionRail` 覆写 `_persist_allow_always()` 直接返回 `False`，跳过写盘逻辑。
- session 内通过 `INTERRUPT_AUTO_CONFIRM_KEY` 记住"已审批"，同一 session 再调同命令不再审批。
- session 结束后 auto_confirm 清除，新 session 里**仍需重新审批**。

这一点和单 Agent 路径相反：单 Agent 的 `PermissionInterruptRail` 审批**会写盘**、跨 session 生效。

### 4.2 approve_tool 何时保留

双开关都开时，leader **必须**保留 `approve_tool`，否则 teammate interrupt 后没有唤醒路径会卡死。保留判断在 `tool_factory.create_team_tools`：非 plan_mode 下，`not team_permissions_enabled` 才排除 `approve_tool`。

## 5. 权限收窄（override）

leader 创建 teammate 时，可以通过 `spawn_teammate` 的 `permissions` 参数收紧某个工具的权限。

- 参数形状：扁平 `{tool_name: level_string}`，例如 `{"bash": "deny"}`。合法 level：`allow` / `ask` / `deny`。
- **只能收紧，不能放宽**：对每个工具取 `strictest(base_level, override_level)`，数学保证结果 ≤ base 且 ≤ override。所以 base 是 `deny` 时，override 给 `allow` 也会被压回 `deny`。
- override 中 base 没列的工具：先从 base 的 `defaults` 解析兜底级别（per-key > 通配 `"*"` > fallback `ASK`），再与 override 做 `strictest` 合并——**不能直接用 override 值**，否则可能放松 defaults 的约束。
- override 不涉及的工具：保留 base 原值不动。
- 其他维度（`defaults` / `rules` / `approval_overrides` / `permission_mode`）leader 不可调，在参数设计层面就排除了，合并逻辑不碰它们。

### 5.1 override 怎么存

override 持久化到 **`TeamMember.options`** 这个统一 JSON 字段里的 `permissions_override` 子键，形状 `{"model_ref": {...}, "worktree": {...}, "permissions_override": {"bash": "deny"}}`。

- session 重启后 `build_context_from_db` 用 `get_member_permissions_override(teammate)` 从 options 重新读出，注入 `TeamRuntimeContext.permissions_override`。
- provider factory 构建 `TeamPermissionRail` 时调用 `narrow_permissions(base_config, ctx.permissions_override)` 合并一次。override 为 None 时直接用 base config。

### 5.2 不支持热更新

team 路径**不支持热更新**。`ToolPermissionHost` 不设 `get_permissions_snapshot`，`resolve_interrupt` 中 `fresh` 始终为 None → 用初始合并后的配置刷新引擎。override 在构建时合并一次，不参与热更新循环。单 Agent 路径照常支持热更新。

## 6. 审批结果的双通道送达

leader 调 `approve_tool` 后，结果靠两条路送达 teammate：

- **pub-sub 主路**：发布 `ToolApprovalResultEvent`（含 team_name / member_name / tool_call_id / approved / feedback / auto_confirm），通知 teammate "有审批结果了"。teammate 收到通知后从 DB message 读详细数据再 resume。
- **DB message 保底路**：`approve_tool` 同时写一条 `protocol="json"` 的 DB message，content 是 JSON：

  ```json
  {"type": "tool_approval_result", "tool_call_id": "...", "approved": true, "feedback": "", "auto_confirm": true}
  ```

  pub-sub 事件丢失时，teammate 的 mailbox drain 从这条 DB message 直接读到审批数据再 resume。

### 6.1 DB message 解析条件

teammate 侧 `_try_parse_approval_payload` 只在**同时满足**两个条件时才放行：

1. message 的 `protocol` 字段 == `"json"`；
2. content 是合法 JSON，且 `type` == `"tool_approval_result"`。

不满足则返回 None，这条消息不会触发 resume。

### 6.2 interrupt 期间的消息处理

teammate 处于 ASK interrupt 等待审批期间，mailbox drain 不再完全阻塞，而是按 `protocol` 字段选择性放行：

- 用户输入只路由到 leader，teammate 不接收 USER_INPUT 事件。
- `protocol="json"` 且含审批字段的消息放行 resume；其余普通消息 `continue defer`，不抢跑。
- interrupt 清除后，`wake_mailbox_if_interrupt_cleared` 重新触发 drain，此前 deferred 的普通消息才被处理。

## 7. leader 权限描述注入

双开关都开且角色为 leader 时，`TeamPermissionPolicyRail`（在 swarm 侧，参照 `TeamSkillStoragePolicyRail` 模式）往 leader 的系统提示词注入一个 prompt section：

- section 名：`team_permission_policy`，priority=39。
- 内容由 `format_base_permissions_for_desc(config, lang)` 生成，包含 base 权限规则（显式 tools + defaults 兜底）和收窄指导文本（"只能收紧，不能放宽"等），支持 cn/en 双语。
- **只注入给 leader**，teammate 不注入。
