# Operating the router

Resolve `scripts/router.py` relative to this skill. Commands below use
`ROUTER_SCRIPT` for its absolute path. Python 3.11+, macOS/Linux, and an
authenticated compatible Codex CLI are required. The app-server interface is
experimental; consult the installed CLI help when checking compatibility.

## Start and inspect

```sh
python3 "$ROUTER_SCRIPT" config
python3 "$ROUTER_SCRIPT" doctor
python3 "$ROUTER_SCRIPT" auto --cwd /absolute/path/to/project
python3 "$ROUTER_SCRIPT" auto --thread THREAD_ID
python3 "$ROUTER_SCRIPT" status --thread THREAD_ID
```

`config` and `status` are local reads. `doctor` queries the existing daemon
without changing settings. `auto` opens the native terminal through a private
Unix proxy and selects before eligible `turn/start` requests. Only that
connection is routed. The daemon must already be running; open ordinary Codex
once if needed. `auto` does not require a hook or `step_model_switching`.

If installed as a symlink, keep its source checkout at the same path. A copied
standalone skill needs only the files inside this directory. It can also be
run directly without registering the skill. The full repository contains the
installer, development tests, and evaluations; those are not runtime needs.

## Explicit choices

Use a leading directive for deterministic selection on the next prompt:

```text
[route:planning] Design the retry policy.
[route:deep-debug] Investigate the intermittent deadlock.
[route:off] Use my native model settings for this prompt.
New task: List the files in this directory.
```

Honor explicit profile/model/effort choices and native `/model` updates.
`[route:off]` forwards the native choice and pins it after acceptance in
selective/task modes. Never counteract it with a live update. An unavailable
model or effort produces a visible error and preserves the previous state.

`run "TASK"` selects only the initial model of a new native session.
`preview "TASK"` proposes a rule-based selection using the local model cache;
it starts no inference. Neither command supplies ongoing proxy retention.

## Deliberate live updates

Use `apply` only for an explicitly requested change during an active turn:

```sh
python3 "$ROUTER_SCRIPT" apply --phase debugging
python3 "$ROUTER_SCRIPT" apply --model MODEL_ID --effort high
```

It uses `CODEX_THREAD_ID` unless `--thread` is supplied. Do not target another
thread without an explicit request. The hosting daemon and active turn must
be accessible. `--failed-attempts 2` can escalate two distinct unsuccessful
fixes; infrastructure failures do not count as failed reasoning.

The experimental live method requires `step_model_switching`. If absent,
explain the prerequisite: enable it in the terminal with
`codex features enable step_model_switching`, then start a new session. The
optional asynchronous legacy hook additionally requires prompt mode and
explicit hook installation/trust. It skips selective/task mode and requests
already handled by `auto`; it can finish after inference has begun.

Codex may reject a destination that changes an admitted Node REPL review
requirement. Preserve the running selection; do not alter review settings,
retry substitute models, or restart a task to evade the check. A later prompt
through `auto` is admitted normally. A separate `apply` connection does not
update the proxy's remembered choice.

## Interpret diagnostics

| Record | Meaning |
| --- | --- |
| `accepted` | Codex acknowledged the requested turn, possibly retaining a choice |
| `applied` | A live update was accepted for subsequent inference captures |
| `unconfirmed` | No valid acknowledgment; do not report success |
| `skipped`, `thread_kind: ephemeral` | Native auxiliary work preserved |
| `selection.kind` | Initial, new-task, phase, retain, override, or native decision |
| `selection.pinned` | Whether an explicit/native choice is retained |
| `turn_status` | Reported task completion state |

These are request and protocol records, not independent model attribution.
Filter by the main thread ID; temporary title work has separate records and
usage. Missing token counters are unknown. `token_usage.total` is cumulative
thread usage: never sum it across records. `last` is the latest call snapshot,
not the entire turn. The router does not calculate billing or combine workers.

If sockets, methods, or the target turn are unavailable, state the limitation
once and continue with existing settings. Do not expand permissions, modify
session databases or global defaults, start replacement tasks, or spawn agents
as a workaround. Switching and delegation can both add overhead; compare
correct completed tasks before claiming savings.
