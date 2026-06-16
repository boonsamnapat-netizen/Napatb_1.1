#!/usr/bin/env python3
"""
Live crypto signal generator.

Examples:
  python signal_cli.py BTCUSDT
  python signal_cli.py ETHUSDT --tf 1h --htf 4h --account 5000 --risk 1.5
  python signal_cli.py SOLUSDT --headlines "SEC approves SOL ETF" "Solana TVL hits ATH"
  python signal_cli.py BTCUSDT --demo        # offline, synthetic data

Outputs a full plan (entry / stop / take-profits / position size / risk / news)
and saves a JSON report under reports/.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
logger = logging.getLogger("signal")


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


DECISION_STYLE = {
    "ENTER": "bold green",
    "WAIT": "bold yellow",
    "AVOID": "bold red",
}
DIR_STYLE = {"LONG": "green", "SHORT": "red", "NEUTRAL": "yellow"}


def render(sig) -> None:
    d = sig.to_dict()
    dec = d["decision"]
    direction = d["direction"]

    header = (
        f"[{DIR_STYLE.get(direction, 'white')}]{direction}[/] "
        f"[{DECISION_STYLE.get(dec, 'white')}]→ {dec}[/]   "
        f"confidence [bold]{d['confidence']}[/]/100"
    )
    console.print(
        Panel(
            header,
            title=f"{d['symbol']}  ({d['entry_timeframe']} / {d['htf_timeframe']})",
            box=box.DOUBLE,
        )
    )

    # Plan table
    if d["entry"]:
        t = Table(title="Trade Plan", box=box.ROUNDED, show_header=True)
        t.add_column("Field", style="cyan")
        t.add_column("Value", style="white")
        t.add_row("Current price", f"{d['current_price']:g}")
        t.add_row("Entry", f"{d['entry']:g}  (zone {d['entry_zone']})")
        t.add_row("Stop loss", f"[red]{d['stop_loss']:g}[/]")
        pp = d["position_plan"]
        for tp in pp.get("take_profits", []):
            t.add_row(
                tp["label"] or "TP",
                f"[green]{tp['price']:g}[/]  ({tp['r_multiple']}R, "
                f"close {tp['allocation_pct']}%)",
            )
        t.add_row("─" * 14, "─" * 30)
        t.add_row("Account", f"{pp.get('account_size'):g}")
        t.add_row("Risk / trade", f"{pp.get('risk_per_trade_pct')}%  (~{pp.get('risk_amount')})")
        t.add_row("Stop distance", f"{pp.get('stop_distance_pct')}%")
        t.add_row("Position size", f"{pp.get('position_size_units')} units")
        t.add_row("Notional", f"{pp.get('position_value')}")
        t.add_row("Suggested leverage", f"{pp.get('suggested_leverage')}x")
        t.add_row("Blended R:R", f"{pp.get('blended_rr')}")
        t.add_row("Expected value", f"{pp.get('expected_value_r')}R "
                                    f"(assumed WR {pp.get('assumed_win_rate')})")
        console.print(t)
    else:
        console.print(Panel("No active trade plan — standing aside.", style="yellow"))

    # Indicator snapshot
    it = Table(title="Indicator Snapshot", box=box.SIMPLE)
    it.add_column("TF", style="cyan")
    for col in ("price", "rsi", "macd_hist", "stoch_k", "adx", "bb_pct_b", "rvol"):
        it.add_column(col, justify="right")
    for tf, snap in d["indicators"].items():
        it.add_row(
            tf,
            f"{snap.get('price')}",
            f"{snap.get('rsi')}",
            f"{snap.get('macd_hist')}",
            f"{snap.get('stoch_k')}",
            f"{snap.get('adx')}",
            f"{snap.get('bb_pct_b')}",
            f"{snap.get('rvol')}",
        )
    console.print(it)

    # Rationale
    if d["rationale"]:
        console.print("\n[bold]Why:[/bold]")
        for line in d["rationale"]:
            console.print(f"  • {line}")

    # News
    news = d.get("news", {})
    if news.get("summary"):
        console.print(
            f"\n[bold]News:[/bold] {news.get('summary')} "
            f"(sentiment {news.get('sentiment_score', 0)}, "
            f"impact {'YES' if news.get('high_impact_event') else 'no'})"
        )

    # Warnings
    if d["warnings"]:
        console.print("\n[bold red]Warnings:[/bold red]")
        for w in d["warnings"]:
            console.print(f"  ! {w}")

    if d.get("thesis"):
        console.print(Panel(d["thesis"], title="AI Thesis", box=box.ROUNDED))

    console.print(
        "\n[dim]Decision-support only. No signal guarantees profit; "
        "manage your risk and trade your own plan.[/dim]\n"
    )


def main():
    ap = argparse.ArgumentParser(description="Live crypto signal generator")
    ap.add_argument("symbol", help="e.g. BTCUSDT, ETH/USDT, SOL")
    ap.add_argument("--config", "-c", default="config/config.yaml")
    ap.add_argument("--tf", help="entry timeframe (overrides config)")
    ap.add_argument("--htf", help="higher timeframe (overrides config)")
    ap.add_argument("--account", type=float, help="account size for MM")
    ap.add_argument("--risk", type=float, help="risk %% per trade")
    ap.add_argument("--limit", type=int, default=400, help="candles to fetch")
    ap.add_argument("--headlines", nargs="*", help="manual news headlines")
    ap.add_argument("--no-news", action="store_true", help="skip news overlay")
    ap.add_argument("--demo", action="store_true", help="use synthetic offline data")
    ap.add_argument("--notify", action="store_true", help="send a Telegram alert (on ENTER)")
    ap.add_argument("--notify-all", action="store_true",
                    help="with --notify, send regardless of decision")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    config = load_config(args.config)
    config.setdefault("signal", {})
    if args.tf:
        config["signal"]["entry_timeframe"] = args.tf
    if args.htf:
        config["signal"]["htf_timeframe"] = args.htf

    from src.signal.signal_engine import SignalEngine

    engine = SignalEngine(config)
    entry_tf = engine.p["entry_timeframe"]
    htf_tf = engine.p["htf_timeframe"]

    if args.demo:
        from src.signal.market_data import generate_demo_ohlcv

        entry_df = generate_demo_ohlcv(
            bars=args.limit, seed=3, trend=0.004, vol=0.010, freq="1h"
        )
        htf_df = generate_demo_ohlcv(
            bars=args.limit // 4, seed=3, trend=0.006, vol=0.010, freq="4h"
        )
    else:
        from src.signal.market_data import MarketData

        md = MarketData(config)
        try:
            entry_df = md.fetch(args.symbol, entry_tf, args.limit)
            htf_df = md.fetch(args.symbol, htf_tf, max(120, args.limit // 4))
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Failed to fetch market data:[/red] {e}")
            console.print("[dim]Tip: try --demo for an offline dry run.[/dim]")
            sys.exit(1)

    sig = engine.analyze(
        symbol=args.symbol,
        entry_df=entry_df,
        htf_df=htf_df,
        manual_headlines=args.headlines,
        account_size=args.account,
        risk_per_trade_pct=args.risk,
        use_news=not args.no_news,
    )

    # Save report
    reports_dir = Path(config.get("output", {}).get("reports_dir", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_sym = args.symbol.replace("/", "")
    out_path = reports_dir / f"signal_{safe_sym}_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sig.to_dict(), f, indent=2, ensure_ascii=False)

    if args.json:
        print(json.dumps(sig.to_dict(), indent=2, ensure_ascii=False))
    else:
        render(sig)
        console.print(f"[dim]Saved report → {out_path}[/dim]")

    # Telegram alert
    if args.notify:
        from src.signal.notifier import TelegramNotifier

        notify_on = config.get("signal", {}).get("telegram", {}).get("notify_on", "ENTER")
        if args.notify_all or sig.decision == notify_on:
            tg = TelegramNotifier(config)
            sent = tg.send(TelegramNotifier.format_signal(sig))
            console.print(f"[dim]Telegram: {'sent' if sent else 'dry-run/not configured'}[/dim]")


if __name__ == "__main__":
    main()
