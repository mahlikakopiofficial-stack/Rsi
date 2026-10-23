#!/usr/bin/env python3
"""Isolated RSI(20) 5-minute Bybit public-data paper trader.

This module has no private Bybit API client and cannot place live orders.
It persists paper positions and signal cursors in SQLite and optionally sends Telegram alerts.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backtest import cfg, integer, number, rsi_series

ROOT = Path(__file__).resolve().parent


def validate_paper_config() -> None:
    if cfg("APP_MODE", "paper").lower() != "paper":
        raise ValueError("paper_bot.py only supports APP_MODE=paper; live execution is not implemented")
    if integer("TIMEFRAME_MINUTES", 5) != 5:
        raise ValueError("paper_bot.py is configured for 5-minute candles only")
    if integer("RSI_PERIOD", 20) < 2:
        raise ValueError("RSI_PERIOD must be at least 2")
    if number("PAPER_NOTIONAL_USD", 5) < 5:
        raise ValueError("PAPER_NOTIONAL_USD must be at least 5 USD")
    if integer("PAPER_MAX_OPEN_POSITIONS", 3) < 1:
        raise ValueError("PAPER_MAX_OPEN_POSITIONS must be at least 1")
    if integer("LOOP_SECONDS", 10) < 5:
        raise ValueError("LOOP_SECONDS must be at least 5 seconds")
    for name, default in (
        ("LONG_ENTRY_CROSS_BELOW", 40), ("LONG_EXIT_CROSS_ABOVE", 70),
        ("SHORT_ENTRY_CROSS_ABOVE", 85), ("SHORT_EXIT_CROSS_BELOW", 30),
    ):
        value = number(name, default)
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")
    symbols = [s.strip().upper() for s in cfg("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
    if not symbols:
        raise ValueError("SYMBOLS must contain at least one symbol")
    if len(set(symbols)) != len(symbols):
        raise ValueError("SYMBOLS contains duplicates")


def fetch_recent_klines(symbol: str) -> list[dict]:
    """Fetch public linear candles; keep current candle for its open as paper fill."""
    base = cfg("BYBIT_PUBLIC_BASE_URL", "https://api.bybit.com").rstrip("/")
    timeout = max(5, integer("HTTP_TIMEOUT_SECONDS", 20))
    query = urlencode({
        "category": cfg("BYBIT_CATEGORY", "linear"),
        "symbol": symbol.upper(),
        "interval": "5",
        "limit": max(50, min(1000, integer("BYBIT_PAGE_LIMIT", 100))),
    })
    request = Request(f"{base}/v5/market/kline?{query}", headers={"User-Agent": "RSI-Paper-Bot/1.0"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("retCode") != 0:
        raise RuntimeError(f"Bybit public market-data error {payload.get('retCode')}: {payload.get('retMsg', '')}")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    candles = []
    for row in payload.get("result", {}).get("list", []):
        candle = {
            "timestamp": int(row[0]), "open": float(row[1]), "high": float(row[2]),
            "low": float(row[3]), "close": float(row[4]), "volume": float(row[5]),
        }
        if not all(math.isfinite(candle[k]) for k in ("open", "high", "low", "close", "volume")):
            raise ValueError(f"{symbol}: Bybit returned non-finite candle data")
        if min(candle["open"], candle["high"], candle["low"], candle["close"]) <= 0 or candle["volume"] < 0:
            raise ValueError(f"{symbol}: Bybit returned invalid OHLC/volume")
        if candle["high"] < max(candle["open"], candle["close"], candle["low"]) or candle["low"] > min(candle["open"], candle["close"], candle["high"]):
            raise ValueError(f"{symbol}: Bybit returned inconsistent OHLC values")
        candles.append(candle)
    candles.sort(key=lambda c: c["timestamp"])
    unique = {c["timestamp"]: c for c in candles}
    candles = [unique[k] for k in sorted(unique)]
    if len(candles) < integer("RSI_PERIOD", 20) + 3:
        raise ValueError(f"{symbol}: insufficient Bybit candles for RSI warm-up")
    if candles[-1]["timestamp"] + 300_000 <= now_ms:
        raise RuntimeError(f"{symbol}: no current 5-minute candle available; skipping to avoid stale execution")
    if candles[-1]["timestamp"] - candles[-2]["timestamp"] != 300_000:
        raise RuntimeError(f"{symbol}: current candle is not contiguous with last closed candle")
    return candles


def telegram_send(message: str) -> None:
    token = cfg("TELEGRAM_BOT_TOKEN", "")
    chat_id = cfg("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    data = urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    timeout = max(5, integer("HTTP_TIMEOUT_SECONDS", 20))
    try:
        with urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API rejected message: {payload.get('description', 'unknown error')}")
    except Exception as exc:
        print(f"WARNING Telegram notification failed: {exc}", file=sys.stderr)


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS cursor (
        symbol TEXT PRIMARY KEY, last_signal_candle_ms INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS positions (
        symbol TEXT PRIMARY KEY, side TEXT NOT NULL, entry_price REAL NOT NULL,
        entry_time_ms INTEGER NOT NULL, entry_rsi REAL NOT NULL, notional_usd REAL NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL,
        entry_price REAL NOT NULL, exit_price REAL NOT NULL, entry_time_ms INTEGER NOT NULL,
        exit_time_ms INTEGER NOT NULL, pnl_usd REAL NOT NULL, exit_rsi REAL NOT NULL)""")
    db.commit()
    return db


def get_signal(candles: list[dict]) -> tuple[str | None, float, int]:
    """Return signal on latest closed candle; fill uses current candle open."""
    closed = candles[:-1]
    rsis = rsi_series([c["close"] for c in closed], integer("RSI_PERIOD", 20))
    previous, current = rsis[-2], rsis[-1]
    if previous is None or current is None:
        return None, float("nan"), closed[-1]["timestamp"]
    le, lx = number("LONG_ENTRY_CROSS_BELOW", 40), number("LONG_EXIT_CROSS_ABOVE", 70)
    se, sx = number("SHORT_ENTRY_CROSS_ABOVE", 85), number("SHORT_EXIT_CROSS_BELOW", 30)
    action = None
    if previous >= le and current < le:
        action = "enter_long"
    elif previous <= se and current > se:
        action = "enter_short"
    elif previous <= lx and current > lx:
        action = "exit_long"
    elif previous >= sx and current < sx:
        action = "exit_short"
    return action, current, closed[-1]["timestamp"]


def process_symbol(db: sqlite3.Connection, symbol: str, candles: list[dict]) -> str | None:
    action, signal_rsi, signal_ts = get_signal(candles)
    cursor = db.execute("SELECT last_signal_candle_ms FROM cursor WHERE symbol=?", (symbol,)).fetchone()
    if cursor is None:
        db.execute("INSERT INTO cursor(symbol,last_signal_candle_ms) VALUES (?,?)", (symbol, signal_ts))
        db.commit()
        return f"Paper bot initialized {symbol}; waiting for next fresh 5-minute close."
    last_ts = int(cursor[0])
    if signal_ts <= last_ts:
        return None
    if signal_ts - last_ts != 300_000:
        db.execute("UPDATE cursor SET last_signal_candle_ms=? WHERE symbol=?", (signal_ts, symbol))
        db.commit()
        return f"Skipped stale {symbol} signal after candle gap; cursor safely advanced."
    db.execute("UPDATE cursor SET last_signal_candle_ms=? WHERE symbol=?", (signal_ts, symbol))
    if action is None or not math.isfinite(signal_rsi):
        db.commit()
        return None

    fill_ts, raw_fill = candles[-1]["timestamp"], candles[-1]["open"]
    cost = number("FEE_RATE_PER_SIDE", 0.00055) + number("SLIPPAGE_RATE_PER_SIDE", 0.0005)
    position = db.execute("SELECT side,entry_price,entry_time_ms,entry_rsi,notional_usd FROM positions WHERE symbol=?", (symbol,)).fetchone()
    notice = None
    if action in ("enter_long", "enter_short"):
        if position:
            db.commit()
            return None
        max_positions = integer("PAPER_MAX_OPEN_POSITIONS", 3)
        opened = db.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        if opened >= max_positions:
            db.commit()
            return f"Paper entry skipped for {symbol}: maximum open positions ({max_positions}) reached."
        side = "long" if action == "enter_long" else "short"
        entry = raw_fill * (1 + cost if side == "long" else 1 - cost)
        notional = number("PAPER_NOTIONAL_USD", 5)
        db.execute("INSERT INTO positions VALUES (?,?,?,?,?,?)", (symbol, side, entry, fill_ts, signal_rsi, notional))
        notice = f"RSI PAPER ENTRY | {symbol} {side.upper()} | RSI20={signal_rsi:.2f} | fill≈{entry:.8g} | notional=${notional:.2f} | 5m"
    elif action in ("exit_long", "exit_short"):
        expected = "long" if action == "exit_long" else "short"
        if not position or position[0] != expected:
            db.commit()
            return None
        side, entry, entry_ts, entry_rsi, notional = position
        exit_price = raw_fill * (1 - cost if side == "long" else 1 + cost)
        pnl = notional * ((exit_price - entry) / entry if side == "long" else (entry - exit_price) / entry)
        db.execute("INSERT INTO paper_trades(symbol,side,entry_price,exit_price,entry_time_ms,exit_time_ms,pnl_usd,exit_rsi) VALUES (?,?,?,?,?,?,?,?)",
                   (symbol, side, entry, exit_price, entry_ts, fill_ts, pnl, signal_rsi))
        db.execute("DELETE FROM positions WHERE symbol=?", (symbol,))
        notice = f"RSI PAPER EXIT | {symbol} {side.upper()} | RSI20={signal_rsi:.2f} | fill≈{exit_price:.8g} | estimated paper PnL=${pnl:+.4f}"
    db.commit()
    return notice


def main() -> int:
    validate_paper_config()
    symbols = [s.strip().upper() for s in cfg("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
    db_path = Path(cfg("PAPER_DB_PATH", "data/paper_trading.sqlite3"))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db = init_db(db_path)
    telegram_send("RSI paper bot started. 5m RSI(20). Paper-only: no live orders are possible.")
    print(f"RSI paper bot started; symbols={','.join(symbols)}; DB={db_path}")
    try:
        while True:
            for symbol in symbols:
                try:
                    candles = fetch_recent_klines(symbol)
                    notice = process_symbol(db, symbol, candles)
                    if notice:
                        print(notice)
                        telegram_send(notice)
                except Exception as exc:
                    message = f"RSI paper bot error | {symbol} | {type(exc).__name__}: {exc}"
                    print(message, file=sys.stderr)
                    telegram_send(message)
            time.sleep(integer("LOOP_SECONDS", 10))
    except KeyboardInterrupt:
        print("Stopping RSI paper bot.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
