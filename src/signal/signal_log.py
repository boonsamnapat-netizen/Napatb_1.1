"""Persistent log of the ENTER signals the system actually pushes (e.g. Telegram).

Every ENTER from a scan is appended once (dedup by date+symbol). Outcomes are
graded from later OHLC by simple first-touch: SL vs TP1 (if a bar spans both,
assume SL first — conservative). This is the forward-test record to compare
against the walk-forward backtest expectation.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

DEFAULT_PATH = "data/signals_log.json"


def _load(path: str) -> dict:
    p = pathlib.Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"signals": []}


def _save(path: str, data: dict) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _tp_prices(sig_dict: dict) -> list[float]:
    plan = sig_dict.get("position_plan") or {}
    return [t["price"] for t in plan.get("take_profits", []) if t.get("price")]


def append_enters(rows, date_str: str, path: str = DEFAULT_PATH) -> int:
    """Append ENTER signals for `date_str`; skip ones already logged. Returns #added."""
    data = _load(path)
    seen = {(s["date"], s["symbol"]) for s in data["signals"]}
    added = 0
    for r in rows:
        d = r.to_dict()
        if d.get("decision") != "ENTER":
            continue
        key = (date_str, d["symbol"])
        if key in seen:
            continue
        # Scanner rows drop `signal` from to_dict(), so the position plan (and
        # therefore the take-profits) only lives on the underlying Signal. Without
        # it every logged signal would have no TP and could only ever close as SL.
        plan_src = d
        sig_obj = getattr(r, "signal", None)
        if sig_obj is not None and hasattr(sig_obj, "to_dict"):
            plan_src = sig_obj.to_dict()
        data["signals"].append({
            "date": date_str,
            "symbol": d["symbol"],
            "direction": d["direction"],
            "confidence": d.get("confidence"),
            "entry": d.get("entry"),
            "stop": d.get("stop_loss"),
            "tps": _tp_prices(plan_src),
            "status": "open",
            "exit": None,
            "result_r": None,
            "closed_date": None,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        })
        seen.add(key)
        added += 1
    if added:
        _save(path, data)
    return added


def _grade(sig: dict, df) -> tuple[str, float, str] | None:
    """First-touch outcome from bars strictly after the signal date.

    Returns (status, result_r, closed_date) or None if still open.
    """
    entry, stop = sig.get("entry"), sig.get("stop")
    tps = sig.get("tps") or []
    if not entry or not stop:
        return None
    tp1 = tps[0] if tps else None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    short = sig["direction"] == "SHORT"
    after = df[df.index > sig["date"]]
    for ts, bar in after.iterrows():
        hi, lo = bar["high"], bar["low"]
        sl_hit = hi >= stop if short else lo <= stop
        tp_hit = (lo <= tp1 if short else hi >= tp1) if tp1 else False
        if sl_hit:  # conservative: SL first if a bar spans both
            return "SL", round((-risk) / risk, 3), ts.strftime("%Y-%m-%d")
        if tp_hit:
            move = (entry - tp1) if short else (tp1 - entry)
            return "TP1", round(move / risk, 3), ts.strftime("%Y-%m-%d")
    return None


def update_outcomes(csv_dir: str, path: str = DEFAULT_PATH) -> int:
    """Grade still-open signals against committed OHLC. Returns #closed this run."""
    import pandas as pd

    data = _load(path)
    closed = 0
    cache: dict = {}
    for sig in data["signals"]:
        if sig["status"] != "open":
            continue
        sym = sig["symbol"]
        if sym not in cache:
            f = pathlib.Path(csv_dir) / f"{sym}.csv"
            if not f.exists():
                cache[sym] = None
            else:
                df = pd.read_csv(f, index_col=0, parse_dates=True)
                df.columns = [c.lower() for c in df.columns]
                cache[sym] = df
        df = cache[sym]
        if df is None:
            continue
        graded = _grade(sig, df)
        if graded:
            status, r, cdate = graded
            sig.update(status=status, result_r=r, closed_date=cdate,
                       exit=(sig["stop"] if status == "SL" else (sig["tps"] or [None])[0]))
            closed += 1
    if closed:
        _save(path, data)
    return closed


def summary(path: str = DEFAULT_PATH) -> dict:
    data = _load(path)
    sigs = data["signals"]
    closed = [s for s in sigs if s["status"] in ("SL", "TP1") and s["result_r"] is not None]
    wins = [s for s in closed if s["result_r"] > 0]
    total_r = sum(s["result_r"] for s in closed)
    return {
        "total": len(sigs),
        "open": sum(s["status"] == "open" for s in sigs),
        "closed": len(closed),
        "wins": len(wins),
        "win_rate": round(len(wins) / len(closed), 3) if closed else None,
        "total_r": round(total_r, 3),
        "avg_r": round(total_r / len(closed), 3) if closed else None,
    }
