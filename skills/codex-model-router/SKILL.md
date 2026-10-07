---
name: codex-model-router
description: Route new prompts by task using the installed local Codex router, or apply compatible model and effort changes during an active turn. Use when task routing is enabled or the user asks to route work; automatic sessions and live updates need an accessible local app-server.
---

# Codex model router

Use the task's ambiguity, consequences, and remaining work to choose a profile in [policy.json](policy.json). Read its actual model preferences rather than assuming the shipped defaults. A phase name alone is not a measure of difficulty. The automatic proxy uses local text rules, not an LLM classifier.

| Work | Profile |
| --- | --- |
| Run already-known checks or inspect status | precheck |
| Small mechanical edit, extraction, or summary | easy |
| Ordinary implementation | coding |
| Routine review or interpreting checks | review |
| Architecture, tradeoffs, or an unclear implementation plan | planning |
| Root-cause investigation | debugging |
| Persistent failure after two distinct unsuccessful fixes, subtle concurrency, or a difficult high-consequence problem | deep-debug |
| Straightforward execution when the user prefers Terra | terra |

The shipped policy prefers Sol medium for substantial coding and high for ambiguity; honor configured alternatives such as Terra for implementation. Extra-high is an escalation, not the default for every bug. Running an existing test is scoped work; deciding what its failure means can require deeper reasoning. Do not downgrade a complex task just because the next action is a check. Do not count network outages, permissions, or missing dependencies as failed reasoning attempts.

Respect an explicit model or effort requested by the user. A leading `[route:off]` disables routing for that prompt; do not counteract it with a live update. A leading `[route:PROFILE]` pins the profile for the turn unless the user changes it. Short continuations such as “go ahead” normally retain the current choice; the proxy uses `planning` for an otherwise unclassified prompt in Codex Plan mode. `policy.json` can disable all automatic routing.

For automatic selection on every new prompt in one conversation, the user launches `python3 /absolute/path/to/scripts/router.py auto` from their terminal. This opens the normal Codex TUI through a private local proxy and selects model/effort before each `turn/start`. Ordinary prompts need no route tags. `auto --thread THREAD_ID` resumes a conversation through the proxy. It handles the collaboration-mode overrides, preserves other request fields, and forwards approval requests to the native client. It does not require `step_model_switching`.

Only the terminal opened through `auto` is proxied. The daemon must already be running. A successful native model-settings update observed through this connection takes priority for the next prompt without a route directive; it does not permanently disable classification. New profile choices are checked against the daemon's available models and efforts. Failure is visible before the affected task starts, with no substitute model selected.

The legacy UserPromptSubmit hook attempts live selection in other terminals; it skips prompts claimed by the automatic proxy. The `run` command selects only the initial task of a new session. Do not present `run` or the hook alone as unrestricted automatic routing.

Reassess within a turn only at a material phase change, after a relevant failure, or when the user changes the task. Do not issue a live update merely to repeat the proxy's selection. Avoid repeated switches between adjacent tool calls. Preserve working context, explicit choices, and the verification standard when switching.

Resolve `scripts/router.py` relative to this SKILL.md and run:

```sh
python3 /absolute/path/to/scripts/router.py apply --phase debugging
```

Use `--failed-attempts 2` for the escalation described above. To honor an explicit choice, use `--model MODEL_ID --effort EFFORT`. The script uses `CODEX_THREAD_ID`, validates choices against the connected server's model catalog, and targets the active turn. Do not supply another thread's ID unless the user explicitly requests that target.

The experimental `turn/settings/update` method requires Codex's `step_model_switching` feature and publishes settings for later inference calls in the same turn. `router.py doctor --thread THREAD_ID` checks the feature for a loaded thread without changing settings. If it is disabled, report the prerequisite: `codex features enable step_model_switching` in the user's terminal, followed by a new Codex session. A response of `applied` confirms publication, not that another inference has already used the model. Already captured steps and child sessions retain their previous settings. Never claim a switch succeeded from a recommendation alone.

Codex can also reject a destination that changes the active turn's admitted Node REPL review requirement. This is a compatibility limit, not a transient failure. Keep working with the current selection and explain it once. Do not retry with altered review settings or another model to evade that requirement. `auto` handles selection for the next new prompt before its turn starts; it does not change the requirements of an already running turn. Steering an active turn keeps its model.

In `status`, automatic-session records have `source: "session-proxy"`. `accepted` means Codex acknowledged `turn/start` with the selected parameters; `turn_status` records completion. `unconfirmed` is not success. This does not independently prove inference usage. Protocol tests use independent fixtures and make no model calls. A user reported working `auto` sessions in the 0.160.0 setup on 2026-10-07; that does not establish compatibility with every future daemon or account.

If the helper reports denied socket access, an unsupported method, or no active turn, keep working with the existing model and state the limitation once. Do not request broader execution permissions just to route, edit Codex defaults or session databases, start replacement tasks, or spawn agents as a workaround. The hook runs independently of the agent's shell; its access may differ. Installation and hook trust must be completed by the user in environments where this session cannot write Codex configuration.

Default `install.py` links the skill only; `--legacy-hook` explicitly adds the optional hook. The router uses an experimental upstream interface. Do not describe hardening, tests, or a successful acknowledgment as proof of production support, inference usage, savings, or universal model compatibility.
