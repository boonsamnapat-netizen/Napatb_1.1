"""
Portfolio Backtesting Engine
==============================
Event-driven daily simulation:
  - Position sizing: ATR-based 1% risk per trade
  - Exits: hard stop -8%, trailing stop, time stop (no take-profit ceiling)
  - Max 10 concurrent positions
  - Transaction costs + slippage
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import config


@dataclass
class Position:
    ticker:      str
    entry_date:  pd.Timestamp
    entry_price: float
    shares:      int
    stop_price:  float
    highest:     float
    trailing_on: bool = False
    strategy:    str  = ''


@dataclass
class Trade:
    ticker:      str
    entry_date:  pd.Timestamp
    exit_date:   pd.Timestamp
    entry_price: float
    exit_price:  float
    shares:      int
    pnl:         float
    pnl_pct:     float
    exit_reason: str
    strategy:    str

    @property
    def duration_days(self) -> int:
        return (self.exit_date - self.entry_date).days


class Portfolio:

    def __init__(self, initial_capital: float = config.INITIAL_CAPITAL):
        self.cash             = initial_capital
        self.initial_capital  = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades:    List[Trade]          = []
        self.equity_curve: List[dict]        = []

    # ── Helpers ───────────────────────────────────────────────────────────

    def total_equity(self, prices: Dict[str, float]) -> float:
        pos_val = sum(
            p.shares * prices.get(p.ticker, p.entry_price)
            for p in self.positions.values()
        )
        return self.cash + pos_val

    def _position_shares(self, price: float, equity: float) -> int:
        """1% risk, stop at -8% → position size."""
        stop_dist = price * config.STOP_LOSS_PCT
        if stop_dist <= 0:
            return 0
        shares = int((equity * config.RISK_PER_TRADE) / stop_dist)
        # Cap at 12% of equity per name
        max_shares = int(equity * 0.15 / price)
        return max(0, min(shares, max_shares))

    # ── Orders ────────────────────────────────────────────────────────────

    def buy(self, ticker: str, date: pd.Timestamp, price: float, strategy: str) -> bool:
        if ticker in self.positions:
            return False
        if len(self.positions) >= config.MAX_POSITIONS:
            return False

        equity = self.total_equity({})
        shares = self._position_shares(price, equity)
        if shares <= 0:
            return False

        cost = shares * price * (1 + config.COMMISSION + config.SLIPPAGE)
        if cost > self.cash:
            shares = max(1, int(self.cash / (price * (1 + config.COMMISSION + config.SLIPPAGE))))
            cost   = shares * price * (1 + config.COMMISSION + config.SLIPPAGE)
            if cost > self.cash:
                return False

        self.cash -= cost
        self.positions[ticker] = Position(
            ticker      = ticker,
            entry_date  = date,
            entry_price = price,
            shares      = shares,
            stop_price  = price * (1 - config.STOP_LOSS_PCT),
            highest     = price,
            strategy    = strategy,
        )
        return True

    def sell(self, ticker: str, date: pd.Timestamp, price: float, reason: str) -> None:
        if ticker not in self.positions:
            return
        pos = self.positions.pop(ticker)

        proceeds = pos.shares * price * (1 - config.COMMISSION - config.SLIPPAGE)
        self.cash += proceeds

        pnl     = proceeds - pos.shares * pos.entry_price
        pnl_pct = (price - pos.entry_price) / pos.entry_price

        self.trades.append(Trade(
            ticker      = ticker,
            entry_date  = pos.entry_date,
            exit_date   = date,
            entry_price = pos.entry_price,
            exit_price  = price,
            shares      = pos.shares,
            pnl         = pnl,
            pnl_pct     = pnl_pct,
            exit_reason = reason,
            strategy    = pos.strategy,
        ))

    # ── Daily Update ──────────────────────────────────────────────────────

    def update_exits(self, date: pd.Timestamp, ohlc: Dict[str, dict]) -> None:
        """Check stop / trailing / time-stop for all open positions.

        Take-profit ceiling removed (Phase 1B): trailing stop is the sole
        upside exit so winners can run to +50-200%.
        """
        to_close: List[tuple] = []

        for ticker, pos in self.positions.items():
            bar = ohlc.get(ticker)
            if bar is None:
                continue

            op, low, high, close = bar['Open'], bar['Low'], bar['High'], bar['Close']

            # --- Exit checks run FIRST, against the stop as it stood at the
            #     start of the day (no same-day look-ahead from today's High). ---

            # Hard stop / trailing stop (use Low of day)
            if low <= pos.stop_price:
                # Overnight gap-down through the stop fills at the (worse) Open.
                exit_px = min(pos.stop_price, op)
                to_close.append((ticker, exit_px, 'STOP_LOSS'))
                continue

            # Time stop: exit if held > TIME_STOP_DAYS with gain < TIME_STOP_MIN_GAIN
            time_held = (date - pos.entry_date).days
            if time_held > config.TIME_STOP_DAYS:
                gain_pct = (close - pos.entry_price) / pos.entry_price
                if gain_pct < config.TIME_STOP_MIN_GAIN:
                    to_close.append((ticker, close, 'TIME_STOP'))
                    continue

            # --- Survivors: update trailing state for use on the NEXT day. ---
            if high > pos.highest:
                pos.highest = high

            gain = (pos.highest - pos.entry_price) / pos.entry_price
            if gain >= config.TRAILING_START:
                pos.trailing_on = True

            if pos.trailing_on:
                trail_stop = pos.highest * (1 - config.TRAILING_STOP)
                pos.stop_price = max(pos.stop_price, trail_stop)

        for ticker, px, reason in to_close:
            self.sell(ticker, date, px, reason)


# ── Engine ─────────────────────────────────────────────────────────────────

class BacktestEngine:

    def __init__(
        self,
        stock_data:  Dict[str, pd.DataFrame],
        market_data: Optional[pd.DataFrame] = None,
    ):
        self.stock_data  = stock_data
        self.market_data = market_data
        self.portfolio   = Portfolio()

    def run(
        self,
        signals_by_date: Dict[pd.Timestamp, List[dict]],
        start_date: str = config.BACKTEST_START,
        end_date:   str = config.BACKTEST_END,
    ) -> Portfolio:
        """
        signals_by_date: {date: [{'ticker', 'score', 'strategy'}, ...]}
        Iterates every trading day, processes exits first then entries.
        """
        all_dates = sorted({
            d for df in self.stock_data.values()
            for d in df.index
            if start_date <= str(d)[:10] <= end_date
        })

        # Cooldown tracker: after a STOP_LOSS exit, block re-entry for COOLDOWN_DAYS
        stop_cooldown: Dict[str, pd.Timestamp] = {}

        for date in all_dates:
            # Build today's OHLC snapshot
            ohlc: Dict[str, dict] = {}
            prices: Dict[str, float] = {}
            for ticker, df in self.stock_data.items():
                if date in df.index:
                    row = df.loc[date]
                    ohlc[ticker]   = {'Open': row['Open'], 'High': row['High'],
                                      'Low': row['Low'],  'Close': row['Close']}
                    prices[ticker] = float(row['Close'])

            # 1. Process exits
            self.portfolio.update_exits(date, ohlc)

            # Update cooldown tracker: record any STOP_LOSS exits that fired today
            for trade in self.portfolio.trades:
                if trade.exit_date == date and trade.exit_reason == 'STOP_LOSS':
                    stop_cooldown[trade.ticker] = date

            # 2. Enter new positions (top-scored signals)
            if date in signals_by_date:
                day_sigs = sorted(signals_by_date[date], key=lambda x: x['score'], reverse=True)
                for sig in day_sigs:
                    ticker = sig['ticker']
                    if ticker not in prices:
                        continue
                    if len(self.portfolio.positions) >= config.MAX_POSITIONS:
                        break
                    # Skip if ticker is in cooldown after a stop-loss
                    if ticker in stop_cooldown:
                        days_since_stop = (date - stop_cooldown[ticker]).days
                        if days_since_stop < config.COOLDOWN_DAYS:
                            continue
                    self.portfolio.buy(ticker, date, prices[ticker], sig['strategy'])

            # 3. Record equity
            eq = self.portfolio.total_equity(prices)
            self.portfolio.equity_curve.append({'date': date, 'equity': eq})

        return self.portfolio
