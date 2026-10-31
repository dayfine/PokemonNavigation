"""Tests for pokenav.traces. Run: cd python && python3 -m unittest discover tests"""

import datetime as dt
import json
import os
import tempfile
import unittest

from pokenav.traces.cfr_parser import parse_out_text
from pokenav.traces.common import parse_since, stick_direction
from pokenav.traces.extract import extract, read_jsonl, read_trace, write_jsonl, write_segments
from pokenav.traces.log_parser import LogParser
from pokenav.traces.segment import batch_tag, objective_slug, segment
from pokenav.traces.summary import summarize

PROFILE = "/lab/Profiles/lab-B"

PROGRAM_LOG = """\
2026-10-30 20:49:14.351842 - [Program]: <b>Starting Program: PokemonBDSP:AutoStory</b>
2026-10-30 20:49:14.352854 - [Program]: [AutoStory] Objective: 00.05f Jubilife: the clown.
2026-10-30 20:49:14.353112 - [Program]: [Checkpoint] jubilife_clown_company: start, 2 events
2026-10-30 20:49:14.353120 - [Program]: [Event] jubilife_clown_company/1 to_the_lamp: start
2026-10-30 20:49:14.353182 - [Console 0]: [Route] Turning west.
2026-10-30 20:49:14.353219 - [Console 0]: issue_left_joystick(): (-1.000,0.000), delay = 400ms, hold = 100ms, cooldown = 0ms
2026-10-30 20:49:14.353300 - [Console 0]: BlackScreenWatcher: Count = 3, Mean = 1 ms, Stddev = 0 ms, Min = 1 ms, Max = 1 ms
2026-10-30 20:49:14.755701 - [Console 0]: issue_left_joystick(): (-1.000,0.000), delay = 400ms, hold = 400ms, cooldown = 0ms
2026-10-30 20:49:15.164130 - [Console 0]: [Walk] West to the hedges: 400ms, screen change 79.537706.
2026-10-30 20:49:15.164792 - [Console 0]: issue_left_joystick(): (-1.000,0.000), delay = 400ms, hold = 400ms, cooldown = 0ms
2026-10-30 20:49:15.569856 - [Console 0]: [Walk] West to the hedges: 800ms, screen change 56.902039.
2026-10-30 20:49:15.569923 - [Console 0]: issue_left_joystick(): (-1.000,0.000), delay = 400ms, hold = 400ms, cooldown = 0ms
2026-10-30 20:49:15.977920 - [Console 0]: [Walk] West to the hedges: 1200ms, screen change 6.371934.
2026-10-30 20:49:15.979862 - [Console 0]: issue_left_joystick(): (-1.000,0.000), delay = 400ms, hold = 400ms, cooldown = 0ms
2026-10-30 20:49:16.385415 - [Console 0]: [Walk] West to the hedges: 1600ms, screen change 5.775185.
2026-10-30 20:49:17.587000 - [Console 0]: [Walk] West to the hedges: blocked after 1600ms, 0 wild battle(s).
2026-10-30 20:49:17.587010 - [Console 0]: [Walk] West to the hedges: stopped on blocked.
2026-10-30 20:49:17.587020 - [Console 0]: [Route] Turning east.
2026-10-30 20:49:17.587030 - [Console 0]: issue_left_joystick(): (1.000,0.000), delay = 400ms, hold = 100ms, cooldown = 0ms
2026-10-30 20:49:17.990000 - [Console 0]: [Walk] East along the hedges: 3 taps.
2026-10-30 20:49:17.990100 - [Console 0]: issue_left_joystick(): (1.000,0.000), delay = 560ms, hold = 160ms, cooldown = 0ms
2026-10-30 20:49:17.990110 - [Console 0]: issue_left_joystick(): (1.000,0.000), delay = 560ms, hold = 160ms, cooldown = 0ms
2026-10-30 20:49:17.990120 - [Console 0]: issue_left_joystick(): (1.000,0.000), delay = 560ms, hold = 160ms, cooldown = 0ms
2026-10-30 20:49:17.990130 - [Console 0]: issue_nop(): duration = 800ms
2026-10-30 20:49:21.000000 - [Console 0]: issue_left_joystick(): (0.000,1.000), delay = 200ms, hold = 200ms, cooldown = 0ms
2026-10-30 20:49:22.400000 - [Console 0]: [Walk] Into the gap beside the sign: limit after a 200ms hold, 0 wild battle(s).
2026-10-30 20:49:22.500000 - [Console 0]: issue_buttons(): A, delay = 80ms, hold = 80ms, cooldown = 0ms
2026-10-30 20:49:24.500000 - [Console 0]: [Talk] Clown by the Poketch Company: no dialogue opened.
2026-10-30 20:49:24.600000 - [Program]: [Event] jubilife_clown_company/1 to_the_lamp: done
2026-10-30 20:49:24.700000 - [Program]: [Checkpoint] Screenshot: /lab/Profiles/lab-B/Screenshots/AutoStory/route/x-step.png
2026-10-30 20:49:30.000000 - [Program]: Program State: STOPPED
"""

CFR_LOG = """\
2026-10-30 23:06:49.000000 - [Program]: <b>Starting Program: NintendoSwitch:CommandFileRunner</b>
2026-10-30 23:06:49.354883 - [Program]: Command File Runner: running m169-w1
2026-10-30 23:06:49.354953 - [Console 0]: issue_left_joystick(): (0.000,-1.000), delay = 800ms, hold = 200ms, cooldown = 0ms
2026-10-30 23:06:50.156777 - [Console 0]: issue_left_joystick(): (1.000,0.000), delay = 200ms, hold = 200ms, cooldown = 0ms
2026-10-30 23:06:55.957974 - [Program]: Command File Runner: inbox is empty.
2026-10-30 23:07:01.000000 - [Program]: Command File Runner: running lost-batch
2026-10-30 23:07:01.100000 - [Console 0]: issue_buttons(): B, delay = 580ms, hold = 80ms, cooldown = 0ms
2026-10-30 23:07:02.000000 - [Program]: Command File Runner: inbox is empty.
"""

CFR_OUT = """\
ok 1 stick L 0 -1 200 600 @0-801ms
walk still after 1600ms, moving 1200ms; changes 22 63 75 76 50 14 5 6
ok 2 walk 1 0 4000 @801-2600ms
shot /lab/Profiles/lab-B/CommandFiles/outbox/m169-w1_lamp.png
ok 3 shot lamp @2600-2660ms
ok 4 stick L -1 0 50 400 @2660-3110ms
ok 5 stick L -1 0 160 600 @3110-3876ms
ok 6 stick L -1 0 160 600 @3876-4642ms
ok 7 stick L -1 0 160 600 @4642-5408ms
ok 8 press A 80 1500 @5408-6990ms
ok 9 dpad UP @6990-7300ms
error line 10 (expect home 3000): timeout
shot /lab/Profiles/lab-B/CommandFiles/outbox/m169-w1_error.png
end
"""


def parse_program_log(text):
    p = LogParser()
    p.feed_lines(text.splitlines())
    p.finish()
    return p.records


class CommonTests(unittest.TestCase):
    def test_stick_direction_y_up_is_north(self):
        self.assertEqual(stick_direction(0, 1), "N")
        self.assertEqual(stick_direction(0, -1), "S")
        self.assertEqual(stick_direction(-1, 0), "W")
        self.assertEqual(stick_direction(1, 1), "NE")
        self.assertEqual(stick_direction(0, 0), "")

    def test_parse_since(self):
        self.assertEqual(parse_since("2026-10-30"), dt.datetime(2026, 10, 30))
        self.assertEqual(parse_since("2026-10-30 20:49"), dt.datetime(2026, 10, 30, 20, 49))
        self.assertEqual(parse_since("2026-10-30T20:49:14.5"), dt.datetime(2026, 10, 30, 20, 49, 14, 500000))
        self.assertEqual(parse_since("20:49", today=dt.date(2026, 10, 30)), dt.datetime(2026, 10, 30, 20, 49))
        with self.assertRaises(ValueError):
            parse_since("yesterday")


class LogParserTests(unittest.TestCase):
    def setUp(self):
        self.records = parse_program_log(PROGRAM_LOG)

    def test_record_sequence(self):
        roles = [(r["kind"], r["role"]) for r in self.records]
        self.assertEqual(roles, [
            ("input", "turn"), ("walk", "walk_until"), ("input", "turn"),
            ("input", "tap"), ("input", "tap"), ("input", "tap"),
            ("input", "walk_for"), ("input", "press"),
        ])

    def test_walk_until(self):
        walk = self.records[1]
        self.assertEqual(walk["label"], "West to the hedges")
        self.assertEqual(walk["outcome"], "blocked")
        self.assertEqual(walk["total_ms"], 1600)
        self.assertEqual(walk["moving_ms"], 800)
        self.assertEqual(walk["changes"], [79.54, 56.9, 6.37, 5.78])
        self.assertEqual(walk["slice_ms"], 400)
        self.assertEqual(walk["input"]["dir"], "W")
        self.assertNotIn("hold_ms", walk["input"])
        self.assertEqual(walk["t"], "2026-10-30T20:49:14.755")
        self.assertEqual(walk["notes"], ["[Walk] West to the hedges: stopped on blocked."])
        self.assertEqual(walk["program"], "PokemonBDSP:AutoStory")
        self.assertEqual(walk["checkpoint"], "jubilife_clown_company")
        self.assertEqual(walk["event"], "jubilife_clown_company/1 to_the_lamp")
        self.assertEqual(walk["source"], "program")

    def test_turn(self):
        turn = self.records[0]
        self.assertEqual(turn["input"], {"type": "stick", "stick": "L", "x": -1.0, "y": 0.0,
                                         "dir": "W", "hold_ms": 100, "release_ms": 300})

    def test_taps_are_scheduled_one_after_another(self):
        taps = self.records[3:6]
        self.assertEqual([t["t"] for t in taps],
                         ["2026-10-30T20:49:17.990", "2026-10-30T20:49:18.550", "2026-10-30T20:49:19.110"])
        self.assertEqual([t["run"]["index"] for t in taps], [0, 1, 2])
        self.assertTrue(all(t["run"]["count"] == 3 and t["label"] == "East along the hedges" for t in taps))
        self.assertEqual(taps[0]["input"]["release_ms"], 400)

    def test_walk_for(self):
        hold = self.records[6]
        self.assertEqual(hold["label"], "Into the gap beside the sign")
        self.assertEqual(hold["outcome"], "limit")
        self.assertEqual(hold["input"]["hold_ms"], 200)
        self.assertEqual(hold["input"]["dir"], "N")

    def test_press_notes_and_no_screenshot(self):
        press = self.records[7]
        self.assertEqual(press["input"]["buttons"], "A")
        self.assertEqual(press["notes"], ["[Talk] Clown by the Poketch Company: no dialogue opened."])
        self.assertFalse(any("screenshot" in rec for rec in self.records))

    def test_unterminated_walk(self):
        text = "\n".join(PROGRAM_LOG.splitlines()[:11]) + \
            "\n2026-10-30 20:49:16.000000 - [Program]: [Event] jubilife_clown_company/1 to_the_lamp: failed: x\n"
        records = parse_program_log(text)
        self.assertEqual(records[-1]["outcome"], "unterminated")
        self.assertEqual(records[-1]["total_ms"], 800)


class CfrTests(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 10, 30, 23, 6, 49, 354883)
        self.records = parse_out_text(CFR_OUT, "m169-w1", self.start, "log")

    def test_records(self):
        self.assertEqual([r["line"] for r in self.records], [1, 2, 4, 5, 6, 7, 8, 9])
        walk = self.records[1]
        self.assertEqual(walk["kind"], "walk")
        self.assertEqual(walk["outcome"], "still")
        self.assertEqual(walk["moving_ms"], 1200)
        self.assertEqual(walk["total_ms"], 1600)
        self.assertEqual(walk["changes"], [22, 63, 75, 76, 50, 14, 5, 6])
        self.assertEqual(walk["walk_max_ms"], 4000)
        self.assertEqual(walk["input"]["dir"], "E")
        self.assertEqual(walk["t"], "2026-10-30T23:06:50.155")

    def test_shot_lines_are_skipped(self):
        self.assertFalse(any("screenshot" in rec for rec in self.records))
        self.assertFalse(any("shot" in note for rec in self.records for note in rec["notes"] or []))

    def test_tap_run_skips_the_turn(self):
        roles = [r["role"] for r in self.records[2:6]]
        self.assertEqual(roles, ["hold", "tap", "tap", "tap"])
        self.assertEqual(self.records[3]["run"], {"id": "m169-w1:5", "index": 0, "count": 3})

    def test_defaults_and_error(self):
        dpad = self.records[-1]
        self.assertEqual(dpad["input"], {"type": "dpad", "dir": "N", "hold_ms": 100, "release_ms": 200})
        self.assertIn("next line failed", dpad["notes"][0])


class ExtractTests(unittest.TestCase):
    def test_log_and_outbox(self):
        with tempfile.TemporaryDirectory() as root:
            log = os.path.join(root, "SerialPrograms.log")
            with open(log, "w") as f:
                f.write(PROGRAM_LOG + CFR_LOG)
            outbox = os.path.join(root, "CommandFiles", "outbox")
            os.makedirs(outbox)
            out = os.path.join(outbox, "m169-w1.out")
            with open(out, "w") as f:
                f.write(CFR_OUT.replace(PROFILE, root))
            written = dt.datetime(2026, 10, 30, 23, 7, 0).timestamp()
            os.utime(out, (written, written))

            records = extract(log, outbox)
            cfr = [r for r in records if r["source"] == "cfr"]
            #  m169-w1 comes from its .out file; lost-batch only from the log.
            self.assertEqual(sum(1 for r in cfr if r["batch"] == "m169-w1"), 8)
            self.assertTrue(all(r.get("time_source") == "log" for r in cfr if r["batch"] == "m169-w1"))
            lost = [r for r in cfr if r["batch"] == "lost-batch"]
            self.assertEqual(len(lost), 1)
            self.assertEqual(lost[0]["input"]["buttons"], "B")
            self.assertEqual(records, sorted(records, key=lambda r: r["t"]))

            later = extract(log, outbox, since=dt.datetime(2026, 10, 30, 23, 0))
            self.assertTrue(all(r["source"] == "cfr" for r in later))

            path = os.path.join(root, "trace.jsonl")
            self.assertEqual(write_jsonl(records[:5], path), 5)
            self.assertEqual(write_jsonl(records, path, append=True), len(records) - 5)
            back = read_jsonl(path)
            self.assertEqual(len(back), len(records))
            #  The program name is used to cut segments, not written.
            self.assertTrue(all("program" in r for r in records))
            self.assertFalse(any("program" in r for r in back))
            self.assertNotIn(None, [v for r in back for v in r.values()])
            json.dumps(back)

            text = summarize(records)
            self.assertIn("tap runs: 2", text)
            self.assertIn("walk_until blocked 1", text)


def _rec(t, source, run_start, **kw):
    rec = {"v": 1, "kind": "input", "t": "2026-10-30T" + t, "source": source,
           "run_start": "2026-10-30T" + run_start}
    if source == "cfr":
        rec["program"] = "NintendoSwitch:CommandFileRunner"
    rec.update(kw)
    rec["id"] = "|".join([source, rec["t"], rec.get("batch") or "", str(rec.get("line") or "")])
    return rec


def _cfr(t, batch, line=1):
    return _rec(t, "cfr", t, batch=batch, line=line)


def _story(t, run_start, objective, checkpoint=None):
    return _rec(t, "program", run_start, program="PokemonBDSP:AutoStory",
                objective=objective, checkpoint=checkpoint)


CLOWN = "00.05f Jubilife: the clown by the Poketch Company (events)."
POKETCH = "00.05g Jubilife: the Poketch from the president (events)."


class SegmentTests(unittest.TestCase):
    def setUp(self):
        self.records = sorted([
            _cfr("19:00:00.000", "m158-load"),
            _cfr("19:01:00.000", "m158-w1"),
            _cfr("19:02:00.000", "m159-w1"),
            _cfr("19:50:00.000", "r158a-load"),
            _story("19:52:00.000", "19:52:00.000", CLOWN, "jubilife_clown_company"),
            _story("19:53:00.000", "19:52:00.000", CLOWN, "jubilife_clown_company"),
            _rec("19:54:00.000", "program", "19:54:00.000", program="NintendoSwitch:PreventSleep"),
            _cfr("19:55:00.000", "keepawake1"),
            _cfr("20:00:00.000", "r159a-load"),
            _story("20:01:00.000", "20:01:00.000", CLOWN, "jubilife_clown_company"),
            #  After the last clown run: walking from its save toward the next leg.
            _cfr("20:05:00.000", "m160-w1"),
            _cfr("22:00:00.000", "r160a-load"),
            _story("22:01:00.000", "22:01:00.000", POKETCH, "jubilife_poketch"),
        ], key=lambda r: r["t"])

    def test_names(self):
        segs = segment(self.records)
        self.assertEqual(list(segs), [
            "2026-10-30/cfr-0005f-jubilife-clown-company-m158-m159",
            "2026-10-30/r158-r159-0005f-jubilife-clown-company",
            "2026-10-30/keepawake-1954-1955",
            "2026-10-30/cfr-0005g-jubilife-poketch-m160",
            "2026-10-30/r160-0005g-jubilife-poketch",
        ])
        self.assertEqual(sorted(r["id"] for v in segs.values() for r in v),
                         sorted(r["id"] for r in self.records))

    def test_gap_and_midnight_cut_a_series(self):
        late = _cfr("23:59:00.000", "m161-w1")
        early = dict(_cfr("00:01:00.000", "m161-w2"), t="2026-10-31T00:01:00.000",
                     run_start="2026-10-31T00:01:00.000")
        segs = segment(self.records + [late, early])
        self.assertIn("2026-10-30/cfr-0005g-jubilife-poketch-m161", segs)
        self.assertIn("2026-10-31/cfr-0005g-jubilife-poketch-m161", segs)

    def test_checkpoint_range_and_objective_text(self):
        recs = [
            _story("13:00:00.000", "13:00:00.000", "00.05a Jubilife: steps.", "jubilife_center"),
            _story("13:01:00.000", "13:00:00.000", "00.05b Jubilife: school.", "jubilife_school"),
            _story("13:02:00.000", "13:00:00.000", "00.05c Jubilife: Barry.", "jubilife_barry"),
            _story("14:00:00.000", "14:00:00.000", "00.04 - After Pokedex (after the catch). Ends: x"),
        ]
        self.assertEqual(list(segment(recs)), [
            "2026-10-30/run-1300-0005a-jubilife-center-to-barry",
            "2026-10-30/run-1400-0004-after-pokedex",
        ])

    def test_helpers(self):
        self.assertEqual(batch_tag("r163a-load"), "r163")
        self.assertEqual(batch_tag("m158-w1"), "m158")
        self.assertEqual(batch_tag("del-3"), "del")
        self.assertEqual(objective_slug(CLOWN), "0005f")
        self.assertEqual(objective_slug("Route 202 to Sandgem's Pokemon Center (events)."),
                         "route-202-to-sandgem")

    def test_write_segments_append(self):
        with tempfile.TemporaryDirectory() as root:
            out = os.path.join(root, "{day}-lab-B")
            first = write_segments(self.records[:5], out)
            self.assertEqual(sum(first.values()), 5)
            again = write_segments(self.records, out, append=True)
            self.assertEqual(sum(again.values()), len(self.records) - 5)
            back = read_trace(os.path.join(root, "2026-10-30-lab-B"))
            self.assertEqual([r["id"] for r in back], [r["id"] for r in self.records])
            self.assertEqual(write_segments(self.records, out, append=True), {})


if __name__ == "__main__":
    unittest.main()
