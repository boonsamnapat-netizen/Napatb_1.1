#!/usr/bin/env python3
"""Backtest the divergence strategy across timeframes and rank them.

Feed it a base OHLCV CSV (ideally 1h, so it can resample up) or a folder of
them; it resamples to each requested timeframe, runs a walk-forward backtest
over the last N days, and prints a ranked table (best TF first).

The sandbox can't reach exchanges, so use committed CSVs. The companion
workflow `.github/workflows/divergence_backtest.yml` fetches real 1h/1d data
via yfinance and runs this sweep on GitHub Actions.

Examples:
  # one base CSV (1h), sweep intraday->daily over the last year
  python signal_divergence_backtest.py --csv data/real/crypto_1h/BTCUSDT.csv \
      --tfs 1h,2h,4h,6h,12h,1d --days 365

  # a whole folder, aggregate across symbols
  python signal_divergence_backtest.py --csv-dir data/real/crypto_1h \
      --tfs 4h,12h,1d --days 365 --notify

  # offline demo (synthetic) just to see the mechanics
  python signal_divergence_backtest.py --demo --tfs 1d,3d,1w
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict

import pandas as pd

from src.signal import market_data
from src.signal.backtester import BacktestResult, backtest, resample
from src.signal.notifier import TelegramNotifier


def _slice_days(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if days <= 0 or df.empty:
        return df
    cutoff = df.index.max() - pd.Timedelta(days=days)
    return df.loc[df.index >= cutoff]


def _aggregate(per_symbol: list[BacktestResult]) -> dict:
    """Pool trades from many symbols on the SAME tf into one combined row."""
    agg = BacktestResult(tf=per_symbol[0].tf, symbol="ALL")
    for r in per_symbol:
        agg.trades += r.trades
        agg.wins += r.wins
        agg.rs.extend(r.rs)
    return agg.as_row()


def _print_table(rows: list[dict]) -> None:
    cols = ["tf", "trades", "win_rate", "avg_R", "total_R", "profit_factor", "max_dd_R"]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    line = "  ".join(c.ljust(widths[c]) for c in cols)
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Divergence TF backtest sweep")
    p.add_argument("--csv", help="single base OHLCV CSV")
    p.add_argument("--csv-dir", help="folder of base OHLCV CSVs")
    p.add_argument("--demo", action="store_true", help="use synthetic demo data")
    p.add_argument("--tfs", default="4h,12h,1d", help="comma list of timeframes")
    p.add_argument("--days", type=int, default=365, help="lookback window in days")
    p.add_argument("--indicator", default="auto", help="auto | rsi | macd")
    p.add_argument("--target-r", type=float, default=2.0, help="take-profit in R")
    p.add_argument("--max-hold", type=int, default=30, help="max bars per trade")
    p.add_argument("--fee-pct", type=float, default=0.05, help="taker fee per side %")
    p.add_argument("--notify", action="store_true", help="send summary to Telegram")
    p.add_argument("--out", help="write full results JSON here")
    args = p.parse_args(argv)

    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]

    # Collect base frames as {symbol: df}.
    bases: dict[str, pd.DataFrame] = {}
    if args.demo:
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            bases[sym] = market_data.demo_series(sym, bars=400)
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
        print("Provide --csv, --csv-dir, or --demo")
        return 1

    if not bases:
        print("No data loaded.")
        return 1

    kw = dict(
        indicator=args.indicator,
        target_r=args.target_r,
        max_hold=args.max_hold,
        fee_pct=args.fee_pct,
    )

    # tf -> list of per-symbol results
    by_tf: dict[str, list[BacktestResult]] = defaultdict(list)
    per_symbol_rows: list[dict] = []
    for sym, df in bases.items():
        for tf in tfs:
            try:
                d = _slice_days(resample(df, tf), args.days)
            except Exception as exc:  # noqa: BLE001
                print(f"  {sym} {tf}: resample error ({exc})")
                continue
            r = backtest(d, sym, tf, **kw)
            by_tf[tf].append(r)
            per_symbol_rows.append(r.as_row())

    rows = [_aggregate(rs) for rs in by_tf.values() if rs]
    # Rank: most total R, but require a minimum sample so noise can't win.
    rows.sort(key=lambda r: (r["trades"] >= 10, r["avg_R"], r["total_R"]), reverse=True)

    syms = ", ".join(sorted(bases))
    print(f"\nDivergence TF sweep — {len(bases)} symbol(s): {syms}")
    print(f"lookback {args.days}d · indicator={args.indicator} · "
          f"target {args.target_r}R · fee {args.fee_pct}%/side\n")
    _print_table(rows)

    if rows:
        best = rows[0]
        print(f"\nBest TF: {best['tf']}  "
              f"(avg {best['avg_R']}R/trade, total {best['total_R']}R, "
              f"WR {best['win_rate']*100:.0f}%, {best['trades']} trades)")

    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps({"summary": rows, "per_symbol": per_symbol_rows}, indent=2)
        )
        print(f"wrote {args.out}")

    if args.notify and rows:
        best = rows[0]
        lines = ["📊 Backtest divergence — หา TF ที่ดีสุด",
                 f"ข้อมูล {len(bases)} เหรียญ · ย้อนหลัง {args.days} วัน",
                 f"TP {args.target_r}R · fee {args.fee_pct}%/ข้าง", ""]
        for r in rows:
            lines.append(
                f"{r['tf']}: avg {r['avg_R']}R · รวม {r['total_R']}R · "
                f"WR {r['win_rate']*100:.0f}% · {r['trades']} ไม้"
            )
        lines.append("")
        lines.append(
            f"🏆 ดีสุด: {best['tf']} (avg {best['avg_R']}R/ไม้, "
            f"รวม {best['total_R']}R)"
        )
        TelegramNotifier().send("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
