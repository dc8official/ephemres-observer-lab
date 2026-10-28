"""Process lifetime and memory: nothing of the lab outlives the dashboard, and memory stays bounded.

* the kernel's parent-death signal (setpriv --pdeathsig) really ends a child when its parent is killed with -9;
* the dashboard's shutdown waits for its probe and escalates Ctrl-C -> SIGTERM -> SIGKILL, and reports it;
* the leftover check finds this project's probe processes and ignores other programs';
* packet rows of saved runs are released beyond the budget and reloaded from disk on demand.
"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

from server import housekeeping

try:
    from server import app as dash
except ImportError:                                       # pragma: no cover
    dash = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:                                                  # a zombie is dead for our purposes
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


@unittest.skipUnless(shutil.which("setpriv"), "setpriv not installed")
class ParentDeathSignalTest(unittest.TestCase):
    def test_child_ends_when_parent_is_killed_hard(self):
        # parent: a shell that starts a long-lived child through setpriv, prints the child's pid, then waits
        parent = subprocess.Popen(["bash", "-c", "setpriv --pdeathsig TERM -- sleep 60 & echo $!; wait"],
                                  stdout=subprocess.PIPE, text=True)
        child = int(parent.stdout.readline())
        # Wait until setpriv has run (it has exec'd into "sleep"): before that, the parent-death signal is not set
        # yet. In the dashboard that window is the first milliseconds of a run; the probes' own check (they stop
        # when nobody reads their output) covers it.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with open(f"/proc/{child}/cmdline", "rb") as f:
                if f.read().startswith(b"sleep"):
                    break
            time.sleep(0.01)
        self.assertTrue(alive(child))
        parent.kill()                                     # kill -9: the parent cannot clean up anything
        parent.wait()
        parent.stdout.close()
        deadline = time.monotonic() + 3
        while alive(child) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(child), "the child outlived its killed parent")

    @unittest.skipIf(dash is None, "FastAPI not installed")
    def test_dashboard_starts_probes_with_the_parent_death_signal(self):
        argv = dash.Manager().build_argv({**dash.RunConfig(targets="10.0.0.1").model_dump(), "targets": "10.0.0.1"})
        self.assertEqual(argv[:4], ["setpriv", "--pdeathsig", "TERM", "--"])


class LeftoverCheckTest(unittest.TestCase):
    def spawn(self, name, cwd):
        p = subprocess.Popen(["bash", "-c", f"exec -a '{name}' sleep 30"], cwd=cwd)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        time.sleep(0.2)
        return p.pid

    def test_finds_this_projects_probe_and_ignores_others(self):
        ours = self.spawn("probe_lab.py --jsonl --targets 10.0.0.1", ROOT)
        with tempfile.TemporaryDirectory() as elsewhere:
            theirs = self.spawn("probe_lab.py --jsonl --targets 10.0.0.2", elsewhere)
            pids = {p["pid"]: p for p in housekeeping.lab_processes()}
        self.assertIn(ours, pids)
        self.assertEqual(pids[ours]["kind"], "Python probe (dashboard run)")
        self.assertNotIn(theirs, pids)                    # not run from this project: not ours to judge
        problems = housekeeping.check()["problems"]
        self.assertTrue(any(f"pid {ours}" in p and f"sudo kill {ours}" in p for p in problems))

    def test_port_owner_names_the_listening_process(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            owner = housekeeping.port_owner(s.getsockname()[1])
        self.assertIsNotNone(owner)
        self.assertEqual(owner["pid"], os.getpid())

    def test_suspended_process_is_recognised(self):
        import signal
        p = subprocess.Popen(["sleep", "30"])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        os.kill(p.pid, signal.SIGSTOP)                    # what Ctrl-Z does
        time.sleep(0.2)
        self.assertTrue(housekeeping.suspended(p.pid))
        os.kill(p.pid, signal.SIGCONT)
        time.sleep(0.2)
        self.assertFalse(housekeeping.suspended(p.pid))

    def test_memory_of_this_process(self):
        self.assertGreater(housekeeping.rss_mb(), 1)


STUBBORN = textwrap.dedent("""
    import json, signal, sys, time
    mode = sys.argv[1]
    if mode in ("ignore-int", "ignore-both"):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    if mode == "ignore-both":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print(json.dumps({"e": "start", "clock": "fake", "routes": []}), flush=True)
    time.sleep(60)
""")


@unittest.skipIf(dash is None, "FastAPI not installed")
class ShutdownTest(unittest.IsolatedAsyncioTestCase):
    async def run_until_shutdown(self, mode):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(STUBBORN)
        self.addCleanup(os.unlink, f.name)
        mgr = dash.Manager()
        mgr.build_argv = lambda c: [sys.executable, f.name, mode]
        with mock.patch.object(dash, "SHUTDOWN_WAIT_S", (0.5, 0.5)):
            await mgr.start(dash.RunConfig(targets="127.0.0.1"))
            await asyncio.sleep(0.5)
            pid = mgr.proc.pid
            report = await mgr.shutdown()
        self.assertFalse(alive(pid), "the probe outlived the shutdown")
        return report[0]

    async def test_probe_runs_in_its_own_process_group(self):
        # so a Ctrl-C typed in the dashboard's terminal does not also reach the probe (or its worker processes)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(STUBBORN)
        self.addCleanup(os.unlink, f.name)
        mgr = dash.Manager()
        mgr.build_argv = lambda c: [sys.executable, f.name, "normal"]
        await mgr.start(dash.RunConfig(targets="127.0.0.1"))
        await asyncio.sleep(0.3)
        try:
            self.assertNotEqual(os.getpgid(mgr.proc.pid), os.getpgid(0))
        finally:
            with mock.patch.object(dash, "SHUTDOWN_WAIT_S", (0.5, 0.5)):
                await mgr.shutdown()

    async def test_cooperative_probe_stops_on_ctrl_c(self):
        self.assertIn("stopped with Ctrl-C", await self.run_until_shutdown("normal"))

    async def test_escalates_to_sigterm(self):
        self.assertIn("sent SIGTERM", await self.run_until_shutdown("ignore-int"))

    async def test_escalates_to_sigkill_and_says_so(self):
        self.assertIn("KILLED", await self.run_until_shutdown("ignore-both"))


@unittest.skipIf(dash is None, "FastAPI not installed")
class MemoryBudgetTest(unittest.TestCase):
    def test_saved_runs_are_released_and_reloaded(self):
        from server import analysis
        from server.analysis import make_row
        with tempfile.TemporaryDirectory() as d:
            for i in range(4):                                       # four saved runs of 50 packets each
                rows = [make_row(0, 0, 1, "t", [s, 0, 1000, 2000, None, 1, 1, 0]) for s in range(50)]
                analysis.save_run(d, f"20261022-12000{i}_py-sc_1ep-burst-sem15-db3_10-0-0-1", {"note": ""}, {}, rows,
                                  analysis.analyse(rows, {}))
            with mock.patch.object(dash, "RESULTS_DIR", dash.Path(d)), mock.patch.object(dash, "ROW_BUDGET", 120):
                mgr = dash.Manager()
                mgr.load_saved()
                m = mgr.memory()
                self.assertLessEqual(m["packets_in_memory"], 120)
                self.assertEqual(m["released_runs"], 2)
                released = [r for r in mgr.runs.values() if r.rows is None][0]
                self.assertEqual(released.brief()["packets"], 50)     # the count stays known while released
                self.assertEqual(len(mgr.rows_of(released)), 50)      # reloaded from its CSV on demand
                self.assertLessEqual(mgr.memory()["packets_in_memory"], 120)
                self.assertEqual(mgr.analysis_of(released)["summary"]["sent"], 50)


if __name__ == "__main__":
    unittest.main()
