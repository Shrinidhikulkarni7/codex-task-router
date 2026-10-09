---
name: codex-model-router
description: Select a Codex model at task or recognized work-phase boundaries, retaining settings for brief follow-ups and honoring explicit choices. Use when task routing is enabled or the user asks to route work; automatic sessions and deliberate live changes need an accessible local app-server.
---

# Codex model router

Use the task's ambiguity, consequences, and remaining work to choose a profile in [policy.json](policy.json). Read its actual model preferences rather than assuming the shipped defaults. A phase name alone is not a measure of difficulty. The automatic proxy defaults to local text rules. Optional `classifier.mode: "shadow"` records local Laya recommendations while keeping rule-based routing; `"laya"` opts into experimental semantic classification. Read [the Laya guide](references/laya.md) for setup, limits, evaluation, or classifier diagnostics. Never enable active mode merely because a reported probability is high.

The rules inspect affirmative action and stated scope before domain keywords. A bounded definition or label edit mentioning deadlocks is easy work; investigating an actual deadlock is a hard-failure signal. Building a whole compiler, distributed database, or operating system can use higher reasoning, while a local change inside such a project remains ordinary coding. The `planning` profile changes settings only; it does not replace requested implementation with planning. Mixed requests retain the strongest recognized affirmative signal, and quoted spans do not create extra action clauses. These heuristics can still miss nuance; do not present authored routing-case agreement as real-world accuracy or model quality.

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

Default `"routing_mode": "selective"` selects the first task and retains brief follow-ups. For unpinned selections, recognized affirmative work instructions can escalate profiles, approved-plan implementation can move planning to coding, and substantial summary/extraction batches can select easy. Equal/lower profile levels otherwise retain settings. The proxy handles these decisions before the next turn starts; do not call `apply` to reproduce them during an active turn. A turn completing does not mean the task ended. The router does not infer completion or count tool failures; it recognizes specific reports such as `Two distinct fixes failed` and excludes recognized infrastructure explanations from that escalation. These heuristics do not predict prices or answer quality.

Leading `New task:` or `[route:new]` marks a new task for automatic selection in the same conversation; it does not clear history. A leading `[route:PROFILE]` or supported explicit model/effort wording overrides retention and pins the accepted choice until another override or task boundary. For deliberate escalation, the user can send `[route:deep-debug] ...` on the next prompt. An unclassified first prompt retains the native choice; a later clear implementation instruction can select coding in selective mode, including after a preliminary listing. Ambiguous wording retains settings.

Respect an explicit model or effort requested by the user. A leading `[route:off]` disables routing for that prompt; do not counteract it with a live update. Its native settings become pinned after acceptance. `policy.json` can disable all routing. Optional `"routing_mode": "task"` retains settings through every ordinary follow-up, including harder work; `"prompt"` restores per-prompt classification. Policies missing this field default to selective mode; explicit existing values keep their behavior. The Plan-mode fallback applies only to an unclassified initial/new task or prompt mode, never to a retained follow-up.

For automatic task selection in one conversation, the user launches `python3 /absolute/path/to/scripts/router.py auto` from their terminal. This opens the normal Codex TUI through a private local proxy and supplies model/effort before `turn/start`. `auto --thread THREAD_ID` resumes and pins Codex's reported settings because past manual-choice provenance is unavailable; forks do the same. Use a new-task boundary to allow automatic phase changes again. The proxy handles collaboration-mode overrides, preserves other request fields, and forwards approvals. It does not require `step_model_switching`.

Only the terminal opened through `auto` is proxied. The daemon must already be running. A successful native model-settings update observed through this connection pins the choice; in prompt mode it has priority for one accepted ordinary prompt. A task boundary or explicit request can select again. Other connections' changes are not observed. New profile choices are checked against the daemon's catalog; failure is visible before the affected task starts and leaves the previous selection, phase, and pin intact.

The native client may create ephemeral threads for auxiliary work such as titles. The proxy preserves their native settings when lifecycle metadata identifies them; `status` labels them `skipped` with `thread_kind: "ephemeral"`. Do not interpret a separate auxiliary thread's record as the user's task switching models, or override its settings with a live update. Filter history by the user's thread ID when inspecting that task.

The legacy UserPromptSubmit hook skips changes in selective and task modes. It only attempts live selection in opt-in prompt mode and skips prompts claimed by the automatic proxy. The `run` command selects only the initial task of a new session. Do not present `run` or the hook alone as selective routing or task retention through this proxy.

Use a live update only for a user-requested change during an active turn. Do not issue one to repeat the proxy's selection, automatically downgrade checks, or bypass task retention. Prefer next-prompt overrides through `auto`: a separate `apply` connection does not update the proxy's remembered choice. Preserve working context and the verification standard when switching.

When the user prioritizes usage, keep a suitable model stable through related work unless there is a concrete reason to change it. A new turn is not a cache boundary: switching can reduce prefix reuse. Cheaper model rates or fewer retries can still outweigh that overhead; cache percentage alone does not determine total cost. Subagents consume their own context and work; do not introduce them solely on an unmeasured savings claim. Default rules make no classifier inference call; optional Laya modes use local inference and add latency/resources. Neither establishes savings.

Laya only proposes an allowed work profile in `auto`; it cannot override explicit/native pins, bypass phase retention or catalog validation, or change active turns. Service errors or uncertain results retain ongoing settings and use rule fallback on initial/new tasks. Comparison records are not evidence of better answers. Other router commands and the existing answer-quality runner still use rules; `evals/laya_compare.py` is a separate opt-in local-model evaluation. Do not silently install weights, start a service, or enable Laya for a user who only requested normal routing.

For an explicitly requested compatible live change, resolve `scripts/router.py` relative to this SKILL.md and run:

```sh
python3 /absolute/path/to/scripts/router.py apply --phase debugging
```

Use `--failed-attempts 2` for the escalation described above. To honor an explicit choice, use `--model MODEL_ID --effort EFFORT`. The script uses `CODEX_THREAD_ID`, validates choices against the connected server's model catalog, and targets the active turn. Do not supply another thread's ID unless the user explicitly requests that target.

The experimental `turn/settings/update` method requires Codex's `step_model_switching` feature and publishes settings for later inference calls in the same turn. `router.py doctor --thread THREAD_ID` checks the feature for a loaded thread without changing settings. If it is disabled, report the prerequisite: `codex features enable step_model_switching` in the user's terminal, followed by a new Codex session. A response of `applied` confirms publication, not that another inference has already used the model. Already captured steps and child sessions retain their previous settings. Never claim a switch succeeded from a recommendation alone.

Codex can also reject a destination that changes the active turn's admitted Node REPL review requirement. This is a compatibility limit, not a transient failure. Keep working with the current selection and explain it once. Do not retry with altered review settings or another model to evade that requirement. `auto` handles selection for the next new prompt before its turn starts; it does not change the requirements of an already running turn. Steering an active turn keeps its model.

In `status`, automatic-session records have `source: "session-proxy"`. `selection.kind` distinguishes initial/new-task/phase/retain/override/native decisions; `selection.profile` and `selection.pinned` explain retained state. `accepted` means Codex acknowledged `turn/start`; `turn_status` records completion. `unconfirmed` is not success. None independently proves inference usage. Protocol tests use independent fixtures and make no model calls. Earlier user-terminal runs verified prompt/task routing; they do not establish a live test of the new selective phase rules or compatibility with every future daemon/account.

When present, `token_usage` is the latest server-reported `thread/tokenUsage/updated` snapshot for that turn. Its `total` is cumulative thread usage, not a per-turn amount or a breakdown by selected model; never sum it across routing records. Its `last` is not a whole-turn aggregate. Missing counters are unknown. The proxy collects these counters for `[route:off]` turns too, but does not calculate cost or aggregate child-agent usage. Compare representative completed tasks before claiming savings.

If the helper reports denied socket access, an unsupported method, or no active turn, keep working with the existing model and state the limitation once. Do not request broader execution permissions just to route, edit Codex defaults or session databases, start replacement tasks, or spawn agents as a workaround. The hook runs independently of the agent's shell; its access may differ. Installation and hook trust must be completed by the user in environments where this session cannot write Codex configuration.

Default `install.py` links the skill only; `--legacy-hook` explicitly adds the optional hook. The router uses an experimental upstream interface. Do not describe hardening, tests, or a successful acknowledgment as proof of production support, inference usage, savings, or universal model compatibility.
