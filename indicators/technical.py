"""
Technical indicators — all vectorized with pandas/numpy.
No TA library dependency.
"""

import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, prev_close = df['High'], df['Low'], df['Close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def bollinger(series: pd.Series, period: int = 20, std_mult: float = 2.0):
    mid    = sma(series, period)
    sd     = series.rolling(period).std()
    upper  = mid + std_mult * sd
    lower  = mid - std_mult * sd
    width  = (upper - lower) / mid.replace(0, np.nan)
    pct    = (series - lower) / (upper - lower).replace(0, np.nan)
    return upper, mid, lower, width, pct


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all TA columns to an OHLCV DataFrame. Returns new DataFrame."""
    d = df.copy()
    c = d['Close']

    # Moving averages
    d['sma20']  = sma(c, 20)
    d['sma50']  = sma(c, 50)
    d['sma150'] = sma(c, 150)
    d['sma200'] = sma(c, 200)

    # Slopes (% change over N days)
    d['sma50_slope']  = d['sma50'].pct_change(10)
    d['sma150_slope'] = d['sma150'].pct_change(20)
    d['sma200_slope'] = d['sma200'].pct_change(20)

    # Trend flags
    d['above_sma50']  = (c > d['sma50']).astype(float)
    d['above_sma150'] = (c > d['sma150']).astype(float)
    d['above_sma200'] = (c > d['sma200']).astype(float)

    # Relative position
    d['price_vs_sma50']  = (c - d['sma50'])  / d['sma50'].replace(0, np.nan)
    d['price_vs_sma200'] = (c - d['sma200']) / d['sma200'].replace(0, np.nan)

    # Momentum (rate of change)
    d['mom1m'] = c.pct_change(21)
    d['mom3m'] = c.pct_change(63)
    d['mom6m'] = c.pct_change(126)

    # RSI
    d['rsi14'] = rsi(c, 14)

    # ATR
    d['atr14']   = atr(d, 14)
    d['atr_pct'] = d['atr14'] / c.replace(0, np.nan)

    # Bollinger Bands
    bb_u, bb_m, bb_l, bb_w, bb_p = bollinger(c, 20)
    d['bb_upper'] = bb_u
    d['bb_mid']   = bb_m
    d['bb_lower'] = bb_l
    d['bb_width'] = bb_w
    d['bb_pct']   = bb_p

    # Volume
    d['vol_sma20'] = d['Volume'].rolling(20, min_periods=5).mean()
    d['vol_ratio'] = d['Volume'] / d['vol_sma20'].replace(0, np.nan)

    # 52-week high / low
    d['high52w']       = d['High'].rolling(252, min_periods=20).max()
    d['low52w']        = d['Low'].rolling(252, min_periods=20).min()
    d['dist_from_high'] = (c - d['high52w']) / d['high52w'].replace(0, np.nan)
    d['dist_from_low']  = (c - d['low52w'])  / d['low52w'].replace(0, np.nan)

    # Regime features
    d['realized_vol_20'] = c.pct_change().rolling(20).std() * np.sqrt(252)
    d['realized_vol_60'] = c.pct_change().rolling(60).std() * np.sqrt(252)
    d['vol_regime'] = (d['realized_vol_20'] / d['realized_vol_60']).fillna(1.0)
    d['mom12m'] = c.pct_change(252)
    d['price_accel'] = d['mom1m'] - d['mom3m'] / 3

    return d
