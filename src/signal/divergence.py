"""Regular divergence detection (RSI / MACD) + overbought/oversold status.

Regular bullish divergence: price prints a LOWER low while the oscillator
prints a HIGHER low -> downside momentum fading, reversal-up bias.
Regular bearish divergence: price prints a HIGHER high while the oscillator
prints a LOWER high -> upside momentum fading, reversal-down bias.

We confirm pivots with a symmetric fractal window, so the most recent pivot is
only "known" once `pivot_window` bars have closed after it. That avoids
repainting on the live (forming) bar.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators

# RSI thresholds.
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
# MACD has no fixed bounds: judge against its own recent range (percentile).
MACD_LOOKBACK = 100
MACD_OB_PCT = 0.80
MACD_OS_PCT = 0.20


@dataclass
class Divergence:
    kind: str            # "bullish" | "bearish"
    indicator: str       # "RSI" | "MACD"
    status: str          # e.g. "MACD Oversold", "RSI Overbought", "MACD Neutral"
    price_prev: float
    price_last: float
    osc_prev: float
    osc_last: float
    idx_prev: pd.Timestamp
    idx_last: pd.Timestamp
    swing_low: float     # protective level for longs (recent pivot low)
    swing_high: float    # protective level for shorts (recent pivot high)


def _pivot_lows(low: pd.Series, window: int) -> list[int]:
    """Indices of confirmed fractal pivot lows."""
    vals = low.values
    out: list[int] = []
    for i in range(window, len(vals) - window):
        seg = vals[i - window : i + window + 1]
        if vals[i] == seg.min() and (seg == vals[i]).sum() == 1:
            out.append(i)
    return out


def _pivot_highs(high: pd.Series, window: int) -> list[int]:
    vals = high.values
    out: list[int] = []
    for i in range(window, len(vals) - window):
        seg = vals[i - window : i + window + 1]
        if vals[i] == seg.max() and (seg == vals[i]).sum() == 1:
            out.append(i)
    return out


def _osc_status(name: str, osc: pd.Series, i: int) -> str:
    """Overbought / oversold / neutral label at bar i for the oscillator."""
    val = osc.iloc[i]
    if name == "RSI":
        if val >= RSI_OVERBOUGHT:
            return "RSI Overbought"
        if val <= RSI_OVERSOLD:
            return "RSI Oversold"
        return "RSI Neutral"
    # MACD: percentile rank within the trailing window.
    lo = max(0, i - MACD_LOOKBACK)
    ref = osc.iloc[lo : i + 1]
    if len(ref) >= 10:
        rank = (ref < val).mean()
        if rank >= MACD_OB_PCT:
            return "MACD Overbought"
        if rank <= MACD_OS_PCT:
            return "MACD Oversold"
    return "MACD Neutral"


def _scan(
    df: pd.DataFrame,
    osc: pd.Series,
    indicator: str,
    window: int,
    max_gap: int,
) -> Divergence | None:
    """Look for a regular divergence on the two most recent confirmed pivots."""
    lows = _pivot_lows(df["low"], window)
    highs = _pivot_highs(df["high"], window)

    bull = None
    if len(lows) >= 2:
        p, l = lows[-2], lows[-1]
        if 0 < (l - p) <= max_gap:
            price_p, price_l = df["low"].iloc[p], df["low"].iloc[l]
            osc_p, osc_l = osc.iloc[p], osc.iloc[l]
            # price lower low, oscillator higher low
            if price_l < price_p and osc_l > osc_p:
                bull = Divergence(
                    kind="bullish",
                    indicator=indicator,
                    status=_osc_status(indicator, osc, l),
                    price_prev=float(price_p),
                    price_last=float(price_l),
                    osc_prev=float(osc_p),
                    osc_last=float(osc_l),
                    idx_prev=df.index[p],
                    idx_last=df.index[l],
                    swing_low=float(price_l),
                    swing_high=float(df["high"].iloc[p:].max()),
                )

    bear = None
    if len(highs) >= 2:
        p, h = highs[-2], highs[-1]
        if 0 < (h - p) <= max_gap:
            price_p, price_h = df["high"].iloc[p], df["high"].iloc[h]
            osc_p, osc_h = osc.iloc[p], osc.iloc[h]
            # price higher high, oscillator lower high
            if price_h > price_p and osc_h < osc_p:
                bear = Divergence(
                    kind="bearish",
                    indicator=indicator,
                    status=_osc_status(indicator, osc, h),
                    price_prev=float(price_p),
                    price_last=float(price_h),
                    osc_prev=float(osc_p),
                    osc_last=float(osc_h),
                    idx_prev=df.index[p],
                    idx_last=df.index[h],
                    swing_low=float(df["low"].iloc[p:].min()),
                    swing_high=float(price_h),
                )

    # Return the most recent of the two (closest pivot to "now").
    candidates = [d for d in (bull, bear) if d is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.idx_last)


def detect(
    df: pd.DataFrame,
    indicator: str = "RSI",
    pivot_window: int = 5,
    max_gap: int = 90,
    rsi_period: int = 14,
) -> Divergence | None:
    """Detect the most recent regular divergence.

    indicator: "RSI", "MACD", or "auto" (prefer the one that is OB/OS).
    """
    indicator = indicator.upper()
    osc_rsi = indicators.rsi(df["close"], rsi_period)
    osc_macd = indicators.macd(df["close"])["macd"]

    if indicator == "RSI":
        return _scan(df, osc_rsi, "RSI", pivot_window, max_gap)
    if indicator == "MACD":
        return _scan(df, osc_macd, "MACD", pivot_window, max_gap)

    # auto: take whichever fired most recently, preferring an OB/OS confirmation.
    found = [
        d
        for d in (
            _scan(df, osc_rsi, "RSI", pivot_window, max_gap),
            _scan(df, osc_macd, "MACD", pivot_window, max_gap),
        )
        if d is not None
    ]
    if not found:
        return None
    confirmed = [d for d in found if not d.status.endswith("Neutral")]
    pool = confirmed or found
    return max(pool, key=lambda d: d.idx_last)
