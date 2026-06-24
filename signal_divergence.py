#!/usr/bin/env python3
"""Divergence signal bot CLI.

Detect RSI / MACD regular divergence (with overbought/oversold status), build a
risk-managed plan (Entry / SL / TP1-3 / RR) and push a Thai alert to Telegram.

The sandbox can only reach raw.githubusercontent.com, so use committed CSVs or
the offline demo generator for ad-hoc runs.

Examples:
  # one coin, offline demo, print only
  python signal_divergence.py BTCUSDT --demo

  # one coin from a CSV, send to Telegram
  python signal_divergence.py BTCUSDT --csv data/real/crypto/BTCUSDT.csv --notify

  # scan a folder of CSVs and alert every divergence found
  python signal_divergence.py --csv-dir data/real/crypto --notify

  # preview a sample alert (no data needed)
  python signal_divergence.py --sample --notify
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from src.signal import market_data
from src.signal.divergence import detect
from src.signal.notifier import TelegramNotifier, format_signal, format_summary
from src.signal.signal_engine import Signal, build_signal


def _symbol_from_path(path: pathlib.Path) -> str:
    return path.stem.upper()


def _process(symbol: str, df, indicator: str) -> Signal | None:
    if len(df) < 60:
        print(f"  {symbol}: not enough bars ({len(df)})")
        return None
    div = detect(df, indicator=indicator)
    if div is None:
        print(f"  {symbol}: no divergence")
        return None
    return build_signal(symbol, df, div=div, indicator=indicator)


def _sample_signal() -> Signal:
    return Signal(
        symbol="BTCUSDT",
        side="LONG",
        kind="Bullish divergent",
        status="MACD Oversold",
        entry=61250.0,
        sl=59900.0,
        tp1=62600.0,
        tp2=63950.0,
        tp3=65300.0,
        rr=(1.0, 2.0, 3.0),
        risk_per_unit=1350.0,
        price_now=61250.0,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Divergence crypto signal bot")
    p.add_argument("symbol", nargs="?", help="e.g. BTCUSDT (with --demo or --csv)")
    p.add_argument("--csv", help="OHLCV CSV for a single symbol")
    p.add_argument("--csv-dir", help="folder of OHLCV CSVs to scan")
    p.add_argument("--demo", action="store_true", help="use offline synthetic data")
    p.add_argument("--sample", action="store_true", help="send a sample alert")
    p.add_argument(
        "--indicator",
        default="auto",
        choices=["auto", "rsi", "macd", "RSI", "MACD", "AUTO"],
        help="oscillator for divergence (default: auto)",
    )
    p.add_argument("--notify", action="store_true", help="send to Telegram")
    p.add_argument("--summary", action="store_true", help="also send a scan summary")
    args = p.parse_args(argv)

    tg = TelegramNotifier()
    indicator = args.indicator

    if args.sample:
        sig = _sample_signal()
        print(format_signal(sig))
        if args.notify:
            print("sent" if tg.send_signal(sig) else "dry-run / failed")
        return 0

    signals: list[Signal] = []

    if args.csv_dir:
        folder = pathlib.Path(args.csv_dir)
        files = sorted(folder.glob("*.csv"))
        if not files:
            print(f"No CSVs in {folder}")
            return 1
        for f in files:
            try:
                df = market_data.load_csv(f)
            except Exception as exc:  # noqa: BLE001
                print(f"  {f.name}: load error ({exc})")
                continue
            sig = _process(_symbol_from_path(f), df, indicator)
            if sig:
                signals.append(sig)
    else:
        symbol = (args.symbol or "BTCUSDT").upper()
        if args.csv:
            df = market_data.load_csv(args.csv)
        elif args.demo:
            df = market_data.demo_series(symbol)
        else:
            print("Provide a data source: --csv, --csv-dir, --demo, or --sample")
            return 1
        sig = _process(symbol, df, indicator)
        if sig:
            signals.append(sig)

    if not signals:
        print("No divergence signals.")
        if args.notify and args.summary:
            tg.send(format_summary(signals))
        return 0

    for sig in signals:
        print("\n" + format_signal(sig))
        if args.notify:
            ok = tg.send_signal(sig)
            print("  -> sent" if ok else "  -> dry-run / not sent")

    if args.notify and args.summary:
        tg.send(format_summary(signals))

    return 0


if __name__ == "__main__":
    sys.exit(main())
