# Evaluating routing decisions and actual answers

There are two different checks. The offline rubric measures whether routing matches explicitly authored expectations. The opt-in quality runner asks actual models a few bounded questions and checks their answers. Neither establishes which model is best for every query or which routing strategy costs least.

## Offline routing rubric

Run from the repository root:

```sh
python3 evals/evaluate.py
python3 evals/evaluate.py --baseline-ref 23efc58
python3 evals/evaluate.py --baseline-ref 23efc58 --json
```

The evaluator uses [70 synthetic cases](../evals/routing_cases.jsonl) authored before the rule changes. Each case includes a rationale and an expected profile. A `previous` field tests a selective follow-up; a null expectation means retain/no new classification. Cases cover bounded explanations and edits, broad implementation, investigations, existing checks, negations and quoted data, mixed work, explicit control, continuations, and retained follow-ups.

The corpus is checked by the ordinary offline test suite and CI. No login, network, Codex process, or model inference is needed. Exit 0 means every case matched; exit 1 means at least one mismatch; exit 2 means invalid input or another evaluation error. JSON output includes case IDs, reasons, source/corpus hashes, category totals, and regressions without copying prompt text.

`--baseline-ref` executes the classifier code from the specified **trusted local Git revision**. It does not switch the checkout or fetch a revision. A shallow clone may not contain the historical commit; omit the flag for the normal CI/local check. The current classifier is read from the working tree.

### Recorded result: 2026-10-09

| Check | Baseline `23efc58` | Revised rules |
| --- | ---: | ---: |
| Matches against the authored rubric | 36 / 70 | 70 / 70 |
| Cases improved relative to baseline | — | 34 |
| Previously matching cases regressed | — | 0 |

The [recorded report](../evals/results/routing-v1.json) includes source and corpus hashes. It is a dated snapshot, not a promise that future revisions have the same score. Additional regression tests cover quoted multi-step text and comma-separated actions.

The main corrections are concrete:

- `Explain what a deadlock is in one sentence` selects easy; `Investigate the deadlock` selects deep debugging.
- Correcting a typo in an authentication README remains a mechanical edit; implementing authorization remains consequential.
- A one-line pure helper selects easy; a whole compiler selects higher reasoning. Adding a button to a compiler UI remains ordinary coding, and explicitly toy compiler scope is treated separately.
- Existing tests whose names mention failures remain prechecks on a fresh task; tests within an ongoing task retain its selection.
- Negated actions and quoted action lists do not create new routing instructions. Recognized mixed requests keep their strongest affirmative work signal.
- Reported repeated attempts caused by recognized permission, network, or dependency problems do not automatically count as failed reasoning.

These examples were used during development. **70/70 is regression agreement, not held-out accuracy.** The rubric reflects chosen policy preferences, not externally established optimal models. Unknown wording, language, scope, and context can still be misclassified. The rules do not learn from usage or grade their own answers.

## Optional checks of actual model answers

List the seven cases without launching Codex:

```sh
python3 evals/task_quality.py
```

The cases cover a definition, extraction, a bounded helper, a routine implementation choice, debugging, concurrency, and migration ordering. They use small synthetic inputs with exact JSON answers. Some are multiple choice or code comprehension: passing them does not demonstrate the ability to implement a full feature or solve an open-ended incident. The [case file](../evals/quality_cases.json) is editable; expected answers are never included in the submitted prompt or temporary working directory.

To start **real inference using your normal Codex account**, explicitly select a case and a new output file:

```sh
python3 evals/task_quality.py --run --case definition \
  --output evals/local-results/definition-router.json
```

To run all seven, or compare against one fixed model/effort:

```sh
python3 evals/task_quality.py --run --all \
  --output evals/local-results/router-run-1.json

python3 evals/task_quality.py --run --all \
  --model gpt-6.1-sol --effort medium \
  --output evals/local-results/fixed-sol-run-1.json
```

These commands consume normal Codex usage. Each case gets a separate ephemeral native `codex exec` session with a private temporary working directory and the read-only sandbox. The prompts request no tool use. Existing user configuration, rules, hook trust, and approval controls remain in force. The runner does not execute generated code; it compares structured final answers with the fixture's expected answer. It does not run through the automatic proxy, so it tests the **initial selection and answer**, not phase retention, live switching, or cache reuse within a conversation.

Models/efforts are checked against Codex's local cache before any case runs. Native Codex remains authoritative if the cache is stale. `--model` and `--effort` must be supplied together for a fixed comparison. `--codex` selects a binary; `--codex-home` selects only the cache location. Set `CODEX_HOME` separately when the subprocess must use a different Codex home.

Reports record requested model/effort, profile, answer correctness, elapsed time, and recognized `codex exec` usage fields when emitted. A requested model is not independent backend attribution. Missing usage stays unknown; counters are not a bill, and auxiliary work may be outside the report. Elapsed time includes CLI startup and execution. Errors are distinct from wrong answers.

Execution errors or timeouts stop the batch without retrying another model. Default timeout is 120 seconds per case, configurable with `--timeout` from 1 to 600. A CLI timeout does not prove daemon-owned work was cancelled; stop and inspect your session before retrying. Output files are created owner-only and existing files are refused before inference. `evals/local-results/` is ignored by Git. Reports may contain paths or echoed text from errors; review them before sharing.

The quality runner and its graders were tested with independent fake CLI results. Its offline listing was run. **Real model-answer checks were not run in this environment:** a read-only `doctor` probe was denied access to the local control socket. No model-quality score or savings result is claimed for this update.

## Deciding whether a model-based classifier is worth adding

Default runtime classification still uses local Python rules and `policy.json`; no additional classifier inference is enabled by default. An optional [Laya backend](../skills/codex-model-router/references/laya.md) now supports shadow comparisons and experimental active classification in `auto`. Its 24 authored paraphrase cases deliberately stress rule weaknesses; `python3 evals/laya_compare.py` lists them offline, and `--run --output NEW_FILE` explicitly performs local Laya inference. These are classification checks, separate from the existing seven native Codex answer checks. The available evidence does not establish that Laya improves completed-task outcomes or cost.

For the next evaluation, collect consented, sanitized examples beyond this development corpus and label their intended scope before tuning. Include unfamiliar wording and a mix of short and substantial tasks. For real engineering work, use clean copies of representative repositories and objective completion checks, including required tests and review of the actual changes. Record retries, elapsed time, and account usage as well as routing decisions. Do not treat these seven answer checks as a substitute for that work.

Compare local rules, a fixed model, and any proposed optional classifier using the same completion requirements. Counterbalance run order and report warm/cold cache conditions where known. Only enable an extra classifier if it improves quality or total completed-task usage on that broader evaluation. Its own inference, retries, and added latency must be included. Keep explicit user choices authoritative and preserve a deterministic fallback for unavailability.
