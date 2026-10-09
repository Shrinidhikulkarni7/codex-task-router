# Documentation

Start with [installation and first use](usage.md#install). The default path is
`install.py` followed by `router.py auto`; no hook or Laya service is required.

| Goal | Guide |
| --- | --- |
| Install, start, resume, update, or uninstall | [Usage](usage.md) |
| Choose models, efforts, and local preferences | [Configuration](../skills/codex-model-router/references/configuration.md) |
| Understand when settings change | [Selective routing](selective-routing.md) |
| Use a local semantic classifier | [Laya setup and boundaries](../skills/codex-model-router/references/laya.md) |
| Diagnose a connection or routing problem | [Troubleshooting](troubleshooting.md) |
| Understand transport, state, and failure handling | [Architecture](architecture.md) |
| Check supported assumptions and tested behavior | [Compatibility](compatibility.md) |
| Interpret token counters and cache tradeoffs | [Usage and cost](usage-and-cost.md) |
| Evaluate rules and actual answers | [Routing evaluation](routing-evaluation.md) |
| Inspect recorded Laya results | [Laya evaluation](laya-evaluation.md) |
| Build or install the standalone skill | [Distribution](distribution.md) |
| Contribute a fix | [Contributing](../CONTRIBUTING.md) |
| Report a vulnerability or inspect data handling | [Security](../SECURITY.md) |

## Repository map

```text
skills/codex-model-router/   Installable skill and dependency-free router
  SKILL.md                  Agent instructions and reference entry points
  agents/openai.yaml        Codex display metadata
  policy.json               Shared defaults
  policy.local.json         Optional personal overrides (ignored)
  references/               Configuration, operations, and Laya guides
  scripts/                  CLI, native session proxy, and Laya adapter
docs/                       User, architecture, and evaluation documentation
evals/                      Authored cases, runners, and dated public evidence
tests/                      Offline behavioral and protocol regressions
scripts/                    Repository checks and distribution builder
videos/router-film/         Editable illustrated demo and media credits
install.py                  Symlink installation and optional legacy hook
```

Only the skill directory is needed at runtime. Development evaluations and
historical evidence are intentionally outside the installed skill. Local
state, overrides, weights, and private reports are excluded from distribution.
