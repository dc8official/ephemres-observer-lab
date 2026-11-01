"""Late replies, loss causes, send lag, the warm-up cycle and note editing (server/analysis.py, probe_lab)."""
import asyncio
import json
import os
import tempfile
import unittest

import probe_lab
from server import analysis
from server.analysis import attach_late, loss_causes, make_row
from server.kernel_clock import Reception

T0 = 1_700_000_000_000_000_000


def pkt(seq, k_us=1000, lag_us=100, send_lag_ns=50_000, lost=False):
    tx = T0 + seq * 1_000_000_000
    if lost:
        return [seq, tx, None, None, None, 0, 0, send_lag_ns]
    krx = tx + int(k_us * 1000)
    return [seq, tx, krx, krx + int(lag_us * 1000), None, 1, seq + 1, send_lag_ns]


class RowTest(unittest.TestCase):
    def test_eight_field_packet_and_old_seven_field_packet(self):
        r = make_row(0, 0, 1, "10.0.0.1", pkt(0, send_lag_ns=1_500_000))
        self.assertAlmostEqual(r["send_lag_us"], 1500)
        old = make_row(0, 0, 1, "10.0.0.1", pkt(0)[:7])         # engines before send-lag recording
        self.assertIsNone(old["send_lag_us"])

    def test_late_reply_is_attached_to_the_lost_row(self):
        rows = [make_row(0, 0, 7, "10.0.0.1", pkt(s, lost=True)) for s in range(2)]
        ok = attach_late(rows, {"icmp_id": 7, "seq": 1, "krx": rows[1]["tx"] + 1_500_000_000, "urx": rows[1]["tx"] + 2_500_000_000})
        self.assertTrue(ok)
        self.assertIsNone(rows[0]["late_krx"])
        self.assertEqual(rows[1]["late_krx"], rows[1]["tx"] + 1_500_000_000)
        self.assertFalse(attach_late(rows, {"icmp_id": 99, "seq": 0, "krx": 1, "urx": 2}))   # warm-up ping: no row


class LossCauseTest(unittest.TestCase):
    def test_three_causes(self):
        rows = [make_row(0, 0, 1, "t", pkt(s, lost=True)) for s in range(3)]
        rows[1]["late_krx"] = rows[1]["tx"] + 1_000_000_000      # kernel had it after 1 s: in time (timeout 2 s)
        rows[2]["late_krx"] = rows[2]["tx"] + 3_000_000_000      # after 3 s: the network was late
        self.assertEqual(loss_causes(rows, 2.0), {"no_reply": 1, "after_timeout": 1, "read_late": 1})


class WarmupTest(unittest.TestCase):
    def setUp(self):
        # cycle 0: huge lag (ramp-up artefact); cycle 1: steady state
        self.rows = ([make_row(0, 0, 1, "t", pkt(s, lag_us=50_000)) for s in range(3)]
                     + [make_row(0, 1, 1, "t", pkt(s, lag_us=100)) for s in range(3, 6)]
                     + [make_row(0, 1, 1, "t", pkt(6, lost=True))])
        self.meta = {"sent": 7, "replied": 6, "reader_calls": 6}

    def test_first_cycle_excluded_when_several_cycles(self):
        s = analysis.analyse(self.rows, self.meta, {"cycles": 2})["summary"]
        self.assertEqual(s["warmup_cycles_excluded"], 1)
        self.assertEqual((s["sent"], s["replied"], s["lost"], s["n_lag"]), (4, 3, 1, 3))
        self.assertAlmostEqual(s["lag_max_us"], 100)
        self.assertEqual(s["reader_calls"], 3)                   # recounted from the measured rows
        self.assertAlmostEqual(s["send_lag_mean_us"], 50)

    def test_single_cycle_keeps_everything(self):
        s = analysis.analyse(self.rows, self.meta, {"cycles": 1})["summary"]
        self.assertEqual((s["warmup_cycles_excluded"], s["sent"], s["n_lag"]), (0, 7, 6))


class LikeForLikeTest(unittest.TestCase):
    def test_new_settings_and_old_runs(self):
        old = {"cfg": {"stagger_window_s": 24}}                   # saved before cycles/timeout/hw existed
        new = {"cfg": {"stagger_window_s": 24.0, "cycles": 1, "cycle_length_s": 60, "timeout_s": 2, "hw_timestamps": False}}
        self.assertEqual(analysis.differing_settings([old, new]), [])
        hw = {"cfg": {**new["cfg"], "hw_timestamps": True}}
        self.assertEqual(analysis.differing_settings([new, hw]), ["hw_timestamps: False / True"])
        multi = {"cfg": {**new["cfg"], "cycles": 3}}
        self.assertTrue(any(d.startswith("cycles") for d in analysis.differing_settings([new, multi])))


class NoteTest(unittest.TestCase):
    def test_update_note_changes_meta_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [make_row(0, 0, 1, "t", pkt(0))]
            an = analysis.analyse(rows, {})
            for base in ("run-a", "run-b"):
                analysis.save_run(d, base, {"note": "old"}, {}, rows, an)
            analysis.update_note(d, "run-b", "checks semaphore 5")
            with open(os.path.join(d, "run-b.meta.json")) as f:
                self.assertEqual(json.load(f)["config"]["note"], "checks semaphore 5")
            with open(os.path.join(d, "INDEX.md")) as f:
                text = f.read()
            self.assertIn("- **Description:** checks semaphore 5", text)
            self.assertEqual(text.count("- **Description:** old"), 1)        # run-a untouched


class FakeSocket:
    def __init__(self):
        self.queue = []

    def send_echo(self, target, icmp_id, seq):
        return T0

    def recv_one(self):
        if not self.queue:
            raise BlockingIOError
        return self.queue.pop(0)


class MuxLateTest(unittest.IsolatedAsyncioTestCase):
    async def test_timed_out_ping_then_late_reply(self):
        mux = probe_lab._RawICMPMultiplexer(FakeSocket())
        seen = []
        mux.on_late = seen.append
        p = await mux.ping("10.0.0.1", 5, 0, timeout=0.01)       # nobody answers in time
        self.assertIsNone(p.rx)
        self.assertIn((5, 0), mux._expired)
        mux.k.queue = [Reception(5, 0, "10.0.0.1", T0 + 30_000_000, None, T0 + 31_000_000, 0)]
        mux._on_readable()
        self.assertEqual((mux.late, mux.unmatched, mux.reader_calls), (1, 0, 0))
        self.assertIs(seen[0], p)
        self.assertEqual(p.late_rx.kernel_ns, T0 + 30_000_000)
        mux.k.queue = [Reception(5, 0, "10.0.0.1", 1, None, 2, 0)]      # a duplicate: now foreign
        mux._on_readable()
        self.assertEqual((mux.late, mux.unmatched), (1, 1))


if __name__ == "__main__":
    unittest.main()


class ErrorPercentTest(unittest.TestCase):
    """The worked example from the docs: four packets RTT 4 ms / lag 0.1 ms (2.5 % each) and one packet with
    RTT 0.2 ms / lag 1 ms (500 %)."""
    def setUp(self):
        self.rows = ([make_row(0, 0, 1, "t", pkt(s, k_us=4000, lag_us=100)) for s in range(4)]
                     + [make_row(1, 0, 2, "t", pkt(4, k_us=200, lag_us=1000))])

    def test_three_definitions(self):
        s = analysis.analyse(self.rows, {})["summary"]
        self.assertAlmostEqual(s["pct_total"], 100 * 1400 / 16200)      # PRIMARY: 8.64 %
        self.assertAlmostEqual(s["pct_median"], 2.5)
        self.assertAlmostEqual(s["pct_mean"], (4 * 2.5 + 500) / 5)       # 102 %
        self.assertAlmostEqual(s["pct_max"], 500)

    def test_endpoint_uses_total_ratio(self):
        eps = {e["ep"]: e for e in analysis.analyse(self.rows, {})["endpoints"]}
        self.assertAlmostEqual(eps[0]["pct_total"], 2.5)
        self.assertAlmostEqual(eps[1]["pct_total"], 500)

    def test_cli_uses_the_same_primary_definition(self):
        pr = [probe_lab.PacketResult(0, 0, "t", 1, i, 0, Reception(1, i, "t", k * 1000, None, k * 1000 + l * 1000, 0))
              for i, (k, l) in enumerate([(4000, 100)] * 4 + [(200, 1000)])]
        self.assertAlmostEqual(probe_lab.total_error_pct(pr), 100 * 1400 / 16200)


class BurstTest(unittest.TestCase):
    def test_windows_merge_skip_warmup_and_align_with_scatter(self):
        t0 = T0                                                     # first measured ping's tx
        bursts = [[0, 0, t0 - 9_000_000, t0 - 6_000_000],           # warm-up cycle: left out when cycles > 1
                  [0, 1, t0 + 1_000_000, t0 + 4_000_000],
                  [1, 1, t0 + 3_000_000, t0 + 6_000_000],           # overlaps the previous one: merged
                  [2, 1, t0 + 10_000_000, t0 + 13_000_000]]
        self.assertEqual(analysis._burst_windows(bursts, t0, skip=1), [[1.0, 6.0], [10.0, 13.0]])
        self.assertEqual(len(analysis._burst_windows(bursts, t0, skip=0)), 3)
        self.assertEqual(analysis._burst_windows(bursts, None, 0), [])

    def test_analyse_returns_bursts_on_the_scatter_axis(self):
        rows = [make_row(0, 0, 1, "t", pkt(s)) for s in range(2)]
        an = analysis.analyse(rows, {}, {}, [[0, 0, rows[0]["tx"] + 2_000_000, rows[0]["tx"] + 5_000_000]])
        self.assertEqual(an["bursts"], [[2.0, 5.0]])


class TinyRttTest(unittest.TestCase):
    def test_flag(self):
        lan = analysis.analyse([make_row(0, 0, 1, "t", pkt(s, k_us=3000)) for s in range(3)], {})["summary"]
        lo = analysis.analyse([make_row(0, 0, 1, "t", pkt(s, k_us=15)) for s in range(3)], {})["summary"]
        self.assertFalse(lan["rtt_too_small"])
        self.assertTrue(lo["rtt_too_small"])
        self.assertAlmostEqual(lo["kernel_rtt_median_us"], 15)


class CombineTest(unittest.TestCase):
    def item(self, lag, engine="go", series="b1", rep=1, role="test"):
        rows = [make_row(0, 0, 1, "t", pkt(s, lag_us=lag)) for s in range(3)]
        return {"name": f"{engine}-{rep}", "meta": {}, "analysis": analysis.analyse(rows, {}),
                "cfg": {"engine": engine, "cpu_mode": "single_core", "series_id": series, "repeat": rep, "role": role}}

    def test_groups_and_median_range(self):
        items = [self.item(100, rep=1), self.item(300, rep=2), self.item(200, rep=3), self.item(50, "rust")]
        groups = analysis.combine(items)
        self.assertEqual([g["n"] for g in groups], [3, 1])
        row = dict((label, stat) for label, _t, stat in groups[0]["rows"])["Observer intrusion mean"]
        self.assertEqual(tuple(round(v) for v in row), (200, 100, 300))
        md = analysis.compare_combined_markdown(items)
        self.assertIn("200.0 µs (100.0 µs to 300.0 µs)", md)

    def test_runs_outside_a_series_stay_single(self):
        a, b = self.item(100, series=None), self.item(100, series=None)
        self.assertEqual([g["n"] for g in analysis.combine([a, b])], [1, 1])

    def test_floor_runs_do_not_trigger_the_like_for_like_warning(self):
        test = {"cfg": {"simulated_db_ms": 3.0, "role": "test"}}
        floor = {"cfg": {"simulated_db_ms": 0.0, "role": "floor"}}
        self.assertEqual(analysis.differing_settings([test, floor]), [])
        self.assertTrue(analysis.differing_settings([test, {"cfg": {"simulated_db_ms": 5.0}}]))
