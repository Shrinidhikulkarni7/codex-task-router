# Configuration reference

The router loads `policy.json` from the installed skill directory, then merges
an optional `policy.local.json` beside it. Objects merge recursively; arrays
and scalar values replace inherited values. Unknown fields and invalid values
stop routing before submission. Defaults are validated before overrides.

Use the local file for personal preferences. The repository ignores it, and
the distribution builder excludes it. With a symlink installation, the file
lives in the checkout. Configuration applies to every project launched through
that installation; there is no project-specific configuration search.

Create the file with only the settings you need. For example:

```json
{
  "routing_mode": "task",
  "profiles": {
    "coding": {"models": ["gpt-5.6-terra"], "effort": "medium"}
  }
}
```

If a local file already exists, merge your changes into it. Do not replace other
preferences accidentally. Remove a field to inherit its default; `null` does
not delete a setting. Remove the local file to restore shipped defaults.

Inspect the merged configuration without contacting Codex or Laya:

```sh
python3 /absolute/path/to/codex-model-router/scripts/router.py config
```

The output identifies both paths and expands classifier defaults. It includes
the name of the optional token environment variable, never its value. Keep
secrets out of both policy files.

## Routing modes

| Field | Values | Default |
| --- | --- | --- |
| `enabled` | Boolean; false forwards native selections | `true` |
| `routing_mode` | `selective`, `task`, `prompt` | `selective` |
| `classifier.mode` | `rules`, `shadow`, `laya` | `rules` |
| `profiles` | Model preference lists and efforts below | Shipped profile map |

- **Selective:** retain brief follow-ups. Recognized work instructions can
  escalate an unpinned choice; approved-plan implementation and substantial
  summary/extraction batches permit specific downward transitions.
- **Task:** retain ordinary follow-ups until a new-task marker or override.
- **Prompt:** reconsider each eligible ordinary prompt. A native model update
  protects the next accepted ordinary prompt.

Explicit choices stay pinned in selective/task modes until an override or
leading `New task:` / `[route:new]`. A boundary keeps the conversation history.
Resumed/forked sessions pin Codex's reported settings because earlier choice
provenance is unavailable. Active-turn steering preserves the running model.

Policy is read for eligible turns. Restart `auto` after changing Python code.
Changing policy does not itself release an existing pin or task selection;
use a task boundary when a fresh decision is intended.

## Profiles

Profiles are preferences, not measured model rankings. Account availability
and supported effort levels come from Codex's catalog.

| Profile | Typical work | Preferred models, in order | Effort |
| --- | --- | --- | --- |
| `precheck` | Existing checks | `gpt-6-luna`, `gpt-5.6-luna` | `low` |
| `easy` | Bounded edit, extraction, summary | Same Luna candidates | `medium` |
| `coding` | Implementation | `gpt-6.1-sol`, `gpt-6-sol`, `gpt-5.6-sol` | `medium` |
| `review` | Routine review | Same Sol candidates | `medium` |
| `planning` | Architecture, broad scope, tradeoffs | Same Sol candidates | `high` |
| `debugging` | Root-cause investigation | Same Sol candidates | `high` |
| `deep-debug` | Difficult failures or explicit escalation | `gpt-6-astra` | `xhigh` |
| `terra` | Explicit execution preference | `gpt-5.6-terra` | `medium` |

Each profile must have exactly `models` (a nonempty list of distinct model IDs)
and `effort` (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, or `ultra`). The first non-hidden advertised candidate is selected, then its effort
is checked. A missing model or unsupported effort is an error; there is no
invented substitute family. An explicit model ID takes priority over the list.

## Optional Laya

For a running local service, a minimal comparison-only override is:

```json
{"classifier": {"mode": "shadow"}}
```

The complete adapter defaults, request limits, local service setup, and active
classification caveats are in [the Laya reference](laya.md). Only `auto` uses
that classifier setting. `preview`, `run`, `apply`, and the hook use rules.

## Updating an existing installation

If you previously edited the tracked `policy.json`, copy just your changed
fields into `policy.local.json` before restoring the shipped file. Review
`git diff -- skills/codex-model-router/policy.json`; keep an external backup
before any restore. `config` verifies the effective result. The installer does
not migrate or overwrite configuration automatically.
