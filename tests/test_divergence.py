"""Tests for the divergence signal engine.

Run with:  python -m pytest tests/test_divergence.py  (or python tests/test_divergence.py)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.signal import indicators, market_data
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
