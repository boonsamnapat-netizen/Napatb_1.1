#!/usr/bin/env python3
"""Performance report — closes the feedback loop for the Napatb signal system.

Runs the walk-forward backtest across the CSV universe, grades the live
forward-test log (ENTER signals actually pushed to Telegram), computes honest
net-of-fees analytics, and writes a self-contained HTML dashboard (+ JSON +
PNGs). Optionally pushes a Thai weekly scorecard to Telegram.

Everything runs offline on committed CSVs — no exchange access needed.

Examples:
  python signal_report.py --csv-dir data/real/crypto --htf-rule W
  python signal_report.py --csv-dir data/real/crypto --htf-rule W --notify
  python signal_report.py --csv-dir data/real/crypto --symbols BTCUSDT,ETHUSDT
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
from datetime import datetime, timezone

import yaml

from src.signal import analytics, dashboard


def load_config(path: str) -> dict:
    p = pathlib.Path(path)
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Performance analytics dashboard")
    ap.add_argument("--config", "-c", default="config/config.yaml")
    ap.add_argument("--csv-dir", default="data/real/crypto",
                    help="folder of committed OHLCV CSVs (1d)")
    ap.add_argument("--htf-rule", default="W",
                    help="higher-timeframe resample rule (W, D, 4h…)")
    ap.add_argument("--symbols", help="comma-separated subset (default: all in --csv-dir)")
    ap.add_argument("--train", type=int, default=500)
    ap.add_argument("--test", type=int, default=250)
    ap.add_argument("--min-bars", type=int, default=300)
    ap.add_argument("--out-dir", default="reports")
    ap.add_argument("--log-path", default="data/signals_log.json",
                    help="forward-test log to grade + track")
    ap.add_argument("--no-png", action="store_true", help="skip matplotlib PNGs")
    ap.add_argument("--notify", action="store_true", help="push Thai scorecard to Telegram")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING))
    config = load_config(args.config)
    config.setdefault("signal", {})
    risk_pct = float(config["signal"].get("risk_per_trade_pct", 2.0))

    from src.signal.backtester import SignalBacktester
    from src.signal.market_data import load_csv_dir, resample_ohlcv

    frames = load_csv_dir(args.csv_dir, min_bars=args.min_bars)
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",")}
        frames = {k: v for k, v in frames.items() if k.upper() in wanted}
    if not frames:
        print(f"No CSVs found in {args.csv_dir}")
        return 1

    bt = SignalBacktester(config)
    all_trades: list[dict] = []
    print(f"Scanning {len(frames)} symbols (walk-forward, net of fees)…")
    for sym, df in sorted(frames.items()):
        try:
            htf = resample_ohlcv(df, args.htf_rule)
            _res, trades = bt.walk_forward_collect(
                df, htf, train=args.train, test=args.test,
                risk_per_trade_pct=risk_pct, symbol=sym,
            )
            all_trades.extend(trades)
            print(f"  {sym:<10} {len(trades):>4} OOS trades")
        except Exception as e:  # noqa: BLE001
            print(f"  {sym:<10} skipped ({e})")

    if not all_trades:
        print("No trades produced — nothing to report.")
        return 1

    # Grade the live forward-test log against the same committed OHLC, then track it.
    forward_summary = None
    try:
        from src.signal import signal_log
        closed = signal_log.update_outcomes(args.csv_dir, path=args.log_path)
        if closed:
            print(f"Graded {closed} forward-test signal(s).")
        forward_summary = signal_log.summary(path=args.log_path)
    except Exception as e:  # noqa: BLE001
        print(f"(forward-test log unavailable: {e})")

    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = analytics.build_report(
        all_trades, risk_per_trade_pct=risk_pct,
        forward_summary=forward_summary, generated_at=gen,
    )

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / "performance.html"
    json_path = out / "performance.json"
    html_path.write_text(dashboard.render_html(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {html_path}")
    print(f"Wrote {json_path}")

    pngs: list[str] = []
    if not args.no_png:
        pngs = dashboard.save_pngs(report, str(out))
        for p in pngs:
            print(f"Wrote {p}")

    s = report["summary"]
    print(f"\n=== OOS across {len(frames)} coins ===")
    print(f"  {s['trades']} trades · WR {s['win_rate']*100:.1f}% · "
          f"exp {s['expectancy_r']:+.3f}R · total {s['total_r']:+.1f}R · "
          f"PF {s.get('profit_factor')} · maxDD {s['max_drawdown_r']:.1f}R")

    if args.notify:
        _notify(config, report, pngs)

    return 0


def _notify(config: dict, report: dict, pngs: list[str]) -> None:
    try:
        from src.signal.notifier import TelegramNotifier
    except Exception as e:  # noqa: BLE001
        print(f"Telegram unavailable: {e}")
        return
    notifier = TelegramNotifier(config)
    text = TelegramNotifier.format_performance_scorecard(report)
    if pngs:
        notifier.send_photo(pngs[0], caption=text)
        for extra in pngs[1:]:
            notifier.send_photo(extra, caption="")
    else:
        notifier.send(text)
    print("Sent Telegram scorecard.")


if __name__ == "__main__":
    raise SystemExit(main())
