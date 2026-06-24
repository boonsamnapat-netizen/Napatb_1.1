"""Technical indicators used by the divergence engine.

Pure pandas/numpy, no network. Each function takes a price Series/DataFrame
and returns aligned Series so callers can attach them straight onto OHLCV
frames.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (0-100)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    out = 100 - (100 / (1 + rs))
    # When avg_loss is 0 the asset only went up -> RSI 100.
    return out.fillna(100.0)


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD line, signal line and histogram."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": hist}
    )


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range, expects columns: high, low, close."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """Supertrend line + direction (+1 uptrend / -1 downtrend).

    Causal: bar i depends only on data up to i. Returns columns
    'supertrend' (the active band) and 'dir'.
    """
    atr_ = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0
    upper = hl2 + mult * atr_
    lower = hl2 - mult * atr_

    close = df["close"].to_numpy()
    up = upper.to_numpy()
    lo = lower.to_numpy()
    n = len(df)
    final_up = np.full(n, np.nan)
    final_lo = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)

    for i in range(n):
        if i == 0:
            final_up[i] = up[i]
            final_lo[i] = lo[i]
            direction[i] = 1
            continue
        # carry the tighter band unless price closes through it
        final_up[i] = up[i] if (up[i] < final_up[i - 1] or close[i - 1] > final_up[i - 1]) else final_up[i - 1]
        final_lo[i] = lo[i] if (lo[i] > final_lo[i - 1] or close[i - 1] < final_lo[i - 1]) else final_lo[i - 1]
        if close[i] > final_up[i - 1]:
            direction[i] = 1
        elif close[i] < final_lo[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]

    line = np.where(direction == 1, final_lo, final_up)
    return pd.DataFrame({"supertrend": line, "dir": direction}, index=df.index)
