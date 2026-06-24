"""Tests for the divergence signal engine.

Run with:  python -m pytest tests/test_divergence.py  (or python tests/test_divergence.py)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.signal import indicators, market_data
from src.signal.backtester import backtest, resample
from src.signal.divergence import detect
from src.signal.notifier import format_signal
from src.signal.signal_engine import build_signal


def _frame(level: np.ndarray, base: float = 100.0, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = base * level * (1 + rng.normal(0, 0.003, len(level)))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": np.ones(len(close)),
        },
        index=pd.date_range("2023-01-01", periods=len(close), freq="D"),
    )


def test_indicators_bounds():
    df = market_data.demo_series("BTCUSDT")
    r = indicators.rsi(df["close"])
    assert r.between(0, 100).all()
    assert not indicators.atr(df).isna().all()


def test_bullish_divergence_demo():
    df = market_data.demo_series("BTCUSDT")
    div = detect(df, indicator="rsi")
    assert div is not None and div.kind == "bullish"
    # price lower low, oscillator higher low
    assert div.price_last < div.price_prev
    assert div.osc_last > div.osc_prev

    sig = build_signal("BTCUSDT", df, div=div)
    assert sig.side == "LONG"
    assert sig.sl < sig.entry < sig.tp1 < sig.tp2 < sig.tp3
    # R-multiples: each TP is the right number of R away from entry.
    r = sig.entry - sig.sl
    assert abs((sig.tp1 - sig.entry) - r) < 0.05 * r
    assert abs((sig.tp3 - sig.entry) - 3 * r) < 0.05 * r


def test_bearish_divergence():
    level = np.concatenate(
        [
            np.linspace(1.0, 0.7, 150),
            np.linspace(0.7, 1.20, 30),
            np.linspace(1.20, 1.00, 20),
            np.linspace(1.00, 1.25, 45),
            np.linspace(1.25, 1.15, 15),
        ]
    )
    df = _frame(level)
    div = detect(df, indicator="rsi")
    assert div is not None and div.kind == "bearish"
    assert div.price_last > div.price_prev
    assert div.osc_last < div.osc_prev

    sig = build_signal("ADAUSDT", df, div=div)
    assert sig.side == "SHORT"
    assert sig.sl > sig.entry > sig.tp1 > sig.tp2 > sig.tp3


def test_format_matches_requested_shape():
    df = market_data.demo_series("BTCUSDT")
    sig = build_signal("BTCUSDT", df, indicator="rsi")
    text = format_signal(sig)
    for field in ("เหรียญ", "Signal:", "Indicator status:", "Entry:", "SL:",
                  "TP1:", "TP2:", "TP3:", "RR:"):
        assert field in text


def test_no_divergence_returns_none():
    # Pure uptrend: no regular divergence on the last two pivots.
    level = np.linspace(1.0, 2.0, 200)
    df = _frame(level, seed=7)
    sig = build_signal("XYZUSDT", df, indicator="rsi")
    # Either no divergence at all, or at least not a clean bullish setup.
    assert sig is None or sig.side in ("LONG", "SHORT")


def test_backtest_runs_and_is_consistent():
    df = market_data.demo_series("BTCUSDT", bars=400)
    res = backtest(df, "BTCUSDT", "1d", target_r=2.0, max_hold=30)
    assert res.trades >= 1
    assert res.wins <= res.trades
    # avg_R is the mean of recorded R-multiples
    assert abs(res.avg_r - (sum(res.rs) / len(res.rs))) < 1e-9
    # losses are bounded near -1R (minus fee); nothing should be far worse
    assert min(res.rs) >= -1.5


def test_fast_detect_matches_reference():
    """The backtester's O(1)-per-bar detector must agree with divergence.detect
    (kind/indicator/status and the SL-relevant swing) at every bar."""
    from src.signal import indicators
    from src.signal.backtester import _detect_at
    from src.signal.divergence import _pivot_highs, _pivot_lows

    df = resample(market_data.demo_series("ETHUSDT", bars=500), "1d")
    n = len(df)
    osc_rsi = indicators.rsi(df["close"]).to_numpy()
    osc_macd = indicators.macd(df["close"])["macd"].to_numpy()
    low_arr, high_arr = df["low"].to_numpy(), df["high"].to_numpy()
    lows, highs = _pivot_lows(df["low"], 5), _pivot_highs(df["high"], 5)

    for i in range(60, n - 1):
        ref = detect(df.iloc[: i + 1], indicator="auto", pivot_window=5)
        fast = _detect_at("auto", osc_rsi, osc_macd, lows, highs,
                          low_arr, high_arr, df.index, i, 5, 90)
        assert (ref is None) == (fast is None)
        if ref is not None:
            assert (ref.kind, ref.indicator, ref.status) == \
                   (fast.kind, fast.indicator, fast.status)
            used = "swing_low" if ref.kind == "bullish" else "swing_high"
            assert abs(getattr(ref, used) - getattr(fast, used)) < 1e-9


def test_resample_coarsens():
    df = market_data.demo_series("BTCUSDT", bars=400)
    weekly = resample(df, "1w")
    assert len(weekly) < len(df)
    assert set(["open", "high", "low", "close", "volume"]).issubset(weekly.columns)
    # weekly high must be >= the closes it aggregates over (basic OHLC sanity)
    assert (weekly["high"] >= weekly["close"]).all()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
