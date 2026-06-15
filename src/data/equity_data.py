"""
US equity OHLCV data provider.

Reads from a local CSV cache first (data/real/<TICKER>.csv, as produced by the
Fetch Real Market Data workflow), then falls back to a live yfinance download.
Returns a normalized DataFrame indexed by UTC timestamp with lowercase columns:
open, high, low, close, volume — matching the shape the backtest engine and
briefing modules expect.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/real")

# Map common ccxt-style timeframes to yfinance intervals.
_INTERVAL_MAP = {
    "1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m", "30m": "30m",
    "60m": "60m", "1h": "60m", "90m": "90m",
    "1d": "1d", "1w": "1wk", "1wk": "1wk", "1mo": "1mo", "1M": "1mo",
}


def to_yf_interval(timeframe: str) -> str:
    """Normalize an arbitrary timeframe string to a yfinance interval."""
    if not timeframe:
        return "1d"
    return _INTERVAL_MAP.get(timeframe, _INTERVAL_MAP.get(timeframe.lower(), "1d"))


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase OHLCV columns and ensure a tz-aware UTC DatetimeIndex."""
    if df is None or df.empty:
        return pd.DataFrame()

    rename = {c: c.lower() for c in df.columns}
    df = df.rename(columns=rename)

    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].copy()

    idx = pd.to_datetime(df.index, utc=True, errors="coerce")
    df.index = idx
    df = df[~df.index.isna()]
    df.index.name = "ts"

    for c in keep:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df.dropna(how="all")


def load_cached(symbol: str, cache_dir: Union[str, Path] = CACHE_DIR) -> Optional[pd.DataFrame]:
    """Load OHLCV for a symbol from the local CSV cache, or None if absent."""
    path = Path(cache_dir) / f"{symbol.upper()}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=0)
        return _normalize(df)
    except Exception as e:
        logger.warning("Failed to read cached data for %s: %s", symbol, e)
        return None


def fetch_yf(
    symbol: str,
    start: Optional[datetime] = None,
    interval: str = "1d",
    limit: int = 400,
) -> pd.DataFrame:
    """Download OHLCV for a symbol from yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — run: pip install yfinance")
        return pd.DataFrame()

    kwargs = {"interval": interval, "auto_adjust": True, "progress": False}
    if start is not None:
        kwargs["start"] = start.date().isoformat()
    else:
        # Daily data: roughly `limit` trading days ≈ limit * 1.5 calendar days.
        period_days = max(limit * 2, 60)
        kwargs["period"] = f"{period_days}d"

    try:
        df = yf.download(symbol, **kwargs)
    except Exception as e:
        logger.warning("yfinance download failed for %s: %s", symbol, e)
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _normalize(df)


def get_ohlcv(
    symbol: str,
    start: Optional[datetime] = None,
    interval: str = "1d",
    limit: int = 400,
    use_cache: bool = True,
    cache_dir: Union[str, Path] = CACHE_DIR,
) -> pd.DataFrame:
    """
    Get OHLCV for a symbol, preferring the local cache when it covers `start`.

    Falls back to a live yfinance download when the cache is missing or does not
    extend back far enough to cover the requested start date.
    """
    df = load_cached(symbol, cache_dir) if use_cache else None

    # Use the cache only if it actually covers the requested start date.
    if df is not None and not df.empty and start is not None:
        start_ts = pd.Timestamp(start)
        start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
        if df.index.min() > start_ts:
            df = None  # cache starts too late — fall back to live download

    if df is None or df.empty:
        df = fetch_yf(symbol, start=start, interval=interval, limit=limit)

    if df.empty:
        return df

    if start is not None:
        start_ts = pd.Timestamp(start)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize("UTC")
        else:
            start_ts = start_ts.tz_convert("UTC")
        df = df[df.index >= start_ts]

    if limit and len(df) > limit:
        df = df.iloc[:limit] if start is not None else df.iloc[-limit:]

    return df
