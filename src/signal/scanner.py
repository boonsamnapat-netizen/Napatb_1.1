"""
Market scanner — the "setup-first" view.

Instead of asking "is BTC a good trade right now?", the scanner asks "across the
whole market, which coins have the best setup right now?". It runs the signal
engine over a universe of symbols, filters to the ones that pass, and ranks them.

Philosophy stays the same: we are NOT looking for whatever is pumping hardest
(that is how the crowd buys tops). We rank by setup quality — confluence,
risk/reward and expected value — and skip anything sitting in an event blackout.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd

from src.signal.market_data import MarketData, normalize_symbol, resample_ohlcv
from src.signal.signal_engine import Signal, SignalEngine

logger = logging.getLogger(__name__)

# Things we never want in a crypto universe: leveraged tokens & stable/stable.
_EXCLUDE_TOKENS = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S")
_STABLES = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USD"}

# Rank order for decisions (higher = surface first).
_DECISION_RANK = {"ENTER": 3, "WAIT": 2, "AVOID": 1, "": 0}


@dataclass
class ScanRow:
    symbol: str
    decision: str
    direction: str
    confidence: float
    price: float
    entry: float | None
    stop_loss: float | None
    blended_rr: float
    expected_value_r: float
    composite: float
    rank_score: float
    warnings: int
    signal: Signal

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "signal"}
        return d


class Scanner:
    def __init__(self, config: dict):
        self.config = config
        self.engine = SignalEngine(config)
        self.md = MarketData(config)
        cfg = config.get("signal", {}).get("scanner", {})
        self.quote = cfg.get("quote", "USDT")
        self.top_n = cfg.get("universe_size", 50)
        self.min_quote_volume = cfg.get("min_quote_volume", 5_000_000)
        self.max_workers = cfg.get("max_workers", 8)
        self.candles = cfg.get("candles", 400)

    # ---- universe (live, via ccxt) --------------------------------------
    def fetch_universe(self) -> list[str]:
        """Top symbols by 24h quote volume on the configured exchange."""
        ex = self.md._get_exchange()
        tickers = ex.fetch_tickers()
        rows = []
        for sym, t in tickers.items():
            if not sym.endswith("/" + self.quote):
                continue
            base = sym.split("/")[0]
            if base in _STABLES or any(tok in base for tok in _EXCLUDE_TOKENS):
                continue
            qv = t.get("quoteVolume") or 0
            if qv >= self.min_quote_volume:
                rows.append((sym, qv))
        rows.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in rows[: self.top_n]]

    # ---- ranking --------------------------------------------------------
    @staticmethod
    def _rank_score(sig: Signal) -> float:
        pp = sig.position_plan or {}
        ev = pp.get("expected_value_r", 0.0)
        rr = pp.get("blended_rr", 0.0)
        base = _DECISION_RANK.get(sig.decision, 0) * 1000
        # within a decision tier, reward confidence, EV and R:R
        return base + sig.confidence + ev * 8 + min(rr, 5) * 2

    def _to_row(self, sig: Signal) -> ScanRow:
        pp = sig.position_plan or {}
        return ScanRow(
            symbol=sig.symbol,
            decision=sig.decision,
            direction=sig.direction,
            confidence=round(sig.confidence, 1),
            price=round(sig.current_price, 8),
            entry=sig.entry,
            stop_loss=sig.stop_loss,
            blended_rr=pp.get("blended_rr", 0.0),
            expected_value_r=pp.get("expected_value_r", 0.0),
            composite=round(sig.composite_score, 3),
            rank_score=round(self._rank_score(sig), 2),
            warnings=len(sig.warnings),
            signal=sig,
        )

    # ---- scanning -------------------------------------------------------
    def scan_universe(
        self,
        universe: dict[str, pd.DataFrame],
        htf_rule: str = "4h",
        use_news: bool = False,
        account_size: float | None = None,
        risk_per_trade_pct: float | None = None,
    ) -> list[ScanRow]:
        """
        Run the engine over a {symbol: entry_df} universe. The higher timeframe is
        derived by resampling each entry frame (so one dataset drives both TFs).
        """
        def work(item):
            symbol, entry_df = item
            try:
                htf_df = resample_ohlcv(entry_df, htf_rule)
                sig = self.engine.analyze(
                    symbol=symbol,
                    entry_df=entry_df,
                    htf_df=htf_df,
                    use_news=use_news,
                    account_size=account_size,
                    risk_per_trade_pct=risk_per_trade_pct,
                )
                return self._to_row(sig)
            except Exception as e:  # noqa: BLE001
                logger.warning("scan failed for %s: %s", symbol, e)
                return None

        rows: list[ScanRow] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(work, item) for item in universe.items()]
            for fut in as_completed(futures):
                r = fut.result()
                if r is not None:
                    rows.append(r)

        rows.sort(key=lambda r: r.rank_score, reverse=True)
        return rows

    def scan_live(
        self,
        symbols: list[str] | None = None,
        entry_tf: str | None = None,
        htf_tf: str | None = None,
        use_news: bool = False,
        account_size: float | None = None,
        risk_per_trade_pct: float | None = None,
    ) -> list[ScanRow]:
        """Fetch each symbol's OHLCV live (ccxt) and scan. One exchange per worker."""
        entry_tf = entry_tf or self.engine.p["entry_timeframe"]
        htf_tf = htf_tf or self.engine.p["htf_timeframe"]
        symbols = symbols or self.fetch_universe()

        local = __import__("threading").local()

        def get_md() -> MarketData:
            if not hasattr(local, "md"):
                local.md = MarketData(self.config)
            return local.md

        def work(symbol):
            try:
                md = get_md()
                entry_df = md.fetch(symbol, entry_tf, self.candles)
                htf_df = md.fetch(symbol, htf_tf, max(120, self.candles // 4))
                sig = self.engine.analyze(
                    symbol=symbol, entry_df=entry_df, htf_df=htf_df,
                    use_news=use_news, account_size=account_size,
                    risk_per_trade_pct=risk_per_trade_pct,
                )
                return self._to_row(sig)
            except Exception as e:  # noqa: BLE001
                logger.warning("scan failed for %s: %s", symbol, e)
                return None

        rows: list[ScanRow] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for fut in as_completed([pool.submit(work, s) for s in symbols]):
                r = fut.result()
                if r is not None:
                    rows.append(r)
        rows.sort(key=lambda r: r.rank_score, reverse=True)
        return rows
