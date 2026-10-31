"""python3 -m pokenav.traces extract <log> [--since TIME] [--out FILE.jsonl | --out-dir DIR]
python3 -m pokenav.traces summary <FILE.jsonl | DIR>"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys

from .common import parse_since
from .extract import default_cfr_dir, extract, read_trace, write_jsonl, write_segments
from .summary import summarize

_EPOCH = _dt.datetime(1970, 1, 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pokenav.traces",
                                 description="Movement traces from console runs (docs/TRACES.md).")
    sub = ap.add_subparsers(dest="cmd")

    ex = sub.add_parser("extract", help="log (+ CFR results) -> JSON lines")
    ex.add_argument("log", help="SerialPrograms.log; '-' for none (CFR results only)")
    ex.add_argument("--since", help="keep records at or after this local time "
                                    "('2026-10-30', '2026-10-30 20:49', or '20:49' for today)")
    out = ex.add_mutually_exclusive_group()
    out.add_argument("--out", help="output .jsonl (default: stdout)")
    out.add_argument("--out-dir", help="one .jsonl per segment in this folder; '{day}' in it is "
                                       "replaced by the day the segment started")
    ex.add_argument("--append", action="store_true",
                    help="append to --out or --out-dir, skipping records already there")
    ex.add_argument("--cfr", help="Command File Runner outbox (default: CommandFiles/outbox "
                                  "next to the log)")
    ex.add_argument("--no-cfr", action="store_true", help="ignore Command File Runner results")
    ex.add_argument("--cfr-all", action="store_true",
                    help="keep every CFR result file, ignoring --since for them")
    ex.add_argument("--quiet", action="store_true", help="no summary on stderr")

    sm = sub.add_parser("summary", help="summarize a .jsonl trace")
    sm.add_argument("trace", help="a .jsonl file, or a folder of them")

    args = ap.parse_args(argv)
    if args.cmd == "extract":
        log = None if args.log == "-" else args.log
        cfr = None
        if not args.no_cfr:
            cfr = args.cfr or (default_cfr_dir(log) if log else None)
        since = parse_since(args.since) if args.since else None
        records = extract(log, cfr, since=since, cfr_since=None if not args.cfr_all else _EPOCH)
        if args.out_dir:
            written = write_segments(records, args.out_dir, append=args.append)
            n = sum(written.values())
        else:
            n = write_jsonl(records, args.out, append=args.append)
        if not args.quiet:
            print("extracted %d records, wrote %d%s" % (
                len(records), n, " new to " + args.out if args.out else ""), file=sys.stderr)
            if args.out_dir:
                for path, count in written.items():
                    print("  %5d %s" % (count, path), file=sys.stderr)
            print(summarize(records), file=sys.stderr)
        return 0
    if args.cmd == "summary":
        print(summarize(read_trace(args.trace)))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
