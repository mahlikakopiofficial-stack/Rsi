# RSI(20) Research Specification

## Signal definitions

Use RSI(20) on completed 15-minute candles for repeatable research.

- Long entry event: RSI crosses from at/above 40 to below 40.
- Long exit event: RSI crosses from at/below 70 to above 70.
- Short entry event: RSI crosses from at/below 85 to above 85.
- Short exit event: RSI crosses from at/above 30 to below 30.

These are signal definitions only, not evidence of profitability. Define how opposing signals, simultaneous signals, missing candles, and open positions are handled before evaluating results.

## Candle timing

Do not treat an unfinished candle as a completed candle. For historical research, record the candle timestamp and only calculate signals after that candle has closed. The price at which a hypothetical trade could be entered may differ from the close due to spread, latency, and slippage.

## Data-quality checklist

- Confirm symbol and contract category.
- Sort candles by timestamp and remove duplicates.
- Identify missing intervals and incomplete candles.
- Verify OHLC values are valid and volume is nonnegative.
- Avoid look-ahead bias: an entry cannot use data that was unavailable at the decision time.

## Risk and liquidation caveats

A liquidation price is account- and position-dependent and can change with margin, funding, fees, other positions, and exchange risk tiers. A stop-loss is not guaranteed to fill before liquidation in fast markets. This document intentionally does not implement leveraged order execution.

## Current scope

Research and paper-only documentation. No live order placement, credential collection, or verified performance claims are included.
