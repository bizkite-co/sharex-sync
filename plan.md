# sharex-sync — Plan

Keep ShareX recording settings, hotkeys, and the microphone in sync so a team
can adopt a single working configuration. Installed via `uv tool install`.

## Status

v1 (config sync + mic + health) is **done** and smoke-tested:

- `sharex-sync status`   - machine readiness report (configs, ffmpeg, mic)
- `sharex-sync mic`      - auto-select recording device (PD100U preferred)
- `sharex-sync config`   - apply tracked capture settings (with backup)
- `sharex-sync hotkeys`  - apply tracked hotkeys (with backup)
- Daily rotating logs, 7-day retention (configurable via env vars).
- README.md - coworker adoption doc (install, commands, `defaults.py` as the
  edit-here point, mic gotchas).
- `sharex-sync cut` - editing pipeline (v1): ffmpeg silencedetect -> keep
  segments -> emits a LosslessCut `.llc` and/or Shotcut `.mlt` project, or
  direct lossless `-c copy` cuts. Backends ("plugins") are pluggable. Tests
  added for `cut.py`. Validated against Shotcut's bundled `melt`.

## Design principles

- One runtime dependency: Rich, for terminal output (house style: borderless
  tables, subtle background bands for grouping, shared with our other tools).
- Only machine-independent settings are tracked in `defaults.py`.
  AudioSource is resolved per machine (device names differ between people).
- Write path: stop ShareX -> edit JSON -> start ShareX, so its save-on-exit
  cannot overwrite the edits.
- Never crash on a missing mic; ShareX records silently instead.

## Next steps (proposed order)

1. ~~**README.md**~~ - done (see Status).
2. **Watchdog** (`sharex-sync watch`) - monitor for long pause/stop latency.
   Root cause is ffmpeg buffer flush on pause (~1.5 s observed); watchdog
   should detect and report stalls, not fix them.
3. **Tests** - unit tests exist for `cut`; extend to `defaults`/`config`/`mic`
   (JSON fixtures, fake ffmpeg device listing) so changes to tracked settings
   stay safe.
4. **CI-friendly checks** - `sharex-sync config --check` reading the real
   config read-only, usable as a pre-commit or scheduled check.
5. **Publishing** - tag + build wheel for the team; document `uv tool install`.
6. **Editing pipeline polish** - `cut --open` integration, keyframe-aware copy
   cuts (probe GOP), segment naming from detection, `.mlt` QA in Shotcut.

## Editing pipeline (decided)

Two backends ("plugins") are supported by `sharex-sync cut`, chosen because
users want options: **Shotcut** (free NLE, no silence detection built in, so
project pre-generation is the win) and **LosslessCut** (free from GitHub
releases - the $19.99 is only the Microsoft Store convenience version;
keyframe-accurate, no re-encode).

`sharex-sync cut` flow:
1. ffmpeg `silencedetect` (noise/duration/margin tunable) -> silent ranges.
2. Invert to "keep" segments with padding.
3. Emit per target:
   - **LosslessCut**: `{video stem}-proj.llc` v2 JSON5 (`cutSegments`), the
     autosave convention, so LosslessCut auto-loads the cut points on open.
   - **Shotcut**: `{video stem}.mlt` - one `producer` per kept segment on V1
     with in/out timecodes; validates in Shotcut's bundled `melt`.
   - **ffmpeg**: direct lossless `-c copy` cut+concat (keyframe-aligned; re-encode
     `--reencode` for frame accuracy).

LosslessCut is also programmable via HTTP API (`--http-api`, port 8080) and
`.llc`/CSV/EDL/XML import-export - future automation hooks.

Not an NLE; when real edits are needed: **DaVinci Resolve** (free) or
**Shotcut/Kdenlive** (lighter). OBS is capture/streaming only, not an NLE.

Remaining: `cut --open` launcher polish, keyframe-aware copy cuts (probe GOP),
segment naming, `.mlt` QA pass.

## Recording source (open question)

ShareX's file management is sharing-focused (History has no duration; upload
destinations). Not a blocker yet - cheapest fix is a recorder browser in
`sharex-sync` (watch Screenshots folder, list ffprobe duration/size, rename
into day folders). Full ffmpeg-direct recorder (own RegisterHotKey + overlay +
pause via NtSuspendProcess for instant pause) is viable but weeks of work;
only pursue if ShareX's pause/overlay becomes a hard blocker.

## Environment notes

- ShareX 21.0.0, config at `%USERPROFILE%\OneDrive\Documents2\ShareX\`
  (personal path: registry -> PersonalPath.cfg -> `MyDocuments\ShareX`).
- ShareX has no "system default" audio device; missing device resets to none.
- Friendly device name (`Microphone (PD100U)`) is reliable; the
  `@device_cm_...\wave_...` form gets double-escaped by ShareX and fails.
- Pause = `Ctrl+Alt+P`; pressing it with no active recording can wedge the
  overlay (force-kill + restart to recover).
