# Security and privacy

This router runs locally between the native Codex terminal and an existing app-server. It is an experimental integration, not a separate security boundary. Its permissions are those of the user running it; code that can modify the installed checkout can change what the symlinked skill executes.

## Execution and transport

`auto` uses a temporary owner-only directory and Unix socket. It does not expose a public TCP listener or implement remote authentication. Do not expose its local endpoint as a network service. Normal exit closes the temporary listener and proxy subprocesses; an already admitted task is owned by the Codex daemon.

The router changes selected model/effort fields and forwards the rest of the conversation, including native approval requests and responses. It does not approve requests itself or weaken sandbox, hook-trust, or admitted review requirements. The optional live-update path reports compatibility failures without trying to evade them.

The installer links the source checkout. Default installation preserves hook configuration. Explicit hook installation or removal validates the relevant configuration, backs up changes, uses atomic replacement, and refuses conflicting links or a symlinked hooks file. Review updates to the checkout as executable code.

These measures are covered by targeted tests; they are not a claim of a completed independent security audit or upstream production support.

## Stored data

Routing metadata is kept in `skills/codex-model-router/.router-state/` in the source checkout. The directory is owner-only; new records and temporary prompt claims are private files. Up to 200 recent routing records are retained, with ten displayed by `status`. Records have no age-based expiration.

Records contain identifiers, timestamps, routing choices, selection kind/phase/pin, reasons, statuses, optional server-reported token/cache counters, and bounded error text. Only recognized numeric usage fields are retained; unknown usage payload fields are excluded. Prompts and tool bodies are not intentionally logged, but upstream errors may echo content. Prompt-claim filenames include a hash derived from the thread and prompt plus a random token; their contents include a creation time and PID. Claims expire after 60 seconds and require a live owner to suppress a duplicate legacy hook. Hashes should not be treated as encryption.

The router has no separate telemetry destination or API-key store. Codex still handles authentication, model inference, conversation storage, and its own configured telemetry. Installer backups contain the previous complete hooks configuration and remain until removed. Read [architecture and retention](docs/architecture.md#local-data-and-retention) before collecting or clearing diagnostics.

Optional Laya modes send the current prompt, prior work profile, and a follow-up flag to a user-started service on literal loopback. The standard-library client refuses remote/hostname endpoints, redirects, URL credentials and environment proxies, and bounds the request, response, and elapsed time. A configured service token is read only from an environment variable. Model files and ML dependencies belong to the separate Laya environment; the router never downloads them or starts the service. Diagnostics retain allowed categories and numbers, not raw responses or request text. Server-side logging is controlled separately. See [Laya data and failure boundaries](skills/codex-model-router/references/laya.md#retention-failure-and-data-boundaries).

The optional developer quality runner starts native Codex inference only with `--run`. It uses a private temporary working directory and the read-only sandbox, preserves user rules and trust controls, and never executes generated code in its grader. Output reports are owner-only, existing paths are refused, and `evals/local-results/` is Git-ignored. Errors can echo paths or text; review reports before sharing. A CLI timeout does not prove cancellation of daemon-owned work. The offline routing evaluator can execute a specifically requested trusted local Git revision via `--baseline-ref`; treat that revision as executable code.

## Reporting issues

For a non-sensitive defect, provide a minimal reproduction, operating system, Python version, CLI and daemon versions, and the relevant sanitized diagnostic fields. Do not publish credentials, real prompts, complete hook backups, or unreviewed error dumps.

A dedicated private reporting channel has not been configured by this project. For a sensitive vulnerability, use GitHub's private vulnerability-reporting flow if available on the repository. Otherwise, ask the maintainer to establish a private channel without posting the sensitive details publicly. This document does not promise a response time or a supported release window.
