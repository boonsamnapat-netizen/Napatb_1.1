"""Walk-forward backtester for the divergence strategy + a TF sweep helper.

Honest, look-ahead-free simulation:
  * a divergence is only acted on once its last pivot is fractal-confirmed
    (handled inside `detect`, which we feed only data up to the signal bar),
  * entry fills at the NEXT bar's open,
  * exits check SL/target intrabar; if both could trigger in one bar we assume
    the stop hit first (conservative),
  * round-trip fees (taker) are charged in R terms.

Metrics are reported per timeframe so callers can rank TFs.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators
from .divergence import (
    MACD_LOOKBACK,
    MACD_OB_PCT,
    MACD_OS_PCT,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    Divergence,
    _pivot_highs,
    _pivot_lows,
)
from .signal_engine import build_signal

# pandas resample rules for common crypto timeframes.
TF_RULES = {
    "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "6h": "6h",
    "8h": "8h", "12h": "12h", "1d": "1D", "2d": "2D", "3d": "3D", "1w": "1W",
}


def resample(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample an OHLCV frame to a coarser timeframe."""
    rule = TF_RULES.get(tf.lower(), tf)
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    out = df.resample(rule, label="right", closed="right").agg(agg).dropna()
    return out


@dataclass
class BacktestResult:
    tf: str
    symbol: str
    trades: int = 0
    wins: int = 0
    rs: list[float] = field(default_factory=list)

    def add(self, r: float) -> None:
        self.trades += 1
        if r > 0:
            self.wins += 1
        self.rs.append(r)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def avg_r(self) -> float:
        return float(np.mean(self.rs)) if self.rs else 0.0

    @property
    def total_r(self) -> float:
        return float(np.sum(self.rs)) if self.rs else 0.0

    @property
    def profit_factor(self) -> float:
        gains = sum(r for r in self.rs if r > 0)
        losses = -sum(r for r in self.rs if r < 0)
        if losses == 0:
            return float("inf") if gains > 0 else 0.0
        return gains / losses

    @property
    def max_dd_r(self) -> float:
        """Max equity drawdown in R along the trade sequence."""
        eq = np.cumsum(self.rs) if self.rs else np.array([0.0])
        peak = np.maximum.accumulate(eq)
        return float(np.max(peak - eq)) if len(eq) else 0.0

    def as_row(self) -> dict:
        return {
            "tf": self.tf,
            "symbol": self.symbol,
            "trades": self.trades,
            "win_rate": round(self.win_rate, 3),
            "avg_R": round(self.avg_r, 4),
            "total_R": round(self.total_r, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_dd_R": round(self.max_dd_r, 2),
        }


def _status_at(name: str, osc: np.ndarray, k: int) -> str:
    """Overbought/oversold/neutral at bar k — numpy mirror of _osc_status."""
    val = osc[k]
    if name == "RSI":
        if val >= RSI_OVERBOUGHT:
            return "RSI Overbought"
        if val <= RSI_OVERSOLD:
            return "RSI Oversold"
        return "RSI Neutral"
    lo = max(0, k - MACD_LOOKBACK)
    ref = osc[lo : k + 1]
    if len(ref) >= 10:
        rank = float((ref < val).mean())
        if rank >= MACD_OB_PCT:
            return "MACD Overbought"
        if rank <= MACD_OS_PCT:
            return "MACD Oversold"
    return "MACD Neutral"


def _scan_at(
    name: str,
    osc: np.ndarray,
    lows: list[int],
    highs: list[int],
    low_arr: np.ndarray,
    high_arr: np.ndarray,
    index: pd.Index,
    i: int,
    window: int,
    max_gap: int,
) -> Divergence | None:
    """Divergence from the last two CONFIRMED pivots as of bar i (positions
    <= i-window). Mirrors divergence._scan but on precomputed arrays."""
    limit = i - window
    bull = bear = None

    k = bisect.bisect_right(lows, limit)
    if k >= 2:
        p, l = lows[k - 2], lows[k - 1]
        if 0 < (l - p) <= max_gap and low_arr[l] < low_arr[p] and osc[l] > osc[p]:
            bull = Divergence(
                kind="bullish", indicator=name, status=_status_at(name, osc, l),
                price_prev=float(low_arr[p]), price_last=float(low_arr[l]),
                osc_prev=float(osc[p]), osc_last=float(osc[l]),
                idx_prev=index[p], idx_last=index[l],
                swing_low=float(low_arr[l]), swing_high=0.0,
            )

    k = bisect.bisect_right(highs, limit)
    if k >= 2:
        p, h = highs[k - 2], highs[k - 1]
        if 0 < (h - p) <= max_gap and high_arr[h] > high_arr[p] and osc[h] < osc[p]:
            bear = Divergence(
                kind="bearish", indicator=name, status=_status_at(name, osc, h),
                price_prev=float(high_arr[p]), price_last=float(high_arr[h]),
                osc_prev=float(osc[p]), osc_last=float(osc[h]),
                idx_prev=index[p], idx_last=index[h],
                swing_low=0.0, swing_high=float(high_arr[h]),
            )

    cands = [d for d in (bull, bear) if d is not None]
    if not cands:
        return None
    return max(cands, key=lambda d: d.idx_last)


def _detect_at(
    indicator: str,
    osc_rsi: np.ndarray,
    osc_macd: np.ndarray,
    lows: list[int],
    highs: list[int],
    low_arr: np.ndarray,
    high_arr: np.ndarray,
    index: pd.Index,
    i: int,
    window: int,
    max_gap: int,
) -> Divergence | None:
    """O(1)-per-bar mirror of divergence.detect using precomputed inputs."""
    ind = indicator.upper()
    args = (lows, highs, low_arr, high_arr, index, i, window, max_gap)
    if ind == "RSI":
        return _scan_at("RSI", osc_rsi, *args)
    if ind == "MACD":
        return _scan_at("MACD", osc_macd, *args)
    found = [d for d in (_scan_at("RSI", osc_rsi, *args),
                         _scan_at("MACD", osc_macd, *args)) if d is not None]
    if not found:
        return None
    confirmed = [d for d in found if not d.status.endswith("Neutral")]
    pool = confirmed or found
    return max(pool, key=lambda d: d.idx_last)


def backtest(
    df: pd.DataFrame,
    symbol: str,
    tf: str,
    indicator: str = "auto",
    target_r: float = 2.0,
    max_hold: int = 30,
    fee_pct: float = 0.05,
    warmup: int = 60,
    pivot_window: int = 5,
    rsi_period: int = 14,
) -> BacktestResult:
    """Run a single-position walk-forward backtest on one OHLCV frame.

    Oscillators (causal), ATR and pivots are precomputed once, so each bar is
    O(1) (plus a bounded pivot bisect) instead of recomputing over the whole
    history — identical results to the naive per-bar `detect`, much faster.
    """
    res = BacktestResult(tf=tf, symbol=symbol)
    n = len(df)
    if n < warmup + 10:
        return res

    osc_rsi = indicators.rsi(df["close"], rsi_period).to_numpy()
    osc_macd = indicators.macd(df["close"])["macd"].to_numpy()
    atr_arr = indicators.atr(df, 14).to_numpy()
    low_arr = df["low"].to_numpy()
    high_arr = df["high"].to_numpy()
    open_arr = df["open"].to_numpy()
    close_arr = df["close"].to_numpy()
    lows = _pivot_lows(df["low"], pivot_window)
    highs = _pivot_highs(df["high"], pivot_window)
    index = df.index
    max_gap = 90

    fee_frac = fee_pct / 100.0
    i = warmup
    while i < n - 1:
        div = _detect_at(indicator, osc_rsi, osc_macd, lows, highs,
                         low_arr, high_arr, index, i, pivot_window, max_gap)
        if div is None:
            i += 1
            continue

        entry = float(open_arr[i + 1])
        sig = build_signal(
            symbol, df, div=div, indicator=indicator,
            entry_price=entry, atr_value=float(atr_arr[i]),
        )
        if sig is None or sig.entry <= 0:
            i += 1
            continue

        risk = abs(sig.entry - sig.sl)
        if risk <= 0:
            i += 1
            continue
        long = sig.side == "LONG"
        target = sig.entry + target_r * risk if long else sig.entry - target_r * risk
        stop = sig.sl
        # round-trip fee expressed in R (approx: notional ~ entry per 1 unit)
        fee_r = (2 * fee_frac * sig.entry) / risk

        outcome = None
        exit_j = min(i + 1 + max_hold, n - 1)
        for j in range(i + 1, exit_j + 1):
            hi, lo = float(high_arr[j]), float(low_arr[j])
            if long:
                if lo <= stop:
                    outcome = -1.0
                    break
                if hi >= target:
                    outcome = target_r
                    break
            else:
                if hi >= stop:
                    outcome = -1.0
                    break
                if lo <= target:
                    outcome = target_r
                    break
        if outcome is None:  # time stop: mark to close
            close = float(close_arr[exit_j])
            outcome = (close - sig.entry) / risk if long else (sig.entry - close) / risk

        res.add(outcome - fee_r)
        # resume scanning after the trade closes (no overlapping positions)
        i = exit_j + 1

    return res


def sweep(
    df_base: pd.DataFrame,
    symbol: str,
    tfs: list[str],
    **kw,
) -> list[BacktestResult]:
    """Backtest one symbol across several timeframes (resampled from df_base)."""
    out: list[BacktestResult] = []
    for tf in tfs:
        try:
            d = resample(df_base, tf)
        except Exception:
            continue
        out.append(backtest(d, symbol, tf, **kw))
    return out
