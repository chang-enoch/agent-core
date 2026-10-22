Browse the single experts (`agent_template` packages) **installed** on this machine. An expert is a ready-made persona plus skills / tools; `spawn_expert` turns one into a teammate without you writing its role.

## When to Use

- The user asks for a kind of expert ("bring in a finance expert"): `action="list"` with a `query` to find the package name, then `spawn_expert`.
- Unsure what an expert covers: `action="get"` for its full description, category, tags, skills and runtime.

## Parameters

| Parameter | Usage |
|---|---|
| **action** | `list` (default) lists all; `get` shows one |
| **query** | `list` only: relevance search over package name, display name, tags, category and description, most relevant first; a package name equal to `query` (case-insensitive) comes first. Words need not match the text verbatim |
| **name** | Required for `get`: the expert's **package name** (`name` in the list, not the display name) |

## Output

- `list`: one line per expert, in relevance order when `query` is given — `name` / `display_name` / `category` / `runtime` (`native`, or the external runtime provider such as `claudecode`) / one-line description.
- `get`: package name, display name, full description, category, tags, version, runtime, skill list, install source. Persona text and tool lists are not returned.

Only installed experts are listed; an uninstalled expert cannot be spawned. Expert groups (several experts packaged together) are browsed with `view_expert_groups`.
