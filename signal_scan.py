#!/usr/bin/env python3
"""
Market scanner — find the coins/assets with the best setup right now.

Runs the signal engine across a whole universe and ranks the results, so instead
of checking one symbol at a time you see "what should I be looking at right now".

Examples:
  python signal_scan.py                       # live: top coins by volume (ccxt)
  python signal_scan.py --symbols BTCUSDT ETHUSDT SOLUSDT
  python signal_scan.py --csv-dir data/real --htf W   # scan a folder of CSVs
  python signal_scan.py --csv-dir data/real --only-enter --top 15
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich import box
from rich.console import Console
from rich.table import Table

console = Console()

DIR_STYLE = {"LONG": "green", "SHORT": "red", "NEUTRAL": "dim"}
DEC_STYLE = {"ENTER": "bold green", "WAIT": "yellow", "AVOID": "dim red"}


def load_config(path: str) -> dict:
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def render(rows, top: int) -> None:
    t = Table(title=f"Setup Scan — top {min(top, len(rows))} of {len(rows)}",
              box=box.ROUNDED)
    t.add_column("#", justify="right", style="dim")
    t.add_column("Symbol", style="cyan")
    t.add_column("Decision")
    t.add_column("Dir")
    t.add_column("Conf", justify="right")
    t.add_column("Price", justify="right")
    t.add_column("Entry", justify="right")
    t.add_column("Stop", justify="right")
    t.add_column("R:R", justify="right")
    t.add_column("EV(R)", justify="right")
    t.add_column("⚠", justify="right")

    for i, r in enumerate(rows[:top], 1):
        d = r.to_dict()
        t.add_row(
            str(i),
            d["symbol"],
            f"[{DEC_STYLE.get(d['decision'],'white')}]{d['decision']}[/]",
            f"[{DIR_STYLE.get(d['direction'],'white')}]{d['direction']}[/]",
            f"{d['confidence']}",
            f"{d['price']:g}",
            f"{d['entry']:g}" if d["entry"] else "-",
            f"{d['stop_loss']:g}" if d["stop_loss"] else "-",
            f"{d['blended_rr']:.2f}",
            f"{d['expected_value_r']:+.2f}",
            str(d["warnings"]) if d["warnings"] else "",
        )
    console.print(t)


def _render_portfolio(config, rows, account):
    from src.signal.portfolio import PortfolioRiskManager

    acct = account or config.get("signal", {}).get("account_size", 1000.0)
    plan = PortfolioRiskManager(config).allocate(rows, acct)
    if not plan.allocations:
        console.print("\n[yellow]Portfolio: no ENTER setups to allocate.[/yellow]")
        return
    t = Table(title=f"Portfolio Allocation (account {acct:g})", box=box.ROUNDED)
    t.add_column("Symbol", style="cyan")
    t.add_column("Dir")
    t.add_column("Risk%", justify="right")
    t.add_column("Risk$", justify="right")
    t.add_column("Size", justify="right")
    t.add_column("Notional", justify="right")
    t.add_column("Lev", justify="right")
    for a in plan.allocations:
        d = a.to_dict()
        t.add_row(d["symbol"], a.direction, f"{d['risk_pct']}", f"{d['risk_amount']:g}",
                  f"{d['size_units']:g}", f"{d['notional']:g}", f"{d['leverage']}x")
    console.print(t)
    console.print(
        f"[bold]Total heat[/bold] {plan.total_risk_pct:.2f}% "
        f"(long {plan.long_risk_pct:.2f}% / short {plan.short_risk_pct:.2f}%), "
        f"gross leverage {plan.gross_leverage:.1f}x"
    )
    for n in plan.notes:
        console.print(f"  [dim]• {n}[/dim]")


def _build_overview(rows, market_regime) -> dict:
    bull = sum(1 for r in rows if r.composite > 0.1)
    bear = sum(1 for r in rows if r.composite < -0.1)
    neutral = len(rows) - bull - bear
    decisions = {"ENTER": 0, "WAIT": 0, "AVOID": 0}
    for r in rows:
        decisions[r.decision] = decisions.get(r.decision, 0) + 1
    if bull > bear * 1.3:
        bias = "LONG-leaning"
    elif bear > bull * 1.3:
        bias = "SHORT-leaning"
    else:
        bias = "mixed / range"
    if market_regime is None:
        regime_label = "n/a"
    elif market_regime > 0:
        regime_label = "\U0001F7E2 Risk-ON (BTC above 200-EMA)"
    else:
        regime_label = "\U0001F534 Risk-OFF (BTC below 200-EMA)"
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "regime_label": regime_label,
        "bias": bias,
        "breadth": {"bullish": bull, "bearish": bear, "neutral": neutral, "total": len(rows)},
        "decisions": decisions,
    }


def _send_summary(config, scanner, rows, universe):
    from src.signal.notifier import TelegramNotifier

    market_regime = scanner._market_regime(universe) if universe else None
    overview = _build_overview(rows, market_regime)

    news = None
    try:
        na = scanner.engine.news_provider.assess("BTC")
        news = na.to_dict()
    except Exception:  # noqa: BLE001
        pass
    try:
        events = [e.to_dict() for e in scanner.engine.calendar.upcoming("BTC", within_hours=48)]
    except Exception:  # noqa: BLE001
        events = []

    msg = TelegramNotifier.format_market_summary(overview, rows[:5], news, events)
    sent = TelegramNotifier(config).send(msg)
    console.print(f"[dim]Telegram summary: {'sent' if sent else 'dry-run/not configured'}[/dim]")


def main():
    ap = argparse.ArgumentParser(description="Signal market scanner")
    ap.add_argument("--config", "-c", default="config/config.yaml")
    ap.add_argument("--symbols", nargs="*", help="explicit symbols (live mode)")
    ap.add_argument("--csv-dir", help="scan a directory of OHLCV CSVs")
    ap.add_argument("--csv-universe", help="scan a single multi-symbol CSV")
    ap.add_argument("--htf", default="4h", help="higher-timeframe resample rule for CSV mode")
    ap.add_argument("--tf")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--only-enter", action="store_true", help="show only ENTER setups")
    ap.add_argument("--portfolio", action="store_true",
                    help="build a portfolio risk allocation across the ENTER setups")
    ap.add_argument("--notify", action="store_true",
                    help="send a Telegram alert summarising ENTER setups")
    ap.add_argument("--summary", action="store_true",
                    help="send a daily market summary (regime, breadth, news, events) every run")
    ap.add_argument("--account", type=float)
    ap.add_argument("--risk", type=float)
    ap.add_argument("--news", action="store_true", help="enable news overlay (slower)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    config = load_config(args.config)
    config.setdefault("signal", {})
    if args.tf:
        config["signal"]["entry_timeframe"] = args.tf

    from src.signal.scanner import Scanner

    scanner = Scanner(config)
    universe = None

    if args.csv_dir or args.csv_universe:
        from src.signal.market_data import load_csv_dir, load_csv_universe

        if args.csv_dir:
            universe = load_csv_dir(args.csv_dir)
            console.print(f"[dim]Loaded {len(universe)} symbols from {args.csv_dir}[/dim]")
        else:
            universe = load_csv_universe(args.csv_universe)
            console.print(f"[dim]Loaded {len(universe)} symbols from {args.csv_universe}[/dim]")
        rows = scanner.scan_universe(
            universe, htf_rule=args.htf, use_news=args.news,
            account_size=args.account, risk_per_trade_pct=args.risk,
        )
    else:
        try:
            rows = scanner.scan_live(
                symbols=args.symbols, use_news=args.news,
                account_size=args.account, risk_per_trade_pct=args.risk,
            )
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Live scan failed:[/red] {e}")
            console.print("[dim]Exchange APIs may be unreachable here. Use "
                          "--csv-dir data/real to scan committed real data.[/dim]")
            return

    if args.only_enter:
        rows = [r for r in rows if r.decision == "ENTER"]

    # Save report
    reports_dir = Path(config.get("output", {}).get("reports_dir", "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"scan_{stamp}.json"
    out_path.write_text(
        json.dumps([r.to_dict() for r in rows], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if args.json:
        print(json.dumps([r.to_dict() for r in rows[: args.top]], indent=2, ensure_ascii=False))
    else:
        if not rows:
            console.print("[yellow]No setups found.[/yellow]")
        else:
            render(rows, args.top)
            enters = sum(1 for r in rows if r.decision == "ENTER")
            console.print(f"\n[bold]{enters}[/bold] ENTER setups found. "
                          f"[dim]Saved → {out_path}[/dim]")
            if args.portfolio:
                _render_portfolio(config, rows, args.account)

    if args.notify and any(r.decision == "ENTER" for r in rows):
        from src.signal.notifier import TelegramNotifier

        plan = None
        if args.portfolio:
            from src.signal.portfolio import PortfolioRiskManager
            acct = args.account or config.get("signal", {}).get("account_size", 1000.0)
            plan = PortfolioRiskManager(config).allocate(rows, acct)
        tg = TelegramNotifier(config)
        sent = tg.send(TelegramNotifier.format_scan(rows, plan))
        console.print(f"[dim]Telegram: {'sent' if sent else 'dry-run/not configured'}[/dim]")

    if args.summary and rows:
        _send_summary(config, scanner, rows, universe)

    console.print(
        "\n[dim]Ranked by setup quality (confluence + R:R + EV), not by who is "
        "pumping hardest. Decision-support only — manage your own risk.[/dim]"
    )


if __name__ == "__main__":
    main()
