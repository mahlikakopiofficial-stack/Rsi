# RSI(20) 5-Minute Bybit Research + Paper Trader

A separate project from EMA-BAND. Defaults to RSI(20) on completed 5-minute Bybit linear candles, with historical backtesting and a persistent paper-execution loop.

## Safety and execution boundary

- `APP_MODE=research`: historical backtest only.
- `APP_MODE=paper`: simulated positions persisted in SQLite; no real orders or private Bybit endpoints.
- Live trading is **not implemented**. The bot deliberately rejects `APP_MODE=live`; private API keys are not used.
- Telegram is optional and used for status, simulated entries/exits, and errors. Keep the bot token and chat ID only in the server's untracked `.env`.
- This repository is independent of EMA-BAND; do not copy its credentials, database, or service state.

## Strategy

- Long entry: RSI crosses from at/above 40 to below 40.
- Long exit: RSI crosses from at/below 70 to above 70.
- Short entry: RSI crosses from at/below 85 to above 85.
- Short exit: RSI crosses from at/above 30 to below 30.

Signals use completed candles. The paper loop uses the next 5-minute candle's open as its simulated fill and applies configurable fee/slippage assumptions. At startup it only establishes a signal cursor; it will not replay old signals. If it detects a candle gap, it skips stale signals rather than catching up with delayed entries. It allows at most one position per symbol and applies a configurable global open-position cap.

## Setup

1. On the server, clone this repository into its own directory and create a virtual environment if desired (the project uses only Python's standard library).
2. Copy `.env.example` to `.env`. Keep secrets out of GitHub.
3. Set `APP_MODE=paper`, review `SYMBOLS`, `PAPER_NOTIONAL_USD` (minimum $5 simulated notional), `PAPER_MAX_OPEN_POSITIONS`, and `LOOP_SECONDS`.
4. Optional Telegram: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in server `.env`. If omitted, the paper loop still runs and logs to stdout.
5. Run validation/tests:

   ```sh
   python3 -m py_compile backtest.py paper_bot.py test_backtest.py
   python3 -m unittest -v test_backtest.py
   ```

6. Run the historical study:

   ```sh
   APP_MODE=research python3 backtest.py
   ```

7. Run the paper trader in a separate terminal or dedicated service:

   ```sh
   APP_MODE=paper python3 paper_bot.py
   ```

The paper loop reads public Bybit V5 klines only. It writes its own SQLite ledger to `data/paper_trading.sqlite3` by default. Backtest CSV/JSON reports are written separately under `reports/`. Both locations are ignored by Git.

## Configuration

All defaults are in `.env.example`. The backtest uses `RESEARCH_NOTIONAL_USD`; the paper bot uses `PAPER_NOTIONAL_USD` and `PAPER_MAX_OPEN_POSITIONS`. These are separate settings. The paper bot sends no live orders and does not set leverage, use liquidation-based stops, or manage exchange positions.

## Operational limitations

This is a paper prototype, not production-ready live execution. Paper fills are approximations based on candle opens and configured costs; they do not model order-book liquidity, funding, liquidation, exchange-specific quantity steps, min order quantities, or real fills. A missing or delayed candle causes a skipped signal. Monitor the process, logs, database backups, API availability, and Telegram delivery. Historical or paper results cannot establish future profitability.

EMA-BAND remains a separate project and is not changed by this repository.
