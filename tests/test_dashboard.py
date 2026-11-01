"""server/app.py: request guard, start failures, and that the probe's stdout is never blocked.

Skipped when FastAPI is not installed (use .venv/bin/python -m unittest).
"""
import asyncio
import os
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

try:
    from fastapi import HTTPException
    from server import app as dash
except ImportError:                                         # pragma: no cover
    dash = None

# A fake probe: ~1 MB/s of NDJSON, recording the longest time any write() blocked.
FAKE_PROBE = textwrap.dedent("""
    import json, sys, time
    def emit(o):
        t = time.perf_counter(); sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
        return time.perf_counter() - t
    emit({"e": "start", "clock": "fake", "routes": []})
    worst, t0, n, last = 0.0, time.monotonic(), 0, 0.0
    pkts = [[0, 1, 2, 3, None, 1, 1]] * 60
    while time.monotonic() - t0 < 2.5:
        worst = max(worst, emit({"e": "cycle", "ep": n, "cyc": 0, "target": "127.0.0.1", "icmp_id": n & 0xFFFF,
                                 "db_wait_ms": 0, "canary": {}, "packets": pkts}))
        n += 1
        if time.monotonic() - last > 0.1:
            last = time.monotonic()
            worst = max(worst, emit({"e": "tick", "t": 0, "sent": n, "replied": n, "reader_calls": n,
                                     "recent_avg_us": 1, "recent_max_us": 1, "max_us": 1}))
        time.sleep(0.002)
    emit({"e": "summary", "sent": n, "replied": n, "max_write_ms": worst * 1000, "stopped": False})
""")


@unittest.skipIf(dash is None, "FastAPI not installed")
class RequestGuardTest(unittest.TestCase):
    def test_allowed(self):
        ok = dash.request_allowed
        self.assertTrue(ok("127.0.0.1:8080", None))                       # curl / scripts
        self.assertTrue(ok("localhost:8080", "http://localhost:8080"))
        self.assertTrue(ok("[::1]:8080", "http://[::1]:8080"))

    def test_rejected(self):
        ok = dash.request_allowed
        self.assertFalse(ok("evil.example:8080", None))                   # DNS rebinding
        self.assertFalse(ok("127.0.0.1.evil.example", None))
        self.assertFalse(ok("127.0.0.1:8080", "https://evil.example"))    # cross-site POST / WebSocket
        self.assertFalse(ok("127.0.0.1:8080", "null"))                    # sandboxed iframe, file://
        self.assertFalse(ok(None, None))


@unittest.skipIf(dash is None, "FastAPI not installed")
class ManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.probe = os.path.join(self.tmp.name, "fake_probe.py")
        with open(self.probe, "w") as f:
            f.write(FAKE_PROBE)
        self.mgr = dash.Manager()

    async def wait_done(self, run, limit=60):
        t = time.monotonic()
        while run.status == "running" and time.monotonic() - t < limit:
            await asyncio.sleep(0.05)

    async def test_failed_start_does_not_block_later_runs(self):          # review finding 4
        self.mgr.build_argv = lambda c: ["/nonexistent/engine"]
        with self.assertRaises(HTTPException) as cm:
            await self.mgr.start(dash.RunConfig(targets="127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 500)
        self.assertEqual(self.mgr.current.status, "error")
        self.mgr.build_argv = lambda c: [sys.executable, self.probe]
        run = await self.mgr.start(dash.RunConfig(targets="127.0.0.1"))   # not a 409
        await self.wait_done(run)
        self.assertEqual(run.status, "done")

    async def test_slow_dashboard_never_blocks_the_probe(self):           # review finding 1
        real = dash.analysis.analyse

        calls = []

        def slow_analyse(*args, **kwargs):           # any signature: it must never fail before being slow
            calls.append(1)
            time.sleep(1.0)                                                # pathological analysis
            return real(*args, **kwargs)

        class StuckBrowser:                                                # stopped reading its socket
            async def send_text(self, _text):
                await asyncio.sleep(3600)

        self.mgr.build_argv = lambda c: [sys.executable, self.probe]
        self.mgr.clients.add(StuckBrowser())
        with mock.patch.object(dash, "SEND_TIMEOUT_S", 0.5), \
                mock.patch.object(dash.analysis, "analyse", slow_analyse):
            run = await self.mgr.start(dash.RunConfig(targets="127.0.0.1"))
            await self.wait_done(run)
        self.assertEqual(run.status, "done")
        self.assertLess(run.meta["max_write_ms"], 50, "the probe's stdout write blocked")
        self.assertFalse(self.mgr.clients, "the stuck browser was not dropped")
        self.assertGreater(len(run.rows), 1000)
        self.assertTrue(calls, "the slow analysis was never exercised")


@unittest.skipIf(dash is None, "FastAPI not installed")
class IdleFloorTest(unittest.TestCase):
    """A run is matched to the most recent finished no-ORM run with the same engine, mode, target and schedule."""
    def make(self, rid, started, **cfg):
        from server.analysis import make_row
        base = {"engine": "go", "cpu_mode": "single_core", "targets": "10.0.0.1", "virtual_endpoints": 100,
                "pings_per_cycle": 5, "interval_s": 8.0, "timeout_s": 2.0, "stagger_window_s": 60.0, "cycles": 3,
                "cycle_length_s": 60.0, "hw_timestamps": False, "simulated_db_ms": 3.0, "db_write_semaphore": 15, "role": "test"}
        base.update(cfg)
        lag = 50 if base["role"] == "floor" else 400
        rows = [make_row(0, 1, 1, "10.0.0.1", [s, 0, 1_000_000, 1_000_000 + lag * 1000, None, 1, s + 1, 0]) for s in range(5)]
        r = dash.Run(id=rid, name=rid, cfg=base, status="done", rows=rows, started_at=started)
        self.mgr.runs[rid] = r
        return r

    def setUp(self):
        self.mgr = dash.Manager()

    def test_matching_and_subtraction(self):
        test = self.make("t", 300)
        self.assertIsNone(self.mgr.analysis_of(test)["summary"]["floor"])           # none measured yet
        self.make("old-floor", 100, role="floor", simulated_db_ms=0.0)
        self.make("new-floor", 200, role="floor", simulated_db_ms=0.0)
        self.make("other-engine", 250, role="floor", simulated_db_ms=0.0, engine="rust")
        self.make("other-interval", 260, role="floor", simulated_db_ms=0.0, interval_s=1.0)
        s = self.mgr.analysis_of(test)["summary"]
        self.assertEqual(s["floor"]["run_id"], "new-floor")
        from server.analysis import _above
        self.assertAlmostEqual(_above(s, "lag_mean_us"), 350)
        self.assertIsNone(self.mgr.floor_for(self.mgr.runs["new-floor"]))           # a floor run has no floor

    def test_old_run_without_role_but_floor_tag(self):
        test = self.make("t", 300)
        legacy = self.make("legacy", 200, simulated_db_ms=0.0, tag="floor")
        legacy.cfg.pop("role")
        self.assertEqual(self.mgr.floor_for(test)["run_id"], "legacy")


QUICK_PROBE = textwrap.dedent("""
    import json, sys, time
    def emit(o): sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
    emit({"e": "start", "clock": "fake", "routes": []})
    t = time.clock_gettime_ns(time.CLOCK_REALTIME)
    for cyc in range(2):
        emit({"e": "cycle", "ep": 0, "cyc": cyc, "target": "127.0.0.1", "icmp_id": 4096, "db_wait_ms": 0,
              "db_start_ns": t + 5_000_000, "db_end_ns": t + 8_000_000, "canary": {},
              "packets": [[cyc * 2 + n, t, t + 1_000_000, t + 1_000_000 + 40_000 * (n + 1), None, 1, n + 1, 1000] for n in range(2)]})
    emit({"e": "summary", "sent": 4, "replied": 4, "stopped": False})
""")


@unittest.skipIf(dash is None, "FastAPI not installed")
class AutosaveTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.probe = os.path.join(self.tmp.name, "quick_probe.py")
        with open(self.probe, "w") as f:
            f.write(QUICK_PROBE)
        self.results = os.path.join(self.tmp.name, "results")
        patch = mock.patch.object(dash, "RESULTS_DIR", dash.Path(self.results))
        patch.start()
        self.addCleanup(patch.stop)

    async def finished_run(self, autosave):
        mgr = dash.Manager()
        mgr.autosave = autosave
        mgr.build_argv = lambda c: [sys.executable, self.probe]
        run = await mgr.start(dash.RunConfig(targets="127.0.0.1", cycles=2, cycle_length_s=60))
        t = time.monotonic()
        while (run.status == "running" or (autosave and not run.saved_as)) and time.monotonic() - t < 20:
            await asyncio.sleep(0.05)
        return mgr, run

    def saved_files(self):
        return sorted(os.listdir(self.results)) if os.path.isdir(self.results) else []

    async def test_finished_run_is_saved_by_itself(self):
        _, run = await self.finished_run(autosave=True)
        self.assertEqual(run.saved_as, run.name)
        self.assertIn(run.name + ".csv", self.saved_files())
        self.assertIn(run.name + ".meta.json", self.saved_files())
        self.assertIn("INDEX.md", self.saved_files())

    async def test_no_autosave_then_save_all(self):
        mgr, run = await self.finished_run(autosave=False)
        self.assertIsNone(run.saved_as)
        self.assertEqual(self.saved_files(), [])
        self.assertEqual(mgr.memory()["unsaved_runs"], 1)
        with mock.patch.object(dash, "mgr", mgr):
            res = await dash.api_save_all()
        self.assertEqual(res["saved"], [run.name])
        self.assertEqual(mgr.memory()["unsaved_runs"], 0)


@unittest.skipIf(dash is None, "FastAPI not installed")
class BatchTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.probe = os.path.join(self.tmp.name, "quick_probe.py")
        with open(self.probe, "w") as f:
            f.write(QUICK_PROBE)
        self.mgr = dash.Manager()
        self.mgr.build_argv = lambda c: [sys.executable, self.probe]
        avail = mock.patch.object(dash, "engine_available", lambda: {"python": True, "go": True, "rust": True})
        avail.start()
        self.addCleanup(avail.stop)

    async def wait_batch(self, limit=60):
        t = time.monotonic()
        while (self.mgr.batch or (self.mgr.current and self.mgr.current.status == "running")) and time.monotonic() - t < limit:
            await asyncio.sleep(0.05)

    async def test_rounds_rotate_engines_and_floor_runs_first(self):
        body = dash.BatchBody(run=dash.RunConfig(targets="127.0.0.1", cycles=2, cycle_length_s=60), repeats=3,
                              engines=["python", "go", "rust"], with_floor=True)
        res = await self.mgr.start_batch(body)
        self.assertEqual(res["total"], 18)
        await self.wait_batch()
        done = sorted(self.mgr.runs.values(), key=lambda r: int(r.id[3:]))
        order = [(r.cfg["repeat"], r.cfg["engine"], r.cfg["role"]) for r in done]
        self.assertEqual([e for (k, e, role) in order if k == 1 and role == "test"], ["python", "go", "rust"])
        self.assertEqual([e for (k, e, role) in order if k == 2 and role == "test"], ["go", "rust", "python"])
        self.assertEqual([e for (k, e, role) in order if k == 3 and role == "test"], ["rust", "python", "go"])
        self.assertEqual([role for (_, _, role) in order[:2]], ["floor", "test"])          # floor just before its test
        self.assertTrue(all(r.status == "done" for r in done))
        self.assertEqual(len({r.cfg["series_id"] for r in done}), 1)
        last_go_test = [r for r in done if r.cfg["engine"] == "go" and r.cfg["role"] == "test"][-1]
        floor = self.mgr.floor_for(last_go_test)
        self.assertTrue(floor and self.mgr.runs[floor["run_id"]].cfg["repeat"] == last_go_test.cfg["repeat"])
        self.assertTrue(self.mgr.analysis_of(last_go_test)["bursts"])                  # ORM windows reached the analysis

    async def test_stop_cancels_the_rest(self):
        await self.mgr.start_batch(dash.BatchBody(run=dash.RunConfig(targets="127.0.0.1"), repeats=5))
        await self.mgr.stop()
        await self.wait_batch()
        self.assertIsNone(self.mgr.batch)
        self.assertLessEqual(len(self.mgr.runs), 2)

    async def test_hw_stamps_refused_when_alternating_engines(self):
        with self.assertRaises(HTTPException):
            await self.mgr.start_batch(dash.BatchBody(run=dash.RunConfig(targets="127.0.0.1", hw_timestamps=True),
                                                      engines=["python", "go"]))


if __name__ == "__main__":
    unittest.main()
