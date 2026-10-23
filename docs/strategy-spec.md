# RSI(20) 5-Minute Historical Research Specification

## Signal definitions

Use RSI(20) on completed 5-minute candles by default; all values are configurable in `.env`.

- Long entry event: RSI crosses from at/above the configured threshold (default 40) to below it.
- Long exit event: RSI crosses from at/below the configured threshold (default 70) to above it.
- Short entry event: RSI crosses from at/below the configured threshold (default 85) to above it.
- Short exit event: RSI crosses from at/above the configured threshold (default 30) to below it.

A signal is observed after candle i closes; the simulated fill is at candle i+1 open. The study tracks at most one hypothetical position per symbol. Opposite entry signals are ignored while a position is open. Unclosed positions at the end of the data window are excluded from completed-trade statistics.

## Public data source

The backtest uses Bybit V5 public market data only: `https://api.bybit.com/v5/market/kline`. No API key, private endpoint, or order submission is used. Market category, API base URL, timeframe, symbol list, time window, request timeout, and page limit are configurable in `.env.example`.

## Assumptions

- Simulated fill at the next candle open, not at the signal close.
- Configurable assumed notional per hypothetical trade, not a recommended position size.
- Configurable fee and slippage assumptions applied to each side's simulated fill.
- One position per symbol, no pyramiding.
- Results exclude an open position at the end of the window.

## Data-quality checklist

- Confirm the correct market category and symbol.
- Sort candles by timestamp and deduplicate.
- Identify missing intervals and incomplete candles.
- Verify OHLC values and nonnegative volume.
- Avoid look-ahead bias: an entry cannot use data unavailable at decision time.
- Review the saved JSON configuration and any missing-candle warnings.

## Important limitations

This simple historical model does not fully model funding, dynamic spreads, order-book liquidity, exchange outages, delistings, contract quantity rules, liquidation, or real-world fill uncertainty. A missing-data warning can materially affect results. Historical results are not forecasts or financial advice and cannot establish future profitability.

## Project boundary

Historical analysis only. No live order execution, private API access, or credential use is implemented. EMA-BAND must remain untouched.
