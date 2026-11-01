"""probe_lab.Lab.run: SIGTERM must clean up like Ctrl-C (close the socket => restore the NIC, emit the summary).

Runs a real Lab in a subprocess (SIGTERM would otherwise hit the test runner) with the raw socket
replaced by a fake, so no root is needed.  The fake's close() is what restores the NIC setting.
"""
import json
import os
import subprocess
import sys
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = textwrap.dedent("""
    import asyncio, os, signal, socket, sys, time
    import probe_lab
    from server.kernel_clock import RouteInfo

    class FakeSocket:                       # never answers: the endpoint waits on its timeout
        def __init__(self):
            self.sock, self._peer = socket.socketpair()
            self.notes, self.mode = [], "fake"
        def open(self): pass
        def close(self): print("FAKE-CLOSED", file=sys.stderr, flush=True)
        def send_echo(self, target, icmp_id, seq): return time.clock_gettime_ns(time.CLOCK_REALTIME)
        def recv_one(self): raise BlockingIOError

    cfg = probe_lab.Config(targets=["192.0.2.1"], endpoints=2, timeout=5.0, warmup=False,
                           csv_path=None, jsonl=True, stagger_window=0)
    lab = probe_lab.Lab(cfg, {"192.0.2.1": RouteInfo("192.0.2.1", "eth0", "10.0.0.2")})
    lab.k = lab.mux.k = FakeSocket()
    async def main():
        asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)
        await lab.run()
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        print("CANCELLED", file=sys.stderr)
""")


CLOSED_PIPE = SCRIPT.replace(
    "asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)",
    "pass                                       # no signal: the reader of stdout simply goes away")


class ClosedOutputTest(unittest.TestCase):
    def test_probe_stops_and_cleans_up_when_its_reader_disappears(self):
        p = subprocess.Popen([sys.executable, "-c", CLOSED_PIPE], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p.stdout.readline()                                 # read the first event, then stop listening
        p.stdout.close()
        _, err = p.communicate(timeout=30)
        self.assertNotIn("Traceback", err)
        self.assertIn("output closed", err)
        self.assertIn("FAKE-CLOSED", err)                   # KernelClockSocket.close() ran => NIC setting restored


# Signals that arrive DURING the teardown: the canary's stop (the teardown's only await) is replaced by one that
# sends the signal(s) first. The remaining steps, including closing the socket (= restoring the NIC), must still run.
INTERRUPTED_TEARDOWN = SCRIPT.replace(
    "asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)",
    """sigs = [getattr(signal, s) for s in sys.argv[1].split(",")]
    async def stop_with_signals():
        for s in sigs:
            os.kill(os.getpid(), s)
        await asyncio.sleep(0.3)               # the signals are delivered while the teardown awaits
    lab.canary.stop = stop_with_signals
    asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)""")

# The reader disappears exactly when the final summary is written (not before).
SUMMARY_BREAKS = SCRIPT.replace(
    "asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)",
    """real = lab._event
    def event(obj):
        if obj.get("e") == "summary":
            r, w = os.pipe(); os.close(r); os.dup2(w, sys.stdout.fileno())
        real(obj)
    lab._event = event
    asyncio.get_running_loop().call_later(0.5, os.kill, os.getpid(), signal.SIGTERM)""")


class TeardownCannotBeCutShortTest(unittest.TestCase):
    def run_script(self, script, *args):
        p = subprocess.run([sys.executable, "-c", script, *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotIn("Traceback", p.stderr)
        self.assertNotIn("KeyboardInterrupt", p.stderr)
        self.assertIn("FAKE-CLOSED", p.stderr)             # the socket (and NIC setting) was still closed
        return p

    def test_sigterm_during_teardown(self):
        self.run_script(INTERRUPTED_TEARDOWN, "SIGTERM")

    def test_double_ctrl_c_during_teardown(self):
        self.run_script(INTERRUPTED_TEARDOWN, "SIGINT,SIGINT")

    def test_reader_disappears_at_the_summary(self):
        p = self.run_script(SUMMARY_BREAKS)
        self.assertIn("output closed", p.stderr)


class SigtermTest(unittest.TestCase):
    def test_sigterm_runs_cleanup_and_emits_summary(self):
        p = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(p.returncode, -15, "killed by SIGTERM: no cleanup ran")
        self.assertIn("FAKE-CLOSED", p.stderr)              # KernelClockSocket.close() => NIC restored
        events = [json.loads(line) for line in p.stdout.splitlines() if line.startswith("{")]
        summary = [e for e in events if e.get("e") == "summary"]
        self.assertEqual(len(summary), 1, p.stdout + p.stderr)
        self.assertTrue(summary[0]["stopped"])


if __name__ == "__main__":
    unittest.main()
