# RSI Research Project

A separate repository for researching RSI(20) signals on 15-minute Bybit futures candles. This repository is independent of EMA-BAND.

## Security first

**Never put API keys, API secrets, Telegram bot tokens, chat IDs, VPS private keys, .env files, or other credentials in this repository.** The repository is public. Anyone can read committed secrets, and deleting a file later does not remove it from Git history.

Store secrets only in a private VPS environment file (for example, /etc/rsi-bot/rsi.env) with restrictive permissions. Do not paste secrets into chat or commit them to GitHub. If any credential has already been exposed publicly, revoke/rotate it immediately.

## Research rules to document

- Timeframe: 15-minute candles.
- Indicator: RSI(20), calculated from completed candles for reproducible research.
- Long signal concept: RSI crosses down through 40.
- Long exit concept: RSI crosses up through 70.
- Short signal concept: RSI crosses up through 85.
- Short exit concept: RSI crosses down through 30.
- Market universe: maintain a separately configured list of symbols; validate instrument status and candle completeness before analysis.
- Initial mode: historical research / paper-only. No live order execution is included here.
- EMA-BAND must remain untouched.

## Credentials

Use .env.example as a list of variable names only. Copy it to a private VPS-only environment file and fill in credentials there. Never commit the filled file.

## Research cautions

Historical results are not predictions. Any candle study should account for candle-close timing, fees, slippage, funding, instrument contract rules, missing data, and look-ahead bias. Liquidation-price estimates depend on exchange margin rules and account state; a fixed percentage rule cannot guarantee a stop executes before liquidation.

## Status

This repository contains safe project scaffolding and configuration guidance. It does not currently contain a live trading engine, does not submit orders, and does not claim a verified backtest result.
