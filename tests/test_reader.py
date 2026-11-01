"""probe_lab._RawICMPMultiplexer: reply matching and the "reader wakeup" definition."""
import asyncio
import unittest

import probe_lab
from server.kernel_clock import Reception


class FakeSocket:
    """Stands in for KernelClockSocket: recv_one() pops queued replies, then 'EAGAIN'."""
    def __init__(self):
        self.queue = []

    def recv_one(self):
        if not self.queue:
            raise BlockingIOError
        return self.queue.pop(0)


def reply(icmp_id, seq):
    return Reception(icmp_id, seq, "10.0.0.1", kernel_ns=1_000, hw_ns=None, user_real_ns=2_000, user_mono_ns=0)


class ReaderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mux = probe_lab._RawICMPMultiplexer(FakeSocket())
        loop = asyncio.get_running_loop()
        self.pending = [probe_lab.Pending("10.0.0.1", 1, s, 0, loop.create_future()) for s in range(3)]
        for p in self.pending:
            self.mux._pending[(1, p.icmp_seq)] = p

    async def test_batch_drained_by_one_wakeup(self):
        self.mux.k.queue = [reply(1, s) for s in range(3)]
        self.mux._on_readable()
        self.assertEqual((self.mux.reader_calls, self.mux.replied), (1, 3))
        for p in self.pending:
            self.assertTrue(p.future.done())
            self.assertEqual((p.batch, p.wakeup), (3, 1))
            self.assertEqual(p.rx.observer_lag_ns, 1_000)

    async def test_wakeups_without_awaited_replies_are_not_counted(self):     # review finding 3
        self.mux.k.queue = [reply(99, 0)]                    # someone else's ping
        self.mux._on_readable()
        self.mux._on_readable()                               # nothing at all
        self.assertEqual((self.mux.reader_calls, self.mux.unmatched), (0, 1))
        self.mux.k.queue = [reply(1, 0)]
        self.mux._on_readable()
        self.assertEqual(self.mux.reader_calls, 1)
        self.assertEqual(self.pending[0].wakeup, 1)

    async def test_late_reply_is_unmatched(self):
        self.mux._pending.clear()                             # every ping already timed out
        self.mux.k.queue = [reply(1, 0)]
        self.mux._on_readable()
        self.assertEqual((self.mux.unmatched, self.mux.replied), (1, 0))


class IcmpIdRangeTest(unittest.TestCase):
    """Review finding 10: too many endpoints must be refused, not crash or wrap."""
    def test_cli_refuses_ids_beyond_16_bits(self):
        limit = 0x10000 - probe_lab.ID_BASE - 1                # one target => one warm-up id
        self.assertEqual(probe_lab.main(["--targets", "10.0.0.1", "--virtual-endpoints", str(limit + 1)]), 2)

    def test_largest_allowed_run_fits(self):
        n = 0x10000 - probe_lab.ID_BASE - 1
        self.assertLessEqual(probe_lab.ID_BASE + n - 1, 0xFFFF)        # last endpoint id
        self.assertLessEqual(probe_lab.ID_BASE + n + 0, 0xFFFF)        # the warm-up id


if __name__ == "__main__":
    unittest.main()
