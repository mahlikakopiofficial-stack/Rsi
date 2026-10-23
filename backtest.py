#!/usr/bin/env python3
"""Historical-only RSI research backtest using Bybit's public market-data API.

No authentication, private endpoints, or order placement are used.
Signals are calculated on completed candles and hypothetical fills occur at
the following candle open to reduce look-ahead bias.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    """Small .env reader; process environment variables take precedence."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env(ROOT / ".env")


def cfg(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def number(name: str, default: float) -> float:
    try:
        return float(cfg(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc


def integer(name: str, default: int) -> int:
    try:
        return int(cfg(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def utc_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list[dict]:
    base = cfg("BYBIT_PUBLIC_BASE_URL", "https://api.bybit.com").rstrip("/")
    category = cfg("BYBIT_CATEGORY", "linear")
    interval = str(integer("TIMEFRAME_MINUTES", 5))
    limit = min(1000, max(1, integer("BYBIT_PAGE_LIMIT", 1000)))
    timeout = max(5, integer("HTTP_TIMEOUT_SECONDS", 20))
    pause = max(0.0, number("REQUEST_PAUSE_SECONDS", 0.15))
    rows: dict[int, dict] = {}
    # Bybit returns klines newest-first. Page backwards from the requested end
    # so windows longer than 1,000 candles do not silently omit older data.
    cursor_end = end_ms

    while cursor_end >= start_ms:
        query = urlencode({
            "category": category,
            "symbol": symbol.upper(),
            "interval": interval,
            "start": start_ms,
            "end": cursor_end,
            "limit": limit,
        })
        url = f"{base}/v5/market/kline?{query}"
        req = Request(url, headers={"User-Agent": "RSI-Research-Backtest/1.0"})
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            raise RuntimeError(
                f"Bybit API error for {symbol}: {payload.get('retCode')} "
                f"{payload.get('retMsg', '')}"
            )
        batch = payload.get("result", {}).get("list", [])
        if not batch:
            break

        timestamps = []
        for item in batch:
            ts = int(item[0])
            timestamps.append(ts)
            if start_ms <= ts <= end_ms:
                rows[ts] = {
                    "timestamp": ts,
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
        oldest = min(timestamps)
        if oldest <= start_ms or len(batch) < limit:
            break
        next_cursor_end = oldest - 1
        if next_cursor_end >= cursor_end:
            raise RuntimeError(f"Bybit pagination did not advance for {symbol}")
        cursor_end = next_cursor_end
        if pause:
            time.sleep(pause)

    candles = [rows[k] for k in sorted(rows)]
    # Only retain fully closed candles. The timestamp is candle open time.
    interval_ms = integer("TIMEFRAME_MINUTES", 5) * 60_000
    now_ms = utc_ms(datetime.now(timezone.utc))
    candles = [c for c in candles if c["timestamp"] + interval_ms <= now_ms]
    validate_candles(symbol, candles, interval_ms)
    return candles


def validate_candles(symbol: str, candles: list[dict], interval_ms: int) -> None:
    if len(candles) < integer("MIN_CANDLES_REQUIRED", 100):
        raise ValueError(
            f"{symbol}: only {len(candles)} valid closed candles; "
            "increase BACKTEST_DAYS or lower MIN_CANDLES_REQUIRED."
        )
    previous = None
    for c in candles:
        if not all(math.isfinite(c[k]) for k in ("open", "high", "low", "close", "volume")):
            raise ValueError(f"{symbol}: non-finite candle value")
        if min(c["open"], c["high"], c["low"], c["close"]) <= 0 or c["volume"] < 0:
            raise ValueError(f"{symbol}: invalid OHLC/volume at {c['timestamp']}")
        if c["high"] < max(c["open"], c["close"], c["low"]):
            raise ValueError(f"{symbol}: invalid high at {c['timestamp']}")
        if c["low"] > min(c["open"], c["close"], c["high"]):
            raise ValueError(f"{symbol}: invalid low at {c['timestamp']}")
        if previous is not None and c["timestamp"] <= previous:
            raise ValueError(f"{symbol}: timestamps are not strictly increasing")
        previous = c["timestamp"]
    gaps = sum(
        1 for a, b in zip(candles, candles[1:])
        if b["timestamp"] - a["timestamp"] != interval_ms
    )
    if gaps:
        print(f"WARNING {symbol}: {gaps} missing candle interval(s); results may be incomplete.")


def rsi_series(closes: list[float], period: int) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if period < 2 or len(closes) <= period:
        return values
    gains = []
    losses = []
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def calc(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        if gain == 0:
            return 0.0
        return 100.0 - (100.0 / (1.0 + gain / loss))

    values[period] = calc(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        avg_gain = ((avg_gain * (period - 1)) + max(change, 0.0)) / period
        avg_loss = ((avg_loss * (period - 1)) + max(-change, 0.0)) / period
        values[i] = calc(avg_gain, avg_loss)
    return values


def backtest_symbol(symbol: str, candles: list[dict]) -> tuple[list[dict], dict]:
    period = integer("RSI_PERIOD", 20)
    long_entry = number("LONG_ENTRY_CROSS_BELOW", 40)
    long_exit = number("LONG_EXIT_CROSS_ABOVE", 70)
    short_entry = number("SHORT_ENTRY_CROSS_ABOVE", 85)
    short_exit = number("SHORT_EXIT_CROSS_BELOW", 30)
    notional = number("RESEARCH_NOTIONAL_USD", 1000)
    fee_rate = number("FEE_RATE_PER_SIDE", 0.00055)
    slippage = number("SLIPPAGE_RATE_PER_SIDE", 0.0005)
    closes = [c["close"] for c in candles]
    rsis = rsi_series(closes, period)
    trades: list[dict] = []
    position = 0
    entry_price = None
    entry_time = None
    entry_rsi = None
    cost_per_side = fee_rate + slippage

    # Signal from candle i's close; hypothetical fill at candle i+1 open.
    for i in range(1, len(candles) - 1):
        prev_rsi, current_rsi = rsis[i - 1], rsis[i]
        if prev_rsi is None or current_rsi is None:
            continue
        action = None
        if position == 0:
            if prev_rsi >= long_entry and current_rsi < long_entry:
                action = "enter_long"
            elif prev_rsi <= short_entry and current_rsi > short_entry:
                action = "enter_short"
        elif position == 1 and prev_rsi <= long_exit and current_rsi > long_exit:
            action = "exit_long"
        elif position == -1 and prev_rsi >= short_exit and current_rsi < short_exit:
            action = "exit_short"

        if action is None:
            continue
        fill_candle = candles[i + 1]
        raw_fill = fill_candle["open"]
        fill_price = raw_fill * (1 + cost_per_side if action in ("enter_long", "exit_short") else 1 - cost_per_side)
        stamp = datetime.fromtimestamp(fill_candle["timestamp"] / 1000, timezone.utc).isoformat()

        if action.startswith("enter"):
            position = 1 if action == "enter_long" else -1
            entry_price = fill_price
            entry_time = stamp
            entry_rsi = current_rsi
        else:
            assert entry_price is not None and entry_time is not None
            direction = position
            gross_return = direction * (fill_price - entry_price) / entry_price
            # Fees/slippage are incorporated into both entry and exit fill prices.
            pnl = notional * gross_return
            trades.append({
                "symbol": symbol,
                "direction": "long" if direction == 1 else "short",
                "entry_time_utc": entry_time,
                "exit_time_utc": stamp,
                "entry_price_adjusted": round(entry_price, 8),
                "exit_price_adjusted": round(fill_price, 8),
                "entry_rsi": round(float(entry_rsi), 4),
                "exit_rsi": round(float(current_rsi), 4),
                "notional_usd_assumed": round(notional, 2),
                "pnl_usd_estimate": round(pnl, 4),
                "return_pct_estimate": round(gross_return * 100, 4),
            })
            position = 0
            entry_price = entry_time = entry_rsi = None

    if position != 0:
        print(f"WARNING {symbol}: open hypothetical position at end was excluded from completed-trade metrics.")
    wins = [t for t in trades if t["pnl_usd_estimate"] > 0]
    losses = [t for t in trades if t["pnl_usd_estimate"] < 0]
    total_pnl = sum(t["pnl_usd_estimate"] for t in trades)
    gross_profit = sum(t["pnl_usd_estimate"] for t in wins)
    gross_loss = abs(sum(t["pnl_usd_estimate"] for t in losses))
    summary = {
        "symbol": symbol,
        "candles": len(candles),
        "completed_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades), 2) if trades else 0.0,
        "net_pnl_usd_estimate": round(total_pnl, 4),
        "profit_factor_estimate": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_usd_estimate": None,
        "first_candle_utc": datetime.fromtimestamp(candles[0]["timestamp"] / 1000, timezone.utc).isoformat(),
        "last_candle_utc": datetime.fromtimestamp(candles[-1]["timestamp"] / 1000, timezone.utc).isoformat(),
    }
    equity = peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl_usd_estimate"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    summary["max_drawdown_usd_estimate"] = round(max_dd, 4)
    return trades, summary


def main() -> int:
    symbols = [s.strip().upper() for s in cfg("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
    if not symbols:
        raise ValueError("SYMBOLS must contain at least one symbol")
    if cfg("APP_MODE", "research").lower() not in {"research", "paper"}:
        raise ValueError("APP_MODE must be research or paper; live mode is not supported")
    days = integer("BACKTEST_DAYS", 90)
    end = datetime.now(timezone.utc)
    configured_end = cfg("BACKTEST_END_UTC", "")
    configured_start = cfg("BACKTEST_START_UTC", "")
    end = datetime.fromisoformat(configured_end.replace("Z", "+00:00")) if configured_end else end
    start = datetime.fromisoformat(configured_start.replace("Z", "+00:00")) if configured_start else end - timedelta(days=days)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("BACKTEST_START_UTC and BACKTEST_END_UTC must include a timezone, e.g. 2026-01-01T00:00:00Z")
    if start >= end:
        raise ValueError("Backtest start must be before end")
    start_ms, end_ms = utc_ms(start), utc_ms(end)
    all_trades: list[dict] = []
    summaries: list[dict] = []
    for symbol in symbols:
        print(f"Downloading public Bybit {cfg('BYBIT_CATEGORY', 'linear')} candles: {symbol}")
        candles = fetch_klines(symbol, start_ms, end_ms)
        trades, summary = backtest_symbol(symbol, candles)
        all_trades.extend(trades)
        summaries.append(summary)
        print(json.dumps(summary, indent=2))

    out_dir = Path(cfg("BACKTEST_OUTPUT_DIR", "reports"))
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trades_path = out_dir / f"trades-{stamp}.csv"
    summary_path = out_dir / f"summary-{stamp}.json"
    if all_trades:
        with trades_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_trades[0].keys()))
            writer.writeheader()
            writer.writerows(all_trades)
    else:
        trades_path.write_text("symbol,direction,entry_time_utc,exit_time_utc,pnl_usd_estimate\n", encoding="utf-8")
    summary_path.write_text(json.dumps({
        "disclaimer": "Historical estimates only; not financial advice or a prediction. No orders were placed.",
        "configuration": {
            "timeframe_minutes": integer("TIMEFRAME_MINUTES", 5),
            "rsi_period": integer("RSI_PERIOD", 20),
            "fee_rate_per_side": number("FEE_RATE_PER_SIDE", 0.00055),
            "slippage_rate_per_side": number("SLIPPAGE_RATE_PER_SIDE", 0.0005),
            "assumed_notional_usd_per_trade": number("RESEARCH_NOTIONAL_USD", 1000),
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
        },
        "symbols": summaries,
        "total_completed_trades": len(all_trades),
        "total_estimated_net_pnl_usd": round(sum(t["pnl_usd_estimate"] for t in all_trades), 4),
    }, indent=2), encoding="utf-8")
    print(f"\nSaved trades: {trades_path}")
    print(f"Saved summary: {summary_path}")
    print("Research only. Results can be materially affected by funding, spreads, gaps, and data quality.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
