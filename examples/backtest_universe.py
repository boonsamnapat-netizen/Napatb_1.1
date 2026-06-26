#!/usr/bin/env python3
"""Walk-forward OOS backtest across the whole universe -> one pooled dataset.

Runs the LIVE config (default weights, fees, trailing) walk-forward on every
committed daily CSV, pools the out-of-sample results, and writes a dataset +
summary. This is the honest, net-of-fees, out-of-sample expectation to compare
the live Telegram journal against.
"""
import json, pathlib, sys
import pandas as pd, yaml
from src.signal.backtester import SignalBacktester

cfg = yaml.safe_load(open("config/config.yaml"))
csv_dir = pathlib.Path("data/real/crypto")
risk = cfg.get("signal", {}).get("risk_per_trade_pct", 2.0)

rows, pooled_trades = [], 0
pooled_wins = pooled_total_r = 0.0
per_coin = []

for csv in sorted(csv_dir.glob("*.csv")):
    sym = csv.stem
    df = pd.read_csv(csv, index_col=0, parse_dates=True)
    df.columns = [c.lower() for c in df.columns]
    htf = df.resample("W").agg({"open": "first", "high": "max", "low": "min",
                                "close": "last", "volume": "sum"}).dropna()
    bt = SignalBacktester(cfg.get("signal", {}))
    try:
        wf = bt.walk_forward(df, htf, risk_per_trade_pct=risk)
    except Exception as e:  # noqa: BLE001
        print(f"  {sym}: SKIP ({e})"); continue
    c = wf["combined_oos"]
    n = c["trades"]
    if not n:
        print(f"  {sym}: 0 OOS trades"); continue
    total_r = c["avg_r"] * n
    pooled_trades += n
    pooled_wins += c["wins"]
    pooled_total_r += total_r
    per_coin.append({"symbol": sym, "trades": n, "win_rate": c["win_rate"],
                     "avg_r": round(c["avg_r"], 3), "total_r": round(total_r, 2),
                     "max_dd_r": c.get("max_drawdown_r")})
    print(f"  {sym}: {n} OOS trades  WR {c['win_rate']*100:.0f}%  avg {c['avg_r']:+.3f}R")

if not pooled_trades:
    print("No trades collected."); sys.exit(1)

summary = {
    "config": "live default (4h-style/W, Supertrend, ATR trail 2.5R, fees on)",
    "pooled_oos_trades": pooled_trades,
    "pooled_win_rate": round(pooled_wins / pooled_trades, 4),
    "pooled_avg_r": round(pooled_total_r / pooled_trades, 4),
    "pooled_total_r": round(pooled_total_r, 2),
    "coins": len(per_coin),
    "per_coin": sorted(per_coin, key=lambda x: x["avg_r"], reverse=True),
}
out = pathlib.Path("data/backtest_universe_oos.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(summary, indent=2))
print("\n" + "=" * 56)
print(f"POOLED OOS  ({summary['coins']} coins, {pooled_trades} trades)")
print(f"  win rate : {summary['pooled_win_rate']*100:.1f}%")
print(f"  avg R    : {summary['pooled_avg_r']:+.4f} R / trade")
print(f"  total R  : {summary['pooled_total_r']:+.1f} R")
print(f"saved -> {out}")
