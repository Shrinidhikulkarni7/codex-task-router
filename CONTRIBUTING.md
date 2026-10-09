# Contributing

Keep changes focused on a reproducible routing or integration behavior. The project uses Python's standard library and has no runtime package dependencies. Use Python 3.11+ on macOS or Linux.

## Development checks

From a checkout:

```sh
python3 scripts/check.py
python3 scripts/build_skill.py
```

The check runner copies only public test inputs into a temporary checkout, excluding personal policy and runtime state. The suite uses temporary Codex homes, model catalogs, and independent protocol peers. Focused tests can also be run with `python3 -m unittest discover -s tests -p test_local_policy.py -v`. It must run without a Codex login, network access, credentials, global installation, or inference calls. The Unix-listener test skips only when the host explicitly denies socket binding; retain the process-pipe coverage when that happens.

[GitHub Actions](.github/workflows/ci.yml) is configured to run the offline checks on macOS and Linux with Python 3.11 and 3.13. A checked-in workflow is not evidence that a remote run has passed; report actual results and skips in a change description.

For a routing or protocol change, add a regression test for the observable behavior. For documentation changes, verify the documented commands and their scope against the parser and implementation. Avoid tests that only duplicate implementation details or match documentation wording.

## Behavior to preserve

- Route only eligible new turns; keep active steering, tool output, approvals, and unrelated fields intact.
- Update both top-level and collaboration-mode model/effort settings when routing.
- Preserve thread context, pinned explicit/native choices in selective/task modes, and one-prompt native priority in prompt mode.
- Commit selection, phase, and pin state only after a valid turn acknowledgment; rejected requests must leave prior state usable.
- Validate model and effort availability; expose failure without an unrequested substitute or replacement task.
- Keep live-update compatibility and review checks enforced by Codex.
- Preserve unrelated hooks, detect installation conflicts, and keep dry-run free of writes.
- Keep runtime state private, bounded, and separate from source; clean up each bridge's own resources.
- Distinguish request submission, acknowledgment, completion, and measured inference in diagnostics and prose.

The local rule classifier is intentionally inspectable. A new trigger should include realistic positive and negative examples, especially pasted logs, ambiguous continuations, and mixed tasks. Changes to default model preferences should explain the intended policy choice without presenting it as a benchmark result.

The authored routing corpus in `evals/routing_cases.jsonl` supplies regression expectations and a rationale per case. Add realistic contrast cases rather than silently changing labels to fit a new implementation. A passing corpus is development-set agreement, not general accuracy. Keep the [evaluation guide](docs/routing-evaluation.md) and dated result provenance accurate. `task_quality.py` lists cases offline by default; never add `--run` to routine CI, because it starts authenticated inference.

The optional Laya adapter has independent transport/response fixtures and routing-state tests. CI must not install Laya, download weights, or contact a real classifier. `laya_compare.py` also lists cases offline by default; `--run` intentionally uses local model inference. Preserve pins, deterministic retention, no-prompt diagnostics, timeout/fallback behavior, and the distinction between model recommendations and actual accepted settings. Never report its authored stress cases as a held-out real-task benchmark.

## Testing a real terminal

Live testing is separate from offline tests and can consume normal Codex usage. Use a disposable project with ordinary permissions. Record the CLI and daemon versions, selected policy, commands used, observed results, and checks skipped. Exercise resume, native model selection, route directives, and shutdown for changes touching the proxy lifecycle.

Do not weaken sandbox settings, bypass hook trust, or change admitted review requirements to obtain a passing test. A denied socket or incompatible live model change is a meaningful boundary to report.

## Change descriptions

Describe the concrete trigger and changed behavior. Include relevant test results, real-terminal observations if any, and compatibility limits. Update [usage](docs/usage.md), [selective rules](docs/selective-routing.md), [troubleshooting](docs/troubleshooting.md), and the [routing skill](skills/codex-model-router/SKILL.md) when behavior changes.

Exclude `.router-state/`, generated caches, private prompts, credentials, and raw diagnostic dumps from commits. Keep final demo artifacts and editable media intentional; the video project documents its rebuild inputs and provenance.

Contributions are made under the repository's [MIT license](LICENSE). Preserve third-party attribution and terms; do not include model weights or external assets without appropriate rights and notices.

## Repository and skill layout

Keep runtime instructions and their references inside `skills/codex-model-router/`.
Keep tests, evaluation runners, and historical evidence outside the installed
skill. References required at runtime must survive a standalone copy. Update
`scripts/build_skill.py` explicitly when adding a distributable file.

A pull request should explain the observable problem, resulting behavior, and
validation. Use the issue templates for reproducible bugs or focused proposals.
See [distribution](docs/distribution.md) for release checks and [the changelog](CHANGELOG.md)
for user-facing changes. Never publish personal policy or local diagnostics.
