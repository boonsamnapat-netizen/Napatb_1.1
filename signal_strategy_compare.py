#!/usr/bin/env python3
"""Compare trading strategies on one timeframe over real data.

Loads a folder of base OHLCV CSVs (1h), resamples to the chosen timeframe
(default 4h), runs every strategy through the shared R-multiple engine, pools
results across symbols, and prints a ranked comparison.

Example:
  python signal_strategy_compare.py --csv-dir data/real/crypto_1h \
      --tf 4h --days 365 --target-r 2.0
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict

import pandas as pd

from src.signal import market_data
from src.signal.backtester import BacktestResult, resample
from src.signal.notifier import TelegramNotifier
from src.signal.strategies import STRATEGIES, backtest_strategy


def _slice_days(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if days <= 0 or df.empty:
        return df
    return df.loc[df.index >= df.index.max() - pd.Timedelta(days=days)]


def _pool(rows: list[BacktestResult]) -> dict:
    agg = BacktestResult(tf=rows[0].tf, symbol="ALL")
    for r in rows:
        agg.trades += r.trades
        agg.wins += r.wins
        agg.rs.extend(r.rs)
    return agg.as_row()


def _table(rows: list[dict], key0: str = "strategy") -> None:
    cols = [key0, "trades", "win_rate", "avg_R", "total_R", "profit_factor", "max_dd_R"]
    w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    line = "  ".join(c.ljust(w[c]) for c in cols)
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w[c]) for c in cols))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Strategy comparison on one TF")
    p.add_argument("--csv-dir", help="folder of base OHLCV CSVs (1h)")
    p.add_argument("--demo", action="store_true", help="use synthetic demo data")
    p.add_argument("--tf", default="4h", help="timeframe to test on")
    p.add_argument("--days", type=int, default=365, help="lookback window in days")
    p.add_argument("--target-r", type=float, default=2.0)
    p.add_argument("--max-hold", type=int, default=30)
    p.add_argument("--fee-pct", type=float, default=0.05)
    p.add_argument("--per-coin", action="store_true", help="also print per-coin")
    p.add_argument("--out", help="write results JSON here")
    p.add_argument("--notify", action="store_true", help="send summary to Telegram")
    args = p.parse_args(argv)

    bases: dict[str, pd.DataFrame] = {}
    if args.demo:
        for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            bases[s] = market_data.demo_series(s, bars=6000)
    elif args.csv_dir:
        for f in sorted(pathlib.Path(args.csv_dir).glob("*.csv")):
            try:
                bases[f.stem.upper()] = market_data.load_csv(f)
            except Exception as exc:  # noqa: BLE001
                print(f"  {f.name}: load error ({exc})")
    else:
        print("Provide --csv-dir or --demo")
        return 1
    if not bases:
        print("No data loaded.")
        return 1

    kw = dict(target_r=args.target_r, max_hold=args.max_hold, fee_pct=args.fee_pct)
    by_strat: dict[str, list[BacktestResult]] = defaultdict(list)
    per_coin: list[dict] = []
    for sym, df in bases.items():
        d = _slice_days(resample(df, args.tf), args.days)
        for name in STRATEGIES:
            r = backtest_strategy(d, sym, name, **kw)
            by_strat[name].append(r)
            row = r.as_row()
            row["strategy"] = name
            per_coin.append(row)

    rows = []
    for name, rs in by_strat.items():
        row = _pool(rs)
        row["strategy"] = name
        rows.append(row)
    rows.sort(key=lambda r: (r["trades"] >= 20, r["avg_R"], r["total_R"]), reverse=True)

    print(f"\nStrategy comparison on {args.tf} — {len(bases)} symbols, "
          f"last {args.days}d, target {args.target_r}R, fee {args.fee_pct}%/side\n")
    _table(rows)
    if rows:
        b = rows[0]
        print(f"\nBest: {b['strategy']}  (avg {b['avg_R']}R/trade, total {b['total_R']}R, "
              f"WR {b['win_rate']*100:.0f}%, PF {b['profit_factor']}, {b['trades']} trades)")

    if args.per_coin:
        for name in STRATEGIES:
            sub = [r for r in per_coin if r["strategy"] == name]
            print(f"\n--- {name} per-coin ---")
            _table([{**r, "strategy": r["symbol"]} for r in sub])

    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps({"summary": rows, "per_coin": per_coin}, indent=2))
        print(f"\nwrote {args.out}")

    if args.notify and rows:
        b = rows[0]
        lines = [f"📊 เทียบกลยุทธ์บน {args.tf} ({len(bases)} เหรียญ, {args.days}d, TP {args.target_r}R)", ""]
        for r in rows:
            lines.append(f"{r['strategy']}: avg {r['avg_R']}R · รวม {r['total_R']}R · "
                         f"WR {r['win_rate']*100:.0f}% · PF {r['profit_factor']} · {r['trades']} ไม้")
        lines += ["", f"🏆 ดีสุด: {b['strategy']} (avg {b['avg_R']}R/ไม้)"]
        TelegramNotifier().send("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
