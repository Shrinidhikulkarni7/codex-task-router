# Diagnostics and troubleshooting

Define `ROUTER_SCRIPT` as in the [usage guide](usage.md). Start with read-only checks:

```sh
python3 "$ROUTER_SCRIPT" doctor
python3 "$ROUTER_SCRIPT" status
```

For a specific project and thread:

```sh
python3 "$ROUTER_SCRIPT" doctor --cwd /absolute/path/to/project --thread THREAD_ID
python3 "$ROUTER_SCRIPT" status --thread THREAD_ID
```

`doctor` contacts the selected daemon but never changes a model or starts a turn. `status` only reads local files. Model IDs shown by `doctor` describe this daemon and account, not universal model access.

## Interpret doctor

| Field | Meaning |
| --- | --- |
| `control_socket: "reachable"` | WebSocket upgrade, initialization, and catalog request succeeded |
| `transport: "websocket-over-unix-proxy"` | Connection used Codex's Unix control transport |
| `models` | Catalog model IDs returned by the connected daemon |
| `live_update` | Explicitly states live switching was not tested |
| `router_hook.found` | This server discovered a matching router hook for the project |
| `router_hook.ready` | A matching hook is enabled and trusted or managed |
| `router_hook.load_issues` | Hook discovery warnings/errors from Codex |
| `live_switching.enabled` | Whether the server reports `step_model_switching`; `null` means unknown |
| `target_thread.loaded_on_this_server` | Whether the requested thread is loaded on this server |
| `recent_routing` | Local recent history, optionally filtered by thread |

A reachable socket alone does not prove that the server hosts your active chat. For live updates, inspect the target thread too. A false hook readiness or disabled live-switching flag does not prevent `auto`: they concern the optional legacy integration. `doctor` may exit successfully with an optional diagnostic error, so inspect the fields rather than relying only on its exit code.

With `--thread`, the feature query uses that loaded thread's refreshed configuration, including project settings. Without a thread it describes server configuration. Another terminal or app can use a different runtime.

## Interpret status

Proxy records have `source: "session-proxy"` and usually `event: "turn/start"`. Connection failures can instead have `event: "connection"`. Hook records identify their event and target IDs when the event provides them.

| Status | Interpretation |
| --- | --- |
| `started` | Record created; selection has not finished |
| `submitted` | Proxy prepared selected settings for forwarding; acknowledgment is pending |
| `accepted` | Codex acknowledged `turn/start` and returned a turn ID |
| `unconfirmed` | Acknowledgment did not establish a turn ID, or the connection closed before acknowledgment |
| `skipped` | No selection was applied; read `reason` for disabled routing, manual priority, or hook deduplication |
| `applied` | A legacy live update was accepted for subsequent captures in the active turn |
| `failed` | Selection, transport, or Codex rejected the operation; read `error` |

For accepted proxy turns, `turn_status` adds the completion status reported by Codex. An accepted turn can still fail during execution. Neither `accepted` nor `applied` proves that a particular model performed inference. The router has no independent usage meter. Native `/status` is useful for checking displayed selection, but is also not a measurement of each inference call.

`status` displays ten recent records; the state directory retains up to 200. No matching records may mean no eligible routing event occurred, a different checkout recorded it, the thread filter is wrong, or state could not be written. Image-only input and active-turn steering do not create normal selection records. Check terminal errors and `history_path`.

## Common failures

| Symptom | Likely cause and next action |
| --- | --- |
| `codex` or `python3` not found | Install the prerequisite and check your shell's `PATH`; use `--codex` for an explicit Codex binary |
| Cannot connect to control socket | Ensure the normal local daemon is running under the intended `CODEX_HOME`; use `--sock` for its explicit socket |
| Permission denied on the control socket or local listener | Run from your normal terminal with existing access; the agent sandbox may deny Unix sockets. Do not weaken Codex permissions to make routing work |
| Timeout during WebSocket handshake | Check the daemon/version/socket. A JSONL stdio endpoint is not this Unix WebSocket transport |
| Timeout during `initialize` or `model/list` | The connection did not complete that RPC. Check the exact stage and daemon health; no successful selection is established |
| Unknown method or field | The installed daemon/client protocol differs. Compare versions and the [compatibility requirements](compatibility.md) |
| `No configured model is available` | None of that profile's IDs is advertised. Check `doctor`, then choose available IDs in the policy or use a valid explicit model |
| Model does not advertise the effort | Use an effort supported by that selected model. The router does not try the next candidate just to satisfy an effort |
| Missing or invalid `models_cache.json` | Open/sign in to Codex so its cache exists, or choose the correct cache via `--codex-home`; `auto` uses the live catalog |
| Policy error | Restore a valid object with `enabled`, the eight known profiles, nonempty model arrays, and supported effort names; remove unknown keys |
| `auto selects each prompt separately` | Remove CLI model/phase/effort overrides; put the choice in a prompt inside `auto` |
| A new prompt unexpectedly retains the current model | It may be active-turn steering, manual one-prompt priority, ambiguous wording, or `[route:off]`; inspect `reason` and selection precedence |
| A follow-up in Plan mode selects planning | This is the Plan-mode fallback for otherwise unclassified prompts |
| Another window does not route | Only the TUI launched through `auto` is proxied. Open or resume that conversation through `auto` |
| No active turn or target no longer active | `apply` only targets running work; do not create a replacement task just to force an update |
| `loaded_on_this_server: false` | The selected daemon does not host that loaded thread; check thread ID, `CODEX_HOME`, and `--sock` |
| `Skill path already exists` | The destination belongs to another installation; inspect it before relocating or removing it |
| Symlinked `hooks.json` refused | Hook mutation cannot replace a symlink safely; manage that file through its existing configuration arrangement. Skill-only installation can remain separate |
| Hook installation changed concurrently | The installer detected an edit; inspect the current file and retry when the writer has finished |

## Legacy live-switching failures

If the hook is missing, explicitly install it with `python3 install.py --legacy-hook`. Start a new session and inspect `/hooks`. The native trust browser owns approval of new or changed hook definitions; the installer does not mark them trusted. [Official hook trust documentation](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).

If `live_switching.enabled` is false or the update reports that it requires `step_model_switching`, enable the feature in your terminal and start a new session:

```sh
codex features enable step_model_switching
```

A feature-query error or `null` state is unknown, not enabled. Hook trust does not enable the feature. Enabling the feature does not guarantee that a model pair is compatible.

`failure_kind: "incompatible_live_switch"` means Codex rejected a change to the active turn's admitted Node REPL review requirement. Retrusting the hook or toggling the feature does not fix that rejection. Keep the running turn's selection; use `auto` to choose before the next new turn or `run` for a new session's initial task. The `next_step` field explains this, including for matching old failures read by `status`.

The hook is asynchronous. Its feedback may arrive after the response you were watching; lack of an immediate quoted message does not establish failure. Use the persisted record and its target IDs. A hook record skipped because `auto` already handled the prompt is expected.

## A safe verification sequence

1. Run the unit tests from a checkout, then run `doctor` in the intended terminal environment.
2. Start `auto` in a disposable working directory with the normal permissions you intend to use.
3. Submit a planning prompt, wait for completion, then a small directory-inspection prompt, then `Continue`.
4. Inspect native selection and `status --thread THREAD_ID`; check that IDs stay in the same conversation and reasons match expectations.
5. If available in your client, change `/model`, submit one prompt, then another recognizable task to check one-prompt priority.

Real prompts can make inference requests and consume normal Codex usage. Automated fixture tests do not. Record the CLI and daemon versions, policy, selected IDs, and observed outcome without claiming measured inference from acknowledgment alone.

Before sharing diagnostics, review errors, paths, thread IDs, and any hook backups for sensitive information. See [security and privacy](../SECURITY.md).
