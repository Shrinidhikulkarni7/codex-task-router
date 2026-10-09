# Selective routing: the complete decision process

Selective routing is the default in `policy.json`. It uses local text rules to reconsider a selection when the work changes, while retaining it for short checks and continuations. Default rules make no classifier call. The optional [Laya classifier](../skills/codex-model-router/references/laya.md) can compare or supply candidate profiles, with the same retention controls. Neither estimates the cheapest model or evaluates answer correctness. Routing uses one conversation; it does not create subagents.

## From prompt to accepted turn

1. **Launch the proxy.** `router.py auto` checks the existing Codex daemon and opens the native terminal through a private local Unix socket. Your existing Codex authentication, conversation, permissions, and approval UI remain in use.
2. **Check eligibility.** Only a new text-bearing `turn/start` is considered. Active-turn steering, tool results, and identified ephemeral threads keep their native settings.
3. **Honor user control.** A disabled policy or `[route:off]` passes the request through. A profile directive or supported explicit model/effort request takes priority. Previously accepted explicit choices and observed `/model` updates remain pinned. A leading `New task:` or `[route:new]` releases the pin unless that prompt also supplies an explicit choice.
4. **Choose or retain.** The classifier looks at affirmative requested actions and scope, separating recognized steps without treating quoted text as new instructions. An initial/new task can use the resulting profile directly; an ordinary selective-mode follow-up applies the retention rules below. If no rule calls for selection, the current model and effort are reused without a catalog request.
5. **Validate a new choice.** Read the live model catalog and take the first advertised, non-hidden candidate from the selected policy profile. Validate its reasoning effort. An unavailable candidate or unsupported effort produces an error before the affected turn starts; there is no unconfigured substitute.
6. **Submit the same conversation.** Change only model and effort, including their collaboration-mode override fields. Forward the original prompt, thread ID, instructions, permissions, and other fields. Codex still owns approvals and execution.
7. **Commit after acknowledgment.** A valid turn ID commits the requested selection, phase, and pin state in memory. A rejected or unconfirmed request leaves the prior state intact. Completion does not end the routing task.
8. **Observe usage.** Save recognized token/cache counters from the daemon's existing notifications. These are snapshots, not extra inference requests, model attribution, or a bill.

## Recognized phase changes

These examples assume automatically selected, unpinned settings and the shipped policy.

| Current phase | Next prompt | Result |
| --- | --- | --- |
| Easy inspection, Luna / medium | `Implement pagination.` | Coding, Sol / medium |
| Coding, Sol / medium | `Run existing tests.` | Retain Sol / medium |
| Coding, Sol / medium | `Review the changes.` | Retain Sol / medium |
| Coding, Sol / medium | `Diagnose the failing test.` | Debugging, Sol / high |
| Planning, Sol / high | `Implement the approved plan.` | Coding, Sol / medium |
| Coding or debugging | `Investigate the intermittent deadlock.` | Deep debugging, Astra / xhigh |
| Coding or debugging | `Two distinct fixes failed. Diagnose it.` | Deep debugging, based on the user's report |
| Deep debugging, Astra / xhigh | `Run tests.` or `Summarize the findings.` | Retain Astra / xhigh |
| Planning or debugging | `Now summarize these 30 release notes.` | Easy batch, Luna / medium |
| Easy batch, Luna / medium | `Summarize the next one.` | Retain Luna / medium |

The rules recognize affirmative work instructions, optionally introduced by `Now`, `Next`, `Please`, `Can you`, `Could you`, `Would you`, or `Let's`. They consider recognized sentence/step boundaries and keep the strongest work signal in a mixed request. Negated clauses, descriptions without instructions, leading quotations, and fenced/log tails do not select phases. This is narrow English matching, not semantic understanding: ambiguous wording can retain a model when you expected a change. Use a boundary or explicit profile for deterministic control.

Action and scope come before domain words. `Explain deadlocks in one sentence` and `Fix the typo in the deadlock warning` are easy work; they do not trigger Astra. `Implement a compiler` requests higher reasoning, while `Add a button to the compiler settings screen` remains routine coding. A selected `planning` profile changes model/effort only; it does not replace an implementation request with a planning task. See [evaluation evidence and limitations](routing-evaluation.md).

Escalation follows **profile preferences**, ordered as easy/precheck, coding/review/Terra, planning/debugging, then deep-debug. These are not measured rankings of arbitrary configured model IDs. Equal or lower levels normally retain settings. A named hard failure must appear in a recognized work instruction, such as `Investigate the deadlock`, rather than only in a pasted log.

There are two automatic downward transitions: planning to coding when explicitly implementing the **approved plan**, and a substantial summary/extraction batch. A batch requires an easy classification plus a numeric quantity of at least five files, documents, reports, articles, release notes, records, or pages, or the wording `as a batch` / `in bulk`. This threshold is a heuristic for scope, not a measured cost break-even point. Other stronger work signals in that prompt can prevent the downgrade. Ordinary checks never automatically lower an ongoing selection.

Repeated-failure escalation recognizes leading reports such as `Two fixes failed`, `Multiple attempts have failed`, or `Still failing after 2 attempts`. Recognized infrastructure explanations, such as a network outage, permission denial, or missing dependency, suppress that specific escalation. It does not inspect tool errors or verify that fixes were distinct, and other recognized work instructions can still select a profile. Prefer an explicit profile when the text rules miss the actual difficulty.

## Pins, modes, and restarts

- **Explicit choices stay pinned.** `[route:coding]`, `Use Terra`, an effort request, or an observed `/model` update prevents automatic phase changes. Use `New task: ...`, `[route:new] ...`, or another explicit choice to change that selection.
- **Resuming/forking pins reported settings.** Codex supplies current model/effort but not this proxy's earlier pin/phase history. Start a new routing task to resume automatic phase decisions. The conversation history remains.
- **`[route:off]` uses the native request.** Its accepted native settings become pinned; globally disabled turns behave the same way when routing is re-enabled. They may differ from the last routed choice.
- **`task` mode** keeps settings through every ordinary follow-up, including harder work, until an explicit boundary/override. **`prompt` mode** classifies each eligible prompt; native `/model` has priority for one accepted ordinary prompt. All three modes remain available.
- **Source changes require a new proxy process.** Policy reloads on eligible prompts, but editing a profile does not retroactively change a retained selection. Its new values apply when a selection is next requested. No edit changes an active turn.

## Verify it locally

After updating, exit the old routed terminal and launch:

```sh
ROUTER_SCRIPT="${CODEX_HOME:-$HOME/.codex}/skills/codex-model-router/scripts/router.py"
python3 "$ROUTER_SCRIPT" auto
```

In a fresh conversation, send each prompt after the preceding response completes:

```text
Run pwd and list the first five entries. Do not edit files.
Implement a Python function that returns the larger of two numbers. Show the code in your reply only; do not edit files.
Run pwd and list the first five entries. Do not edit files.
New task: Run pwd and list the first five entries. Do not edit files.
Use Sol with medium effort. Reply with OK only.
Summarize the previous answer in one sentence.
```

Expected choices: **Luna, Sol, Sol, Luna, Sol, Sol**, all medium with the shipped policy. Expected `selection.kind` values: `initial`, `phase`, `retain`, `new_task`, `override`, `retain`. The last two records have `selection.pinned: true`.

From another terminal, run `python3 "$ROUTER_SCRIPT" status --thread THREAD_ID` after each step. The ten-record display also includes hook/auxiliary records, so filter by your conversation. Inspect `routing_mode`, `reason`, `selection`, `model`, `effort`, `status`, and `turn_status`. `selection.profile` describes the remembered routing phase; it can be null when no phase is known. A `phase` decision can change only effort or resolve to the same model under a customized policy.

These are suggested live checks, not claims that this exact sequence has already run. The new phase logic is covered by offline tests; the previous [live task-mode verification](usage-and-cost.md#live-task-retention-verification-2026-10-08) tested retention and explicit boundaries. Read [compatibility](compatibility.md) for environment limits and [usage and cost](usage-and-cost.md) before drawing savings conclusions.
