"""
Validate trade setups against historical OHLCV data via ccxt.
Determines outcome: WIN / LOSS / PARTIAL / PENDING / INVALID
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import ccxt
import ccxt.pro as ccxtpro
import pandas as pd

from src.parser.discord_parser import TradeSetup

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    message_id: str
    symbol: str
    direction: str
    entry: Optional[float]
    stop_loss: Optional[float]
    take_profits: list[float]
    outcome: str = "PENDING"      # WIN / LOSS / PARTIAL / PENDING / INVALID
    hit_entry: bool = False
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    tp_hit_index: int = -1        # which TP was hit (-1 = none)
    pnl_pct: float = 0.0          # % PnL from entry
    risk_reward_actual: float = 0.0
    risk_reward_planned: float = 0.0
    max_adverse_excursion: float = 0.0   # worst % drawdown after entry
    max_favorable_excursion: float = 0.0  # best % gain after entry
    candles_to_exit: int = 0
    notes: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class BacktestEngine:
    def __init__(self, config: dict):
        cfg = config.get("backtest", {})
        # "crypto" → ccxt exchange data; "stock"/"equity" → yfinance/CSV cache
        self.market = cfg.get("market", "crypto").lower()
        self.exchange_id = cfg.get("exchange", "binance")
        self.default_tf = cfg.get("default_timeframe", "1h")
        self.lookahead = cfg.get("candles_lookahead", 200)
        self.slippage = cfg.get("slippage_pct", 0.05) / 100
        self._exchange = None

    @property
    def is_stock(self) -> bool:
        return self.market in ("stock", "stocks", "equity", "equities")

    def _get_exchange(self):
        if self._exchange is None:
            exchange_class = getattr(ccxt, self.exchange_id)
            self._exchange = exchange_class({"enableRateLimit": True})
        return self._exchange

    def _fetch_ohlcv(
        self, symbol: str, timeframe: str, since_ts: int, limit: int
    ) -> pd.DataFrame:
        ex = self._get_exchange()
        try:
            raw = ex.fetch_ohlcv(symbol, timeframe, since=since_ts, limit=limit)
        except ccxt.BadSymbol:
            # Try alternate format
            alt = symbol.replace("USDT", "/USDT")
            raw = ex.fetch_ohlcv(alt, timeframe, since=since_ts, limit=limit)

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.set_index("ts")

    def _fetch_ohlcv_equity(
        self, symbol: str, timeframe: str, since_ts: int, limit: int
    ) -> pd.DataFrame:
        """Fetch US equity OHLCV via the cache/yfinance provider."""
        from src.data.equity_data import get_ohlcv, to_yf_interval

        start_dt = datetime.fromtimestamp(since_ts / 1000, tz=timezone.utc)
        return get_ohlcv(
            symbol,
            start=start_dt,
            interval=to_yf_interval(timeframe),
            limit=limit,
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTCUSDT → BTC/USDT for ccxt (crypto only)."""
        if "/" in symbol:
            return symbol.upper()
        if symbol.endswith("USDT"):
            return symbol[:-4] + "/USDT"
        return symbol + "/USDT"

    def _parse_timestamp(self, ts_str: str) -> int:
        """Parse ISO timestamp to milliseconds."""
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except Exception:
            return int(datetime.now(timezone.utc).timestamp() * 1000)

    def _simulate(self, setup: TradeSetup, df: pd.DataFrame) -> BacktestResult:
        result = BacktestResult(
            message_id=setup.message_id,
            symbol=setup.symbol,
            direction=setup.direction,
            entry=setup.entry,
            stop_loss=setup.stop_loss,
            take_profits=setup.take_profits,
        )

        if df.empty or setup.entry is None:
            result.outcome = "INVALID"
            result.notes = "No price data or missing entry"
            return result

        entry = setup.entry
        sl = setup.stop_loss
        tps = setup.take_profits
        is_long = setup.direction == "LONG"

        # Apply slippage
        if is_long:
            entry *= 1 + self.slippage
        else:
            entry *= 1 - self.slippage

        # Calculate planned RR
        if sl and tps:
            risk = abs(entry - sl)
            reward = abs(tps[-1] - entry)
            result.risk_reward_planned = round(reward / risk, 2) if risk > 0 else 0.0

        hit_entry = False
        mfe = 0.0
        mae = 0.0

        for i, (ts, row) in enumerate(df.iterrows()):
            # Check entry
            if not hit_entry:
                if is_long and row["low"] <= entry:
                    hit_entry = True
                elif not is_long and row["high"] >= entry:
                    hit_entry = True
                if not hit_entry:
                    continue

            result.hit_entry = True

            # Price relative to entry
            if is_long:
                candle_mfe = (row["high"] - entry) / entry * 100
                candle_mae = (entry - row["low"]) / entry * 100
            else:
                candle_mfe = (entry - row["low"]) / entry * 100
                candle_mae = (row["high"] - entry) / entry * 100

            mfe = max(mfe, candle_mfe)
            mae = max(mae, candle_mae)

            # Check SL
            if sl is not None:
                if is_long and row["low"] <= sl:
                    result.outcome = "LOSS"
                    result.exit_price = sl
                    result.exit_time = str(ts)
                    result.pnl_pct = round((sl - entry) / entry * 100, 3)
                    result.candles_to_exit = i
                    break
                elif not is_long and row["high"] >= sl:
                    result.outcome = "LOSS"
                    result.exit_price = sl
                    result.exit_time = str(ts)
                    result.pnl_pct = round((entry - sl) / entry * 100, 3)
                    result.candles_to_exit = i
                    break

            # Check TPs (nearest first)
            for tp_idx, tp in enumerate(tps):
                if is_long and row["high"] >= tp:
                    result.outcome = "WIN" if tp_idx == len(tps) - 1 else "PARTIAL"
                    result.exit_price = tp
                    result.exit_time = str(ts)
                    result.tp_hit_index = tp_idx
                    result.pnl_pct = round((tp - entry) / entry * 100, 3)
                    result.candles_to_exit = i
                    if sl:
                        risk = abs(entry - sl)
                        result.risk_reward_actual = round(
                            abs(tp - entry) / risk, 2
                        ) if risk > 0 else 0.0
                    break
                elif not is_long and row["low"] <= tp:
                    result.outcome = "WIN" if tp_idx == len(tps) - 1 else "PARTIAL"
                    result.exit_price = tp
                    result.exit_time = str(ts)
                    result.tp_hit_index = tp_idx
                    result.pnl_pct = round((entry - tp) / entry * 100, 3)
                    result.candles_to_exit = i
                    if sl:
                        risk = abs(entry - sl)
                        result.risk_reward_actual = round(
                            abs(entry - tp) / risk, 2
                        ) if risk > 0 else 0.0
                    break

            if result.outcome != "PENDING":
                break

        result.max_favorable_excursion = round(mfe, 3)
        result.max_adverse_excursion = round(mae, 3)

        return result

    def run(self, setups: list[TradeSetup]) -> list[BacktestResult]:
        """Run backtest for all setups."""
        results = []
        for setup in setups:
            if not setup.symbol or not setup.entry:
                results.append(
                    BacktestResult(
                        message_id=setup.message_id,
                        symbol=setup.symbol,
                        direction=setup.direction,
                        entry=setup.entry,
                        stop_loss=setup.stop_loss,
                        take_profits=setup.take_profits,
                        outcome="INVALID",
                        notes="Missing symbol or entry",
                    )
                )
                continue

            timeframe = setup.timeframe if setup.timeframe else self.default_tf
            since_ts = self._parse_timestamp(setup.timestamp)

            try:
                if self.is_stock:
                    df = self._fetch_ohlcv_equity(
                        setup.symbol.upper(), timeframe, since_ts, self.lookahead
                    )
                else:
                    ccxt_symbol = self._normalize_symbol(setup.symbol)
                    df = self._fetch_ohlcv(
                        ccxt_symbol, timeframe, since_ts, self.lookahead
                    )
                result = self._simulate(setup, df)
                results.append(result)
                logger.info(
                    "%-12s %-5s %-8s → %s",
                    setup.symbol, setup.direction, setup.pattern or "-", result.outcome,
                )
            except Exception as e:
                logger.warning("Backtest failed for %s: %s", setup.symbol, e)
                results.append(
                    BacktestResult(
                        message_id=setup.message_id,
                        symbol=setup.symbol,
                        direction=setup.direction,
                        entry=setup.entry,
                        stop_loss=setup.stop_loss,
                        take_profits=setup.take_profits,
                        outcome="INVALID",
                        notes=str(e),
                    )
                )

        return results
