# Compatibility and verification

This project integrates with a local Codex app-server, whose experimental protocol can change. Repository hardening and passing tests do not establish upstream production support. OpenAI's current documentation labels the app-server/WebSocket interface experimental and unsupported for production workloads. [Official App Server documentation](https://learn.chatgpt.com/docs/app-server#protocol).

## Runtime requirements

| Area | Requirement or boundary |
| --- | --- |
| Operating system | macOS or Linux with Unix domain sockets and an interactive terminal |
| Python | 3.11+; standard library only |
| Native CLI | Supports `--remote unix://PATH`, `--cd`, and `resume THREAD_ID` |
| Existing daemon | Reachable via `codex app-server proxy`, optionally `--sock PATH` |
| Protocol for `auto` | HTTP WebSocket upgrade; initialization; thread start/resume; `model/list`; `turn/start`; lifecycle events |
| Account | Existing Codex authentication and access to every selected model/effort |
| Legacy live updates | Experimental `turn/settings/update`, `step_model_switching`, a loaded active target, and compatible admission requirements |
| Optional hook | `UserPromptSubmit` event with session/turn IDs, hook discovery, and native trust |

The router does not offer a Windows transport, remote TCP/TLS configuration, arbitrary Codex argument passthrough, an inference backend, or automatic routing of independently opened app windows. Child agents and already captured inference requests are not retroactively updated. A standalone Codex process without an accessible shared daemon cannot use `auto` or the live helper; `run` can still choose initial CLI settings from a local cache.

The public API describes selecting `model` and `effort` at `turn/start`, and steering a running turn separately. A skill loaded inside an already admitted turn does not control its original start parameters. [Official turn API](https://learn.chatgpt.com/docs/app-server#start-a-turn).

## Evidence as of 2026-10-08

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| User reported successful `auto` use in the Codex 0.160.0 setup | The user observed the per-prompt terminal workflow working in that environment | Universal compatibility, a measured inference trace, or a reproducible performance benchmark |
| User previously verified `run` with Luna / medium and Sol 6.1 | Initial-session launch behavior worked there | Every later prompt was routed by `auto` |
| User-run directory listing in 0.160.1, checked against local rollout and daemon diagnostics | The user turn requested Luna / medium, completed, and its usage counters matched `status`; a separate title-generation thread exposed an unintended Sol selection | A cost comparison, or live verification of the subsequent ephemeral-thread exclusion |
| User-provided status from a new live run after the fix, 2026-10-07 | The listing was accepted on Luna / medium and completed; the separate ephemeral turn was skipped by routing and completed with usage recorded; the legacy hook skipped duplicate routing | The auxiliary model's identity, universal compatibility, or a controlled cost comparison |
| Eight-turn user-run comparison across four models, checked against local records and rollout | Requested model/effort choices matched turn contexts; per-turn usage differences matched reported call counters; switch turns had more uncached input than their following repeats | Exact billing, a model-quality ranking, a cheaper subagent design, or a universal switching penalty; see [measurements and limitations](usage-and-cost.md#observed-model-switch-comparison-2026-10-07) |
| Local `codex --version` subsequently returned 0.160.1 | The inspected CLI binary's version and advertised flags | The running daemon's version or a new live end-to-end test |
| Local generated schemas inspected during development | Expected fields and experimental methods existed in that build | Future schema stability or every runtime feature's enablement |
| Independent simulated native client and daemon fixtures | Protocol forwarding and routing invariants under covered scenarios | Actual model inference, account access, upstream load behavior, or native UI correctness in all versions |
| Task-retention tests and an eight-prompt offline comparison | Related follow-ups retain model/effort; explicit boundaries and overrides select again; the comparison made zero model changes in task mode versus five in prompt mode | New live token savings or a cost comparison; see [local comparison](usage-and-cost.md#what-the-local-comparison-verifies) |
| Selective-phase tests and the extended independent protocol fixture | Clear phase instructions can escalate, approved-plan implementation and qualifying summary batches can lower selection, brief checks retain settings, and explicit choices stay pinned | Live verification of the new phase rules, measured task quality, or cost savings |
| Six-turn user-terminal check on 2026-10-08, verified against a saved baseline, routing records, and local rollout | Sol/Sol/Luna/Luna/Sol/Sol at medium effort; retention, explicit task boundary, override, completion, command output, hook deduplication, and token-counter agreement all matched expectations | A controlled cost comparison, independent backend attribution, or broad task-quality claims; see [live verification](usage-and-cost.md#live-task-retention-verification-2026-10-08) |
| Real Unix-listener smoke test | Socket/launcher integration on hosts that permit it | Coverage on a host where the test is explicitly skipped |

The development agent's sandbox denied local socket binding/control access. Process-pipe fixtures therefore exercised the protocol without real inference; successful user-terminal use is reported separately. Do not collapse these into a claim that the agent independently verified every real model transition.

The local suite after selective routing reported **154 tests: 153 passed and one real Unix-listener smoke test was skipped** because the sandbox denied binding. Python compilation, skill validation, installer dry-run, CLI preview, whitespace, and local documentation-link checks passed. The command-line error path also has a subprocess regression test, preventing an invalid `auto` option from leaking a traceback.

Task and selective tests cover first selection, older policy defaults, retained model and effort, work-phase transitions, repeated-failure reports, batch thresholds, task boundaries, explicit/native pins, rejection/missing-acknowledgment rollback, catalog failures, resume/fork, thread isolation, policy changes, quoted/negated requests, disabled routing, and legacy-hook suppression. An independent client/daemon fixture exercises fourteen prompts over WebSocket frames carried through process pipes, including phase changes, retention, deliberate switches, boundaries, and unchanged approvals.

Usage tests cover snapshot replacement, notification ordering, thread/turn association, disabled routing, malformed data, privacy, bounded history, and local status reads. Temporary-thread tests cover native setting preservation, request/response/notification metadata, lifecycle cleanup, and separate usage recording. The user supplied live status confirming the earlier ephemeral-thread exclusion and later ran the six-turn task-retention check documented above. The agent verified existing local logs and usage-counter differences; it did not launch the live tasks. The read-only control-socket probe was denied by the sandbox. Selective phase rules have not yet had a live user-terminal check, and no controlled cost comparison across the three modes has run. Remote CI results are available in [GitHub Actions](https://github.com/Shrinidhikulkarni7/codex-task-router/actions); the local suite alone does not establish those results.

The title-generation defect was diagnosed from the user's local 0.160.1 logs: a native temporary structured task asked for a conversation title, but its text was classified as implementation work. The proxy now excludes threads identified as ephemeral through protocol metadata rather than matching title-prompt wording. Ordinary user requests to write titles remain eligible for normal routing. Usage records from before the fix are not rewritten.

## Live switching

`turn/settings/update` was present in the inspected local experimental schema but is not described as a stable method on the fetched public App Server page. In the diagnosed 0.160.0 setup it required `step_model_switching`, a feature marked under development and disabled by default in that setup.

An `applied` response confirms settings publication for subsequent captures in the active turn. The async hook can run after the first inference has begun. Captured requests and child sessions retain their previous settings.

Codex rejected a destination that changed the active turn's admitted Node REPL review requirement. At diagnosis time, the local cache marked GPT-6 Astra and GPT-6/6.1 Sol as requiring that review, and GPT-6 Luna plus GPT-5.6 Terra/Sol/Luna as not requiring it. These values explain the observed Astra/Sol-to-Luna rejection; they are not a permanent model compatibility table or a guarantee that any other pair can switch.

The server is authoritative. The router reports rejection and preserves the running turn; it does not alter review requirements, bypass permissions, retry a substitute model, or restart the task. Selecting before a later new turn with `auto` lets Codex evaluate that destination through normal admission.

## Model and performance claims

The shipped model IDs are policy preferences. Model availability, defaults, effort levels, and access can change; `auto`, `apply`, and the hook use the connected catalog. `preview` and `run` use a cache that may be stale. The local rules can misclassify nuanced or mixed tasks.

No benchmark in this repository establishes lower cost, faster completion, higher quality, or fewer retries. Routing adds local processing and catalog round trips. Evaluate correctness and normal Codex usage on representative tasks before adopting or changing a policy. `accepted`, `applied`, and displayed model labels are selection evidence, not independently measured inference usage.

Optional `thread/tokenUsage/updated` recording observes the existing stream without extra requests. Fields were checked against the generated local 0.160.1 schema. The recorder preserves the server's latest snapshot rather than calculating per-turn or per-model usage. It does not calculate billing or aggregate worker threads. See [cache tradeoffs and comparison instructions](usage-and-cost.md).

## Check a Codex upgrade

Before relying on a new version, inspect the installed CLI help and daemon version, run the repository tests, check `doctor` under the intended account/home, and complete a small real `auto` session. Exercise resume, manual selection, a route directive, active steering, and normal exit when those matter to your workflow. Keep the tested version and any skipped checks in release notes.

Tests should remain usable without login, network access, or model calls. Do not turn routine CI into a paid or authenticated live integration test.
