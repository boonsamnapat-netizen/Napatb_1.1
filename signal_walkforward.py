#!/usr/bin/env python3
"""Walk-forward / out-of-sample test to gauge over-fitting.

Splits each symbol's history by time into in-sample (older) and out-of-sample
(newer). A small parameter grid is optimised on IS (pooled across symbols),
then the chosen config is scored on OOS — the honest number. A fixed default
config is reported alongside so we can see whether 'optimising' actually helps
or just curve-fits.

Example:
  python signal_walkforward.py --csv-dir data/real/crypto_1h --tf 4h \
      --strategy bos_retest --is-frac 0.65
"""
from __future__ import annotations

import argparse
import itertools
import pathlib
import sys

import pandas as pd

from src.signal import market_data
from src.signal.backtester import BacktestResult, resample
from src.signal.strategies import (
    bos_retest_signals,
    ema_cross_signals,
    run,
)


def _pool(df_map, gen_kw, exit_kw) -> BacktestResult:
    agg = BacktestResult(tf="pool", symbol="ALL")
    for sym, (df, gen) in df_map.items():
        side, riskdist = gen(df, **gen_kw)
        r = run(df, side, riskdist, sym, "x", **exit_kw)
        agg.trades += r.trades
        agg.wins += r.wins
        agg.rs.extend(r.rs)
    return agg


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Walk-forward OOS test")
    p.add_argument("--csv-dir", required=True)
    p.add_argument("--tf", default="4h")
    p.add_argument("--strategy", default="bos_retest",
                   choices=["bos_retest", "ema_cross"])
    p.add_argument("--days", type=int, default=730)
    p.add_argument("--is-frac", type=float, default=0.65,
                   help="fraction of each series used as in-sample (older)")
    p.add_argument("--min-trades", type=int, default=40)
    args = p.parse_args(argv)

    # Load + resample + time-split each symbol.
    is_map: dict = {}
    oos_map: dict = {}
    gen = bos_retest_signals if args.strategy == "bos_retest" else ema_cross_signals
    for f in sorted(pathlib.Path(args.csv_dir).glob("*.csv")):
        df = resample(market_data.load_csv(f), args.tf)
        if args.days > 0:
            df = df.loc[df.index >= df.index.max() - pd.Timedelta(days=args.days)]
        cut = int(len(df) * args.is_frac)
        sym = f.stem.upper()
        is_map[sym] = (df.iloc[:cut], gen)
        oos_map[sym] = (df.iloc[cut:], gen)

    # Grid: structure params x exit policy.
    if args.strategy == "bos_retest":
        grid_gen = [dict(window=w, retest_bars=rb)
                    for w in (3, 5, 8) for rb in (4, 6, 10)]
    else:
        grid_gen = [dict()]  # ema_cross has no structural knobs here
    grid_exit = [
        dict(target_r=2.0, max_hold=30),
        dict(target_r=4.0, max_hold=30),
        dict(trail_atr=2.0, max_hold=120),
        dict(trail_atr=3.0, max_hold=120),
    ]

    rows = []
    for g, e in itertools.product(grid_gen, grid_exit):
        r = _pool(is_map, g, e)
        rows.append((g, e, r.avg_r, r.trades))

    valid = [r for r in rows if r[3] >= args.min_trades]
    if not valid:
        print("No config met the min-trades threshold on in-sample.")
        return 1
    best = max(valid, key=lambda r: r[2])
    g_best, e_best, is_avg, is_n = best

    def _label(g, e):
        exit_s = (f"trail{e['trail_atr']}x" if "trail_atr" in e
                  else f"{e['target_r']}R")
        return f"{g} | {exit_s}"

    oos_best = _pool(oos_map, g_best, e_best)
    # Default baseline for reference.
    g_def = {} if args.strategy == "ema_cross" else dict(window=5, retest_bars=6)
    e_def = dict(trail_atr=3.0, max_hold=120)
    oos_def = _pool(oos_map, g_def, e_def)
    is_def = _pool(is_map, g_def, e_def)

    print(f"\nWalk-forward — {args.strategy} on {args.tf}, "
          f"IS={args.is_frac:.0%}/OOS={1-args.is_frac:.0%}, last {args.days}d\n")
    print(f"{'set':24}{'IS avgR':>9}{'IS n':>6}{'OOS avgR':>10}{'OOS n':>7}")
    print("-" * 56)
    print(f"{'optimised: '+_label(g_best,e_best):24}"
          f"{is_avg:>9.3f}{is_n:>6}{oos_best.avg_r:>10.3f}{oos_best.trades:>7}")
    print(f"{'default: '+_label(g_def,e_def):24}"
          f"{is_def.avg_r:>9.3f}{is_def.trades:>6}{oos_def.avg_r:>10.3f}{oos_def.trades:>7}")

    print(f"\nOOS profit factor — optimised {oos_best.profit_factor:.2f} | "
          f"default {oos_def.profit_factor:.2f}")
    verdict = ("OOS holds up — edge looks real"
               if oos_best.avg_r > 0 and oos_best.profit_factor > 1.05
               else "OOS weak — likely over-fit / regime-dependent")
    print(f"Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
