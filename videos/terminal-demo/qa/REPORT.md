# Export verification

Verified on 9 October 2026.

## Delivered artifact

- `renders/codex-task-router-terminal.mp4`
- H.264, `yuv420p`, 1080 × 1920, 30 fps.
- Exactly 35 seconds and 1,050 frames; 926,097 bytes.
- Fast-start MP4 with burned-in captions; intentionally no audio stream.
- Seven explanatory SRT cues cover 0–35 seconds without gaps or overlap.

## Checks completed

- Matched all three selected models/efforts, prompts, executed commands, and
  outputs to consecutive native session turns and accepted router records.
  The source session used task mode. Raw records remain private and are not
  included in this project.
- Reviewed original-size artwork for the opening, follow-up, override, and
  ending. Reviewed the exported-video contact sheet spanning the entire clip.
- Measured text bounds in the browser at all 1,050 frame times: no text crossed
  the defined safe rectangle. Main captions stay above the bottom 185 pixels.
- Compared repeated forward/backward seeks at 14 sample times: identical SVG
  output. Every captured frame also returned its expected frame index.
- Fully decoded the exported MP4 with FFmpeg: no decode errors. FFprobe read
  all 1,050 frames and confirmed dimensions, frame rate, and duration.
- Played the complete exported MP4 in Chromium to its `ended` event: all 1,050
  frames presented, zero dropped frames, no media errors, final time 35 seconds.
- Verified the offline player's play, pause, keyboard seek, and restart
  controls at a 390 × 844 mobile viewport.
- Checked all source and embedded data for the private path/session markers
  used during verification: none present in the distributed files.
- Static JavaScript syntax checks and HyperFrames lint passed (zero errors,
  zero warnings). Runtime validation was performed directly in Chromium.
- Computed contrast: main headings 11.19:1, terminal output 15.27:1, terminal
  secondary labels 8.24:1, and footer 5.61:1. Inactive step labels use 3.69:1
  at 29 px. No audio balance or pronunciation check applies to this silent edit.

## Environment limits

- A fresh native Codex recording could not be made: the environment denied
  access to the local control socket. The finished video visibly identifies
  itself as a verified session replay. Model selection is recorded evidence,
  not independent proof of backend inference attribution.
- HyperFrames' full runtime check could not open a local port:
  `listen EPERM: operation not permitted 127.0.0.1`. Its empty runtime/layout/
  contrast sample lists are not treated as passing checks. The custom browser
  checks above cover the rendered composition instead.
- Registry installation, skill refresh, and usage lookup were unavailable
  through the restricted network. HyperFrames usage allowance is unknown.
  The installed CLI (0.8.75) supplied the scaffold and static lint.
- Export used the available Playwright browser tool to capture every PNG frame
  and local FFmpeg to encode them. The standalone `source/render.mjs` rebuild
  uses the same capture/encode sequence; it passed syntax review but was not
  launched as a separate Node process. A clean dependency install and the
  alternative HyperFrames render path were not verified in this environment.
- System fonts are not redistributed. The delivered MP4 has a fixed appearance;
  the editable player may use fallback fonts on a different operating system.

See [browser-checks.json](browser-checks.json) and
[contact-sheet.jpg](contact-sheet.jpg) for retained verification artifacts.
