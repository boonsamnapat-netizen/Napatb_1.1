"""
Minervini VCP + SEPA Strategy
==============================
Stage 2 uptrend + volatility contraction + volume breakout.

SEPA criteria (vectorized):
  1. Close > SMA50 > SMA150 > SMA200  (Stage 2)
  2. SMA150 and SMA200 sloping up
  3. Price within 25% of 52-week high
  4. Price >= 25% above 52-week low (strong base)
  5. RSI 35-80

VCP proxy (vectorized):
  6. BB width < 80% of its own 40-day mean  (volatility contracting)
  7. Volume 20-day MA declining (supply drying up)

Breakout:
  8. Close > prior 20-day high  (pivot breakout)
  9. Volume ratio >= 1.4  (institutional buying)

Market filter:
  10. SPY Close > SPY SMA200
"""

import pandas as pd
import numpy as np
from .base import BaseStrategy


class VCPMinerviniStrategy(BaseStrategy):

    def __init__(self, vol_threshold: float = 1.4, max_dist_from_high: float = 0.25):
        self.vol_threshold = vol_threshold
        self.max_dist_from_high = max_dist_from_high

    def generate_signals(self, df: pd.DataFrame, market_df: pd.DataFrame = None) -> pd.Series:
        if len(df) < 210:
            return pd.Series(0, index=df.index)

        d = df.copy()

        # ── 1. Stage 2: Close > SMA50 > SMA150 > SMA200 ─────────────────
        stage2 = (
            (d['Close']  > d['sma50'])  &
            (d['sma50']  > d['sma150']) &
            (d['sma150'] > d['sma200'])
        )

        # ── 2. MAs sloping up ────────────────────────────────────────────
        ma_slope = (d['sma150_slope'] > 0) & (d['sma200_slope'] > 0)

        # ── 3. Near 52-week high ──────────────────────────────────────────
        near_high = d['dist_from_high'] >= -self.max_dist_from_high

        # ── 4. Above 52-week low ─────────────────────────────────────────
        above_low = d['dist_from_low'] >= 0.25

        # ── 5. RSI healthy ────────────────────────────────────────────────
        rsi_ok = (d['rsi14'] >= 35) & (d['rsi14'] <= 80)

        # ── 6. VCP: Bollinger width contracting ───────────────────────────
        bb_avg = d['bb_width'].rolling(40, min_periods=20).mean()
        vcp_tight = d['bb_width'] < bb_avg * 0.80

        # ── 7. Volume drying up during consolidation ─────────────────────
        vol_declining = d['vol_sma20'] < d['vol_sma20'].shift(15)

        # ── 8–9. Breakout on volume ───────────────────────────────────────
        pivot = d['High'].rolling(20, min_periods=10).max().shift(1)
        price_breakout = d['Close'] > pivot
        vol_surge      = d['vol_ratio'] >= self.vol_threshold

        # ── 10. Market regime ─────────────────────────────────────────────
        if market_df is not None and 'sma200' in market_df.columns:
            mkt_up = (market_df['Close'] > market_df['sma200']).reindex(d.index, method='ffill').fillna(False)
        else:
            mkt_up = pd.Series(True, index=d.index)

        signal = (
            stage2 & ma_slope & near_high & above_low & rsi_ok &
            vcp_tight & vol_declining & price_breakout & vol_surge & mkt_up
        ).fillna(False)

        return signal.astype(int)

    def name(self) -> str:
        return 'VCP_Minervini'
