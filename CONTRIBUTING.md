# Contributing

Keep changes focused on a reproducible routing or integration behavior. The project uses Python's standard library and has no runtime package dependencies. Use Python 3.11+ on macOS or Linux.

## Development checks

From a checkout:

```sh
python3 -m unittest discover -s tests -v
python3 install.py --help
python3 skills/codex-model-router/scripts/router.py --help
```

The test suite uses temporary Codex homes, model catalogs, and independent protocol peers. It must run without a Codex login, network access, credentials, global installation, or inference calls. The Unix-listener test skips only when the host explicitly denies socket binding; retain the process-pipe coverage when that happens.

[GitHub Actions](.github/workflows/ci.yml) is configured to run the offline checks on macOS and Linux with Python 3.11 and 3.13. A checked-in workflow is not evidence that a remote run has passed; report actual results and skips in a change description.

For a routing or protocol change, add a regression test for the observable behavior. For documentation changes, verify the documented commands and their scope against the parser and implementation. Avoid tests that only duplicate implementation details or match documentation wording.

## Behavior to preserve

- Route only eligible new turns; keep active steering, tool output, approvals, and unrelated fields intact.
- Update both top-level and collaboration-mode model/effort settings when routing.
- Preserve thread context and the one-prompt priority of observed native model changes.
- Validate model and effort availability; expose failure without an unrequested substitute or replacement task.
- Keep live-update compatibility and review checks enforced by Codex.
- Preserve unrelated hooks, detect installation conflicts, and keep dry-run free of writes.
- Keep runtime state private, bounded, and separate from source; clean up each bridge's own resources.
- Distinguish request submission, acknowledgment, completion, and measured inference in diagnostics and prose.

The local rule classifier is intentionally inspectable. A new trigger should include realistic positive and negative examples, especially pasted logs, ambiguous continuations, and mixed tasks. Changes to default model preferences should explain the intended policy choice without presenting it as a benchmark result.

## Testing a real terminal

Live testing is separate from offline tests and can consume normal Codex usage. Use a disposable project with ordinary permissions. Record the CLI and daemon versions, selected policy, commands used, observed results, and checks skipped. Exercise resume, native model selection, route directives, and shutdown for changes touching the proxy lifecycle.

Do not weaken sandbox settings, bypass hook trust, or change admitted review requirements to obtain a passing test. A denied socket or incompatible live model change is a meaningful boundary to report.

## Change descriptions

Describe the concrete trigger and changed behavior. Include relevant test results, real-terminal observations if any, and compatibility limits. Update [usage](docs/usage.md), [troubleshooting](docs/troubleshooting.md), and the [routing skill](skills/codex-model-router/SKILL.md) when behavior changes.

Exclude `.router-state/`, generated caches, private prompts, credentials, and raw diagnostic dumps from commits. Keep final demo artifacts and editable media intentional; the video project documents its rebuild inputs and provenance.

No repository license has been selected. Do not add a license or represent a contributor's ownership without the maintainer's decision.
