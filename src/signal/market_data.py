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
