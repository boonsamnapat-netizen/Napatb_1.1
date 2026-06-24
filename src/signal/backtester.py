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

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .divergence import detect
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
) -> BacktestResult:
    """Run a single-position walk-forward backtest on one OHLCV frame."""
    res = BacktestResult(tf=tf, symbol=symbol)
    n = len(df)
    if n < warmup + 10:
        return res

    fee_frac = fee_pct / 100.0
    i = warmup
    while i < n - 1:
        window = df.iloc[: i + 1]
        div = detect(window, indicator=indicator, pivot_window=pivot_window)
        if div is None:
            i += 1
            continue

        entry = float(df["open"].iloc[i + 1])
        sig = build_signal(
            symbol, window, div=div, indicator=indicator, entry_price=entry
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
            hi, lo = float(df["high"].iloc[j]), float(df["low"].iloc[j])
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
            close = float(df["close"].iloc[exit_j])
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
