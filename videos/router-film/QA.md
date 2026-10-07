# Delivery verification

Verified locally on 2026-10-07. The delivered film is 48 seconds, landscape
1920×1080 at 30 fps, with original SVG animation, narration, music and effects.

## Completed checks

- Rendered all 1,440 frames in a browser from the final standalone player;
  checked every requested frame index. SVG generation is deterministic and
  contains no invalid numeric values across the full timeline.
- Encoded the final MP4 as H.264 `yuv420p` with 48 kHz stereo AAC. `ffprobe`
  counted 1,440 frames and reported exactly 48 seconds for both streams.
- Decoded the entire exported MP4 with `ffmpeg -v error -xerror`; exit status
  was zero, with no decode errors.
- Played the actual MP4 from beginning to end in Chromium: the media element
  reached 48 seconds with no error, 1,440 displayed frames and zero dropped
  frames reported by the browser.
- Visually inspected 96 frames extracted from the exported MP4, at half-second
  intervals across all six scenes. Also reviewed full-size opening and ending
  frames during development. See the [contact sheet](qa/contact-sheet.jpg).
- Reviewed labels, character placement, policy examples and transitions;
  widened the policy label, corrected its deep-debug wording, separated it
  from the hat, improved supporting-copy contrast, and completed the short
  task-envelope movements before their scene changes.
- Sampled SVG text bounds at 192 points, every quarter second; no text
  extended beyond the checked frame margins. Essential copy remains within
  the landscape safe area. This is a 16:9 delivery; a vertical crop needs
  a separate layout pass.
- Tested standalone-player play, pause, seek, restart, mute and unmute. It
  completed a full 48-second playback, showed Replay, and selected frame
  1,439 at the ending. It requested no external resources.
- Measured audio loudness and true peak. Narration ends at 44.239 seconds,
  allowing approximately 3.76 seconds for the final message and musical tail.
  Narration clips do not overlap. Music is ducked during speech and its
  speech-frequency bands are reduced. Exact measurements are in the
  [technical report](qa/REPORT.md).
- HyperFrames static lint passed with zero errors and zero warnings.
  The editable Node renderer passed a JavaScript syntax check.

## Verification limits and unmet requirement

The requested verified neural TTS voice was unavailable. Cloud TTS was not
authenticated; network downloads and local neural weights were unavailable.
The delivered fallback is Apple AVFoundation's **Nicky** voice,
`com.apple.ttsbundle.siri_nicky_en-US_compact`. Its underlying model version
and neural status are unknown. Source clips and separate stems are supplied
so that a verified neural voice can replace it.

No direct auditory listening review was possible through the tools used.
Pronunciation, expressive performance and perceived voice/music balance remain
unverified by ear. Timing, media playback, signal levels and loudness were
checked programmatically; those checks do not substitute for listening.

HyperFrames' complete runtime check and preview could not bind a local server
(`listen EPERM`). They did not pass. Its optional export wrapper has not been
verified to match the delivered MP4. The delivered export used the working
managed browser tool and FFmpeg. The portable `source/render.mjs` implements
the same capture/encoding procedure, but was not run end to end as a standalone
local Node process in this environment.

Product claims were checked against the repository; the film illustrates its
default policy. It is not a recording of fresh inference, and it makes no
performance, savings or universal compatibility claim. See [sources and
asset attribution](SOURCES.md) and [repository compatibility](../../docs/compatibility.md).

This report records local verification. It does not establish the status of
later repository pushes, remote CI runs or other publishing steps.
