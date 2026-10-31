#!/bin/sh
# Append the movement trace of a BDSP console run to measurements/bdsp/.
#
# Usage: scripts/collect_bdsp_trace.sh START_TIME [PROFILE]
#   START_TIME  when the run started, local time: '2026-10-30 20:49' or '20:49' (today)
#   PROFILE     SerialPrograms profile folder name (default lab-B)
#
# Writes measurements/bdsp/<date>-<PROFILE>.jsonl (date of START_TIME, else today),
# skipping records already in it, and prints a short summary of what was added.
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
DAY=$(printf '%s' "$START" | grep -Eo '^[0-9]{4}-[0-9]{2}-[0-9]{2}' || date +%F)
OUT="$ROOT/measurements/bdsp/$DAY-$PROFILE.jsonl"

cd "$ROOT/python"
python3 -m pokenav.traces extract "$LOG" --since "$START" --out "$OUT" --append
