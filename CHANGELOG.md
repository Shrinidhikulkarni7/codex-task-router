# Changelog

Changes are described by behavior. The project is currently experimental;
dated entries do not imply a stable protocol or a versioned release.

## Unreleased

### Added

- Personal `policy.local.json` overrides and an offline `config` command.
- MIT licensing, self-contained skill references, and Codex display metadata.
- Reproducible skill archives with checksums and private-file exclusion.
- One-command isolated checks, distribution tests, and contribution templates.

### Changed

- Documentation organized around installation, configuration, operation, and
  evaluation, with a shorter README and explicit Laya responsibilities.
- Personal settings separated from distributed defaults; tests use an isolated
  copy so local preferences cannot enable classifier calls in routine checks.

## 2026-10-09

- Added optional local Laya shadow and active classification, with bounded
  loopback transport, response validation, retention, and failure handling.
- Published a 24-case local comparison and offline threshold replay. The
  evidence does not justify enabling active Laya by default.
- Refined action/scope rules and published the 70-case development rubric.

## 2026-10-08

- Added selective work-phase routing while retaining explicit choices and brief
  follow-ups. Fixed-task and per-prompt modes remain available.
- Recorded a six-turn retention check and token/cache observations.

## 2026-10-07

- Added native terminal proxy routing before turn admission, local diagnostics,
  model/effort validation, and usage snapshot recording.
- Preserved native selections for identified ephemeral threads.
- Added the standalone skill installer and optional legacy live-update hook.
