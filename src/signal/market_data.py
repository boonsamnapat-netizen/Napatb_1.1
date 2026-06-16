"""
Market data access via ccxt, with multi-timeframe support and an offline demo
generator so the whole pipeline can be exercised without a network connection.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str) -> str:
    """BTCUSDT / btc -> BTC/USDT for ccxt."""
    s = symbol.upper().strip()
    if "/" in s:
        return s
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[:-len(quote)]}/{quote}"
    return f"{s}/USDT"


class MarketData:
    def __init__(self, config: dict):
        cfg = config.get("backtest", {}) | config.get("signal", {}).get("data", {})
        self.exchange_id = cfg.get("exchange", "binance")
        self._exchange = None

    def _get_exchange(self):
        if self._exchange is None:
            import ccxt

            exchange_class = getattr(ccxt, self.exchange_id)
            self._exchange = exchange_class({"enableRateLimit": True})
        return self._exchange

    def fetch(self, symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
        """Fetch the most recent `limit` candles for a timeframe."""
        ex = self._get_exchange()
        ccxt_symbol = normalize_symbol(symbol)
        raw = ex.fetch_ohlcv(ccxt_symbol, timeframe, limit=limit)
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(
            raw, columns=["ts", "open", "high", "low", "close", "volume"]
        )
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.set_index("ts")

    def fetch_multi(
        self, symbol: str, timeframes: list[str], limit: int = 400
    ) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for tf in timeframes:
            try:
                out[tf] = self.fetch(symbol, tf, limit)
            except Exception as e:  # noqa: BLE001
                logger.warning("fetch %s %s failed: %s", symbol, tf, e)
                out[tf] = pd.DataFrame()
        return out


def _find_col(columns, names) -> str | None:
    for c in columns:
        if str(c).lower().strip() in names:
            return c
    for c in columns:
        cl = str(c).lower().strip()
        if any(cl.endswith(sep + n) for n in names for sep in (".", "_", " ", "-")):
            return c
    return None


def normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce an arbitrary CSV frame into an OHLCV frame indexed by UTC time."""
    date_col = _find_col(df.columns, {"date", "time", "timestamp", "datetime", "ts"})
    o = _find_col(df.columns, {"open"})
    h = _find_col(df.columns, {"high"})
    low = _find_col(df.columns, {"low"})
    c = _find_col(df.columns, {"close", "price", "priceusd"})
    v = _find_col(df.columns, {"volume", "vol", "volumefrom"})
    if not (o and h and low and c):
        raise ValueError(
            f"CSV missing OHLC columns (open={o}, high={h}, low={low}, close={c})"
        )

    out = pd.DataFrame()
    out["open"] = pd.to_numeric(df[o], errors="coerce")
    out["high"] = pd.to_numeric(df[h], errors="coerce")
    out["low"] = pd.to_numeric(df[low], errors="coerce")
    out["close"] = pd.to_numeric(df[c], errors="coerce")
    out["volume"] = pd.to_numeric(df[v], errors="coerce") if v else 0.0

    if date_col is not None:
        out.index = pd.to_datetime(df[date_col], utc=True, errors="coerce")
        out = out[out.index.notna()]
    return out.dropna(subset=["open", "high", "low", "close"]).sort_index()


def load_csv(source: str, symbol: str | None = None) -> pd.DataFrame:
    """
    Load OHLCV from a local path or http(s) URL. If the file has a symbol/name
    column and `symbol` is given, keep only that symbol's rows. pandas reads URLs
    directly, so this works with e.g. raw.githubusercontent.com datasets.
    """
    df = pd.read_csv(source)
    sym_col = _find_col(df.columns, {"symbol", "name", "ticker", "asset"})
    if sym_col is not None and symbol:
        df = df[df[sym_col].astype(str).str.upper() == symbol.upper()]
    return normalize_ohlcv_frame(df)


def load_csv_universe(source: str, min_bars: int = 60) -> dict[str, pd.DataFrame]:
    """Load a multi-symbol CSV (with a symbol/name column) into {symbol: frame}."""
    df = pd.read_csv(source)
    sym_col = _find_col(df.columns, {"symbol", "name", "ticker", "asset"})
    if sym_col is None:
        raise ValueError("CSV has no symbol/name column for a universe load")
    out: dict[str, pd.DataFrame] = {}
    for sym, g in df.groupby(sym_col):
        try:
            frame = normalize_ohlcv_frame(g)
            if len(frame) >= min_bars:
                out[str(sym).upper()] = frame
        except ValueError:
            continue
    return out


def load_csv_dir(directory: str, min_bars: int = 60) -> dict[str, pd.DataFrame]:
    """Load every *.csv in a directory as {FILENAME_STEM: ohlcv_frame}."""
    import pathlib

    out: dict[str, pd.DataFrame] = {}
    for p in sorted(pathlib.Path(directory).glob("*.csv")):
        try:
            frame = load_csv(str(p))
            if len(frame) >= min_bars:
                out[p.stem.upper()] = frame
        except Exception:  # noqa: BLE001
            continue
    return out


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate to a higher timeframe (e.g. '4h', 'D', 'W')."""
    agg = {"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"}
    return df.resample(rule).agg(agg).dropna(subset=["open", "high", "low", "close"])


def generate_demo_ohlcv(
    bars: int = 400,
    start_price: float = 100.0,
    seed: int | None = 7,
    trend: float = 0.0008,
    vol: float = 0.012,
    freq: str = "1h",
) -> pd.DataFrame:
    """Synthetic but realistic-looking OHLCV (geometric random walk with drift)."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, vol, bars)
    close = start_price * np.exp(np.cumsum(returns))

    # Build candles around the close path.
    high_noise = np.abs(rng.normal(0, vol, bars))
    low_noise = np.abs(rng.normal(0, vol, bars))
    open_ = np.empty(bars)
    open_[0] = start_price
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) * (1 + high_noise)
    low = np.minimum(open_, close) * (1 - low_noise)
    base_vol = rng.lognormal(mean=10.0, sigma=0.4, size=bars)
    volume = base_vol * (1 + 3 * np.abs(returns) / vol)

    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("h"), periods=bars, freq=freq)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
