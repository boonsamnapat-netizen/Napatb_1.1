"""
Standalone real-market-data downloader
======================================
Run on GitHub Actions runners (where yfinance is reachable). Downloads daily
OHLCV for the ticker universe and writes one CSV per ticker into ``data/real/``.

Self-contained: does NOT import config.py. The ticker universe is read from
``data/universe.txt`` (one ticker per line) if present, else a hardcoded
default list of the current 37 tickers.

Usage:
    python data/download_real.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    sys.stderr.write("yfinance is required: pip install yfinance pandas\n")
    raise

# ── Configuration ───────────────────────────────────────────────────────────

START = "2015-01-01"
END = date.today().isoformat()

_DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "TSLA", "AMD", "AVGO",
    "ORCL", "CRWD", "PANW", "DDOG", "NET", "MDB", "TTD", "CELH", "LULU",
    "ENPH", "DECK", "LLY", "UNH", "ISRG", "TMO", "JPM", "V", "MA", "GS",
    "SPGI", "COST", "HD", "MCD", "WMT", "CMG", "XOM", "CVX", "SPY",
]

_HERE = os.path.dirname(os.path.abspath(__file__))
_UNIVERSE_FILE = os.path.join(_HERE, "universe.txt")
_OUT_DIR = os.path.join(_HERE, "real")


def load_universe() -> list[str]:
    """Read tickers from data/universe.txt if present, else use default list."""
    if os.path.isfile(_UNIVERSE_FILE):
        tickers: list[str] = []
        with open(_UNIVERSE_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    tickers.append(line.upper())
        if tickers:
            return tickers
    return list(_DEFAULT_UNIVERSE)


def download_one(ticker: str) -> pd.DataFrame | None:
    """Download adjusted OHLCV for a single ticker; return DataFrame or None."""
    df = yf.download(
        ticker,
        start=START,
        end=END,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if df is None or len(df) == 0:
        return None

    # yfinance may return a MultiIndex column frame when given a single ticker.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    cols = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return None

    out = df[cols].copy()
    out.index.name = "Date"
    out = out.dropna()
    return out if len(out) > 0 else None


def main() -> int:
    os.makedirs(_OUT_DIR, exist_ok=True)
    tickers = load_universe()
    print(f"Universe: {len(tickers)} tickers  range {START} .. {END}")
    print(f"Output dir: {_OUT_DIR}")

    ok, failed = [], []
    for ticker in tickers:
        try:
            df = download_one(ticker)
        except Exception as exc:  # noqa: BLE001 - skip on any failure
            print(f"  {ticker:6s} FAILED ({exc})")
            failed.append(ticker)
            continue

        if df is None or len(df) < 50:
            n = 0 if df is None else len(df)
            print(f"  {ticker:6s} SKIP (only {n} rows)")
            failed.append(ticker)
            continue

        path = os.path.join(_OUT_DIR, f"{ticker}.csv")
        df.to_csv(path)
        print(f"  {ticker:6s} OK   {len(df)} rows -> {os.path.basename(path)}")
        ok.append(ticker)

    print("\nSummary")
    print(f"  succeeded: {len(ok)}  -> {' '.join(ok)}")
    print(f"  failed:    {len(failed)} -> {' '.join(failed) if failed else '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
