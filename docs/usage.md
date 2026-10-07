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

Installation is optional for `auto`. From this checkout you can instead run `python3 skills/codex-model-router/scripts/router.py auto` directly. The installer also makes the companion skill discoverable for compatible live phase changes.

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

Wait for a response to finish, then submit another task normally. Routing applies when the client creates a new text `turn/start`; it does not run for every tool call, image-only input, tool-output turn, or active-turn steering message. It applies to this proxy connection, not to separate app windows or ordinary terminals. Exit the native TUI normally to close the proxy and its temporary socket.

`auto` fetches the live model catalog when it needs a new selection. If it cannot select a valid model/effort, that request returns a visible error before the task starts. Correct the policy or request and submit again. It does not silently fall back to a different family.

### Selection precedence

For an eligible new text prompt, the current implementation processes selection in this order:

1. A disabled policy or leading `[route:off]` passes the native client's request through unchanged.
2. A successful native model-settings update takes priority for the next prompt without a leading route directive. This is the protocol behavior behind native `/model` selection; it is not a permanent pin.
3. A leading `[route:PROFILE]` selects that profile. An unknown profile is an error.
4. Supported explicit model or effort wording is resolved against the live catalog.
5. The local classifier chooses a profile for recognizable work.
6. An otherwise unclassified prompt in Codex Plan mode uses `planning`.
7. Other continuations retain the proxy's last accepted model/effort, or the selection provided by the native client when no previous choice is known.

The manual priority is specific to updates observed through this connection. A setting changed in an unrelated window is not a proxy-wide lock. A route directive applies to its prompt; the next recognizable task is classified again. `[route:off]` uses the native request's choice, which may differ from the last routed choice.

### Explicit requests

Put directives at the start of the prompt:

```text
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

Validation permits exactly `enabled` and `profiles` at the top level and exactly `models` and `effort` in each profile. Model IDs must be nonempty, unique within the profile, and contain no whitespace. Recognized effort names are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, and `ultra`; a recognized name must also be advertised by the selected model. Unknown keys or profile names are errors.

For a Sol planning / Terra execution / Luna checks preference, replace the `coding` entry inside `profiles` with:

```json
"coding": {"models": ["gpt-5.6-terra"], "effort": "medium"}
```

If you deliberately want a fallback across families, explicitly list it, for example `"models": ["gpt-5.6-terra", "gpt-6.1-sol"]`. The router uses exactly the candidates you configure.

Selection takes the first available non-hidden model, then validates the effort on that model. An unsupported effort is an error; the router does not search later candidates for one that accepts it. Availability is determined at runtime and differs by client or account.

`auto` reloads the policy for each eligible new prompt. Other commands read it when invoked. Editing the policy does not change an active turn. Set top-level `"enabled": false` to stop automatic selections. For `auto`, the proxy still forwards traffic and creates metadata for skipped eligible prompts.

The classifier uses ordered text rules, not a learned difficulty score. Named concurrency or corruption failures select `deep-debug`; investigation wording selects `debugging`; consequential areas such as authentication or migration select `planning`; implementation, review, existing checks, and simple edits have separate rules. Order matters, so mixed prompts can route differently from a single isolated task. The rule implementation is [classify in router.py](../skills/codex-model-router/scripts/router.py). A profile name is a routing preference, not evidence that the work is easy or difficult.

## Preview without starting a task

```sh
python3 "$ROUTER_SCRIPT" preview "Run the existing unit tests"
python3 "$ROUTER_SCRIPT" preview --phase debugging
python3 "$ROUTER_SCRIPT" preview --phase coding --failed-attempts 2
python3 "$ROUTER_SCRIPT" preview --model gpt-5.6-terra --effort medium
```

`preview` prints JSON and makes no inference request. It uses `models_cache.json` from `--codex-home`, `$CODEX_HOME`, or `~/.codex`. The cache can be absent or stale; a preview does not prove that the live daemon can start the same model. Ambiguous text returns `unchanged` because there is no proxy conversation state to retain. Its result can therefore differ from `auto` for Plan mode, manual updates, continuations, and natural-language overrides.

`--failed-attempts 2` explicitly escalates `coding` or `debugging` to `deep-debug`; with no phase, it also selects `deep-debug`. An explicit route directive takes precedence. The helper never counts failures from command exit codes. Count distinct unsuccessful fixes, not permission denials, network outages, or missing dependencies.

## Route one initial task

```sh
python3 "$ROUTER_SCRIPT" run "Implement pagination for search results"
python3 "$ROUTER_SCRIPT" run --phase easy "Run pwd and list five entries."
python3 "$ROUTER_SCRIPT" run --model gpt-6.1-sol --effort high "Review this implementation"
python3 "$ROUTER_SCRIPT" run --cwd /absolute/path/to/project "Run the existing tests"
```

`run` requires a task and opens a new interactive Codex session with initial model settings supplied as CLI arguments. It uses the cached catalog for a routed task and needs neither the router's control connection nor `step_model_switching` for initial selection. Ambiguous, disabled, or `[route:off]` tasks launch with native defaults. It routes only the initial task; subsequent prompts are not handled by the automatic proxy. Use `auto` for repeated per-prompt routing.

The printed `launching` record describes requested startup arguments. Inspect native `/status` and local routing diagnostics as applicable; a launcher message alone is not inference telemetry.

## Optional legacy hook

From the checkout:

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

Look for `router_hook.ready: true`, a trusted or managed hook, `live_switching.enabled: true`, and `target_thread.loaded_on_this_server: true`. These describe the server the helper contacted. Hook trust and feature enablement are separate prerequisites.

The hook runs after prompt submission and may arrive after inference starts. Its output can be delivered later in the conversation. It skips prompts claimed by `auto`, so the two mechanisms do not intentionally route the same prompt twice. Unknown follow-ups are skipped by the hook and retain the native thread default. [Official background-hook behavior](https://learn.chatgpt.com/docs/hooks#how-background-hooks-run).

### Apply a compatible change in an active turn

```sh
python3 "$ROUTER_SCRIPT" apply --phase debugging
python3 "$ROUTER_SCRIPT" apply --phase coding --failed-attempts 2
python3 "$ROUTER_SCRIPT" apply --thread THREAD_ID --model gpt-6.1-sol --effort high
python3 "$ROUTER_SCRIPT" apply --thread THREAD_ID --turn TURN_ID --phase review
```

`apply` uses `--thread`, or `CODEX_THREAD_ID` when omitted. It targets the supplied turn or discovers the current in-progress turn. It never creates or resumes a task. `applied` means Codex accepted publication for later inference calls in that turn. Already captured requests and child sessions are unaffected.

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
