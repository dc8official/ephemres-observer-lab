"""server/stats.py: percentile, RFC 3550 jitter, compute_stats."""
import math
import unittest

from server.stats import compute_stats, percentile, rfc3550_jitter


class PercentileTest(unittest.TestCase):
    def test_matches_numpy_linear_interpolation(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertEqual(percentile(vals, 0.0), 1.0)
        self.assertEqual(percentile(vals, 0.5), 3.0)
        self.assertEqual(percentile(vals, 1.0), 5.0)
        self.assertAlmostEqual(percentile(vals, 0.95), 4.8)      # numpy.percentile(vals, 95)
        self.assertAlmostEqual(percentile([10.0, 20.0], 0.25), 12.5)

    def test_edge_cases(self):
        self.assertEqual(percentile([], 0.95), 0.0)
        self.assertEqual(percentile([7.0], 0.95), 7.0)


class JitterTest(unittest.TestCase):
    def test_constant_rtt_has_no_jitter(self):
        self.assertEqual(rfc3550_jitter([100.0] * 10), 0.0)

    def test_one_step_is_smoothed_by_one_sixteenth(self):
        self.assertAlmostEqual(rfc3550_jitter([100.0, 116.0]), 1.0)          # J += (16 - 0) / 16
        self.assertAlmostEqual(rfc3550_jitter([100.0, 116.0, 116.0]), 15 / 16)

    def test_short_inputs(self):
        self.assertEqual(rfc3550_jitter([]), 0.0)
        self.assertEqual(rfc3550_jitter([5.0]), 0.0)


class ComputeStatsTest(unittest.TestCase):
    def test_all_fields(self):
        st = compute_stats([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        self.assertEqual((st.n, st.min, st.max, st.avg), (8, 2.0, 9.0, 5.0))
        self.assertAlmostEqual(st.std_dev, 2.0)                               # population std dev
        self.assertAlmostEqual(st.p95, percentile(sorted([2, 4, 4, 4, 5, 5, 7, 9]), 0.95))

    def test_empty(self):
        st = compute_stats([])
        self.assertEqual(st.n, 0)
        self.assertIsNone(st.avg)
        self.assertFalse(math.isnan(st.n))


if __name__ == "__main__":
    unittest.main()
