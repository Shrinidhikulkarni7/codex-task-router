# Compatibility and verification

This is an experimental integration with a local Codex app-server. Passing
repository checks does not establish upstream production support. The inspected
OpenAI documentation describes the app-server/WebSocket interface as experimental
and unsupported for production workloads. [Official protocol documentation](https://learn.chatgpt.com/docs/app-server#protocol).

## Runtime requirements

| Area | Requirement |
| --- | --- |
| Platform | macOS or Linux, Unix domain sockets, interactive terminal |
| Python | 3.11+; standard library only for the router |
| CLI | Native `--remote unix://PATH`, `--cd`, and `resume THREAD_ID` support |
| Daemon | Existing local server reachable through `codex app-server proxy` |
| Account | Normal Codex authentication and access to selected models/efforts |
| Automatic routing | Initialization, thread lifecycle, `model/list`, `turn/start` |
| Optional live update | `turn/settings/update`, enabled `step_model_switching`, compatible active turn |
| Optional hook | `UserPromptSubmit`, correct thread/turn IDs, native hook trust |
| Optional classifier | Separate Laya service; extended HTTP contract tested with Laya 0.4.1 |

The inspected CLI was **0.160.1**. Earlier terminal checks also used 0.160.0.
These observations do not identify every running daemon's version or promise
compatibility with newer builds. Check the intended installed version before use.

Windows, remote TCP/TLS transports, arbitrary Codex flag passthrough, and
automatic routing of independently opened app windows are outside scope.
The router does not retroactively change captured inference or child sessions.
A standalone CLI without an accessible daemon can use `run` for initial
selection from a local catalog cache, but cannot use `auto`.

## Verification coverage

| Evidence | Verified scope | Remaining limits |
| --- | --- | --- |
| Offline regression suite | Classification, retention/pins, independent protocol peers, approvals, validation, installer ownership, local configuration, archive isolation | No real model inference or account access |
| CI matrix | macOS/Linux with Python 3.11/3.13; see [actual runs](https://github.com/Shrinidhikulkarni7/codex-task-router/actions/workflows/ci.yml) | A passing revision does not validate another revision or future upstream changes |
| 70 authored rule cases | Development-rubric agreement; [method and provenance](routing-evaluation.md) | Not held-out accuracy or completed-task quality |
| Native terminal checks, October 7–8, 2026 | Request/context agreement, completed tasks, usage snapshots, ephemeral exclusion, boundaries and explicit overrides | Not independent backend attribution or a controlled cost trial |
| Six-turn retention check | Expected Sol/Sol/Luna/Luna/Sol/Sol sequence; [measured records](usage-and-cost.md#live-task-retention-verification-2026-10-08) | Does not exercise every selective phase transition |
| Local Laya comparison, October 9, 2026 | 22 validated responses and two deliberate skips on 24 cases | No recommendation reached the provisional 0.8 threshold |
| Native Laya shadow check | One validated response and one timeout both preserved rule-controlled selection and completion | No general accuracy, latency, or savings guarantee |

Run `python3 scripts/check.py` for current offline results. It tests an isolated
copy with shipped defaults so personal settings cannot contact a classifier.
Unix-listener and loopback HTTP tests skip only when the host explicitly denies
binding. Independent process-pipe and buffered HTTP coverage remain active.

The restricted development environment denied socket binding and live control
access. Native checks were performed in a separate unrestricted terminal, then
verified from saved routing and session records. This distinction matters:
fixture coverage, inspected records, and newly executed live tests are different
evidence. [Laya methods and results](laya-evaluation.md) document the same boundary.

## Live switching

The experimental `turn/settings/update` method requires the hosting build's
`step_model_switching` feature. It publishes settings for later captures in an
active turn. An asynchronous hook can finish after inference has already begun.
`applied` acknowledges publication, not subsequent inference usage.

Codex can reject a destination that changes the turn's admitted Node REPL review
requirement. This occurred in a Sol/Astra-to-Luna transition during development;
it is not a permanent compatibility table. The server is authoritative. The
router preserves the running turn and does not alter review settings or retry
substitute models to evade rejection. `auto` selects before a later turn is
admitted normally and does not require the live-switching feature.

## Model and performance limits

Configured model IDs are preferences checked against the account catalog, not
verified model rankings. `preview` and `run` use a cache that can be stale.
The text rules can miss nuance. Laya active mode remains experimental and is
not enabled by default. No evaluation establishes lower cost, faster completion,
higher task quality, or fewer retries.

`accepted` and displayed model labels describe selections. Optional usage
notifications contain thread snapshots without model attribution; the router
is not a billing meter and does not aggregate child-agent work. See
[usage and cache interpretation](usage-and-cost.md).

## Validate a Codex upgrade

Check CLI help and the intended daemon version, run offline checks, and run
`doctor` under the intended account/home. Complete a small `auto` session with
initial routing, a boundary, a pinned override, resume, native model selection,
active steering, and normal exit when those features matter. Record the exact
version, outcomes, and skipped checks. Keep live inference out of routine CI.
