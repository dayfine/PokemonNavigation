"""Combine the lab log and Command File Runner results into one trace."""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Dict, Iterable, List, Optional

from .cfr_parser import list_out_files, parse_out_file
from .common import format_time
from .log_parser import parse_log


def default_cfr_dir(log_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(log_path)), "CommandFiles", "outbox")


def record_id(rec: Dict[str, Any]) -> str:
    """Stable across re-extraction, so appends can skip records already kept."""
    parts = [rec["source"], rec["t"], rec["kind"]]
    if rec.get("batch"):
        parts.append(rec["batch"])
    if rec.get("line") is not None:
        parts.append(str(rec["line"]))
    return "|".join(parts)


def extract(log_path: Optional[str], cfr_dir: Optional[str] = None,
            since: Optional[_dt.datetime] = None, cfr_since: Optional[_dt.datetime] = None
            ) -> List[Dict[str, Any]]:
    """All records, sorted by time. `since` filters log records (and CFR
    records unless `cfr_since` is given separately)."""
    records: List[Dict[str, Any]] = []
    batch_starts = []
    if log_path:
        parser = parse_log(log_path)
        batch_starts = parser.batch_starts
        records.extend(parser.records)

    out_files = list_out_files(cfr_dir) if cfr_dir else []
    covered = set()
    cfr_records: List[Dict[str, Any]] = []
    for path in out_files:
        recs = parse_out_file(path, batch_starts)
        if recs and recs[0].get("time_source") == "log":
            covered.add((recs[0]["batch"], recs[0]["run_start"]))
        cfr_records.extend(recs)

    kept = []
    for rec in records:
        key = rec.pop("_batch_start", None)
        if key is not None and (rec["batch"], key) in covered:
            #  The .out file has this batch's commands with their results.
            continue
        if key is not None:
            rec["run_start"] = key
        kept.append(rec)

    since_s = format_time(since) if since else None
    cfr_since_s = format_time(cfr_since) if cfr_since else since_s
    result = [r for r in kept if since_s is None or r["t"] >= since_s]
    result += [r for r in cfr_records if cfr_since_s is None or r["t"] >= cfr_since_s]
    result.sort(key=lambda r: (r["t"], r.get("line") or 0))
    profile = profile_dir(log_path, cfr_dir)
    for rec in result:
        rec["id"] = record_id(rec)
        shot = rec.get("screenshot")
        if shot and profile and shot.startswith(profile + os.sep):
            rec["screenshot"] = shot[len(profile) + 1:]
    return result


def profile_dir(log_path: Optional[str], cfr_dir: Optional[str]) -> Optional[str]:
    """The lab profile folder (holds SerialPrograms.log, Screenshots/ and
    CommandFiles/). Screenshot paths under it are kept relative to it."""
    if log_path:
        return os.path.dirname(os.path.abspath(log_path))
    if cfr_dir:
        return os.path.dirname(os.path.dirname(os.path.abspath(cfr_dir)))
    return None


def write_jsonl(records: Iterable[Dict[str, Any]], path: Optional[str], append: bool = False) -> int:
    """Writes records, one JSON object per line. With `append`, skips records
    whose id is already in the file. Returns how many were written."""
    import sys
    existing = set()
    if append and path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing.add(json.loads(line).get("id"))
                    except ValueError:
                        pass
    count = 0
    if path:
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        f = open(path, "a" if append else "w", encoding="utf-8")
    else:
        f = sys.stdout
    try:
        for rec in records:
            if rec.get("id") in existing:
                continue
            compact = {k: v for k, v in rec.items() if v is not None}
            f.write(json.dumps(compact, separators=(",", ":"), ensure_ascii=False) + "\n")
            count += 1
    finally:
        if path:
            f.close()
    return count


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    opener = open
    if path.endswith(".gz"):
        import gzip
        opener = gzip.open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
