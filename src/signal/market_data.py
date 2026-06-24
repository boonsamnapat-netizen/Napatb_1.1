"""Price data loading.

The sandbox can only reach raw.githubusercontent.com, so live exchange
fetching is intentionally out of scope here: load committed CSVs, or generate
a deterministic demo series for offline testing/preview.
"""
from __future__ import annotations

import pathlib
import zlib

import numpy as np
import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case columns, parse a date index, keep OHLCV."""
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    # Find a datetime-ish column for the index if not already indexed.
    for cand in ("date", "datetime", "timestamp", "time"):
        if cand in df.columns:
            df[cand] = pd.to_datetime(df[cand], utc=True, errors="coerce")
            df = df.set_index(cand)
            break
    missing = [c for c in OHLCV if c not in df.columns]
    if "volume" in missing:  # volume optional -> synthesise zeros
        df["volume"] = 0.0
        missing.remove("volume")
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    df = df[OHLCV].apply(pd.to_numeric, errors="coerce").dropna(subset=OHLCV[:4])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def load_csv(path: str | pathlib.Path) -> pd.DataFrame:
    """Load an OHLCV CSV into a normalised frame."""
    df = pd.read_csv(path)
    return _normalise(df)


def demo_series(symbol: str = "BTCUSDT", bars: int = 320) -> pd.DataFrame:
    """Deterministic synthetic OHLCV that ends on a bullish divergence.

    Price prints two troughs where the SECOND is a lower low but the decline
    into it is shallower per-bar, so RSI/MACD print a higher low -> a textbook
    regular bullish divergence. Useful for previews and tests without network.
    The seed (from the symbol) only adds light, reproducible noise.
    """
    # Stable per-symbol seed (Python's hash() is process-randomised, so use a
    # deterministic hash to keep demo data reproducible across runs/tests).
    seed = zlib.crc32(symbol.encode())
    rng = np.random.default_rng(seed)
    base = 100 + (seed % 5000)

    # Build the price path level-by-level (in multiples of base) so the two
    # troughs land where we want: B is a LOWER low than A, but reached via a
    # gentler slope -> momentum makes a HIGHER low -> bullish divergence.
    n0 = bars - 110
    seg = [
        np.linspace(1.0, 1.5, n0),     # earlier uptrend
        np.linspace(1.5, 0.95, 30),    # steep sell-off -> trough A (~0.95)
        np.linspace(0.95, 1.15, 20),   # bounce to a lower high
        np.linspace(1.15, 0.90, 45),   # long, gentle decline -> lower trough B (~0.90)
        np.linspace(0.90, 1.02, 15),   # confirming bounce
    ]
    level = np.concatenate(seg)[:bars]
    close = base * level * (1 + rng.normal(0, 0.004, len(level)))

    high = close * (1 + np.abs(rng.normal(0, 0.005, len(close))))
    low = close * (1 - np.abs(rng.normal(0, 0.005, len(close))))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = rng.uniform(1e3, 5e3, len(close))

    idx = pd.date_range(
        end=pd.Timestamp.utcnow().normalize(), periods=len(close), freq="D"
    )
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )
