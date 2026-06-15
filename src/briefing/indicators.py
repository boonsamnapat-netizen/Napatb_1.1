"""
Lightweight technical context for a single symbol's daily OHLCV series.

No TA library dependency — just pandas. Produces the compact numeric snapshot
the briefing feeds to Claude (and renders as a fallback table).
"""

from typing import Optional

import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0 or pd.isna(last_loss):
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return round(100 - (100 / (1 + rs)), 1)


def _pct(a: float, b: float) -> Optional[float]:
    if b in (0, None) or pd.isna(b):
        return None
    return round((a - b) / b * 100, 2)


def compute_context(symbol: str, df: pd.DataFrame) -> dict:
    """Return a snapshot dict of trend/momentum/range context for one symbol."""
    if df is None or df.empty or len(df) < 2:
        return {"symbol": symbol, "error": "no data"}

    close = df["close"]
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else None
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    window_52w = close.tail(252)
    hi_52w = float(window_52w.max())
    lo_52w = float(window_52w.min())

    vol = df["volume"]
    avg_vol20 = vol.rolling(20).mean().iloc[-1] if len(vol) >= 20 else None
    vol_ratio = (
        round(float(vol.iloc[-1]) / float(avg_vol20), 2)
        if avg_vol20 and avg_vol20 > 0 else None
    )

    snap = {
        "symbol": symbol,
        "last": round(last, 2),
        "chg_1d_pct": _pct(last, prev),
        "chg_5d_pct": _pct(last, float(close.iloc[-6])) if len(close) >= 6 else None,
        "chg_20d_pct": _pct(last, float(close.iloc[-21])) if len(close) >= 21 else None,
        "vs_sma20_pct": _pct(last, float(sma20)) if sma20 is not None else None,
        "vs_sma50_pct": _pct(last, float(sma50)) if sma50 is not None else None,
        "vs_sma200_pct": _pct(last, float(sma200)) if sma200 is not None else None,
        "pct_off_52w_high": _pct(last, hi_52w),
        "pct_above_52w_low": _pct(last, lo_52w),
        "rsi14": _rsi(close),
        "vol_vs_avg20": vol_ratio,
    }

    # Derived tags that make the digest scannable.
    tags = []
    if snap["pct_off_52w_high"] is not None and snap["pct_off_52w_high"] >= -2:
        tags.append("near 52w high")
    if snap["pct_above_52w_low"] is not None and snap["pct_above_52w_low"] <= 5:
        tags.append("near 52w low")
    if snap["chg_1d_pct"] is not None and abs(snap["chg_1d_pct"]) >= 4:
        tags.append("big move")
    if vol_ratio is not None and vol_ratio >= 2:
        tags.append("volume spike")
    if snap["rsi14"] is not None and snap["rsi14"] >= 70:
        tags.append("overbought")
    if snap["rsi14"] is not None and snap["rsi14"] <= 30:
        tags.append("oversold")
    if (
        snap["vs_sma50_pct"] is not None and snap["vs_sma200_pct"] is not None
        and snap["vs_sma50_pct"] > 0 and snap["vs_sma200_pct"] > 0
    ):
        tags.append("uptrend")
    snap["tags"] = tags
    return snap


def attention_score(snap: dict) -> float:
    """Rank how much a symbol deserves attention today (higher = more)."""
    if snap.get("error"):
        return -1.0
    score = 0.0
    score += abs(snap.get("chg_1d_pct") or 0) * 1.5
    if snap.get("vol_vs_avg20"):
        score += max(0, snap["vol_vs_avg20"] - 1) * 3
    if snap.get("pct_off_52w_high") is not None and snap["pct_off_52w_high"] >= -2:
        score += 4
    if snap.get("rsi14") is not None and (snap["rsi14"] >= 70 or snap["rsi14"] <= 30):
        score += 3
    score += len(snap.get("tags", []))
    return round(score, 2)
