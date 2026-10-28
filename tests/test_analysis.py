"""server/analysis.py: per-run analysis, like-for-like check, CSV round trip."""
import os
import tempfile
import unittest

from server import analysis
from server.analysis import differing_settings, make_row

T0 = 1_700_000_000_000_000_000          # an arbitrary CLOCK_REALTIME ns


def pkt(seq, k_us, lag_us, batch=1, wakeup=1):
    """A 'cycle' event packet: kernel RTT k_us, observer lag lag_us (None = lost)."""
    tx = T0 + seq * 1_000_000_000
    if k_us is None:
        return [seq, tx, None, None, None, 0, 0]
    krx = tx + int(k_us * 1000)
    return [seq, tx, krx, krx + int(lag_us * 1000), None, batch, wakeup]


class MakeRowTest(unittest.TestCase):
    def test_derived_microseconds(self):
        r = make_row(3, 0, 0x1003, "10.0.0.1", pkt(0, 2000, 150))
        self.assertAlmostEqual(r["k_us"], 2000)
        self.assertAlmostEqual(r["u_us"], 2150)
        self.assertAlmostEqual(r["lag_us"], 150)

    def test_lost_packet(self):
        r = make_row(0, 0, 1, "10.0.0.1", pkt(0, None, None))
        self.assertIsNone(r["k_us"])
        self.assertIsNone(r["lag_us"])


class AnalyseTest(unittest.TestCase):
    def setUp(self):
        self.rows = ([make_row(0, 0, 1, "10.0.0.1", pkt(s, 1000, lag)) for s, lag in enumerate([40, 120, 600])]
                     + [make_row(1, 0, 2, "10.0.0.1", pkt(0, 1000, 30_000, batch=3, wakeup=9)),
                        make_row(1, 0, 2, "10.0.0.1", pkt(1, None, None))])
        self.an = analysis.analyse(self.rows, {"sent": 5, "replied": 4, "reader_calls": 2})

    def test_summary(self):
        s = self.an["summary"]
        self.assertEqual((s["sent"], s["replied"], s["lost"]), (5, 4, 1))
        self.assertAlmostEqual(s["lag_mean_us"], (40 + 120 + 600 + 30_000) / 4)
        self.assertAlmostEqual(s["lag_max_us"], 30_000)
        self.assertAlmostEqual(s["pct_max"], 3000.0)                       # 30 ms lag on a 1 ms RTT
        self.assertEqual(s["packets_per_wakeup"], 2.0)
        self.assertEqual(s["max_batch"], 3)

    def test_histogram_buckets(self):
        counts = dict(zip(self.an["hist"]["labels"], self.an["hist"]["counts"]))
        self.assertEqual(counts["<50 µs"], 1)
        self.assertEqual(counts["100-150 µs"], 1)
        self.assertEqual(counts["0.5-1 ms"], 1)
        self.assertEqual(counts["25-50 ms"], 1)
        self.assertEqual(sum(counts.values()), 4)

    def test_kernel_quantiles(self):
        kq = {q["q"]: q["rtt_us"] for q in self.an["kernel_quantiles"]}
        self.assertEqual(set(kq), set(analysis.QUANTILES))
        self.assertAlmostEqual(kq[0.0], 1000)                              # every reply had a 1 ms kernel RTT
        self.assertAlmostEqual(kq[1.0], 1000)
        self.assertEqual(analysis.analyse([])["kernel_quantiles"], [])

    def test_worst_endpoint_first(self):
        eps = self.an["endpoints"]
        self.assertEqual(eps[0]["ep"], 1)
        self.assertEqual((eps[0]["sent"], eps[0]["replied"]), (2, 1))

    def test_empty_run(self):
        s = analysis.analyse([], {})["summary"]
        self.assertEqual(s["sent"], 0)
        self.assertIsNone(s["lag_mean_us"])


class DifferingSettingsTest(unittest.TestCase):
    def test_int_and_float_are_the_same_setting(self):           # review finding 6
        runs = [{"cfg": {"stagger_window_s": 24, "targets": "10.0.0.1"}},
                {"cfg": {"stagger_window_s": 24.0, "targets": "10.0.0.1"}}]
        self.assertEqual(differing_settings(runs), [])

    def test_real_differences_are_reported(self):
        self.assertEqual(differing_settings([{"cfg": {"stagger_window_s": 24}}, {"cfg": {"stagger_window_s": 30.0}}]),
                         ["stagger_window_s: 24 / 30"])
        self.assertTrue(differing_settings([{"cfg": {"targets": "10.0.0.1"}}, {"cfg": {"targets": "10.0.0.2"}}]))
        self.assertTrue(differing_settings([{"cfg": {"simulated_db_ms": None}}, {"cfg": {"simulated_db_ms": 3}}]))


class ExportTest(unittest.TestCase):
    def test_packets_csv_round_trip(self):
        rows = [make_row(0, 0, 1, "10.0.0.1", pkt(s, 1000, 50 * (s + 1), batch=2, wakeup=s)) for s in range(3)]
        rows.append(make_row(0, 0, 1, "10.0.0.1", pkt(3, None, None)))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.csv")
            with open(path, "w", newline="") as f:
                f.write(analysis.packets_csv(rows, {"engine": "go"}))
            back = analysis.load_rows(path)
        self.assertEqual(len(back), 4)
        for a, b in zip(rows, back):
            for k in ("ep", "seq", "tx", "krx", "urx", "batch", "wakeup"):
                self.assertEqual(a[k], b[k], k)
            self.assertEqual(a["lag_us"] is None, b["lag_us"] is None)

    def test_compare_csv_uses_raw_numbers(self):
        an = analysis.analyse([make_row(0, 0, 1, "10.0.0.1", pkt(0, 1000, 100))], {"sent": 1, "replied": 1})
        item = {"name": "a", "cfg": {}, "meta": {}, "analysis": an}
        lines = analysis.compare_csv([item, item]).splitlines()
        self.assertIn("Observer intrusion mean,100.0,100.0", lines)
        self.assertIn("Packets sent / replied / lost,1 / 1 / 0,1 / 1 / 0", lines)   # text when no number


if __name__ == "__main__":
    unittest.main()
