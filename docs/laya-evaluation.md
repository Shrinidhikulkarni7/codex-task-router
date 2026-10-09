# First local Laya evaluation: 2026-10-09

The local service and adapter worked, but this run does **not** justify enabling active classification. All 22 model responses passed the adapter's response checks; their highest probabilities were below the provisional 0.8 threshold. Two other cases skipped inference as intended. Shadow mode is the next comparison step; the distributed policy remains `rules`.

## Evidence and scope

The user started Laya outside the development agent's restricted environment, warmed the service with a two-option request, and ran `evals/laya_compare.py` on all 24 authored cases. The agent then inspected the saved report and verified its corpus and router/classifier source hashes. The [recorded report](../evals/results/laya-typed-decisions-20261009.json) contains case IDs, decisions, probabilities, timings, and provenance; the case text is in the [public corpus](../evals/laya_cases.jsonl).

The report requested `typed-decisions`, and the adapter validated the returned checkpoint name. Following the run, the installed environment reported Laya 0.4.1, PyTorch 2.14.1, Transformers 5.19.0, and Python 3.11.4 on arm64 macOS. The comparison did not record a loaded-weight revision or compute device, so it cannot establish those details.

This corpus intentionally stresses weaknesses of the Python rules. It is development data, not a representative sample of Codex tasks or a held-out calibration set. The user ran the actual HTTP inference; the agent's sandbox still denied loopback connections. The subsequent threshold comparisons are **offline replays of saved probabilities**, not further model runs.

## Results

- Cases: **24**, comprising **22 model responses** and **2 deliberate skips**.
- Highest returned probability per response: **0.2033–0.5106**.
- Original adapter elapsed time across the 22 calls: **79.8 ms median**, **1,180.6 ms maximum**. These include the local HTTP call and response handling, exclude skipped cases, and do not measure complete Codex tasks or predict latency on other machines.
- Python rules matched **7/24** final expected decisions on this stress corpus. Offline shadow replay preserved those same decisions, also **7/24**.

| Active-mode probability threshold | Recommendations accepted | Final rubric matches, including retention/fallback | Accepted recommendations producing a rubric mismatch |
| --- | ---: | ---: | ---: |
| 0.80, current provisional default | 0 | 5/24 | 0 |
| 0.50 | 1 | 6/24 | 0 |
| 0.40 | 5 | 10/24 | 0 |
| 0.35 | 7 | 10/24 | 1 |
| 0.25 | 19 | 14/24 | 7 |
| 0.00, probability gate disabled for replay | 22 | 16/24 | 8 |

The default active-mode result is lower than the rules baseline because uncertainty deliberately retains settings during an ongoing task. That prevents two transitions the rubric expects: the summary batch and approved-plan implementation. Shadow mode leaves those rule decisions intact. This is an observed consequence of the active fallback policy, not a service failure.

Accepting every returned profile would improve agreement on this particular corpus, but still produce eight mismatches after phase retention. Examples include choosing `coding` for an access-control change whose rubric expects `planning`, treating an incident title being capitalized as a `deep-debug` request, and missing the approved-plan transition. These are routing disagreements; no actual code quality or task failure was measured.

The earlier two-option warm-up returned `easy` at 0.797. It used different instructions and two labels rather than this adapter's eight labels. Its probability cannot establish a suitable threshold for this routing schema. Likewise, five correct accepted recommendations at 0.4 do not establish a reliable cutoff: that cutoff was inspected after seeing this small set.

## Reproduce the analysis without inference

```sh
python3 evals/laya_replay.py evals/results/laya-typed-decisions-20261009.json

python3 evals/laya_replay.py evals/results/laya-typed-decisions-20261009.json \
  --threshold 0.8 --threshold 0.4 --threshold 0 --json
```

The replayer needs only Python's standard library. It checks the corpus and runtime source hashes, reproduces the original decisions at the recorded threshold, and verifies that shadow decisions still equal the rules. It refuses incomplete/error reports, changed expectations, invalid probabilities, and source drift. It does not contact Laya, download weights, submit Codex tasks, or edit policy. The replay reconstructs the accepted probability fields; the original raw HTTP response was not retained, so transport validation is not repeated.

If a later code change makes the source hashes differ, use the original trusted repository revision to reproduce this historical result. Do not replace the stored hashes to make changed code appear equivalent.

## Next validation

Use `classifier.mode: "shadow"` locally to collect recommendations on representative work while keeping the existing selection policy. Keep the provisional threshold unchanged until a separate calibration set and held-out evaluation justify a change. Useful next checks include paraphrases, quoted text, ambiguous follow-ups, consequential changes, and each retention boundary.

A live native Codex session with shadow classification still needs to be checked separately. Better routing labels would also need completed-task checks for correctness, retries, elapsed time, and Codex usage before any quality or savings claim. The [setup guide](../skills/codex-model-router/references/laya.md) explains activation, diagnostics, and rollback.
