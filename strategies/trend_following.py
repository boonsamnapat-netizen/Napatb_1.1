"""
Trend Following Strategy
=========================
Inspired by long-only momentum (Renaissance / Medallion simplified).
Buys stocks with confirmed momentum in an uptrend.

Rules:
  1. Close > SMA50 > SMA200  (uptrend)
  2. SMA50 sloping up
  3. RSI crosses above 50 (momentum confirmation) OR RSI 50-70 with rising price
  4. 1-month and 3-month momentum positive
  5. Volume ratio >= 1.0 (at least average volume)
  6. Price not too extended: dist_from_high > -20%

Market filter: SPY above 200 MA
"""

import pandas as pd
import numpy as np
from .base import BaseStrategy


class TrendFollowingStrategy(BaseStrategy):

    def __init__(self, rsi_cross: bool = True):
        self.rsi_cross = rsi_cross

    def generate_signals(self, df: pd.DataFrame, market_df: pd.DataFrame = None) -> pd.Series:
        if len(df) < 110:
            return pd.Series(0, index=df.index)

        d = df.copy()

        # ── 1. Uptrend ────────────────────────────────────────────────────
        uptrend = (d['Close'] > d['sma50']) & (d['sma50'] > d['sma200'])

        # ── 2. SMA50 sloping up ───────────────────────────────────────────
        ma_up = d['sma50_slope'] > 0

        # ── 3. RSI signal ──────────────────────────────────────────────────
        rsi_prev = d['rsi14'].shift(1)
        if self.rsi_cross:
            # RSI crosses above 48 from below (more permissive than 50)
            rsi_ok = (rsi_prev < 48) & (d['rsi14'] >= 48)
        else:
            rsi_ok = (d['rsi14'] >= 45) & (d['rsi14'] <= 75)

        # ── 4. Positive momentum ─────────────────────────────────────────
        momentum_ok = (d['mom1m'] > 0.02) & (d['mom3m'] > 0.05)

        # ── 5. Average or above-average volume ────────────────────────────
        vol_ok = d['vol_ratio'] >= 1.0

        # ── 6. Not too extended ───────────────────────────────────────────
        not_extended = d['dist_from_high'] >= -0.20

        # ── Market filter ─────────────────────────────────────────────────
        if market_df is not None and 'sma200' in market_df.columns:
            mkt_up = (market_df['Close'] > market_df['sma200']).reindex(d.index, method='ffill').fillna(False)
        else:
            mkt_up = pd.Series(True, index=d.index)

        signal = (uptrend & ma_up & rsi_ok & momentum_ok & vol_ok & not_extended & mkt_up).fillna(False)

        return signal.astype(int)

    def name(self) -> str:
        return 'Trend_Following'
