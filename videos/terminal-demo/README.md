# Captioned terminal demo

A 35-second portrait replay showing three routing decisions in one Codex
conversation: automatic selection for a new task, retention for a follow-up,
and an explicit profile override.

[Watch or download the MP4](renders/codex-task-router-terminal.mp4) ·
[Offline HTML player](renders/player.html) ·
[SRT captions](renders/terminal-demo.srt) ·
[Cover image](renders/cover.png)

The MP4 is 1080 × 1920 at 30 fps, with burned-in captions. It is deliberately
silent for feed viewing. The HTML player is self-contained: download it and
open it in a browser; no server, sign-in, or network access is required.
GitHub's source-file view does not play an HTML file directly.

## What the footage demonstrates

| Recorded input | Recorded model and effort | Decision |
| --- | --- | --- |
| `New task: Run pwd and list the first five entries.` | `gpt-6-luna`, medium | Automatic easy-task selection |
| `Run pwd and list the first five entries.` | `gpt-6-luna`, medium | Keep the current task selection |
| `[route:coding] Run pwd and list the first five entries.` | `gpt-6.1-sol`, medium | Honor the explicit coding profile |

These are prompt excerpts. Every turn executed the same command,
`pwd && ls -1A | head -n 5`, and returned the output shown. The full prompts
and sanitized output are in [assets/session.json](assets/session.json).

**This is a designed replay of a verified session, not a fresh screen recording.**
The Oct 8, 2026 source session used **task mode**. Its prompts, command output,
and selected model/effort were checked against the native session records and
the matching accepted router records. The selection panel is an editorial
overlay based on that evidence, not a Codex interface widget. Private paths
were anonymized; typing and pauses were edited. The visible disclosure remains
throughout the video.

The recording illustrates task boundaries and explicit control. It does not
test every rule in the current default selective mode, prove backend inference
attribution, or demonstrate token or cost savings. Available models and profile
mappings depend on the installation.

## Edit and rebuild

Requirements: Python 3.10+, Node.js 20+, FFmpeg on `PATH`, and Chromium installed
by Playwright. From this directory:

```sh
npm install
npx playwright install chromium
npm run build
npm run check
npm run render
```

`npm run render` uses the pure JavaScript animation and captures all 1,050
frames through Playwright, then encodes H.264 with FFmpeg. Set `FFMPEG` to an
explicit executable path if needed. The alternative `npm run render:hyperframes`
uses the pinned HyperFrames CLI; that export path was not verified in the
restricted creation environment. HyperFrames needs permission to open a local
preview/check port.

- [source/film.js](source/film.js): artwork, typography, time-based animation.
- [source/player.html](source/player.html): offline playback controls.
- [source/build.py](source/build.py): embeds source/data, builds the player and SRT.
- [source/render.mjs](source/render.mjs): deterministic browser capture and encoding.
- [assets/captions.json](assets/captions.json): editable explanatory captions.
- [STORYBOARD.md](STORYBOARD.md): timing and editorial plan.
- [design.md](design.md): visual specification.
- [assets/credits.json](assets/credits.json): assets, fonts, and tool credits.
- [qa/REPORT.md](qa/REPORT.md): completed checks and environment limits.

The player uses installed system fonts. The final MP4 preserves the rendered
appearance; regenerating it on another operating system can change glyphs and
line metrics. Recheck readability after changing fonts, copy, or timings.

## Publishing copy

**Cover:** One conversation. Three routing decisions.

**Caption:** A quick look at Codex Task Router: choose a model for a new task,
keep it for a follow-up, and override it when needed. This captioned replay
uses three verified terminal turns. Code and setup:
https://github.com/Shrinidhikulkarni7/codex-task-router

Upload the MP4 directly to the publishing platform. Captions are already in the
picture; the SRT is also available for platforms that support a caption track.
No third-party visual or audio assets are bundled. Original project files use
the repository's MIT license.
