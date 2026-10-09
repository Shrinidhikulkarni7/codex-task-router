# Optional local Laya classifier

The shipped policy uses `classifier.mode: "rules"`. No Laya installation, download, network request, or inference is needed for that mode. Laya is an experimental alternative for interpreting varied wording; it has not demonstrated better routing or lower completed-task cost in this project.

Only `router.py auto` uses this classifier setting. `preview`, `run`, `apply`, the legacy hook, and the existing `evals/task_quality.py` answer checks continue to use the deterministic classifier. The separate `evals/laya_compare.py` tool tests local Laya decisions without starting Codex.

## Modes

| `classifier.mode` | Behavior |
| --- | --- |
| `rules` | Default. Classify locally with Python rules; no Laya calls |
| `shadow` | Ask Laya for a recommendation and record the comparison. The rule-based routing decision remains in control |
| `laya` | Experimental active classification. A usable Laya recommendation supplies the candidate profile, subject to the existing retention rules and Codex catalog validation |

`shadow` preserves the rule-based choice, but adds the time spent waiting for Laya. It is not a background, zero-latency comparison. Start with this mode and review results before enabling active classification.

## Run a local service

Laya runs separately from the standard-library router. Install it in a dedicated environment, following [upstream installation instructions](https://github.com/NandhaKishorM/laya#installation-details). The adapter targets the extended HTTP contract inspected in the upstream 0.4.1 source. A subsequent user-run local service comparison exercised that contract with real model responses; see the [results and limits](../../../docs/laya-evaluation.md).

For example, from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'laya[serve]==0.4.1'
LAYA_HOST=127.0.0.1 LAYA_PORT=8000 LAYA_MODELS=typed-decisions \
  LAYA_MAX_LOADED=1 LAYA_PRELOAD=1 LAYA_JEV_STRICT=0 \
  .venv/bin/laya-serve
```

The first start downloads model weights and loads them into local memory. Wait for the service to finish starting. Keep this terminal open. The router does not install Laya or start, stop, or restart this service. Laya uses local CPU/GPU resources; its local classification does not consume Codex inference tokens. Codex execution still uses your normal account.

Bind to loopback as shown: upstream's server default is broader. If the service uses `LAYA_API_KEY`, export the same value in the terminal launching `auto`; the router reads it from the environment and never saves it in policy or diagnostics. Do not put a secret into a URL or `policy.json`.

Use canonical checkpoint names (`english`, `multilingual`, `typed-decisions`) or an exact server-registered custom name. The adapter rejects answers whose `routing.model` does not match the requested name. `typed-decisions` is a starting experiment, not a benchmark-backed recommendation for Codex routing or all languages. Compare checkpoints on your own cases.

## First comparison

In another terminal, from the repository root, list the cases without contacting any service:

```sh
python3 evals/laya_compare.py
```

Then explicitly run one synthetic case against local Laya:

```sh
python3 evals/laya_compare.py --run --case invoice-download \
  --output evals/local-results/laya-one.json
```

For all 24 cases, or a different checkpoint/threshold:

```sh
python3 evals/laya_compare.py --run \
  --output evals/local-results/laya-comparison-1.json

python3 evals/laya_compare.py --run --checkpoint multilingual --threshold 0.9 \
  --output evals/local-results/laya-multilingual-1.json
```

These commands perform local Laya inference only. They do not submit Codex tasks, change live settings, or update policy. Reports are created owner-only; existing output paths are refused before inference. Service errors stop the comparison without retries. Exit 0 means all effective decisions matched the rubric, exit 1 means a mismatch, and exit 2 means an input/service/output error. A match count includes deterministic retention and fallback decisions; inspect `usable_recommendations` and each classifier status before attributing results to Laya.

The 24 authored cases deliberately stress known rule weaknesses, including paraphrases, misleading domain words, and follow-ups. They are not a representative accuracy benchmark, and become development data if used for tuning. Reports contain IDs, expected/effective profiles, probabilities and source/corpus hashes, without copying prompts. The [first user-run local report and analysis](../../../docs/laya-evaluation.md) are now committed: 22 responses passed adapter checks, but none reached the provisional 0.8 probability threshold. The development agent still cannot contact the service because its sandbox denies loopback access; it can inspect and replay saved reports.

To inspect different thresholds without making another inference request:

```sh
python3 evals/laya_replay.py evals/local-results/laya-comparison-1.json
```

This verifies the saved corpus/source hashes and original decisions before replay. It never edits the threshold or enables routing. Low probability is an abstention by the router's gate, not a connection failure. Do not lower the cutoff just to obtain accepted recommendations; use separate calibration and evaluation data.

## Enable session comparisons

In [policy.json](../policy.json), set the top-level classifier object:

```json
"classifier": {
  "mode": "shadow",
  "endpoint": "http://127.0.0.1:8000/v1/systemone",
  "model": "typed-decisions",
  "timeout_ms": 2000,
  "max_input_chars": 4000,
  "min_probability": 0.8,
  "api_key_env": "LAYA_API_KEY"
}
```

Every field except `mode` may be omitted to use the values above. Older policies without `classifier` use `rules`. The endpoint must use HTTP with literal `127.0.0.1` or `::1` and the `/v1/systemone` path. Hostnames, remote addresses, URL credentials, queries, redirects, environment HTTP proxies, and compressed/chunked responses are not supported; the stock Laya JSON response supplies a content length.

Restart `auto` after updating Python source. Later policy edits load on eligible prompts. Source installation is a symlink, so no reinstall is needed. Existing explicit/resumed selections stay pinned: begin an unpinned routing task with `New task: ...` to exercise classification.

Inspect `router.py status --thread THREAD_ID`. A `classifier` object appears only when the classifier path is reached. For example, a simulated disagreement can look like:

```json
{
  "mode": "shadow",
  "status": "recommended",
  "rules_profile": null,
  "profile": "coding",
  "proposed_profile": "coding",
  "agrees_with_rules": false,
  "used": false
}
```

`profile` is Laya's candidate; `proposed_profile` applies deterministic phase-retention rules to that candidate. Null means no new selection. `used` means the candidate was used by the classifier path; retention may still keep settings, or Codex may reject the turn. It does not prove an inference used a model. Shadow records always have `used: false`. The top-level routing `selection`, `status`, and `turn_status` retain their existing meanings.

## Retention, failure, and data boundaries

Explicit profile/model/effort requests, disabled routing, identified ephemeral threads, active-turn steering, and tool-output turns bypass Laya. In default selective mode, pinned/resumed choices also bypass it. Task mode retains existing tasks without Laya. Exact brief continuations such as `ok` and `continue`, leading quoted/code-only input, and selective follow-ups classified as existing checks also skip calls. Other substantive candidates can be assessed even when Python has a matching rule, since a match can be wrong.

Opt-in `routing_mode: "prompt"` deliberately reclassifies each eligible ordinary prompt instead of retaining a task's pin. An observed native model update protects the next accepted ordinary prompt; explicit requests always take priority on the prompt containing them. Prompt mode classifies with `previous_profile: null` and `followup: false`, and uses the Python rules when a recommendation is unusable, including within an ongoing conversation.

Laya receives only the current prompt plus the prior routing profile and a follow-up flag. The adapter does not read project files or send conversation history, thread IDs, Codex credentials, tool bodies, or the expected evaluation label. Material pasted inside the current prompt is part of that prompt and may reach the local service. The optional Laya service token is sent in its authentication header. Prompt length is capped; oversized inputs fall back rather than being cut by the client. The service must report that it did not truncate the input or collapse choices. Missing truncation metadata, including strict Jev responses, is rejected.

Usable results must contain the allowed profile labels, a valid probability distribution, a matching chosen probability, and the requested checkpoint. The client uses the chosen option's probability, not the entropy-based `confidence` field. The default 0.8 threshold is provisional and **not calibrated for this workload**. Upstream also warns against treating shipped confidence values as established accuracy; calibrate and validate on separate data. [Upstream confidence contract](https://github.com/NandhaKishorM/laya/blob/main/laya/confidence.py).

On an uncertain, malformed, unavailable, or timed-out recommendation, active classification in selective mode keeps an ongoing task's settings; an initial/new task falls back to Python rules and their native-choice fallback. Shadow mode always keeps the rules in control. A valid selective-mode candidate still passes through the existing phase rules: it cannot arbitrarily downgrade a task or override pins. Every mode restricts candidates to configured profiles and validates the selected model and effort against Codex's catalog. An accepted candidate can select the same model with a different effort.

One request has a total deadline (default two seconds; configurable 100–10,000 ms), a 64 KiB response limit, and no retry. Service errors create a 30-second cooldown. Concurrent attempts while one is pending fall back instead of queuing. A client timeout does not prove the service stopped inference. Runtime diagnostics keep allowed labels, numeric probabilities, comparison results, timing, and fixed error codes; raw server responses and error bodies are not recorded. Service-side logging is controlled by the Laya operator.

## Enable or disable active classification

After reviewing comparisons, set `classifier.mode` to `laya` to opt into experimental active decisions. Change it to `rules` to stop Laya calls. The last accepted model/effort remains part of the ongoing task; use a new-task boundary or explicit choice if you also want to reselect it.

Evaluate completed tasks as well as routing labels. Compare correctness, retries, elapsed time, local resource usage, and Codex usage. The existing seven answer checks use the rule classifier and do not test this Laya path. No measurement currently establishes that adding Laya improves Codex task quality or cost.
