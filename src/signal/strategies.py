"""Multi-strategy 4H comparison harness.

Every strategy emits, per bar i (using only data up to i), a trigger:
  side[i]      in {0 none, +1 long, -1 short}
  riskdist[i]  > 0  — the stop distance from entry (defines 1R)

A single engine then trades them identically — enter at the NEXT bar's open,
stop at entry -/+ riskdist, take-profit at target_r * riskdist, time-stop after
max_hold bars, round-trip taker fee charged in R — so results are comparable
across strategies on an apples-to-apples, risk-normalised (R-multiple) basis.

Strategies: divergence (raw), divergence+trend filter, Donchian breakout,
EMA crossover, Supertrend flip.
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from . import indicators
from .backtester import (
    BacktestResult,
    _detect_at,
    _pivot_highs,
    _pivot_lows,
)

MIN_STOP_PCT = 0.3  # floor on the stop distance (% of price)


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
def run(
    df: pd.DataFrame,
    side: np.ndarray,
    riskdist: np.ndarray,
    symbol: str,
    name: str,
    target_r: float = 2.0,
    max_hold: int = 30,
    fee_pct: float = 0.05,
    warmup: int = 210,
    trail_atr: float | None = None,
) -> BacktestResult:
    """Trade the signals. Exit is either a fixed `target_r` take-profit, or —
    when `trail_atr` is set — an ATR chandelier trailing stop (no fixed TP):
    the stop ratchets to high_since_entry - trail_atr*ATR (mirror for shorts).
    Either way the initial 1R risk is `riskdist`, so results stay R-comparable.
    """
    res = BacktestResult(tf=name, symbol=symbol)
    n = len(df)
    if n < warmup + 10:
        return res
    open_arr = df["open"].to_numpy()
    high_arr = df["high"].to_numpy()
    low_arr = df["low"].to_numpy()
    close_arr = df["close"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy() if trail_atr else None
    fee_frac = fee_pct / 100.0

    i = warmup
    while i < n - 1:
        s = side[i]
        if s == 0 or not np.isfinite(riskdist[i]) or riskdist[i] <= 0:
            i += 1
            continue
        entry = float(open_arr[i + 1])
        risk = max(float(riskdist[i]), entry * MIN_STOP_PCT / 100.0)
        long = s > 0
        stop = entry - risk if long else entry + risk
        target = entry + target_r * risk if long else entry - target_r * risk
        fee_r = (2 * fee_frac * entry) / risk

        outcome = None
        exit_j = min(i + 1 + max_hold, n - 1)
        extreme = entry  # highest high (long) / lowest low (short) since entry
        for j in range(i + 1, exit_j + 1):
            hi, lo = float(high_arr[j]), float(low_arr[j])
            if long:
                if lo <= stop:
                    outcome = (stop - entry) / risk
                    break
                if trail_atr:
                    extreme = max(extreme, hi)
                    stop = max(stop, extreme - trail_atr * float(atr_arr[j]))
                elif hi >= target:
                    outcome = target_r
                    break
            else:
                if hi >= stop:
                    outcome = (entry - stop) / risk
                    break
                if trail_atr:
                    extreme = min(extreme, lo)
                    stop = min(stop, extreme + trail_atr * float(atr_arr[j]))
                elif lo <= target:
                    outcome = target_r
                    break
        if outcome is None:
            close = float(close_arr[exit_j])
            outcome = (close - entry) / risk if long else (entry - close) / risk

        res.add(outcome - fee_r)
        i = exit_j + 1
    return res


# --------------------------------------------------------------------------- #
# Signal generators -> (side, riskdist)
# --------------------------------------------------------------------------- #
def _empty(n: int) -> tuple[np.ndarray, np.ndarray]:
    return np.zeros(n, dtype=int), np.full(n, np.nan)


def divergence_signals(
    df: pd.DataFrame,
    indicator: str = "auto",
    pivot_window: int = 5,
    atr_buffer: float = 0.5,
    trend_filter: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Raw divergence, optionally gated by an EMA200 trend filter
    (longs only above EMA200, shorts only below)."""
    n = len(df)
    side, riskdist = _empty(n)
    osc_rsi = indicators.rsi(df["close"]).to_numpy()
    osc_macd = indicators.macd(df["close"])["macd"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()
    low_arr = df["low"].to_numpy()
    high_arr = df["high"].to_numpy()
    close_arr = df["close"].to_numpy()
    ema200 = indicators.ema(df["close"], 200).to_numpy()
    lows = _pivot_lows(df["low"], pivot_window)
    highs = _pivot_highs(df["high"], pivot_window)
    index = df.index

    for i in range(60, n):
        div = _detect_at(indicator, osc_rsi, osc_macd, lows, highs,
                         low_arr, high_arr, index, i, pivot_window, 90)
        if div is None:
            continue
        pad = atr_arr[i] * atr_buffer
        if div.kind == "bullish":
            if trend_filter == "ema200" and not (close_arr[i] > ema200[i]):
                continue
            side[i] = 1
            riskdist[i] = max(close_arr[i] - (div.swing_low - pad), 0.0)
        else:
            if trend_filter == "ema200" and not (close_arr[i] < ema200[i]):
                continue
            side[i] = -1
            riskdist[i] = max((div.swing_high + pad) - close_arr[i], 0.0)
    return side, riskdist


def donchian_signals(
    df: pd.DataFrame, period: int = 20, atr_mult: float = 2.0
) -> tuple[np.ndarray, np.ndarray]:
    """Breakout above/below the prior `period`-bar high/low (first cross only)."""
    n = len(df)
    side, riskdist = _empty(n)
    close = df["close"].to_numpy()
    hh = df["high"].rolling(period).max().shift(1).to_numpy()
    ll = df["low"].rolling(period).min().shift(1).to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()
    for i in range(period + 1, n):
        if not (np.isfinite(hh[i]) and np.isfinite(hh[i - 1])):
            continue
        if close[i] > hh[i] and close[i - 1] <= hh[i - 1]:
            side[i] = 1
            riskdist[i] = atr_mult * atr_arr[i]
        elif close[i] < ll[i] and close[i - 1] >= ll[i - 1]:
            side[i] = -1
            riskdist[i] = atr_mult * atr_arr[i]
    return side, riskdist


def ema_cross_signals(
    df: pd.DataFrame, fast: int = 20, slow: int = 50, atr_mult: float = 1.5
) -> tuple[np.ndarray, np.ndarray]:
    """Long on fast-EMA crossing above slow-EMA, short on the reverse."""
    n = len(df)
    side, riskdist = _empty(n)
    ef = indicators.ema(df["close"], fast).to_numpy()
    es = indicators.ema(df["close"], slow).to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()
    for i in range(slow + 1, n):
        if ef[i] > es[i] and ef[i - 1] <= es[i - 1]:
            side[i] = 1
            riskdist[i] = atr_mult * atr_arr[i]
        elif ef[i] < es[i] and ef[i - 1] >= es[i - 1]:
            side[i] = -1
            riskdist[i] = atr_mult * atr_arr[i]
    return side, riskdist


def supertrend_signals(
    df: pd.DataFrame, period: int = 10, mult: float = 3.0, atr_mult: float = 2.0
) -> tuple[np.ndarray, np.ndarray]:
    """Enter on a Supertrend direction flip."""
    n = len(df)
    side, riskdist = _empty(n)
    st = indicators.supertrend(df, period, mult)
    d = st["dir"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()
    for i in range(period + 1, n):
        if d[i] == 1 and d[i - 1] == -1:
            side[i] = 1
            riskdist[i] = atr_mult * atr_arr[i]
        elif d[i] == -1 and d[i - 1] == 1:
            side[i] = -1
            riskdist[i] = atr_mult * atr_arr[i]
    return side, riskdist


# --------------------------------------------------------------------------- #
# Discretionary "screen-watcher" playbooks, codified
# --------------------------------------------------------------------------- #
def _recent_confirmed(positions: list[int], i: int, window: int) -> int | None:
    """Most recent pivot position confirmed as of bar i (pos <= i - window)."""
    k = bisect.bisect_right(positions, i - window)
    return positions[k - 1] if k else None


def ema_pullback_signals(
    df: pd.DataFrame, fast: int = 20, slow: int = 50, trend: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Trend-continuation: in an established trend (EMA50 vs EMA200), buy the
    pullback when price closes back above the fast EMA (mirror for shorts).
    Stop sits just beyond the pullback wick — the classic discretionary entry."""
    n = len(df)
    side, riskdist = _empty(n)
    ef = indicators.ema(df["close"], fast).to_numpy()
    es = indicators.ema(df["close"], slow).to_numpy()
    et = indicators.ema(df["close"], trend).to_numpy()
    close = df["close"].to_numpy()
    low = df["low"].to_numpy()
    high = df["high"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()
    for i in range(trend + 1, n):
        up = es[i] > et[i] and close[i] > et[i]
        dn = es[i] < et[i] and close[i] < et[i]
        # close crosses back above fast EMA after dipping to it -> resume up
        if up and close[i] > ef[i] and close[i - 1] <= ef[i - 1]:
            stop = min(low[i], low[i - 1]) - 0.2 * atr_arr[i]
            side[i] = 1
            riskdist[i] = max(close[i] - stop, 0.0)
        elif dn and close[i] < ef[i] and close[i - 1] >= ef[i - 1]:
            stop = max(high[i], high[i - 1]) + 0.2 * atr_arr[i]
            side[i] = -1
            riskdist[i] = max(stop - close[i], 0.0)
    return side, riskdist


def bos_retest_signals(
    df: pd.DataFrame, window: int = 5, retest_bars: int = 6,
) -> tuple[np.ndarray, np.ndarray]:
    """Break of structure + retest: price closes through the last confirmed
    swing high/low (BOS), then we wait for a pullback that retests the broken
    level and holds, and enter in the breakout direction."""
    n = len(df)
    side, riskdist = _empty(n)
    highs = _pivot_highs(df["high"], window)
    lows = _pivot_lows(df["low"], window)
    high_arr = df["high"].to_numpy()
    low_arr = df["low"].to_numpy()
    close = df["close"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()

    pend_long: tuple[float, int] | None = None   # (level, expiry_bar)
    pend_short: tuple[float, int] | None = None
    for i in range(window + 2, n):
        sh_pos = _recent_confirmed(highs, i, window)
        sl_pos = _recent_confirmed(lows, i, window)
        # arm a pending retest on a fresh BOS
        if sh_pos is not None:
            lvl = high_arr[sh_pos]
            if close[i] > lvl and close[i - 1] <= lvl:
                pend_long = (lvl, i + retest_bars)
        if sl_pos is not None:
            lvl = low_arr[sl_pos]
            if close[i] < lvl and close[i - 1] >= lvl:
                pend_short = (lvl, i + retest_bars)
        # fire on retest that holds
        if pend_long is not None:
            lvl, exp = pend_long
            if i > exp:
                pend_long = None
            elif low_arr[i] <= lvl and close[i] > lvl:
                stop = min(low_arr[i], lvl) - 0.2 * atr_arr[i]
                side[i] = 1
                riskdist[i] = max(close[i] - stop, 0.0)
                pend_long = None
        if pend_short is not None and side[i] == 0:
            lvl, exp = pend_short
            if i > exp:
                pend_short = None
            elif high_arr[i] >= lvl and close[i] < lvl:
                stop = max(high_arr[i], lvl) + 0.2 * atr_arr[i]
                side[i] = -1
                riskdist[i] = max(stop - close[i], 0.0)
                pend_short = None
    return side, riskdist


def liquidity_sweep_signals(
    df: pd.DataFrame, window: int = 5, max_gap: int = 60,
) -> tuple[np.ndarray, np.ndarray]:
    """ICT-style stop hunt: price wicks through a recent confirmed swing low to
    grab liquidity but CLOSES back above it -> long (mirror for shorts). Stop
    goes beyond the sweep wick."""
    n = len(df)
    side, riskdist = _empty(n)
    highs = _pivot_highs(df["high"], window)
    lows = _pivot_lows(df["low"], window)
    high_arr = df["high"].to_numpy()
    low_arr = df["low"].to_numpy()
    close = df["close"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()

    for i in range(window + 2, n):
        sl_pos = _recent_confirmed(lows, i, window)
        sh_pos = _recent_confirmed(highs, i, window)
        if sl_pos is not None and 0 < (i - sl_pos) <= max_gap:
            lvl = low_arr[sl_pos]
            if low_arr[i] < lvl and close[i] > lvl:   # swept low, closed back up
                stop = low_arr[i] - 0.2 * atr_arr[i]
                side[i] = 1
                riskdist[i] = max(close[i] - stop, 0.0)
        if side[i] == 0 and sh_pos is not None and 0 < (i - sh_pos) <= max_gap:
            lvl = high_arr[sh_pos]
            if high_arr[i] > lvl and close[i] < lvl:  # swept high, closed back down
                stop = high_arr[i] + 0.2 * atr_arr[i]
                side[i] = -1
                riskdist[i] = max(stop - close[i], 0.0)
    return side, riskdist


STRATEGIES = {
    "divergence": lambda df: divergence_signals(df),
    "divergence+trend": lambda df: divergence_signals(df, trend_filter="ema200"),
    "donchian": lambda df: donchian_signals(df),
    "ema_cross": lambda df: ema_cross_signals(df),
    "supertrend": lambda df: supertrend_signals(df),
    "ema_pullback": lambda df: ema_pullback_signals(df),
    "bos_retest": lambda df: bos_retest_signals(df),
    "liq_sweep": lambda df: liquidity_sweep_signals(df),
}


def backtest_strategy(
    df: pd.DataFrame, symbol: str, name: str, **kw
) -> BacktestResult:
    side, riskdist = STRATEGIES[name](df)
    return run(df, side, riskdist, symbol, name, **kw)


def latest_setup(
    df: pd.DataFrame,
    name: str,
    tp_r: tuple[float, float, float] = (2.0, 3.0, 4.0),
    fresh_bars: int = 1,
) -> dict | None:
    """Return the most recent live setup if the strategy triggered within the
    last `fresh_bars` closed bars. Entry = last close (proxy for next open);
    SL = entry -/+ riskdist; TP1-3 = entry +/- tp_r * riskdist.
    """
    side, riskdist = STRATEGIES[name](df)
    n = len(df)
    close = df["close"].to_numpy()
    for i in range(n - 1, max(n - 1 - fresh_bars, -1), -1):
        if side[i] != 0 and np.isfinite(riskdist[i]) and riskdist[i] > 0:
            entry = float(close[i])
            risk = max(float(riskdist[i]), entry * MIN_STOP_PCT / 100.0)
            long = side[i] > 0
            tps = [entry + m * risk if long else entry - m * risk for m in tp_r]
            return {
                "side": "LONG" if long else "SHORT",
                "entry": entry,
                "sl": entry - risk if long else entry + risk,
                "tps": tps,
                "rr": tp_r,
                "risk": risk,
                "bar_time": df.index[i],
            }
    return None
