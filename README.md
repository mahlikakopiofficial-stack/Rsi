# RSI Historical Research

A separate historical-research project for RSI(20) signals on completed 5-minute Bybit linear candles. This repository is independent of EMA-BAND.

## What is implemented

- Downloads public historical candles from the Bybit V5 market-data endpoint (no authentication required).
- Uses a configurable RSI period and thresholds.
- Uses the signal candle close to decide, then simulates a fill at the **next candle open** to reduce look-ahead bias.
- Applies configurable per-side fee and slippage assumptions to hypothetical fill prices.
- Writes a per-trade CSV and JSON summary under the configured output directory.
- Includes unit tests for the RSI calculation.

It is a historical analysis script only: it does not connect to private endpoints, submit orders, manage positions, or require Bybit/Telegram credentials.

## Strategy definitions

- Long entry: RSI crosses from at/above 40 to below 40.
- Long exit: RSI crosses from at/below 70 to above 70.
- Short entry: RSI crosses from at/below 85 to above 85.
- Short exit: RSI crosses from at/above 30 to below 30.

Signals are based on completed candles. If an entry/exit signal appears at candle i close, the simulated fill uses candle i+1 open. Only one hypothetical position per symbol is tracked; opposite entry signals are ignored while a position is open. Any still-open position at the end is excluded from completed-trade metrics.

## Quick start

1. Copy `.env.example` to `.env` and edit the settings. Never commit `.env`.
2. Review `BYBIT_CATEGORY`, `SYMBOLS`, date range, RSI thresholds, fees, slippage and assumed research notional.
3. Run the tests:

   ```sh
   python3 -m unittest -v test_backtest.py
   ```

4. Run the historical study:

   ```sh
   python3 backtest.py
   ```

No third-party Python packages are required. Public Bybit market-data access and an internet connection are required to fetch candles. Use a conservative date window first; the script may warn about missing intervals or insufficient data.

## Configuration

All backtest settings are in `.env.example`: public API base URL, market-data documentation link, contract category, timeframe, RSI period/thresholds, date window, candle minimum, symbols, assumed notional, per-side fee and slippage, HTTP timeout, request pause, and output directory.

The `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` entries are placeholders only and are **not used** by this script. Do not put real credentials in this public repository. Historical public candle retrieval does not require them.

## Results and limitations

Reports are estimates, not forecasts or financial advice. The simplified model does not fully model funding payments, spread variation, order-book liquidity, contract-specific quantity rules, exchange outages, liquidation, or real fill uncertainty. Results can be misleading if candles are missing or symbols are delisted. Inspect warnings and the JSON configuration before interpreting results. No backtest is evidence of future profitability.

EMA-BAND is a separate project and must remain untouched.
