#!/usr/bin/env python3
"""
Send a SAMPLE ENTER signal to Telegram so you can preview what a real alert looks
like (used by the auto_scan_alert workflow's `sample_signal` input). The numbers
are illustrative — this is NOT a live trade signal.
"""

from datetime import datetime, timezone

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import yaml

from src.signal.notifier import TelegramNotifier
from src.signal.signal_engine import Signal


def build_sample() -> Signal:
    entry, sl = 65000.0, 63200.0
    risk = entry - sl
    account, risk_pct = 1000.0, 1.0
    risk_amount = account * risk_pct / 100
    size = risk_amount / risk
    tps = [
        {"price": 67700, "r_multiple": 1.5, "allocation_pct": 50, "label": "TP1 (de-risk)"},
        {"price": 69500, "r_multiple": 2.5, "allocation_pct": 30, "label": "TP2"},
        {"price": 72200, "r_multiple": 4.0, "allocation_pct": 20, "label": "TP3 (runner)"},
    ]
    blended = sum(t["r_multiple"] * t["allocation_pct"] for t in tps) / 100
    sig = Signal(
        symbol="BTCUSDT", entry_timeframe="4h", htf_timeframe="1d",
        generated_at=datetime.now(timezone.utc).isoformat(),
        direction="LONG", decision="ENTER", confidence=61.5,
        current_price=entry, entry=entry, entry_zone=[64600.0, 65000.0], stop_loss=sl,
    )
    sig.position_plan = {
        "take_profits": tps, "risk_per_trade_pct": 1.0, "risk_amount": round(risk_amount, 2),
        "position_size_units": round(size, 8), "suggested_leverage": 1.0,
        "blended_rr": round(blended, 2), "expected_value_r": 0.72,
    }
    return sig


def main():
    cfg = yaml.safe_load(open("config/config.yaml"))
    tg = TelegramNotifier(cfg)
    body = "🧪 ตัวอย่างสัญญาณ (ไม่ใช่สัญญาณจริง)\n\n" + \
        TelegramNotifier.format_signal(build_sample())
    ok = tg.send(body)
    print("configured & sent" if ok else "DRY-RUN: secrets not set (or send failed)")


if __name__ == "__main__":
    main()
