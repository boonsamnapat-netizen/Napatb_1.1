#!/usr/bin/env python3
"""Seed data/signals_log.json from the AUTHORITATIVE list of signals that the
daily workflow actually pushed to Telegram (read from the run logs).

Entry/SL/TP are reproduced by running the engine on committed end-of-day data
sliced to each signal's date. The live runs used the still-forming current-day
bar (and yfinance later revised bars), so reproduced entries can differ from the
literally-sent value by a few percent — good enough for outcome tracking, and
disclosed as such. Confidence is taken from the logs (exact).

Future signals are logged exactly (in-job) by signal_scan.py — no reproduction.
"""
import json, pathlib
import pandas as pd, yaml
from src.signal.signal_engine import SignalEngine
from src.signal import signal_log

# (date, symbol, direction, confidence-as-sent) — from the workflow scan logs
SENT = [
    ("2026-06-20", "AVAXUSDT", "SHORT", 58.7),
    ("2026-06-25", "DOGEUSDT", "SHORT", 60.1),
    ("2026-06-26", "XRPUSDT",  "SHORT", 63.7),
    ("2026-06-26", "DOGEUSDT", "SHORT", 59.7),
    ("2026-06-26", "DOTUSDT",  "SHORT", 55.2),
]
CSV_DIR = "data/real/crypto"
PATH = signal_log.DEFAULT_PATH

cfg = yaml.safe_load(open("config/config.yaml"))
eng = SignalEngine(cfg.get("signal", {}))

data = {"signals": []}
for date, sym, direction, conf in SENT:
    df = pd.read_csv(f"{CSV_DIR}/{sym}.csv", index_col=0, parse_dates=True)
    df.columns = [c.lower() for c in df.columns]
    sl = df[df.index <= date]
    htf = sl.resample("W").agg({"open": "first", "high": "max", "low": "min",
                                "close": "last", "volume": "sum"}).dropna()
    sig = eng.analyze(sym, sl, htf, use_news=False,
                      account_size=100.0, risk_per_trade_pct=2.0).to_dict()
    plan = sig.get("position_plan") or {}
    data["signals"].append({
        "date": date, "symbol": sym, "direction": direction,
        "confidence": conf,                       # exact, from the live log
        "entry": round(sig.get("entry") or 0, 8),
        "stop": round(sig.get("stop_loss") or 0, 8),
        "tps": [round(t["price"], 8) for t in plan.get("take_profits", [])],
        "entry_note": "reproduced end-of-day (live used forming bar)",
        "status": "open", "exit": None, "result_r": None, "closed_date": None,
        "logged_at": date + "T01:00:00+00:00",
    })

pathlib.Path(PATH).parent.mkdir(parents=True, exist_ok=True)
pathlib.Path(PATH).write_text(json.dumps(data, indent=2, ensure_ascii=False))
graded = signal_log.update_outcomes(CSV_DIR)
print(f"Seeded {len(data['signals'])} sent signals, {graded} graded.")
print("Summary:", json.dumps(signal_log.summary(), ensure_ascii=False))
