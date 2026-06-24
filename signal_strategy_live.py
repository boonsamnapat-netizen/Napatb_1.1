#!/usr/bin/env python3
"""Live signal emitter for the backtested winners (default: bos_retest on 4H).

Scans base OHLCV CSVs (1h), resamples to the chosen timeframe, and if a
strategy triggered on the most recent CLOSED bar, emits a Thai Telegram alert
in the same Entry/SL/TP1-3/RR format as the divergence bot — with wide,
let-winners-run targets (2R/3R/4R) per the 4H comparison study.

Examples:
  python signal_strategy_live.py --csv-dir data/real/crypto_1h --tf 4h
  python signal_strategy_live.py --csv-dir data/real/crypto_1h --strategy bos_retest --notify
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from src.signal import market_data
from src.signal.backtester import resample
from src.signal.notifier import TelegramNotifier, format_signal
from src.signal.signal_engine import Signal, _round
from src.signal.strategies import STRATEGIES, latest_setup

# Friendly Thai-ish labels for the alert "Signal:" line.
_LABEL = {
    "bos_retest": "Break of Structure + retest",
    "ema_cross": "EMA crossover",
    "ema_pullback": "EMA pullback (trend)",
    "supertrend": "Supertrend flip",
    "donchian": "Donchian breakout",
    "liq_sweep": "Liquidity sweep",
    "divergence": "Divergence",
    "divergence+trend": "Divergence + trend",
}


def _to_signal(symbol: str, name: str, tf: str, s: dict) -> Signal:
    tp1, tp2, tp3 = (_round(x) for x in s["tps"])
    return Signal(
        symbol=symbol,
        side=s["side"],
        kind=f"{_LABEL.get(name, name)} ({tf})",
        status=f"{s['side']} setup • {s['bar_time']:%Y-%m-%d %H:%M} UTC",
        entry=_round(s["entry"]),
        sl=_round(s["sl"]),
        tp1=tp1, tp2=tp2, tp3=tp3,
        rr=tuple(s["rr"]),
        risk_per_unit=_round(s["risk"]),
        price_now=_round(s["entry"]),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Live strategy signal emitter")
    p.add_argument("--csv-dir", help="folder of base OHLCV CSVs (1h)")
    p.add_argument("--csv", help="single base OHLCV CSV")
    p.add_argument("--demo", action="store_true", help="use synthetic demo data")
    p.add_argument("--strategy", default="bos_retest", choices=list(STRATEGIES))
    p.add_argument("--tf", default="4h", help="timeframe to scan")
    p.add_argument("--fresh-bars", type=int, default=1,
                   help="how many of the last closed bars count as 'fresh'")
    p.add_argument("--notify", action="store_true", help="send to Telegram")
    args = p.parse_args(argv)

    bases: dict[str, "object"] = {}
    if args.demo:
        for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            bases[s] = market_data.demo_series(s, bars=4000)
    elif args.csv:
        path = pathlib.Path(args.csv)
        bases[path.stem.upper()] = market_data.load_csv(path)
    elif args.csv_dir:
        for f in sorted(pathlib.Path(args.csv_dir).glob("*.csv")):
            try:
                bases[f.stem.upper()] = market_data.load_csv(f)
            except Exception as exc:  # noqa: BLE001
                print(f"  {f.name}: load error ({exc})")
    else:
        print("Provide --csv-dir, --csv, or --demo")
        return 1

    tg = TelegramNotifier()
    found = 0
    for sym, df in bases.items():
        d = resample(df, args.tf)
        s = latest_setup(d, args.strategy, fresh_bars=args.fresh_bars)
        if not s:
            continue
        found += 1
        sig = _to_signal(sym, args.strategy, args.tf, s)
        print("\n" + format_signal(sig))
        if args.notify:
            print("  -> sent" if tg.send_signal(sig) else "  -> dry-run / not sent")

    if not found:
        print(f"No fresh {args.strategy} setup on {args.tf} "
              f"(last {args.fresh_bars} bar(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
