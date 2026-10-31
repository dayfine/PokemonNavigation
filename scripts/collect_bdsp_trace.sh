#!/bin/sh
# Add the movement trace of a BDSP console run to measurements/bdsp/.
#
# Usage: scripts/collect_bdsp_trace.sh START_TIME [PROFILE]
#   START_TIME  when the run started, local time: '2026-10-30 20:49' or '20:49' (today)
#   PROFILE     SerialPrograms profile folder name (default lab-B)
#
# Writes one file per segment (a series of AutoStory runs, a CFR session,
# keep-awake presses; see docs/TRACES.md) to measurements/bdsp/<day>-<PROFILE>/,
# <day> being the day the segment started. Skips records already there and
# prints the files written and a short summary.
set -eu

if [ $# -lt 1 ]; then
    sed -n '4,7p' "$0" >&2
    exit 2
fi
START=$1
PROFILE=${2:-lab-B}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROFILE_DIR="$HOME/Library/Application Support/SerialPrograms/Profiles/$PROFILE"
LOG="$PROFILE_DIR/SerialPrograms.log"

cd "$ROOT/python"
python3 -m pokenav.traces extract "$LOG" --since "$START" \
    --out-dir "$ROOT/measurements/bdsp/{day}-$PROFILE" --append
