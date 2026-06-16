"""
Mainstream technical indicators, implemented in pure pandas/numpy.

These are deliberately the indicators *most* of the market watches (EMA, RSI,
MACD, Bollinger Bands, Stochastic, ADX, ATR, OBV, volume). The thesis of the
system is that because the crowd watches them, the levels they produce become
real liquidity / reaction zones — so we want to see exactly what they see, then
decide better around it.

All functions take an OHLCV DataFrame with columns:
    open, high, low, close, volume
indexed by timestamp, oldest first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA) — used by RSI, ATR, ADX."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = _wilder(gain, period)
    avg_loss = _wilder(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When there is no loss at all, RSI is 100; no gain → 0.
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(avg_gain != 0, out)
    return out


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": hist}
    )


def bollinger(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid.replace(0.0, np.nan)
    # %B: where price sits inside the bands (0 = lower, 1 = upper)
    pct_b = (close - lower) / (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame(
        {"mid": mid, "upper": upper, "lower": lower, "width": width, "pct_b": pct_b}
    )


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return _wilder(true_range(df), period)


def stochastic(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3, smooth_k: int = 3
) -> pd.DataFrame:
    low_min = df["low"].rolling(k_period).min()
    high_max = df["high"].rolling(k_period).max()
    raw_k = 100.0 * (df["close"] - low_min) / (high_max - low_min).replace(0.0, np.nan)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return pd.DataFrame({"k": k, "d": d})


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average Directional Index + directional indicators (+DI / -DI)."""
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = true_range(df)
    atr_ = _wilder(tr, period).replace(0.0, np.nan)
    plus_di = 100.0 * _wilder(plus_dm, period) / atr_
    minus_di = 100.0 * _wilder(minus_dm, period) / atr_

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = _wilder(dx, period)
    return pd.DataFrame({"adx": adx_, "plus_di": plus_di, "minus_di": minus_di})


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0.0))
    return (direction * df["volume"]).cumsum()


def relative_volume(df: pd.DataFrame, period: int = 20) -> pd.Series:
    avg = df["volume"].rolling(period).mean()
    return df["volume"] / avg.replace(0.0, np.nan)


def compute_all(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """Attach every indicator as columns onto a copy of the OHLCV frame."""
    p = params or {}
    out = df.copy()

    out["ema_fast"] = ema(df["close"], p.get("ema_fast", 21))
    out["ema_mid"] = ema(df["close"], p.get("ema_mid", 50))
    out["ema_slow"] = ema(df["close"], p.get("ema_slow", 200))
    out["rsi"] = rsi(df["close"], p.get("rsi_period", 14))

    macd_df = macd(
        df["close"],
        p.get("macd_fast", 12),
        p.get("macd_slow", 26),
        p.get("macd_signal", 9),
    )
    out["macd"] = macd_df["macd"]
    out["macd_signal"] = macd_df["signal"]
    out["macd_hist"] = macd_df["hist"]

    bb = bollinger(df["close"], p.get("bb_period", 20), p.get("bb_std", 2.0))
    out["bb_mid"] = bb["mid"]
    out["bb_upper"] = bb["upper"]
    out["bb_lower"] = bb["lower"]
    out["bb_width"] = bb["width"]
    out["bb_pct_b"] = bb["pct_b"]

    out["atr"] = atr(df, p.get("atr_period", 14))

    st = stochastic(df, p.get("stoch_k", 14), p.get("stoch_d", 3), p.get("stoch_smooth", 3))
    out["stoch_k"] = st["k"]
    out["stoch_d"] = st["d"]

    adx_df = adx(df, p.get("adx_period", 14))
    out["adx"] = adx_df["adx"]
    out["plus_di"] = adx_df["plus_di"]
    out["minus_di"] = adx_df["minus_di"]

    out["obv"] = obv(df)
    out["rvol"] = relative_volume(df, p.get("rvol_period", 20))

    return out
