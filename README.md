# sharex-sync

Keep ShareX recording settings, hotkeys, and the microphone in sync across the
team. Run one command on a new machine and it's configured to record the same
way everyone else does - no hunting through ShareX menus.

Zero runtime dependencies; works with any Python >= 3.10.

## Install

```powershell
uv tool install .          # from a checkout of this repo
uv tool install sharex-sync   # once published to PyPI
```

The executable is `sharex-sync`, also installed under the short alias `sharex`
- ShareX itself ships no CLI, so the name is free. Both run the exact same
commands; `sharex` is just less to type. A machine that has ShareX installed
(with its bundled `ffmpeg.exe`) is ready to go - nothing else needs to be set up.

## Commands

Run any command with `--help` for full options. All commands read ShareX's
config location automatically (registry, then `PersonalPath.cfg`, then
`MyDocuments\ShareX`); pass `--config-dir` to point at a specific folder.

Bare `sharex` (no subcommand) prints this help.

### `sharex-sync status`

Read-only readiness report for this machine. Exit code 0 = ready to record,
1 = something needs attention.

```
OK  config-dir         C:\Users\you\Documents\ShareX
OK  application-config ...
OK  hotkeys-config     ...
OK  sharex-installed   ...
OK  ffmpeg             ...
OK  sharex-running     running (leave running)
!! mic                no AudioSource configured (recordings will be silent) - run `sharex-sync mic`
```

Good first thing to run on a new machine or when something "stopped working".

### `sharex-sync mic`

Ensures ShareX's audio source points at a real microphone. Devices are detected
through ffmpeg; the first one whose name matches a preferred pattern (see
below) wins, falling back to any device named like "microphone"/"mic".

```
sharex-sync mic             # check only, no changes
sharex-sync mic --apply     # rewrite AudioSource if needed
```

Returns "already correct" if the saved device is still present, so it's safe to
run in a login script or scheduled task.

### `sharex-sync recctl`

An always-on-top recording control panel - for when ShareX's own Stop/Pause
toolbar fails to render (Avalonia rewrite, multi-monitor setups), and for when
the hotkeys themselves are hard to remember. It stays visible whether idle or
recording, and shows:

- which microphone is in use (from `ApplicationConfig.json`)
- a red `REC` indicator with elapsed time (or `IDLE`)
- **Record**, **Pause**, **Stop**, and **Abort** buttons, each labeled with its
  tracked keycap combo, that trigger the corresponding ShareX hotkeys
  (`ScreenRecorderActiveWindow`, `PauseScreenRecording`, `StopScreenRecording`,
  `AbortScreenRecording`) - so it doubles as a cheat sheet even if you never
  click it. Only the buttons valid for the current state are enabled (e.g.
  Pause/Stop/Abort are disabled while idle, matching the "don't press pause
  with nothing recording" gotcha below).

It detects recording by watching for ShareX's `ffmpeg.exe` worker process, so no
ShareX integration is needed. Requires the recording hotkeys to be registered:

```
sharex-sync hotkeys --apply
sharex-sync recctl
```

Close it with the **✕** button. Leave it running (e.g. add a shortcut to your
Startup folder) if you want it available at all times.

### `sharex-sync keys`

Prints the tracked hotkey cheat sheet - keycap combo (this machine's Keychron
legends) and the underlying Windows chord - straight from `defaults.py`, so it
never drifts from what's actually applied:

```
$ sharex-sync keys
Action                              Keycaps                    Windows chord
Capture region                      Control+PrintScreen        Ctrl+PrintScreen
Capture active window               Control+Option+W           Ctrl+Win+W
Start/Stop screen recording         Shift+PrintScreen          Shift+PrintScreen
Start/Stop screen recording (GIF)   Control+Shift+PrintScreen  Ctrl+Shift+PrintScreen
Record active window                Control+Option+R           Ctrl+Win+R
Pause/Resume screen recording       Control+Option+B           Ctrl+Win+B
Stop screen recording               Control+Option+X           Ctrl+Win+X
Abort screen recording              Control+Option+A           Ctrl+Win+A
```

### `sharex-sync config`

Applies the tracked capture settings (codec, FPS, bitrates, ...) to
`ApplicationConfig.json`, preserving everything machine-specific (mic, folders,
uploaders).

```
sharex-sync config --dry-run    # show what would change, write nothing
sharex-sync config --apply      # write changes and restart ShareX
sharex-sync config --apply --silent   # write but don't touch ShareX
```

A `.bak` backup of the previous file is written before every change.

### `sharex-sync hotkeys`

Writes the tracked hotkey set to `HotkeysConfig.json` (also with a `.bak`
backup). Use `--apply` to write and restart ShareX.

### `sharex-sync cut`

Finds the silent sections in a recording and prepares cut points for your
editor. One detection pass, then it emits project files for whichever editor
you use:

```
sharex-sync cut rec.mp4                       # write .llc + .mlt (default)
sharex-sync cut rec.mp4 --target losslesscut  # LosslessCut only
sharex-sync cut rec.mp4 --target shotcut      # Shotcut only
sharex-sync cut rec.mp4 --target ffmpeg       # cut directly, no editor
sharex-sync cut rec.mp4 --dry-run             # just show the cut plan
```

- **LosslessCut** writes `rec-proj.llc` — LosslessCut's own autosave format,
  so it auto-loads the cut points when you open `rec.mp4`. Review, then export.
- **Shotcut** writes `rec.mlt` — a project with the kept segments already on
  the timeline (it has no built-in silence detection, so this saves the manual
  marking). Open it, review the cuts, export.
- **ffmpeg** cuts and concatenates the kept segments directly into
  `rec.cut.mp4`. Lossless `-c copy` cuts are keyframe-aligned — the start can
  round back to the previous keyframe (several seconds with ShareX's default
  GOP). Pass `--reencode` for frame-accurate cuts.

Tunables: `--threshold-db` (default -30), `--min-silence` (default 1.0s),
`--margin` (default 0.2s of padding kept around speech). `--open` launches
Shotcut/LosslessCut with the generated project.

LosslessCut is free from GitHub releases; the Microsoft Store charge only buys
auto-updates and a signed installer.

### Why commands restart ShareX

ShareX writes its configs on exit. If you edit the files while it's running,
ShareX will overwrite your edits when it closes. The sync commands stop ShareX
(`-ExitShareX`), write the files, then restart it (`-silent`) so the changes
stick. `--silent` skips the stop/start if you're managing ShareX yourself.

## What is tracked, and where to change it

All tracked settings live in **`defaults.py`** in the repo - this is the single
"edit here" point. Change a value, commit, and the whole team gets it.

Three things are managed there:

| Block | Applies to | Contents |
| --- | --- | --- |
| `FFMPEG_SETTINGS` | `DefaultTaskSettings.CaptureSettings.FFmpegOptions` | codec, x264 preset/CRF, bitrates, resolution/FPS args |
| `CAPTURE_SETTINGS` | `DefaultTaskSettings.CaptureSettings` | FPS, cursor visibility, auto-start |
| `HOTKEYS` | `HotkeysConfig.json` | key combos mapped to ShareX jobs (capture, record, pause) |

**Only machine-independent settings are tracked.** The microphone
(`AudioSource`) is deliberately not in `defaults.py` because device names
differ between people; it's resolved per machine by `sharex-sync mic`.

### Editing defaults.py after `uv tool install`

`uv tool install` copies the package into an isolated venv, so your edits go
to the installed copy there, not the repo:

```
%LOCALAPPDATA%\uv\tools\sharex-sync\Lib\site-packages\sharex_sync\defaults.py
```

Editing that file works but is overwritten by the next `uv tool install`. For
team-wide changes, edit it in the repo and reinstall (or wait for a published
release).

## Microphone gotchas

- ShareX has **no "system default" audio device**. If the saved device name
  doesn't match a device on the machine, it falls back to none and recordings
  are silent. `sharex-sync status` reports this, and `sharex-sync mic` fixes it.
- Use the **friendly device name** (e.g. `Microphone (PD100U)`). The raw
  `@device_cm_...\wave_...` form gets double-escaped by ShareX and fails.
- A missing device never crashes ShareX - it just records without audio. So
  don't worry about a machine without a mic; it still records video.

## Hotkeys worth knowing (Keychron on this machine)

Windows mode: **Left Option → Win**, **Command → Alt**, **Right Option → RAlt**.

Recording suite — **same modifiers** (Control+Option+… = Ctrl+Win+…):

| Action | Press (keycaps) | Windows chord | Notes |
|--------|-----------------|---------------|--------|
| Record | **Control+Option+R** | Ctrl+Win+R | |
| Pause | **Control+Option+B** | Ctrl+Win+B | **P is OS-reserved** (Ctrl+Win+P) |
| Stop (save) | **Control+Option+X** | Ctrl+Win+X | |
| Abort | **Control+Option+A** | Ctrl+Win+A | Esc does not abort |

## Keep ShareX running

```powershell
sharex-sync start          # start ShareX if not running
sharex-sync mic --apply    # also ensures ShareX is up
sharex-sync hotkeys --apply
```
- Don't press pause when **no recording is active** - it can wedge ShareX's
  overlay. Recover by force-killing ShareX and restarting.

## Logging

The package writes a daily-rotating log (7 days retained by default) to
`~/.sharex-sync/logs/`. Configurable with environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SHAREX_SYNC_LOG_DIR` | `~/.sharex-sync/logs` | where `sharex-sync.log` lives |
| `SHAREX_SYNC_LOG_RETENTION` | `7` | daily log backups to keep |

`--verbose` switches both console and file logging to debug level.

## Development

```powershell
uv sync                # create .venv
uv run sharex-sync status
```

## Roadmap

- **Editing pipeline** - `sharex-sync cut` is in: silence detection with
  LosslessCut (`.llc`) and Shotcut (`.mlt`) project generation plus direct
  lossless ffmpeg cuts. Next: `--open` polish, keyframe-aware copy cuts
  (probe GOP), segment naming from detection.
- **Watchdog** - detect and report long pause/stop stalls caused by ffmpeg's
  buffer flush.
- **Publishing** - tag + build wheel so `uv tool install sharex-sync` works
  without a checkout.
