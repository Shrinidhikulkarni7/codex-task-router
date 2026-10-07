# Export report — 2026-10-07

| Property | Measured result |
| --- | --- |
| Container | MP4, fast-start metadata |
| File size | 7,875,592 bytes |
| Video | H.264 High, `yuv420p`, 1920×1080 |
| Rate / frame count | 30/1 fps, 1,440 frames |
| Video / audio duration | 48.000 / 48.000 seconds |
| Audio | AAC-LC, 48,000 Hz, 2 channels |
| Integrated loudness | −15.92 LUFS |
| True peak | −1.50 dBTP |
| Loudness range | 6.00 LU |
| Final narration end | 44.239458 seconds |
| Complete FFmpeg decode | Exit 0; no errors |
| Chromium MP4 playback | Ended at 48s; 1,440 frames; 0 dropped; no media error |
| Standalone HTML playback | Ended at 48s; final frame 1,439; no media error |
| Standalone external requests | 0 |

Visual sampling covered every half second of the export, 0–47.5 seconds:
96 decoded images, reviewed in four contact sheets. This retained
[six-frame overview](contact-sheet.jpg) shows the main visual states.
The delivered cover is the actual exported frame at 45 seconds.

Reproduce the file checks from the film directory:

```sh
ffprobe -v error -count_frames \
  -show_entries format=duration,size:stream=index,codec_name,width,height,avg_frame_rate,nb_read_frames,sample_rate,channels,duration \
  -of json renders/codex-task-router.mp4
ffmpeg -v error -xerror -i renders/codex-task-router.mp4 -f null -
ffmpeg -hide_banner -i renders/codex-task-router.mp4 -vn \
  -af loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json -f null -
```

The loudness values above are the filter's **input** measurements of the
already encoded export. No second normalization pass was applied to the MP4.

See [QA.md](../QA.md) for the voice limitation, unperformed auditory review,
HyperFrames runtime restriction and independent rebuild verification limit.
