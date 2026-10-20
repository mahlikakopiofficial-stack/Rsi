import unittest

from backtest import rsi_series


class RsiSeriesTests(unittest.TestCase):
    def test_output_length_matches_input(self):
        values = rsi_series([float(i + 1) for i in range(30)], 20)
        self.assertEqual(len(values), 30)

    def test_first_value_is_after_warmup(self):
        values = rsi_series([float(i + 1) for i in range(30)], 20)
        self.assertTrue(all(v is None for v in values[:20]))
        self.assertIsNotNone(values[20])

    def test_monotonic_rise_has_rsi_100(self):
        values = rsi_series([float(i + 1) for i in range(30)], 20)
        self.assertAlmostEqual(values[-1], 100.0)

    def test_monotonic_fall_has_rsi_zero(self):
        values = rsi_series([float(100 - i) for i in range(30)], 20)
        self.assertAlmostEqual(values[-1], 0.0)

    def test_invalid_short_series_returns_none(self):
        values = rsi_series([1.0, 2.0, 3.0], 20)
        self.assertTrue(all(v is None for v in values))


if __name__ == "__main__":
    unittest.main()
