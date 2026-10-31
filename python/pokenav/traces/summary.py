"""A short text summary of a trace: outcomes, single holds, tap runs."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List


def _first_slice_moved(rec: Dict[str, Any]) -> bool:
    changes = rec.get("changes") or []
    return bool(changes) and changes[0] >= (rec.get("still_threshold") or 10)


def summarize(records: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    kinds = Counter((r["source"], r["kind"]) for r in records)
    lines.append("records: %d (%s)" % (
        len(records), ", ".join("%s %s %d" % (s, k, n) for (s, k), n in sorted(kinds.items()))))
    if records:
        lines.append("time span: %s to %s" % (records[0]["t"], records[-1]["t"]))

    # Outcomes of everything that reports one.
    outcomes = Counter()
    for r in records:
        if r.get("outcome"):
            outcomes[(r.get("role") or r["kind"], r["outcome"])] += 1
    lines.append("")
    lines.append("outcomes (by walker):")
    by_role = defaultdict(list)
    for (role, outcome), n in outcomes.items():
        by_role[role].append((outcome, n))
    for role in sorted(by_role):
        parts = sorted(by_role[role], key=lambda p: -p[1])
        lines.append("  %-10s %s" % (role, ", ".join("%s %d" % p for p in parts)))

    # Walks: how much moved.
    walks = [r for r in records if r["kind"] == "walk" and r.get("moving_ms") is not None]
    if walks:
        still_start = sum(1 for r in walks if r["moving_ms"] == 0)
        lines.append("walks with a screen-change series: %d; never moved: %d" % (len(walks), still_start))

    # Single holds of 160 and 200 ms.
    lines.append("")
    lines.append("single holds of 160 / 200 ms (stick, not part of a tap run):")
    for hold in (160, 200):
        singles = [r for r in records if r["kind"] == "input"
                   and (r.get("input") or {}).get("type") == "stick"
                   and (r["input"].get("hold_ms") == hold) and r.get("role") in ("hold", "walk_for")]
        by = Counter((r["source"], r["role"], r.get("outcome") or "-") for r in singles)
        lines.append("  %d ms: %d total; %s" % (
            hold, len(singles), ", ".join("%s/%s/%s %d" % (k + (n,)) for k, n in sorted(by.items()))))
    lines.append("  (a timed hold has no screen-change reading in the log or the CFR")
    lines.append("   results; 'moved' is only known where a walk measured it:)")
    for hold in (160, 200):
        measured = [r for r in records if r["kind"] == "walk" and r.get("role") == "walk_until"
                    and r.get("total_ms") == hold and r.get("changes")]
        moved = sum(1 for r in measured if r["moving_ms"])
        lines.append("  program walk_until of one %d ms slice: %d, moved %d" % (hold, len(measured), moved))
    cfr_walks = [r for r in records if r.get("role") == "cfr_walk" and r.get("changes")]
    if cfr_walks:
        moved = sum(1 for r in cfr_walks if _first_slice_moved(r))
        lines.append("  CFR walk, first 200 ms slice changed the screen: %d of %d (%.0f%%)" % (
            moved, len(cfr_walks), 100.0 * moved / len(cfr_walks)))
        moved2 = sum(1 for r in cfr_walks if len(r["changes"]) > 1 and max(r["changes"][:2]) >= (r.get("still_threshold") or 10))
        lines.append("  CFR walk, moved within its first 400 ms: %d of %d" % (moved2, len(cfr_walks)))

    # Tap runs.
    runs = defaultdict(list)
    for r in records:
        if r.get("role") == "tap" and r.get("run"):
            runs[(r["source"], r["run"]["id"])].append(r)
    lines.append("")
    lines.append("tap runs: %d" % len(runs))
    shapes = Counter()
    for (source, _), taps in runs.items():
        inp = taps[0]["input"]
        shapes[(source, len(taps), inp.get("hold_ms"), inp.get("release_ms"))] += 1
    for (source, n, hold, release), count in sorted(shapes.items()):
        lines.append("  %-7s %2d taps of %s ms, %s ms apart: %d" % (source, n, hold, release, count))
    return "\n".join(lines)
