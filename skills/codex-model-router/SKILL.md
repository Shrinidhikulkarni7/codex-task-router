---
name: codex-model-router
description: Select a Codex model and reasoning effort at task or recognized work-phase boundaries, retain related follow-ups, and honor explicit choices. Use when task routing is enabled or the user asks to configure, inspect, or change routing. Automatic sessions and deliberate live changes need an accessible local Codex app-server.
license: MIT. See LICENSE.txt.
---

# Codex Model Router

Use the installed policy to match settings to the requested work. Resolve
`scripts/router.py` relative to this file. Read the effective configuration
with `python3 /absolute/path/to/scripts/router.py config`; personal overrides
in `policy.local.json` merge with shipped defaults. Do not assume particular
model IDs are available or change global Codex defaults.

## Choose the appropriate path

- **Automatic selection:** the user launches `router.py auto` in their terminal.
  Its local proxy selects before eligible turns in one native conversation.
  Let the proxy handle selection; do not repeat it with a live update.
- **Inspect or troubleshoot:** use `config`, `status`, or `doctor`. Read
  [operations](references/operations.md) for command scope, connection failures,
  acknowledgments, usage counters, and live-update prerequisites.
- **Configure preferences:** read [configuration](references/configuration.md).
  Preserve unrelated local settings and explicit user choices.
- **Evaluate semantic routing:** read [Laya](references/laya.md). Rules are the
  default. Do not install dependencies, download weights, start a service, or
  enable Laya unless that work is requested.
- **Explicit active-turn change:** use `apply` only when the user requests that
  change. Read the live-update section of operations first. Never target a
  different thread without an explicit request.

## Reason about the work

| Work | Profile |
| --- | --- |
| Already-known checks or status inspection | `precheck` |
| Bounded mechanical edit, extraction, or summary | `easy` |
| Ordinary implementation | `coding` |
| Routine review or interpretation of checks | `review` |
| Architecture, tradeoffs, broad or unclear implementation | `planning` |
| Root-cause investigation | `debugging` |
| Subtle concurrency, difficult failure, or deliberate escalation | `deep-debug` |
| Straightforward execution when explicitly preferred | `terra` |

Consider affirmative action, scope, ambiguity, and consequences before domain
keywords. Defining a deadlock is bounded work; investigating a deadlock is not.
A local edit inside a compiler differs from building an entire compiler.
`planning` changes model settings; it must not turn an implementation request
into a plan-only response. Mixed requests need enough capability for their
hardest substantive work. Extra-high is an escalation, not every bug's default.

Do not downgrade a difficult task merely because its next step is a test.
Two distinct unsuccessful fixes can justify escalation; network outages,
permissions, and missing dependencies are not failed reasoning attempts.
The automatic rules recognize some such reports but do not count tool failures
or infer that a task is complete. Unrecognized or ambiguous input can retain
settings. Do not portray these heuristics as complete language understanding.

## Preserve continuity and control

Default selective mode retains brief follow-ups. Recognized instructions can
escalate unpinned settings; approved-plan implementation and substantial
summary/extraction batches permit specific downward transitions. Task mode
retains ordinary follow-ups; prompt mode deliberately reclassifies them.

Honor explicit profile/model/effort requests and observed native `/model`
updates. In selective/task modes, these pin the accepted choice until another
override or leading `New task:` / `[route:new]`. A boundary retains history.
Resumes and forks pin Codex's reported settings. A leading `[route:off]` passes
through the native choice; never counteract it with `apply`.

Active-turn steering and identified ephemeral threads preserve native settings.
Only traffic through `auto` is routed. `run` selects only a new session's first
task; the legacy asynchronous hook skips selective/task routing. It is not
needed for `auto` and cannot reproduce pre-turn selection safely during a turn.

## Report evidence accurately

`accepted` confirms a turn acknowledgment; `applied` confirms publication of a
live update. Neither alone proves which model performed inference. Do not
report a recommendation or unconfirmed request as a successful switch.

Keep a suitable model stable when usage matters unless the work warrants a
change. Switching can reduce cache reuse; delegation also consumes context
and inference. The router establishes no savings or model-quality ranking.
Default rules make no classifier inference call. Optional Laya adds local
latency and compute, including in shadow mode. A high reported probability
alone is not grounds to enable active classification.

If access or compatibility prevents a change, explain the limitation once and
continue with existing settings. Do not weaken permissions or review controls,
modify session databases, create replacement tasks, or spawn agents as a
workaround. Preserve the user's task and verification standard.
