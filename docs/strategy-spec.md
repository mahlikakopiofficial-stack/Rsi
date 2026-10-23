# RSI(20) 5-Minute Strategy and Execution Boundary

## Signal definitions

Use RSI(20) on completed 5-minute candles by default; settings are configurable in the server's untracked `.env`.

- Long entry: RSI crosses from at/above 40 to below 40.
- Long exit: RSI crosses from at/below 70 to above 70.
- Short entry: RSI crosses from at/below 85 to above 85.
- Short exit: RSI crosses from at/above 30 to below 30.

The paper loop evaluates the most recently closed candle and simulates the fill at the next candle's open. On first start it establishes a cursor without taking a historical signal. When the signal cursor skips more than one interval, the loop advances without replaying stale signals. A single position per symbol is supported, with a global open-position cap.

## Bybit route

The paper bot requests `GET /v5/market/kline` from the configured public Bybit base URL with category `linear`, symbol, and interval `5`. It uses no API key, private endpoint, account state, or order-placement endpoint. Returned candles are sorted and deduplicated, OHLC/volume are validated, and the latest candle must be current and contiguous with the preceding candle before a paper fill is simulated.

## Telegram route

If both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured in the server's untracked `.env`, the paper bot calls Telegram Bot API `sendMessage` for startup, simulated entries/exits, skipped stale signals, and errors. Telegram failure is logged and does not turn a notification into a trade. The bot does not expose Telegram commands or allow remote execution control.

## Paper accounting

- `PAPER_NOTIONAL_USD` is the simulated notional per position and must be at least $5.
- `PAPER_MAX_OPEN_POSITIONS` caps the total number of simultaneous simulated positions.
- Configured fee and slippage rates adjust simulated entry and exit prices.
- Positions, signal cursors, and completed paper trades are persisted to a separate SQLite database.
- Historical backtest notional and output reports are separate from paper trading state.

## Safety and limitations

`paper_bot.py` rejects every mode other than `APP_MODE=paper`. Live execution is not implemented; private Bybit credentials in the example template are intentionally unused. Paper fills do not model order-book depth, funding, liquidation, contract quantity increments, exchange-side position reconciliation, or real fill certainty. Historical/paper results do not predict future performance.

EMA-BAND is a separate project and must remain untouched.
