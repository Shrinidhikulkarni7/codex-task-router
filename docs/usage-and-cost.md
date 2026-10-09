# Tokens, cache reuse, and routing

The default is now **selective switching**: keep suitable settings for brief follow-ups, reconsider on recognized work-phase instructions, and honor explicit choices. Optional `task` mode keeps a selection until a boundary/override; `prompt` mode retains the earlier per-prompt strategy. All use one conversation without automatic worker creation. The default classifier makes no inference call; optional [Laya modes](../skills/codex-model-router/references/laya.md) add local inference time and resource usage, including in comparison-only mode. See [the exact rules](selective-routing.md).

The [manual comparison below](#observed-model-switch-comparison-2026-10-07) found more uncached input after each model change than on its following repeat. That supports avoiding unnecessary switches, but does not prove that a stable model is always cheaper. Model rates, total work, retries, and correctness also matter. No measured cheapest-strategy claim follows from these trials.

## Choose a strategy for the work

| Work | Starting point | Tradeoff |
| --- | --- | --- |
| Short, independent tasks | `auto`, marking each new task with `New task:` or using a fresh conversation | Avoids delegation overhead; changing models can still reduce reuse of the conversation's cached prefix |
| Related work with occasional changes in difficulty | Default selective mode in `auto` | Retains brief steps and recognizes some phase changes; heuristic scope and quality judgments can be wrong |
| One long task where the chosen model should stay fixed | Optional task mode, or an explicit pinned choice in selective mode | Preserves model and effort, but does not guarantee cache reuse or the lowest cost |
| Substantial independent work that benefits from parallelism or separate context | Consider explicitly requested native subagents | Worker inference, context, and coordination also consume tokens; compare completed results rather than assuming savings |

Prompt caching reuses model state for a matching rendered prefix. Model settings, tools, instructions, and retention can affect reuse. Moving a switch to a new turn does not make it cache-neutral, and switching does not necessarily erase every earlier cache entry. [OpenAI prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching).

OpenAI documents that comparable subagent workflows consume more tokens because workers do their own model and tool work. Bounded context and cheaper models may still make a particular workflow useful, but that is not evidence of savings for this router. [Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).

Token count, cache reuse, and money are different measurements. A cached input token is still part of usage; different models and billing plans can price work differently. The router does not translate counters into dollars or ChatGPT credits.

## Why a cache miss can still be cheaper

For illustration, the published **standard Codex credit rates per million tokens**, checked on 2026-10-08, were:

| Model | Uncached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| GPT-6.1 Sol | 50 | 2.5 | 250 |
| GPT-6 Luna | 2.5 | 0.25 | 12.5 |

These are Codex credit rates, not API dollar prices or a formula for a particular subscription's included allowance. Other tiers, discounts, and billing arrangements can differ. The Codex credit page states that cache writes do not add a separate charge under that pricing. Check [current official pricing](https://learn.chatgpt.com/docs/pricing#token-rates) before using these values.

Using those rates and the reported main-thread counts from the six-turn check below gives this **illustrative calculation**:

```text
credits = (uncached_input × input_rate
         + cached_input × cached_rate
         + output × output_rate) / 1,000,000
```

| Observed step | Illustrative standard credits |
| --- | ---: |
| Step 2: repeat on Sol | 0.153550 |
| Step 3: switch to Luna | 0.047281 |
| Step 4: repeat on Luna | 0.015895 |
| Step 5: return to Sol | 0.604750 |

This assumes the requested model produced all reported work in each step, an attribution the usage notification does not independently prove. It excludes auxiliary threads and is neither an account charge nor a controlled comparison. Luna's lower rates make its switch step cheaper in this illustration despite lower cache reuse; returning to Sol is more expensive. There was no all-Sol control run with the same context, so this does not establish the savings of the full sequence.

Choose models for successful completed work. A more capable model might reduce retries; a smaller model may suit a substantial simple phase. Both are possibilities to measure, not results established here. OpenAI likewise recommends comparing whole-task quality, latency, and cost rather than treating a high cache-hit percentage as sufficient evidence of savings. [Official agent observability guidance](https://developers.openai.com/api/docs/guides/agents-api/observability#prompt-caching).

## Inspect reported usage

After updating the checkout, open a new `auto` session and complete a task. Existing proxy processes keep their old code. From another terminal:

```sh
ROUTER_SCRIPT="${CODEX_HOME:-$HOME/.codex}/skills/codex-model-router/scripts/router.py"
python3 "$ROUTER_SCRIPT" status --thread THREAD_ID
```

When the connected daemon emits a valid usage notification, a matching record includes the following structure. **These numbers are illustrative, not benchmark results.**

```json
{
 "token_usage": {
  "source": "thread/tokenUsage/updated",
  "last": {
    "inputTokens": 200,
    "cachedInputTokens": 128,
    "cacheWriteInputTokens": 32,
    "outputTokens": 30,
    "reasoningOutputTokens": 10,
    "totalTokens": 230
  },
  "total": {
    "inputTokens": 1000,
    "cachedInputTokens": 640,
    "cacheWriteInputTokens": 160,
    "outputTokens": 150,
    "reasoningOutputTokens": 50,
    "totalTokens": 1150
  },
  "modelContextWindow": 200000
 }
}
```

| Field | How to interpret it |
| --- | --- |
| `last` | The server's latest usage breakdown, not the sum of all inference calls in a turn |
| `total` | The server's cumulative thread snapshot at that notification; **do not add totals across records** |
| `inputTokens`, `outputTokens`, `totalTokens` | Reported counts; use the supplied total rather than adding every counter together |
| `cachedInputTokens` | Reported cached input; inspect alongside input count when evaluating reuse |
| `cacheWriteInputTokens` | Reported cache-write input when the daemon includes it; absence is unknown, not zero |
| `reasoningOutputTokens` | Reported reasoning output; do not add it again to invent a larger total |
| `modelContextWindow` | Optional reported context capacity, not tokens consumed |

The recorder observes the existing notification stream and adds no model or RPC requests. Notifications are forwarded unchanged. Only recognized numeric fields are saved; no prompt or tool body is added to the history. Repeated snapshots replace the previous snapshot instead of accumulating it.

`accepted` still describes the requested selection. The usage notification has no model identifier, so a record's selected model must not be treated as an attribution of its cumulative counters. Server rerouting, earlier turns, compaction, and work outside this connection can also complicate interpretation.

The native client may also generate a conversation title in a separate ephemeral thread. The proxy leaves identified ephemeral threads on Codex's native settings and labels them `skipped` with `thread_kind: "ephemeral"`; their counters are separate. They still consume normal usage. Filter by your task's thread to inspect its counters, and account for auxiliary work separately when comparing the whole session.

## What the local comparison verifies

The offline regression in `tests/test_task_routing.py` feeds the same eight prompts to all three strategies: plan architecture, implement the approved plan, run tests, diagnose a failing test, rerun tests, review, list files, and continue. It uses a simulated model catalog and valid turn acknowledgments, with no model inference.

| Strategy | Model changes after initial selection | Model or effort changes | Catalog lookups during the eight prompts |
| --- | ---: | ---: | ---: |
| Default selective mode | 0 | 2 | 3 |
| Optional task mode | 0 | 0 | 1 |
| Opt-in prompt mode | 5 | 6 | 7 |

The catalog counts exclude the common startup probe. Selective mode adjusts effort at approved-plan implementation and investigation in this sequence, retaining settings for the short checks. Other sequences can change models; the selective tests cover Luna-to-Sol-to-Astra escalation and a summary-batch downgrade. This is **not a token or cost benchmark**. The sandbox denied live control-socket access. The earlier [user-terminal sequence](#live-task-retention-verification-2026-10-08) verified task-mode retention and usage, but did not exercise the newly added selective rules. There is no controlled live strategy comparison.

## Compare strategies with live tasks

1. Choose several representative tasks with concrete completion checks. Record the repo revision, prompts, CLI/daemon versions, policy, selected settings, and available tools. Use separate clean working copies for edits.
2. Set policy `"routing_mode": "prompt"` and start a fresh `auto` conversation for the per-prompt trial. Complete the entire task, including fixes and checks. Read `status --thread THREAD_ID` and retain the latest reported thread total after completion, along with correctness and elapsed time. Finish and close this trial before changing policy; active proxies reload the same file.
3. Repeat in separate fresh conversations with `"routing_mode": "task"` and `"routing_mode": "selective"`. Keep the initial task, follow-ups, correctness checks, and completion requirements identical. Avoid boundaries, model requests, and profile directives unless they are part of the behavior being measured. Confirm actual recorded selections; selective mode may reasonably retain the same model throughout some tasks.
4. Repeat the trials, varying their order. Control starting files and inputs, and record whether a run began with warm or cold cache conditions when known. One warm-cache run versus one cold-cache run is not a reliable comparison.
5. Compare successful completed tasks, including retries, input/cache counters, output, latency, and actual account usage where available. Prefer the strategy that meets your quality requirement with acceptable usage. Do not infer dollars from token count alone.

These are manual comparison instructions, not an automated benchmark or proof that any strategy wins. No paid or authenticated benchmark runs as part of the test suite.

For an explicitly fixed-model baseline, select native `/model` and prefix every prompt with `[route:off]` through the same proxy; skipped routing still records usage. Explicit `Use MODEL_ID` prompts override retention, so repeating the eight-model-switch trial below deliberately switches in every mode. It cannot demonstrate savings from selective decisions.

## Observed model-switch comparison: 2026-10-07

The user ran eight turns in one fresh `auto` conversation using CLI 0.160.1: Luna twice, Sol 6.1 twice, Terra 5.6 twice, then Astra twice. All requested medium effort and the same task, changing only `MODEL_ID`:

```text
Use MODEL_ID with medium reasoning. Run pwd and list the first five entries in the current directory. Do not edit files. Return only the command output.
```

The router records were checked against the local rollout: eight user turns, two reported inference-usage updates per turn, one shell command per turn, and no recorded compaction. Each command was `pwd && ls -1 | head -n 5`. Turn-context model and effort fields matched the requested choices. This is local request/usage evidence, not independent backend or billing attribution.

For each counter, per-turn usage was calculated as the current cumulative total minus the previous turn's total, starting at zero only after checking that this was a fresh thread with no preceding turns. Those differences matched the sum of the two reported call breakdowns in each turn. Uncached input here means reported input minus reported cached input. Duration comes from the rollout's task-completion event.

| Turn | Selected model | Input | Cached input | Uncached input | Output | Duration (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1, initial | `gpt-6-luna` | 40,967 | 28,160 | 12,807 | 96 | 6.307 |
| 2, repeat | `gpt-6-luna` | 41,351 | 40,448 | 903 | 96 | 5.203 |
| 3, switch | `gpt-6.1-sol` | 50,627 | 36,736 | 13,891 | 134 | 10.911 |
| 4, repeat | `gpt-6.1-sol` | 51,065 | 50,560 | 505 | 110 | 13.262 |
| 5, switch | `gpt-5.6-terra` | 65,529 | 39,424 | 26,105 | 176 | 11.941 |
| 6, repeat | `gpt-5.6-terra` | 66,009 | 65,024 | 985 | 97 | 8.107 |
| 7, switch | `gpt-6-astra` | 77,391 | 50,048 | 27,343 | 110 | 12.061 |
| 8, repeat | `gpt-6-astra` | 77,803 | 77,184 | 619 | 110 | 11.894 |

Across the three switches (turns 3, 5, and 7), uncached input totaled **67,339**, versus **2,109** across their following repeats: **31.9 times as much**, or a difference of **65,230**. The initial Luna turn is excluded from this switch comparison. Cache reuse on the three switch turns was 72.6%, 60.2%, and 64.7%; on their repeats it was 99.0%, 98.5%, and 99.2%. Total input was similar within each pair: the large difference was in cached versus uncached input. The 31.9 ratio is not a cost multiplier or an isolated causal estimate.

The full main thread reported 470,742 input tokens (387,584 cached) and 929 output tokens, totaling 471,671. Its separate temporary title task reported 5,146 input tokens (4,864 cached) and 53 output tokens, totaling 5,199; that auxiliary work is excluded from the table and switch ratio.

The recorded context also changed at each model switch: new developer-instruction blocks appeared on turns 3, 5, and 7, but not on their repeats. First-call input grew from 20,426 tokens on initial Luna to 25,237 on Sol, 32,667 on Terra, and 38,631 on Astra. The original task text stayed the same apart from the requested model. This sequence does not isolate the contributions of instruction updates, conversation growth, or model-specific processing, and it is not a model-efficiency ranking.

All eight turns were marked completed and their shell calls succeeded. The second Terra answer stopped after a partial file listing even though the tool returned the full output. Completion status alone therefore did not establish answer correctness. Durations varied; the cached Sol repeat was slower than its preceding switch turn.

This is one ordered sequence on one simple task, recorded before task retention was implemented. Cache state was not reset or controlled, model order was not randomized, and there was no return-to-Luna run, all-one-model baseline, subagent trial, or billing measurement. It motivated adding retention to avoid unnecessary switches. It does not establish dollar savings, a universal switching penalty, or live validation of selective routing.

## Live task-retention verification: 2026-10-08

The user ran six prompts in the same `auto` conversation after an initial Sol 6.1 / medium selection. A baseline of the routing records and cumulative usage was saved before the sequence. The unprefixed prompt was identical for all six steps except for the deliberate routing prefixes:

```text
Run pwd and list the first five entries. Use `pwd && ls -1A | head -n 5`. Do not edit files. Return only the command output.
```

Steps 1, 2, 4, and 6 used that prompt unchanged. Step 3 added `New task: `, and step 5 added `[route:coding] `. Expected selections were Sol, Sol, Luna, Luna, Sol, Sol, all with medium effort.

All six passed verification against both the local router history and the session rollout:

- The submitted prompts exactly matched the sequence. Model and effort matched in the router records and recorded turn contexts; the thread ID remained the same.
- Ordinary follow-ups recorded `Retaining model and effort for current task`. The boundary and explicit override recorded their expected selection reasons. Every turn was accepted and completed.
- Every turn made one tool call with the same requested shell command. Each final answer matched the command's recorded output. No editing commands or compaction were recorded.
- Each turn had one legacy-hook record that skipped duplicate routing, and two reported inference-usage breakdowns. Each cumulative-counter difference matched their sum and the router's latest snapshot.

| Step | Action | Selected model | Input | Cached input | Uncached input | Output | Duration (s) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Retain after idle interval | `gpt-6.1-sol` | 43,064 | 32,896 | 10,168 | 79 | 26.147 |
| 2 | Repeat | `gpt-6.1-sol` | 43,412 | 42,880 | 532 | 79 | 7.886 |
| 3 | New-task boundary | `gpt-6-luna` | 51,234 | 36,352 | 14,882 | 79 | 8.122 |
| 4 | Repeat | `gpt-6-luna` | 51,582 | 50,688 | 894 | 79 | 4.245 |
| 5 | Explicit override | `gpt-6.1-sol` | 60,818 | 51,840 | 8,978 | 105 | 6.808 |
| 6 | Repeat | `gpt-6.1-sol` | 61,205 | 60,672 | 533 | 92 | 6.746 |

The immediate repeats reused 98.77%, 98.27%, and 99.13% of input respectively. The two switches reused 70.95% and 85.24%. Returning to Sol therefore did not fully reuse its earlier prefix in this sequence. The first retained turn followed more than six hours of inactivity, so it is not treated as a warm-cache control.

Across these six turns, the main thread reported **311,315 input tokens**, including **275,328 cached** and **35,987 uncached**, plus **513 output tokens**: **311,828 total**. Reasoning output of 11 tokens is already included in output; reported cache-write input was zero. These figures subtract the saved baseline and exclude its initial turn and any auxiliary threads.

Each switch coincided with two new developer-instruction messages in the rollout. First-call input grew from 21,483 on Sol to 25,568 on Luna and 30,347 on returning to Sol. No compaction was recorded. This check does not isolate the effects of model changes, instruction updates, conversation growth, or cache state.

This verifies the tested retention, boundary, and override behavior in the user's terminal, with local request and usage evidence. It supports avoiding unnecessary switches. It does not independently establish backend model identity, dollar savings, a causal switching penalty, or general correctness on larger tasks. There was no randomized order, all-one-model control, prompt-mode comparison, or subagent trial. The agent read the existing local logs; it did not start these live tasks or bypass the blocked control socket.

## Coverage and limits

- The daemon's optional `thread/tokenUsage/updated` event must reach this proxy. Missing, malformed, or old records mean unknown usage. No history is backfilled, and the latest observed snapshot may precede final billing.
- Snapshots are matched by both thread and turn ID. Notifications may arrive before acknowledgment or after completion; up to 200 recent entries per connection are retained to handle that ordering. Events outside that window or after disconnect can be missed.
- The router does not sum child-agent threads into a parent. A delegation comparison must account for workers separately through usage reporting that covers them. Parent-only counters cannot establish the cost of the full workflow.
- `run`, ordinary Codex windows, `apply`, and the legacy hook do not collect these snapshots. New `auto` sessions collect them even when routing is disabled or skipped. `status` shows ten recent records from at most 200 local records.
- The field names were checked against the schema generated by local Codex 0.160.1. A user-run file-listing task subsequently produced counters matching its local rollout, and a further user-provided live status confirmed the ephemeral-thread exclusion. Simulated protocol tests cover both behaviors; the development sandbox prevents an agent-launched live test. See [compatibility evidence](compatibility.md).

The event is documented in the [official App Server notifications](https://learn.chatgpt.com/docs/app-server#notifications). Protocol availability does not make the router an independent billing meter.
