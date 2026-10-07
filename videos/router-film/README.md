# Keep the thread

A 48-second illustrated introduction to **Codex Task Router**. Landscape
1920×1080, 30 fps, original SVG animation, narration, original music and sound
effects. The theme is **“Different tasks. One conversation.”**

## Watch and download

- [MP4](renders/codex-task-router.mp4): H.264 picture and AAC stereo audio.
- [Self-contained player](renders/player.html): download and open in a modern
  browser. Click Play to enable audio. Play/pause, seeking, restart, mute,
  responsive layout and sentence captions are included. No server or internet
  connection is needed.
- [Subtitles](renders/codex-task-router.srt): sentence-level SRT, timed to the
  actual narration clips; these are not inferred word timestamps.
- [Cover](renders/cover.png): 1920×1080 PNG.

The film is an illustrated explanation, **not a live terminal recording**.
Model labels show examples from the default policy. Availability and policy
configuration determine actual routing.

## Voice limitation

The requested high-quality neural voice could not be supplied in this
environment: online TTS was not signed in, package/model downloads were
unavailable, and no Kokoro model was cached. The delivered fallback is Apple's
installed **Nicky** system voice through AVFoundation, identifier
`com.apple.ttsbundle.siri_nicky_en-US_compact`, rate `0.44`, pitch multiplier
`1.02`, 22,050 Hz mono source, resampled for the final 48 kHz stereo mix.
The exact underlying model/version and neural status are not exposed and have
**not** been verified. This is not presented as a verified neural voice.

The exact script is supplied, and voice, music and SFX remain separate. Replace
the voice clips with an authorized neural provider or a human recording, adjust
timings and rebuild if a verified neural voice is required. No API keys or voice
model weights are included. See [QA.md](QA.md) for verification limits.

## Editable project

| File | Purpose |
| --- | --- |
| `source/film.js` | All original illustration, glyph paths, palette, motion and scene timings; plain JavaScript producing SVG |
| `script.json` | Narration text, line start times and output specification |
| `STORYBOARD.md` | Six scenes and their purpose |
| `design.md` | Palette, lettering, framing and motion direction |
| `source/voice.swift`, `source/narrate.py` | Optional macOS system-voice regeneration |
| `source/audio.py` | Original musical score, procedural SFX, speech timing, EQ carve, ducking, mix and SRT |
| `assets/audio/01-*.caf` … `08-*.caf` | Original rendered narration clips |
| `assets/audio/narration.wav` | Assembled voice stem |
| `assets/audio/music-original.wav` | Original instrumental stem |
| `assets/audio/sfx-original.wav` | Original sound-effects stem |
| `assets/audio/mix.wav`, `mix.m4a` | Final stereo mix; M4A is embedded in the player |
| `assets/audio/timing.json` | Measured voice durations and actual provider attribution |
| `source/build.py` | Embeds artwork and audio in `renders/player.html`; also generates optional HyperFrames wrapper |
| `source/render.mjs` | Offline browser frame rendering and FFmpeg MP4 encoding |
| `index.html`, `hyperframes.json` | Optional HyperFrames authoring/export wrapper; animation remains plain JavaScript |

Every visual frame comes from `RouterFilm.frame(time)` in `film.js`. Seeking is
deterministic; there is no simulation state, fetch, random seed or third-party
animation library required at playback. Original vector glyphs avoid font
downloads and font substitution.

## Rebuild

The delivered files play immediately. A rebuild needs Python 3 with NumPy,
Node.js, FFmpeg/ffprobe, Playwright and its Chromium browser. Install dependencies
in a local virtual environment and this project; no global install is needed:

```sh
cd videos/router-film
python3 -m venv .venv
.venv/bin/python -m pip install numpy
npm install
npx playwright install chromium
```

Reusing the supplied narration clips:

```sh
.venv/bin/python source/audio.py
.venv/bin/python source/build.py
node source/render.mjs
```

To change only the artwork or copy, edit `source/film.js`, run `source/build.py`
and render. To edit speech, edit `script.json` and replace/regenerate the clips
first. macOS with the listed voice and Xcode Command Line Tools can regenerate
the delivered system voice explicitly:

```sh
.venv/bin/python source/narrate.py
.venv/bin/python source/audio.py
.venv/bin/python source/build.py
node source/render.mjs
```

`narrate.py` deliberately identifies its actual Apple voice; it does not claim
to generate a neural replacement or silently call a paid provider. Audio mixing
refuses overlapping narration and a closing line that overruns the ending.
Any substantial retiming also requires updating `film.js`, `script.json` and
the fixed duration/frame count in the build/render scripts together.

The renderer uses the exact same standalone player as the deliverable. PNG
frames are piped directly to FFmpeg, with `libx264`, CRF 17, `yuv420p`, 30 fps,
AAC audio copied from the final mix and fast-start MP4 metadata. No HTTP server
is necessary. The environment used for this delivery exposed a managed browser
tool; frames were captured through it, then encoded with these same settings.

Optional HyperFrames commands are pinned to the cached authoring version in
`package.json`. Its static lint passed here, but its runtime check/preview could
not bind a local server (`listen EPERM`). Those checks are not claimed as
passed, and HyperFrames export parity has not been established.

## Cover and publishing copy

**Cover:** Different tasks. One conversation.

**Caption:** Tiny tasks, big plans, tangled bugs. Codex Task Router chooses a
model and reasoning effort before each new turn in an automatic session—while
keeping the conversation together. Explore the editable policy and try `auto`.

Repository: <https://github.com/Shrinidhikulkarni7/codex-task-router>

Suggested accessibility description: A hand-drawn paper character in a folded
hat guides a file, a plan and a bug along one coral thread. Task examples receive
Luna, Sol and Astra labels. A policy book and approval symbol reinforce editable
choices and continued Codex approvals. The thread ends beneath “Different
tasks. One conversation.”

The repository README links to the MP4, cover, offline player and subtitles.
Download the player before opening it; GitHub's file view does not execute HTML.
