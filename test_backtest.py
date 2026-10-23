import os
import unittest
from unittest.mock import patch

from backtest import rsi_series, validate_strategy_config


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


class StrategyConfigTests(unittest.TestCase):
    def test_default_strategy_config_is_valid(self):
        with patch.dict(os.environ, {}, clear=True):
            validate_strategy_config()

    def test_five_minute_timeframe_is_valid(self):
        with patch.dict(os.environ, {"TIMEFRAME_MINUTES": "5"}, clear=True):
            validate_strategy_config()

    def test_unsupported_timeframe_is_rejected(self):
        with patch.dict(os.environ, {"TIMEFRAME_MINUTES": "7"}, clear=True):
            with self.assertRaisesRegex(ValueError, "TIMEFRAME_MINUTES"):
                validate_strategy_config()

    def test_rsi_threshold_outside_range_is_rejected(self):
        with patch.dict(os.environ, {"LONG_ENTRY_CROSS_BELOW": "101"}, clear=True):
            with self.assertRaisesRegex(ValueError, "LONG_ENTRY_CROSS_BELOW"):
                validate_strategy_config()

    def test_nonpositive_notional_is_rejected(self):
        with patch.dict(os.environ, {"RESEARCH_NOTIONAL_USD": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "RESEARCH_NOTIONAL_USD"):
                validate_strategy_config()


if __name__ == "__main__":
    unittest.main()
