"""
Dan Zanger Volume Breakout Strategy
=====================================
Key rules (from Fortune Magazine-verified track record):
  1. Stock within 15% of 52-week high  (focus on leaders)
  2. Base formation: 15-day price range < 20% of price  (tight consolidation)
  3. Breakout: Close > 15-day high
  4. Volume surge: vol_ratio >= 1.5  (50%+ above 20-day avg)
  5. In uptrend: Close > SMA50

Market filter: SPY above 200 MA
"""

import pandas as pd
import numpy as np
from .base import BaseStrategy


class ZangerBreakoutStrategy(BaseStrategy):

    def __init__(self, vol_multiplier: float = 1.5, base_days: int = 15, max_dist: float = 0.15):
        self.vol_multiplier = vol_multiplier
        self.base_days      = base_days
        self.max_dist       = max_dist

    def generate_signals(self, df: pd.DataFrame, market_df: pd.DataFrame = None) -> pd.Series:
        if len(df) < 60:
            return pd.Series(0, index=df.index)

        d = df.copy()

        # ── 1. Near 52-week high ──────────────────────────────────────────
        near_high = d['dist_from_high'] >= -self.max_dist

        # ── 2. Tight consolidation base ───────────────────────────────────
        base_high = d['High'].rolling(self.base_days, min_periods=5).max()
        base_low  = d['Low'].rolling(self.base_days,  min_periods=5).min()
        base_range = (base_high - base_low) / base_low.replace(0, np.nan)
        tight_base = base_range < 0.20

        # ── 3. Breakout: close > prior base high ──────────────────────────
        prior_high     = base_high.shift(1)
        price_breakout = d['Close'] > prior_high

        # ── 4. Volume surge ───────────────────────────────────────────────
        vol_surge = d['vol_ratio'] >= self.vol_multiplier

        # ── 5. Uptrend ────────────────────────────────────────────────────
        uptrend = d['Close'] > d['sma50']

        # ── Market filter: SPY above SMA200 ───────────────────────────────
        if market_df is not None and 'sma200' in market_df.columns:
            mkt_up = (market_df['Close'] > market_df['sma200']).reindex(d.index, method='ffill').fillna(False)
        else:
            mkt_up = pd.Series(True, index=d.index)

        signal = (near_high & tight_base & price_breakout & vol_surge & uptrend & mkt_up).fillna(False)

        return signal.astype(int)

    def name(self) -> str:
        return 'Zanger_Breakout'
