"""Live parity test: all three engines on REAL raw sockets, without root.

`unshare -rn` gives the test a private network namespace in which it is root, so raw ICMP sockets
work on that namespace's own loopback (nothing touches the host's network).  `tc netem` delays the
loopback by 150 ms each way (a 300 ms round trip) against a 200 ms timeout, so every reply is LATE.  That exercises late-reply reporting, multi-cycle numbering
and send-lag recording in every engine with real kernel timestamps.

Skipped when the system forbids unprivileged user namespaces or `tc` is missing, and for an
engine that is not built.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARGS = ["--targets", "127.0.0.1", "--virtual-endpoints", "3", "--pings", "2", "--interval", "0.4",
        "--timeout", "0.2", "--cycles", "2", "--cycle-length", "1.2", "--stagger-window", "0.3"]


def netns_ok() -> bool:
    if not shutil.which("unshare") or not shutil.which("tc"):
        return False
    p = subprocess.run(["unshare", "-rn", "true"], capture_output=True)
    return p.returncode == 0


def in_netns(cmd: list, netem: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
    setup = "ip link set lo up; " + ("tc qdisc add dev lo root netem delay 150ms; " if netem else "")
    script = setup + 'exec "$@"'
    return subprocess.run(["unshare", "-rn", "sh", "-c", script, "sh", *cmd], cwd=ROOT,
                          capture_output=True, text=True, timeout=timeout)


ENGINES = {"python": [sys.executable, "probe_lab.py", "--jsonl"],
           "go": [os.path.join(ROOT, "bin", "go_prober")],
           "rust": [os.path.join(ROOT, "bin", "rust_prober")]}


@unittest.skipUnless(netns_ok(), "unprivileged network namespaces or tc not available")
class LiveEngineParityTest(unittest.TestCase):
    def run_engine(self, name):
        cmd = ENGINES[name]
        if name != "python" and not os.access(cmd[0], os.X_OK):
            self.skipTest(f"{name} engine not built")
        p = in_netns(cmd + ARGS)
        events = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{")]
        self.assertTrue(events, p.stderr)
        return events

    def test_engines_report_the_same_things(self):
        for name in ENGINES:
            with self.subTest(engine=name):
                ev = self.run_engine(name)
                cycles = [e for e in ev if e["e"] == "cycle"]
                late = [e for e in ev if e["e"] == "late"]
                summary = [e for e in ev if e["e"] == "summary"]
                self.assertEqual(sorted((e["ep"], e["cyc"]) for e in cycles), [(i, c) for i in range(3) for c in range(2)])
                seqs = {p[0] for e in cycles for p in e["packets"]}
                self.assertEqual(seqs, {0, 1, 2, 3})                       # cycle * pings + n, unique across cycles
                for e in cycles:
                    for p in e["packets"]:
                        self.assertEqual(len(p), 8)                        # ... + send_lag_ns
                        self.assertGreaterEqual(p[7], 0)
                        # Sanity only: this test checks that send lag is RECORDED, not how fast an engine is.
                        # (Go single-core occasionally sends 50-150 ms late here: real scheduler behaviour.)
                        self.assertLess(p[7], 1_000_000_000)
                        self.assertIsNone(p[3])                            # every reply is late (300 ms > 200 ms)
                self.assertGreaterEqual(len(late), 9)                      # the last ones may come after exit
                for e in late:
                    self.assertGreater(e["krx"] - e["tx"], 200_000_000)    # kernel saw them after the timeout
                self.assertEqual(summary[0]["late"], len(late))
                for e in cycles:                                           # ORM work window, on the packet clock
                    self.assertLessEqual(e["db_start_ns"], e["db_end_ns"])
                    self.assertGreater(e["db_start_ns"], max(p[1] for p in e["packets"]))
                self.assertFalse(summary[0]["stopped"])


@unittest.skipUnless(netns_ok(), "unprivileged network namespaces or tc not available")
class LiveCliFilesTest(unittest.TestCase):
    def test_terminal_run_writes_csv_meta_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "run.csv")
            p = in_netns([sys.executable, "probe_lab.py", "--targets", "127.0.0.1", "--virtual-endpoints", "4",
                          "--pings", "2", "--interval", "0.2", "--cycles", "2", "--cycle-length", "0.8",
                          "--stagger-window", "0.2", "--quiet", "--csv", csv_path], netem=False)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("cycle 0 of 2 is a warm-up", p.stdout)
            with open(os.path.join(d, "run.meta.json")) as f:
                meta = json.load(f)
            self.assertEqual(meta["config"]["cycles"], 2)
            self.assertFalse(meta["config"]["hw_timestamps"])
            self.assertIn("warnings", meta["meta"]["host"])
            from server import analysis
            rows = analysis.load_rows(csv_path)
            self.assertEqual(len(rows), 16)
            self.assertTrue(all(r["send_lag_us"] is not None for r in rows))
            self.assertTrue(os.path.exists(os.path.join(d, "INDEX.md")))


if __name__ == "__main__":
    unittest.main()
