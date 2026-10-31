# Movement traces

Every console run leaves a trace: one JSON object per line, one line per
controller input or screen-checked walk, so the physics model
([PHYSICS.md](PHYSICS.md)) can be fitted from what was pressed and what the
screen showed.

## Making a trace

```sh
cd python
python3 -m pokenav.traces extract <SerialPrograms.log> [--since TIME] [--out FILE.jsonl | --out-dir DIR]
python3 -m pokenav.traces summary FILE.jsonl|DIR
```

- `<SerialPrograms.log>`: the lab app's log, e.g.
  `~/Library/Application Support/SerialPrograms/Profiles/lab-B/SerialPrograms.log`.
  Only lines matching the patterns below are read; the file can be large.
- Command File Runner (CFR) results are read from `CommandFiles/outbox/*.out`
  next to the log (`--cfr DIR` for another folder, `--no-cfr` to skip them).
- `--since`: local time, `2026-10-30`, `2026-10-30 20:49` or `20:49` (today).
  `--cfr-all` keeps every `.out` file regardless of `--since`.
- `--out-dir`: one file per segment (below), `DIR/<name>.jsonl`; `{day}` in
  `DIR` is replaced by the day the segment started.
- `--append`: add to `--out` or `--out-dir`, skipping records whose `id` is
  already there (anywhere in the folder for `--out-dir`).
- A summary (outcome counts, single holds, tap runs) goes to stderr.
  `summary` takes a file or a folder of them.

After each console run, the main session runs

```sh
scripts/collect_bdsp_trace.sh "2026-10-30 20:49"   # the run's start time [PROFILE]
```

which adds the run's segments to `measurements/bdsp/<day>-lab-B/`. Run it
after the run has ended: a walk still going is recorded as `unterminated` and
is not replaced later.

## Segments

A day's trace is split into files by what was being done
(`python/pokenav/traces/segment.py`). A unit is one program run or one CFR
batch; units form three series:

| Series | Units | File name |
|---|---|---|
| AutoStory runs | AutoStory runs, keyed by the objective they started from, and the CFR batches that loaded their save (`r<N>...`, e.g. `r163a-load`) | `<first>-<last run tag>-<objective id>-<checkpoints>`, e.g. `r158-r163-0005f-jubilife-clown-company`, `r142-r153-0005a-jubilife-center-to-barry` |
| CFR work | other CFR batches (walking by hand, probing, menus), keyed by the objective of the next AutoStory run (else the one before) | `cfr-<objective id>-<what that run does>-<first>-<last batch tag>`, e.g. `cfr-0005f-jubilife-clown-company-m158-m163` |
| Keep-awake | other programs (`PreventSleep`) and `keepawake*` CFR batches | `keepawake-<start>-<end>` (HHMM) |

A series is cut where a unit starts more than 45 minutes after the previous
unit of the series ended, and at midnight. Other details:

- A run tag is the batch name's leading letters and digits (`m158-w1` ->
  `m158`, `r163a-load` -> `r163`); a run with no load batch is named
  `run-<HHMM>`.
- The objective id drops the dot (`00.05f` -> `0005f`); an objective
  without one adds nothing. Then come the checkpoints the runs went
  through, first to last (`sandgem-center-to-mart-lady`), or, for runs
  without checkpoints, the objective's text (`0004-after-pokedex`).
- Load batches with no AutoStory run in the trace are `cfr-loads-<tags>`.
- AutoStory runs of two panels can overlap in time; so can their segments.
- Names depend on what the extraction saw: collecting one run at a time can
  name a segment differently than extracting the whole day at once. Records
  are never duplicated (`--append` skips known `id`s).

## Sources

| Source | `source` | Where the times come from |
|---|---|---|
| A program run (e.g. `PokemonBDSP:AutoStory`) in the log | `program` | the log line that queued the input |
| A CFR batch with its `.out` file | `cfr` | the log's `Command File Runner: running <name>` time plus the `@start-end` offsets (`time_source: "log"`), or, without that line, the file's modification time minus the batch length (`time_source: "mtime"`) |
| A CFR batch whose `.out` was overwritten or never written | `cfr` | the log, like a program run; no `line`, `command` or walk results |

Log lines read: `Starting Program: X`, `Program State: STOPPED`,
`[AutoStory] Objective:`, `[Checkpoint] X: start`, `[Event] cp/i name:
start|done|failed`, `Command File Runner: running X`, `issue_left_joystick()`,
`issue_right_joystick()`, `issue_buttons()`, `issue_dpad()`,
`issue_mash_button()`, `issue_nop()` (timing only), `[Walk] ...`,
`[Route] Turning X.`, other `[Route]`/`[Talk]`/`[Sign]` lines (kept as notes),
and screenshot lines (`[Checkpoint] Screenshot:`, `Failure screenshot:`,
`Save prompt screenshot:`).

## Record

A field that is unknown or does not apply is left out.

| Field | Type | Meaning |
|---|---|---|
| `v` | int | Schema version (1). |
| `id` | str | `source\|t\|kind[\|batch\|line]`; stable when the same log is read again. |
| `kind` | str | `input` (one controller command) or `walk` (a hold that watched the screen). |
| `t` | str | Start, local wall clock of the lab Mac, ISO to the ms (`2026-10-30T20:49:14.755`). No time zone. |
| `t_end` | str | End: the input's start plus hold plus release; a walk's last slice end, or the time its result was logged if later. |
| `source` | str | `program` or `cfr`. |
| `program` | str | Program name, e.g. `PokemonBDSP:AutoStory`, `NintendoSwitch:CommandFileRunner`. |
| `run_start` | str | When the program run (or CFR batch) started; groups records of one run. |
| `batch`, `line`, `command` | str, int, str | CFR: batch (file) name, line number in it, and the command text. |
| `time_source` | str | CFR: `log` or `mtime` (see Sources). |
| `objective`, `checkpoint`, `event` | str | AutoStory context at the time: objective text, checkpoint id, `checkpoint/index name` of the event running. |
| `input` | obj | What was pressed (below). For a walk: the stick position held, no hold or release. |
| `role` | str | `turn`, `tap`, `hold`, `walk_for`, `probe`, `press` for inputs; `walk_until`, `cfr_walk` for walks (below). |
| `run` | obj | Taps only: `{id, index, count}`: which run of taps, its 0-based position, how many taps it has. |
| `label` | str | The program's name for the walk, e.g. `West to the hedges`, `To the Pokemon Center: south 3 (to wall)`. |
| `outcome` | str | How a walk or a `walk_for` hold ended (below). Plain inputs have none. |
| `total_ms` | int | Walks: how long the stick was held in all (sum of slices). `walk_for`: its hold. |
| `moving_ms` | int | Walks: end of the last slice that changed the screen by at least `still_threshold`, from the start of the walk; 0 if none did. |
| `slice_ms` | int | Walks: slice length (program `walk_until` 400, CFR `walk` 200). |
| `changes` | [num] | Walks: screen change of each slice, in order: RMSD between frames at 192x108 (0 identical). Walking scrolls about 16 to 110 per 400 ms slice; standing against a wall reads 3 to 9; above 120 is a scene change. |
| `still_threshold` | num | Walks: below this a slice counts as still (10). |
| `walk_max_ms` | int | CFR walks: the `max` argument. |
| `wild_battles` | int | Wild battles run from during the walk. |
| `battle_inputs` | int | Inputs sent during a walk to run from battles (not recorded on their own). |
| `notes` | [str] | Up to 8 log lines after the record and before the next input (`[Route]`, `[Talk]`, `[Sign]`, `[Walk] ... stopped on blocked.`), or what a CFR command printed. |
| `screenshot` | str | The next screenshot of the same run or batch after this record; relative to the lab profile folder (`Screenshots/...`, `CommandFiles/outbox/...`) when under it. |
| `screenshot_after_ms` | int | From `t_end` to the screenshot. |
| `probe_first_move_ms`, `probe_last_move_ms` | int | `probe_walk()` results. |

### `input`

| `type` | Fields |
|---|---|
| `stick` | `stick` (`L`/`R`), `x`, `y` in -1..1, **y = +1 is north (up)**, `dir` (`N`, `S`, `E`, `W`, or a diagonal such as `NE`; `""` centred), `hold_ms`, `release_ms` |
| `button` | `buttons` (`A`, `B`, `HOME`, ...), `hold_ms`, `release_ms`; `mash: true` for a mash, whose `hold_ms` is its duration |
| `dpad` | `dir` (`N`/`S`/`E`/`W`), `hold_ms`, `release_ms` |

`release_ms` is the time after the hold before the next command may start
(the log's `delay - hold`; the CFR command's release argument).

### `role`

| Role | What it is |
|---|---|
| `turn` | Program: the short hold after `[Route] Turning X.` (100 ms) that faces a direction. |
| `tap` | Program: one of the holds after `[Walk] <label>: N taps.` CFR: one of two or more consecutive `stick L` lines toward one direction with holds of 100 to 300 ms. |
| `walk_for` | Program: a single timed hold (`walk_for()`), ended with `limit after a N ms hold`. |
| `hold` | Any other stick hold (a CFR `stick` line, or a program hold with no walk line). |
| `probe` | Program: a `probe_walk()` hold. |
| `press` | A button or d-pad press. |
| `walk_until` | Program walk: 400 ms slices until the screen stops changing, a dialog, a black screen, or the limit. |
| `cfr_walk` | CFR `walk x y [max] [still]`: 200 ms slices until two slices in a row are still, or `max`. |

### `outcome`

| Outcome | Meaning |
|---|---|
| `blocked` | Program walk: two slices in a row changed the screen less than 10: walking into something. |
| `still` | CFR walk: the same test (two still slices). |
| `limit` | Ran out of time (the walk's limit, a `walk_for` hold's length, a CFR walk's `max`) without stopping. |
| `transition` | The screen went black and came back without a battle: a door or a new area. |
| `dialog` | A dialog box opened. |
| `arrived` | The caller's own check (e.g. a location banner) matched. |
| `unterminated` | The walk's end was never logged: the event failed or the program stopped mid-walk. |

## What a record does not know

These are not in the log, so a record cannot say them; later measurements
(screenshots read for position, map overlays, pret data, emulator memory for
FRLG) can add fields for them:

- **The true position**: tile, sub-tile offset, and map, before and after.
  `label`, `event` and the screenshot are hints, not positions.
- **Facing before the input**, so whether a hold turned, stepped, or both.
- **Whether a timed hold moved at all**, and how far: `turn`, `tap`, `hold`
  and `walk_for` records have no screen reading. Only walks measure movement,
  and only as screen change per slice, not tiles.
- **Exact console timing**: `t` is when the app queued the command (and for
  commands queued together, the sum of earlier delays), not when the Switch
  saw it. Expect tens of ms of jitter; the controller's frame boundaries are
  unknown.
- **What blocked a walk**: a wall, a sign, an NPC, a ledge, or a dropped
  frame; a slice with change exactly 0 is a stalled video, which the program
  walker ignores but the record keeps.
- **NPC positions**, time of day, running or biking (the inputs say whether B
  was pressed, not whether the player ran).
- **The camera**: screen change depends on what scrolls into view (an
  animated TV keeps a still player "moving").

## Summary of 2026-10-30 (lab-B)

`measurements/bdsp/2026-10-30-lab-B/` (26 files) and
`measurements/bdsp/2026-10-29-lab-B/` (4 files, CFR batches of the day
before): the lab-B log from 2026-10-30 00:00 and every CFR `.out` file.
7,746 records:
5,173 program inputs, 859 program walks, 1,490 CFR inputs, 224 CFR walks.

- Program walks (`walk_until`): blocked 575, limit 219, transition 25,
  arrived 22, dialog 17, unterminated 1. `walk_for`: limit 499.
- CFR walks: still 196, limit 28. Of the 1,068 walks with a screen-change
  series, 184 never moved.
- Single holds: 160 ms, 268 (223 program `walk_for`, 45 CFR); 200 ms, 155
  (77 `walk_for`, 78 CFR). None has a screen reading. The only program walk
  of a single 160 ms slice (2) read still. A CFR walk's first 200 ms slice
  changed the screen in 51 of 224 walks (23%); 188 of 224 had moved by the end
  of their second slice (400 ms), so walking shows on screen only after about
  200 ms of holding.
- Tap runs: 47; program 23 (14 single taps, 7 of 4, 2 of 6, all 160 ms hold
  and 400 ms release), CFR 24 (2 to 11 taps of 100 to 200 ms, 300 to 1200 ms
  apart).
