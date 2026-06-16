#!/usr/bin/env python3
"""
Backtest the signal rules and (optionally) walk-forward tune the indicator
weights. Reports the REAL win-rate / expectancy so money management can stop
guessing.

Examples:
  python signal_backtest.py BTCUSDT --tf 1h --htf 4h --limit 1500
  python signal_backtest.py ETHUSDT --optimize          # walk-forward tuning
  python signal_backtest.py BTCUSDT --demo               # offline synthetic data
  python signal_backtest.py BTCUSDT --optimize --apply   # write calibrated_win_rate to config
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import yaml
from rich import box
from rich.console import Console
from rich.table import Table

console = Console()


def load_config(path: str) -> dict:
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _apply_calibration(path: str, value: float) -> None:
    """Set signal.calibrated_win_rate via a targeted text edit (keeps comments)."""
    import re

    p = Path(path)
    text = p.read_text(encoding="utf-8")
    new_line = (
        f"  calibrated_win_rate: {value}   # auto-calibrated from signal_backtest.py"
    )
    pattern = re.compile(r"^\s*#?\s*calibrated_win_rate:.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(new_line, text, count=1)
    else:
        # insert as the first key under the `signal:` block
        text = re.sub(r"^(signal:\s*\n)", r"\1" + new_line + "\n", text, count=1,
                      flags=re.MULTILINE)
    p.write_text(text, encoding="utf-8")


def render_metrics(title: str, m: dict) -> None:
    t = Table(title=title, box=box.ROUNDED)
    t.add_column("Metric", style="cyan")
    t.add_column("Value", style="white")
    t.add_row("Trades", str(m["trades"]))
    t.add_row("Wins / Losses", f"{m['wins']} / {m['losses']}")
    t.add_row("Win rate", f"{m['win_rate']*100:.1f}%")
    t.add_row("Expectancy", f"{m['expectancy_r']:+.3f} R / trade")
    t.add_row("Profit factor", f"{m['profit_factor']:.2f}")
    t.add_row("Total", f"{m['total_r']:+.2f} R")
    t.add_row("Max drawdown", f"{m['max_drawdown_r']:.2f} R")
    t.add_row("Return (compounded)", f"{m['return_pct']:+.2f}%")
    t.add_row("Max drawdown %", f"{m['max_drawdown_pct']:.2f}%")
    if m.get("weights"):
        t.add_row("Weights", json.dumps({k: round(v, 2) for k, v in m["weights"].items()}))
    console.print(t)


def main():
    ap = argparse.ArgumentParser(description="Signal backtester / weight tuner")
    ap.add_argument("symbol")
    ap.add_argument("--config", "-c", default="config/config.yaml")
    ap.add_argument("--tf")
    ap.add_argument("--htf")
    ap.add_argument("--limit", type=int, default=1500)
    ap.add_argument("--risk", type=float, default=1.0)
    ap.add_argument("--optimize", action="store_true", help="walk-forward weight tuning")
    ap.add_argument("--train", type=int, default=500)
    ap.add_argument("--test", type=int, default=250)
    ap.add_argument("--apply", action="store_true",
                    help="write calibrated_win_rate back to config")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--csv", help="backtest a local/URL OHLCV CSV (real data)")
    ap.add_argument("--htf-rule", default="W",
                    help="higher-timeframe resample rule for --csv (e.g. W, D, 4h)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    config = load_config(args.config)
    config.setdefault("signal", {})
    if args.tf:
        config["signal"]["entry_timeframe"] = args.tf
    if args.htf:
        config["signal"]["htf_timeframe"] = args.htf

    from src.signal.backtester import SignalBacktester

    bt = SignalBacktester(config)
    entry_tf = bt.engine.p["entry_timeframe"]
    htf_tf = bt.engine.p["htf_timeframe"]

    if args.csv:
        from src.signal.market_data import load_csv, resample_ohlcv

        entry_df = load_csv(args.csv, symbol=args.symbol)
        htf_df = resample_ohlcv(entry_df, args.htf_rule)
        htf_tf = args.htf_rule
    elif args.demo:
        from src.signal.market_data import generate_demo_ohlcv

        entry_df = generate_demo_ohlcv(bars=args.limit, seed=11, trend=0.0015,
                                       vol=0.013, freq="1h")
        htf_df = generate_demo_ohlcv(bars=args.limit // 4, seed=11, trend=0.0025,
                                     vol=0.013, freq="4h")
    else:
        from src.signal.market_data import MarketData

        md = MarketData(config)
        try:
            entry_df = md.fetch(args.symbol, entry_tf, args.limit)
            htf_df = md.fetch(args.symbol, htf_tf, max(200, args.limit // 4))
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Failed to fetch data:[/red] {e}")
            console.print("[dim]Tip: use --demo for an offline dry run.[/dim]")
            return

    console.print(f"[bold]Backtesting {args.symbol}[/bold] "
                  f"({entry_tf}/{htf_tf}, {len(entry_df)} candles)\n")

    if args.optimize:
        result = bt.walk_forward(entry_df, htf_df, train=args.train, test=args.test,
                                 risk_per_trade_pct=args.risk)
        if args.json:
            print(json.dumps(result, indent=2))
            return
        for i, w in enumerate(result["windows"], 1):
            console.print(f"[cyan]Window {i}[/cyan] test {w['test_range']} "
                          f"weights={w['chosen_weights']}")
            console.print(f"  OOS: {w['oos']['trades']} trades, "
                          f"WR {w['oos']['win_rate']*100:.1f}%, "
                          f"exp {w['oos']['expectancy_r']:+.3f}R, "
                          f"PF {w['oos']['profit_factor']:.2f}")
        console.print()
        render_metrics("Combined OUT-OF-SAMPLE", result["combined_oos"])
        cwr = result["calibrated_win_rate"]
        console.print(f"\n[bold]Calibrated win-rate (OOS):[/bold] {cwr}")
        if args.apply and cwr:
            _apply_calibration(args.config, cwr)
            console.print(f"[green]Wrote calibrated_win_rate={cwr} to {args.config}[/green]")
    else:
        m = bt.run(entry_df, htf_df, risk_per_trade_pct=args.risk)
        d = m.to_dict()
        if args.json:
            print(json.dumps(d, indent=2))
            return
        render_metrics("In-sample backtest (default weights)", d)
        console.print(
            "\n[dim]Use --optimize for walk-forward (out-of-sample) results — "
            "the honest number. In-sample alone overstates performance.[/dim]"
        )

    console.print(
        "\n[dim]Backtest results are historical and do not guarantee future "
        "performance. Account for fees, slippage and funding in live trading.[/dim]"
    )


if __name__ == "__main__":
    main()
