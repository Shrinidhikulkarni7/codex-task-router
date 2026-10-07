# Sources and asset credits

## Product claims

Reviewed 2026-10-07. The repository implementation is the source of truth for
this particular router; OpenAI documentation supplies protocol context.

| Film claim | Evidence |
| --- | --- |
| `auto` chooses model and reasoning effort for new prompts before turn admission | [session_proxy.py](../../skills/codex-model-router/scripts/session_proxy.py), `TurnRouter.prepare`, `set_choice`, `Bridge` |
| The same conversation is retained | The bridge forwards thread identifiers and non-routing messages rather than creating replacement threads |
| Easy → Luna / medium, planning → Sol / high, deep debug → Astra / xhigh | [policy.json](../../skills/codex-model-router/policy.json); [router.py](../../skills/codex-model-router/scripts/router.py), `classify` and `select_model` |
| Policy is editable and models must be available | Policy loading and validation against the server's advertised catalog |
| Approvals still go through Codex | Bidirectional forwarding in the bridge; it does not approve server requests |

Protocol reference: [official Codex App Server documentation](https://learn.chatgpt.com/docs/app-server),
particularly `turn/start` model/effort fields and collaboration settings.
This interface is experimental; the film does not claim universal production
support, compatibility with every Codex version, measured cost/speed benefits,
better outcomes or arbitrary changes halfway through an active turn.

The user reported a successful automatic routing session. The animated examples
are illustrative and do not present fabricated live output, results or quotes.

## Assets actually used

- **Artwork and texture:** original SVG paths and deterministic paper pattern
  authored in `source/film.js`; no stock images or AI-generated raster images.
- **Lettering:** original centerline glyph paths in `source/film.js`; no
  third-party font files. Player controls use the viewer's system UI font.
- **Music:** original 100 BPM composition synthesized in `source/audio.py` with
  plucked tones, bass and bell-like notes. No music samples or catalog tracks.
- **Sound effects:** original synthesized paper swishes and tonal clicks; no
  third-party SFX files.
- **Narration:** Apple AVFoundation, installed Nicky voice,
  `com.apple.ttsbundle.siri_nicky_en-US_compact`. Neural status/model version
  unknown. Rendered locally from the supplied original script. Apple's voice
  technology is third-party; no voice-model weights are redistributed and this
  document grants no separate rights to that technology.
- **Production tools:** JavaScript/SVG, Python/NumPy, Apple AVFoundation,
  Chromium via Playwright browser tooling, FFmpeg; HyperFrames 0.8.123 was used
  for scaffolding, workflow and static lint. Its network skill refresh and
  registry asset download failed; no registry artwork was incorporated.

The repository owner determines the project's distribution license. This file
records provenance and does not invent a license grant for the repository,
Apple technology or production dependencies.
