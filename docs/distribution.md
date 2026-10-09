# Distribution and release checks

The repository contains one installable skill. Its instructions, references,
license, and Python scripts work without the surrounding repository. Codex,
its running local daemon, and optional Laya remain separate prerequisites.

## Install from a checkout

The recommended developer installation is `python3 install.py` at the root.
It creates a symlink and preserves existing hooks. Keep the checkout in place;
updates become available when a new routed session starts. See [usage](usage.md)
for custom Codex homes, conflict handling, updates, and removal.

## Build a portable archive

```sh
python3 scripts/check.py
python3 scripts/build_skill.py
```

The builder writes `dist/codex-model-router.zip` and `dist/SHA256SUMS`.
It uses an explicit file manifest, fixed timestamps, stable permissions, and
sorted entries. Identical source files produce identical archive bytes. The
archive contains no local policy, routing history, credentials, private reports,
model weights, demo assets, or development dependencies.

Verify a downloaded artifact with `shasum -a 256 -c SHA256SUMS` on macOS or
`sha256sum -c SHA256SUMS` on Linux. A checksum detects changes relative to a
trusted checksum file; it is not a publisher signature.

Extract into a new directory and inspect it first:

```sh
unzip codex-model-router.zip -d router-download
python3 router-download/codex-model-router/scripts/router.py config
```

To register the extracted skill, copy the `codex-model-router` directory into
`${CODEX_HOME:-$HOME/.codex}/skills/` only when that destination does not already
exist. Restart Codex to discover a newly installed skill. The helper can also
be run directly from the extracted directory without registering it.

For a copied installation, preserve `policy.local.json` before replacing the
skill with a reviewed update. The checkout installer manages only its own
symlink and recognized hook; it deliberately refuses to replace or remove a
copied installation. Remove a copied skill manually after closing its sessions.

## Prepare a release

1. Review changes against [the contribution invariants](../CONTRIBUTING.md).
2. Run the offline checks and verify all CI matrix jobs on the exact revision.
3. Record any Codex version tested live and any checks not performed. Validate
   the intended account, model catalog, task boundaries, manual choices, resume,
   and shutdown for protocol changes. Keep live inference outside routine CI.
4. Build the archive, verify its checksum, and inspect its contents. The
   distribution tests check reproducibility, private-file exclusion, and an
   independent extracted `config` command.
5. Update [the changelog](../CHANGELOG.md) and compatibility notes. Publish the
   reviewed commit and attach the ZIP/checksum if creating a GitHub release.

No versioned release or upstream production-support guarantee is implied by a
successful build. The app-server remains experimental. Historical evaluation
reports retain the source hashes of their original run; do not rewrite them
to appear current after a source change.
