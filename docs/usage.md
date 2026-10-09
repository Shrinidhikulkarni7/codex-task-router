# Usage guide

This guide describes the repository's Python CLI. All examples assume macOS or Linux and Python 3.11+. Windows and remote TCP servers are outside this router's current implementation.

## Install

Install and sign in to Codex using its normal setup. Check the binary you will use:

```sh
python3 --version
codex --version
codex login status
codex app-server proxy --help
```

`auto` needs an existing local daemon. Opening ordinary Codex in a terminal starts it in the usual shared-daemon setup. The locally inspected CLI also provides `codex app-server daemon start`; use your installed version's `--help` before using daemon management commands. The router itself never starts, restarts, or replaces the daemon.

Clone into a persistent location and install:

```sh
git clone https://github.com/Shrinidhikulkarni7/codex-task-router.git
cd codex-task-router
python3 install.py --dry-run
python3 install.py
```

The default install creates a `skills/codex-model-router` symlink under `$CODEX_HOME` (or `~/.codex`) pointing to this checkout's skill directory. There is no package download or code copy. Existing `hooks.json` is preserved. Installing the skill alone does not put independently launched Codex windows behind the proxy.

The installer refuses to replace a different file, directory, or symlink at the destination. Move or remove that conflicting installation deliberately before retrying. Keep the checkout at its installed path.

Define the helper path in each terminal where you use these examples:

```sh
ROUTER_SCRIPT="${CODEX_HOME:-$HOME/.codex}/skills/codex-model-router/scripts/router.py"
python3 "$ROUTER_SCRIPT" --help
```

Installation is optional for `auto`. From this checkout you can instead run `python3 skills/codex-model-router/scripts/router.py auto` directly. The installer also makes the companion skill discoverable for routing guidance and explicitly requested compatible live changes.

### A different Codex home or executable

`install.py --codex-home PATH` selects where the installer links the skill and, when requested, edits hooks. It does not change your shell environment. Keep installation and runtime configuration aligned:

```sh
CODEX_HOME=/absolute/path/to/codex-home python3 install.py
CODEX_HOME=/absolute/path/to/codex-home python3 skills/codex-model-router/scripts/router.py auto
```

For the router, `--codex-home PATH` selects only the `models_cache.json` location used by `preview` and `run`. Set the `CODEX_HOME` environment variable when the Codex subprocess itself must use a different home. `--codex /absolute/path/to/codex` selects a binary. `--sock /absolute/path/to/control.sock` selects the existing local daemon's control socket.

## Automatic sessions

From your project directory:

```sh
python3 "$ROUTER_SCRIPT" doctor
python3 "$ROUTER_SCRIPT" auto
```

Other supported starts:

```sh
python3 "$ROUTER_SCRIPT" auto --cwd /absolute/path/to/project
python3 "$ROUTER_SCRIPT" auto "Plan the cache architecture"
python3 "$ROUTER_SCRIPT" auto --thread THREAD_ID
python3 "$ROUTER_SCRIPT" auto --thread THREAD_ID "Continue"
python3 "$ROUTER_SCRIPT" auto --sock /absolute/path/to/control.sock
```

Replace `THREAD_ID` and example paths with your own values. Use the native client's thread information to obtain the ID. Resuming through `auto` preserves the existing conversation; the proxy does not create a replacement task to switch models.

The default `routing_mode` is `selective`. Describe the whole task and its scope in the first prompt. Brief checks and continuations retain the accepted selection; clear work-phase instructions can change it. The classifier distinguishes bounded definitions and literal edits from investigations, and recognizes some broad implementation scopes. Wait for each response to finish before submitting the next prompt. The proxy handles text `turn/start` requests, not individual tool calls, image-only input, tool-output turns, or active-turn steering. It applies to this proxy connection, not to separate app windows or ordinary terminals. Exit the native TUI normally to close the proxy and its temporary socket.

For example, send these prompts one at a time in a new `auto` conversation:

```text
Implement pagination for search results.
Run the existing tests.
Review the changes.
New task: Run pwd and list five entries in this directory.
```

With the shipped policy and available models, the first three stay on Sol / medium; the last selects Luna / medium. `[route:new]` is an alternative to `New task:`. Both must be leading prefixes, are case-insensitive, and are retained in the text forwarded to Codex. They mark a routing boundary within the same conversation; they do not clear history or reset the cache.

The router never infers that an assistant response completed the entire task, and it does not count failed fixes. Selective mode recognizes affirmative phase instructions and specific user reports such as `Two distinct fixes failed`. To escalate deliberately, submit `[route:deep-debug] Investigate this failure` or a supported explicit model request. Explicit choices become pinned until a boundary or override. A wholly new conversation allows fresh classification; `auto --thread THREAD_ID` and native forks pin Codex's reported model/effort because previous pin/phase history is unavailable.

An unclassified first prompt (including a greeting) retains the native choice. In selective mode a subsequent `Implement pagination` can select coding automatically, including after an initial Luna file listing. Ambiguous follow-ups retain settings. Use `New task:` for deterministic fresh classification. See [the complete phase rules and live verification prompts](selective-routing.md).

Ephemeral threads identified through lifecycle metadata, such as Codex's background title-generation threads, retain the native client's settings. Their turns are recorded as skipped and do not use routing policy or catalog lookups. Filter history by your user thread ID when checking a task's selection; auxiliary usage is recorded separately when reported.

`auto` fetches the live model catalog when it needs a new selection. If it cannot select a valid model/effort, that request returns a visible error before the task starts. Correct the policy or request and submit again. It does not silently fall back to a different family.

### Read choices and usage

From another terminal, read recent local records without contacting the daemon:

```sh
python3 "$ROUTER_SCRIPT" status
python3 "$ROUTER_SCRIPT" status --thread THREAD_ID
```

For acknowledged proxy turns, `turn_status` records completion. When Codex reports token usage, `token_usage` contains its latest `last` and cumulative `total` snapshots, including available cache counters. Do not sum cumulative totals across records or interpret them as the cost of the selected model. Missing usage is unknown. These counters are also collected for `[route:off]` prompts, allowing a stable-model comparison through the same proxy. See [usage and cost](usage-and-cost.md) for field meanings, comparison steps, and coverage limits.

Records identify `routing_mode` and include `selection.kind`, `selection.profile`, and `selection.pinned` when a routing decision was made. Kinds are `initial`, `new_task`, `phase`, `retain`, `override`, and `native`. An `accepted` record may confirm retention rather than a switch. A new selection, phase, or pin only replaces the remembered state after an acknowledgment containing a valid turn ID. Rejected or unconfirmed requests keep the previous state. Older records are not backfilled.

### Selection precedence

For an eligible new text prompt in default selective mode:

1. A disabled policy or leading `[route:off]` passes the native client's request through unchanged.
2. A leading `[route:PROFILE]` selects that profile. An unknown profile is an error, even when a choice is retained.
3. Supported explicit model or effort wording is resolved against the live catalog.
4. If a selection exists without a leading `New task:` or `[route:new]`, retain pinned choices. For unpinned choices, the [selective phase rules](selective-routing.md#recognized-phase-changes) can reselect; otherwise retain model and effort without a catalog lookup.
5. Otherwise the classifier chooses a profile from affirmative action and scope signals in the initial/new task.
6. An otherwise unclassified initial/new task in Codex Plan mode uses `planning`.
7. If no profile applies, keep the last accepted choice or the native choice when none is known.

A successful native model-settings update (the protocol path used for `/model`) observed through this connection replaces and pins the choice. A new-task marker or explicit request can select again. Changes in another window or a separate `apply` connection are not observed as manual updates; resume to refresh Codex's reported settings, or request the selection through this proxy.

`[route:off]` forwards the native choice unchanged, which may differ from the last routed choice. Once accepted, that requested choice is pinned for subsequent selective/task follow-ups. Disabling and re-enabling policy has the same effect. A Plan-mode toggle alone does not change a retained model or effort.

With `"routing_mode": "task"`, step 4 always retains settings without phase classification or a catalog lookup. Harder follow-ups need an explicit boundary or override. This is the earlier retention strategy, still available by choice.

With `"routing_mode": "prompt"`, the retention step is omitted. Each recognizable prompt can choose again, and an observed native settings update has priority for one accepted ordinary prompt. Explicit profile/model requests and new-task markers override that one-prompt priority. Unclassified prompts use the same Plan-mode/current-choice fallback. This is the original switching strategy, available by choice.

### Explicit requests

Put directives at the start of the prompt:

```text
New task: Implement pagination.
[route:new] Summarize this short document.
[route:precheck] Run the existing tests.
[route:easy] Correct the spelling in this sentence.
[route:coding] Implement pagination.
[route:review] Review this change.
[route:planning] Design the retry policy.
[route:debugging] Investigate the flaky test.
[route:deep-debug] Diagnose this deadlock.
[route:terra] Implement the approved simple changes.
[route:off] Use the model I selected manually.
```

In `auto`, supported model wording starts with `Use`, `Switch to`, `Stay on`, or `Keep using`, optionally preceded by `Please`. Aliases are `Sol`, `Luna`, `Astra`, and `Terra`; full `gpt-...` model IDs are also accepted:

```text
Use Luna with low reasoning to run the existing tests.
Switch to gpt-6.1-sol with high effort and investigate the failure.
Use Terra to implement the straightforward change.
Use high reasoning for this next step.
```

The last example preserves the known model and requests a new effort. Alias choices use their corresponding policy profiles (`coding`, `easy`, `deep-debug`, `terra`). An exact model ID without an effort uses its advertised default effort, or `medium` when no default is advertised. Only supported efforts are accepted. Natural-language recognition is deliberately narrow: use a directive or CLI flags when exact selection matters.

`preview`, `run`, and the legacy hook do not implement the proxy's natural-language model resolver. Use `--model` and `--effort` with `preview`, `run`, or `apply` for explicit choices. The hook leaves explicit model wording for the companion skill to interpret.

## Customize the policy

Edit [policy.json](../skills/codex-model-router/policy.json) in the checkout. All eight profile IDs must remain present: `precheck`, `easy`, `coding`, `review`, `planning`, `debugging`, `deep-debug`, and `terra`. Each profile contains a nonempty ordered `models` array and an `effort` string. Keep valid JSON; comments and trailing commas are not accepted.

Required top-level fields are `enabled` and `profiles`. The optional `routing_mode` is `"selective"` (default, including policies that omit it), `"task"`, or `"prompt"`. Explicit existing mode values keep their behavior. Each profile permits exactly `models` and `effort`. Model IDs must be nonempty, unique within the profile, and contain no whitespace. Recognized effort names are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`; a recognized name must also be advertised by the selected model. Unknown keys or profile names are errors.

To select Terra for new coding tasks, replace the `coding` entry inside `profiles` with:

```json
"coding": {"models": ["gpt-5.6-terra"], "effort": "medium"}
```

If you deliberately want a fallback across families, explicitly list it, for example `"models": ["gpt-5.6-terra", "gpt-6.1-sol"]`. The router uses exactly the candidates you configure.

Selection takes the first available non-hidden model, then validates the effort on that model. An unsupported effort is an error; the router does not search later candidates for one that accepts it. Availability is determined at runtime and differs by client or account.

`auto` reloads policy for each eligible new prompt. Profile edits apply when a selection is next requested: a boundary/override, or a recognized selective phase change. Repeated work in the same phase retains its accepted settings. Switching modes takes effect on the next eligible prompt: `task` retains the latest choice, `prompt` reclassifies, and `selective` uses phase rules while honoring known pins. Other commands read policy when invoked. No edit changes an active turn. Set top-level `"enabled": false` to stop automatic selections; the proxy still forwards traffic and records skipped eligible prompts.

The default classifier uses ordered text rules, not a learned difficulty score. It considers each recognized affirmative action: bounded definitions, literal edits, summaries, and existing checks can remain small even when they mention difficult concepts. An actual investigation of concurrency/corruption selects `deep-debug`; other investigations select `debugging`. Consequential implementation/review and broad system construction can select `planning`, meaning higher reasoning without changing the requested work. Routine implementation selects `coding`. A one-line helper can select `easy`, but a one-line authorization change remains consequential.

Sentence/step boundaries allow mixed requests to keep their strongest recognized work signal. Quoted spans do not create extra steps, negated clauses are ignored, and fenced/log tails do not supply routing instructions. These are narrow English heuristics: unusual wording and nuanced context can still be missed. The [70-case evaluation](routing-evaluation.md) measures agreement with an authored rubric, not universal accuracy or task quality. See [classify in router.py](../skills/codex-model-router/scripts/router.py) for the implementation.

`auto` also supports optional local Laya classification through top-level `classifier.mode`: `rules` (default), `shadow` (record recommendations but keep rules), or `laya` (experimental active recommendations). Selective/task retention and catalog validation remain in control; prompt mode keeps its per-prompt behavior. See the [complete Laya setup and evaluation guide](../skills/codex-model-router/references/laya.md). Other commands below continue to use the rule classifier; `preview` is not a Laya preview.

## Preview without starting a task

```sh
python3 "$ROUTER_SCRIPT" preview "Run the existing unit tests"
python3 "$ROUTER_SCRIPT" preview --phase debugging
python3 "$ROUTER_SCRIPT" preview --phase coding --failed-attempts 2
python3 "$ROUTER_SCRIPT" preview --model gpt-5.6-terra --effort medium
```

`preview` prints JSON for a fresh selection and makes no inference request. It uses `models_cache.json` from `--codex-home`, `$CODEX_HOME`, or `~/.codex`. The cache can be absent or stale; a preview does not prove that the live daemon can start the same model. It has no task-retention state, so `preview "Run tests"` can propose Luna while the same follow-up in `auto` retains Sol. Ambiguous text returns `unchanged`. Plan mode, manual updates, and natural-language overrides can also differ from `auto`.

`--failed-attempts 2` explicitly escalates `coding` or `debugging` to `deep-debug`; with no phase, it also selects `deep-debug`. An explicit route directive takes precedence. The helper never counts failures from command exit codes. Count distinct unsuccessful fixes, not permission denials, network outages, or missing dependencies.

## Route one initial task

```sh
python3 "$ROUTER_SCRIPT" run "Implement pagination for search results"
python3 "$ROUTER_SCRIPT" run --phase easy "Run pwd and list five entries."
python3 "$ROUTER_SCRIPT" run --model gpt-6.1-sol --effort high "Review this implementation"
python3 "$ROUTER_SCRIPT" run --cwd /absolute/path/to/project "Run the existing tests"
```

`run` requires a task and opens a new interactive Codex session with initial model settings supplied as CLI arguments. It uses the cached catalog for a routed task and needs neither the router's control connection nor `step_model_switching` for initial selection. Ambiguous, disabled, or `[route:off]` tasks launch with native defaults. It routes only the initial task; subsequent prompts are not handled by the automatic proxy. Use `auto` for task retention and explicit task boundaries.

The printed `launching` record describes requested startup arguments. Inspect native `/status` and local routing diagnostics as applicable; a launcher message alone is not inference telemetry.

## Optional legacy hook

The legacy hook does not change settings in selective or task mode. It records `skipped` with a message directing you to `router.py auto`, preventing an older hook from changing the task's selection. To opt into its older behavior, set `"routing_mode": "prompt"` in policy first. Then, from the checkout:

```sh
python3 install.py --legacy-hook --dry-run
python3 install.py --legacy-hook
codex features enable step_model_switching
```

Start a new Codex session, open `/hooks`, and review/trust **Selecting Codex model**. This is Codex's own hook trust requirement. Hook edits may require renewed review. [Official hook discovery and trust](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).

The installer merges one asynchronous `UserPromptSubmit` handler with a 12-second timeout. Other hook handlers are retained, and changed hook configuration is backed up as `hooks.json.router-backup-TIMESTAMP`. The command uses the Python executable that ran the installer. The installer does not enable feature flags or mark a hook trusted. Rerunning default `install.py` preserves an already installed legacy hook; it does not remove it.

Check the relevant project and, when available, the active thread:

```sh
python3 "$ROUTER_SCRIPT" doctor --cwd /absolute/path/to/project --thread THREAD_ID
```

Look for `router_hook.ready: true`, a trusted or managed hook, `live_switching.enabled: true`, and `target_thread.loaded_on_this_server: true`. These describe the server the helper contacted. Hook trust, feature enablement, and policy opting into prompt mode are separate prerequisites.

The hook runs after prompt submission and may arrive after inference starts. Its output can be delivered later in the conversation. It skips prompts claimed by `auto`, so the two mechanisms do not intentionally route the same prompt twice. Unknown follow-ups are skipped by the hook and retain the native thread default. [Official background-hook behavior](https://learn.chatgpt.com/docs/hooks#how-background-hooks-run).

### Apply a compatible change in an active turn

```sh
python3 "$ROUTER_SCRIPT" apply --phase debugging
python3 "$ROUTER_SCRIPT" apply --phase coding --failed-attempts 2
python3 "$ROUTER_SCRIPT" apply --thread THREAD_ID --model gpt-6.1-sol --effort high
python3 "$ROUTER_SCRIPT" apply --thread THREAD_ID --turn TURN_ID --phase review
```

`apply` uses `--thread`, or `CODEX_THREAD_ID` when omitted. It targets the supplied turn or discovers the current in-progress turn. It never creates or resumes a task. `applied` means Codex accepted publication for later inference calls in that turn. Already captured requests and child sessions are unaffected.

`apply` is a deliberate live override and remains available in all three routing modes. It does not update another proxy process's retained choice. Prefer a profile/model request on the next prompt; do not invoke `apply` automatically just because implementation has moved into tests or review.

Codex can reject live changes that alter the admitted Node REPL review requirement. For example, an Astra/Sol-to-Luna switch was rejected in the diagnosed setup. This is a compatibility boundary, not a reason to weaken review settings or retry another model to evade it. Continue on the existing model and use `auto` for a later new prompt. See [compatibility](compatibility.md#live-switching).

## Commands and flags

The parser exposes common flags for all commands, but they only affect the scopes listed here. Unknown flags produce an argument error; arbitrary Codex flags are not forwarded.

| Argument | Applies to | Meaning |
| --- | --- | --- |
| `command` | Required | `auto`, `preview`, `run`, `apply`, `doctor`, `status`, or `hook` |
| `task` | `auto`, `preview`, `run`, `apply` | One quoted text argument; required for `run`, optional elsewhere |
| `--phase PROFILE` | `preview`, `run`, `apply` | One of the eight profiles; a leading route directive takes priority |
| `--failed-attempts N` | `preview`, `run`, `apply` | Nonnegative explicit failure count; relevant escalation begins at 2 |
| `--model MODEL_ID` | `preview`, `run`, `apply` | Exact catalog ID; no silent model substitution |
| `--effort EFFORT` | `preview`, `run`, `apply` | Override effort; use with a routable task, phase, or model |
| `--thread THREAD_ID` | `auto`, `apply`, `doctor`, `status` | Resume, target, inspect, or filter a thread respectively |
| `--turn TURN_ID` | `apply` | Target an explicit active turn; otherwise it is discovered |
| `--cwd PATH` | `auto`, `run`, `doctor` | Native project directory, or project for hook discovery; defaults to current directory |
| `--sock PATH` | `auto`, `apply`, `doctor`, `hook` | Existing daemon's Unix control socket |
| `--codex PATH` | Commands that launch/connect to Codex | Executable name or path; default `codex` |
| `--codex-home PATH` | `preview`, `run` | Model cache directory only; defaults to `$CODEX_HOME` or `~/.codex` |
| `-h`, `--help` | All | Print CLI usage |

`auto` rejects `--phase`, `--model`, `--effort`, and nonzero `--failed-attempts`; put routing choices in individual prompts instead. `hook` reads Codex's event JSON from stdin and is an internal integration command, not a terminal prompt launcher. It uses the event's session/turn IDs.

| Installer flag | Meaning |
| --- | --- |
| No flags | Install the skill link; preserve existing hooks |
| `--legacy-hook` | Also install or update the optional prompt hook |
| `--codex-home PATH` | Installation/configuration destination |
| `--dry-run` | Validate and print intended changes without writing |
| `--uninstall` | Remove this installation's skill link and recognized hook |
| `-h`, `--help` | Print installer usage |

`--legacy-hook` and `--uninstall` cannot be combined. Normal helper errors exit with code 1; argparse usage errors use code 2. A handled legacy-hook routing failure returns JSON feedback and code 0 so routing does not block the task. `auto` and `run` normally return the launched Codex process's exit status.

## Update and remove

Close active routed sessions before updating Python source. Preserve local policy edits, inspect upstream changes, and pull from your checkout:

```sh
git status --short
git pull --ff-only
python3 -m unittest discover -s tests -v
```

The symlink points directly at this source; there is no copied skill to reinstall after a normal update. Start a new `auto` session to load new code. If you use the legacy hook, rerun `python3 install.py --legacy-hook` when its command definition or Python path changes, then check `/hooks` for any required trust review. Upgrading Codex separately can change its protocol or model catalog; recheck `doctor` and a small real session.

To remove the integration from the same checkout and home used for installation:

```sh
python3 install.py --uninstall --dry-run
python3 install.py --uninstall
```

Uninstall removes only the recognized hook and a symlink owned by this checkout. It preserves unrelated hooks, the checkout, diagnostics, backups, and Codex feature flags. It does not stop an already running proxy or undo settings already accepted by a turn. Close routed sessions separately. If you enabled `step_model_switching` solely for the legacy hook, you can disable it separately with `codex features disable step_model_switching`.

After stopping routers, you may delete `skills/codex-model-router/.router-state/` to clear their local diagnostic history. Review any hook backups before deleting them; they may contain unrelated configuration. See [data handling](architecture.md#local-data-and-retention).
