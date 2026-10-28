"""server/naming.py: result file names must round-trip through parse_name()."""
import os
import time
import unittest

from server.naming import _n, parse_name, result_name, scenario_key

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def roundtrip(**kw):
    args = dict(targets=["10.0.0.1"], endpoints=10, stagger_s=30.0, semaphore=15, db_ms=3.0, pings=5,
                 interval_s=1.0, engine="python", cpu_mode="single_core", tag="", cycles=1, cycle_s=None)
    args.update(kw)
    name = result_name(args["targets"], args["endpoints"], args["stagger_s"], args["semaphore"], args["db_ms"],
                       args["pings"], args["interval_s"], engine=args["engine"], cpu_mode=args["cpu_mode"],
                       tag=args["tag"], cycles=args["cycles"], cycle_s=args["cycle_s"])
    return name, parse_name(name)


class NumberFormatTest(unittest.TestCase):
    def test_short_fixed_point(self):
        self.assertEqual([_n(x) for x in (3.0, 0.05, 24, 30.5, 0)], ["3", "0p05", "24", "30p5", "0"])

    def test_no_exponent_form(self):          # review finding 11: f"{1e-05:g}" == "1e-05"
        self.assertEqual(_n(0.00001), "0p00001")


class RoundTripTest(unittest.TestCase):
    def test_typical_and_unusual_values(self):
        for kw in ({}, {"stagger_s": 0.0}, {"db_ms": 0.00001}, {"interval_s": 0.05}, {"pings": 7},
                   {"engine": "go", "cpu_mode": "multi_core"}, {"engine": "rust"}, {"tag": "Sem Sweep #2"},
                   {"targets": ["10.0.0.1", "10.0.0.2", "10.0.0.3"]}):
            with self.subTest(**kw):
                name, cfg = roundtrip(**kw)
                self.assertIsNotNone(cfg, name)
                self.assertAlmostEqual(cfg["simulated_db_ms"], kw.get("db_ms", 3.0))
                self.assertAlmostEqual(cfg["interval_s"], kw.get("interval_s", 1.0))
                self.assertAlmostEqual(cfg["stagger_window_s"], kw.get("stagger_s", 30.0))
                self.assertEqual(cfg["pings_per_cycle"], kw.get("pings", 5))
                self.assertEqual(cfg["engine"], kw.get("engine", "python"))

    def test_cycles_round_trip(self):
        name, cfg = roundtrip(cycles=3, cycle_s=60.0, interval_s=8.0)
        self.assertIn("-i8-c3x60_", name)
        self.assertEqual((cfg["cycles"], cfg["cycle_length_s"], cfg["interval_s"]), (3, 60.0, 8.0))
        name, cfg = roundtrip()                                   # one cycle: nothing added, old names unchanged
        self.assertNotIn("-c", name.split("_")[2])
        self.assertEqual((cfg["cycles"], cfg["cycle_length_s"]), (1, None))

    def test_defaults_are_left_out_of_the_name(self):
        name, _ = roundtrip()
        self.assertNotIn("-p5", name)
        self.assertNotIn("-i1", name)

    def test_scenario_key_ignores_engine(self):
        _, py = roundtrip(engine="python")
        _, go = roundtrip(engine="go", cpu_mode="multi_core")
        self.assertEqual(scenario_key(py), scenario_key(go))

    def test_saved_results_regenerate_their_own_names(self):
        folder = os.path.join(ROOT, "test_results")
        bases = [f[:-4] for f in os.listdir(folder) if f.endswith(".csv") and not f.endswith("_cycles.csv")]
        for base in bases:
            with self.subTest(base=base):
                c = parse_name(base)
                self.assertIsNotNone(c)
                when = time.mktime(time.strptime(base[:15], "%Y%m%d-%H%M%S"))
                self.assertEqual(result_name(c["targets"].split(","), c["virtual_endpoints"], c["stagger_window_s"],
                                             c["db_write_semaphore"], c["simulated_db_ms"], c["pings_per_cycle"],
                                             c["interval_s"], when=when, engine=c["engine"],
                                             cpu_mode=c["cpu_mode"], tag=c["tag"],
                                             cycles=c["cycles"], cycle_s=c["cycle_length_s"]), base)


if __name__ == "__main__":
    unittest.main()
