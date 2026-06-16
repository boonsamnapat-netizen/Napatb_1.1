"""
Signal backtester + walk-forward weight tuning.

Replays the *exact same decision logic* the live engine uses, bar by bar with no
look-ahead, so we can measure the real win-rate / expectancy of the rules instead
of assuming one. The measured win-rate can then be fed back into money management
(config.signal.calibrated_win_rate) to make position sizing honest.

Trade model (matches the engine's plan):
  - enter at the signalled price when decision == ENTER (one position at a time),
  - scale out at TP1/TP2/TP3 by their allocations,
  - move stop to breakeven after the first TP fills (pro discipline),
  - exit remainder on stop or after a max hold.

Walk-forward: optimise the indicator weights on an in-sample window, then measure
performance only on the following out-of-sample window. Reported metrics are
out-of-sample — the honest number.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field

import pandas as pd

from src.signal import indicators as ind
from src.signal import levels as lv
from src.signal.signal_engine import DEFAULTS, SignalEngine, _clamp, score_timeframe

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_index: int
    exit_index: int
    direction: str
    entry: float
    stop: float
    realized_r: float
    outcome: str            # WIN / LOSS / BREAKEVEN / TIMEOUT
    confidence: float
    bars_held: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class BacktestMetrics:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_r: float = 0.0
    expectancy_r: float = 0.0       # mean R per trade
    profit_factor: float = 0.0
    total_r: float = 0.0
    max_drawdown_r: float = 0.0
    return_pct: float = 0.0         # compounded, given risk_per_trade_pct
    max_drawdown_pct: float = 0.0
    weights: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("win_rate", "avg_r", "expectancy_r", "profit_factor",
                  "total_r", "max_drawdown_r", "return_pct", "max_drawdown_pct"):
            d[k] = round(d[k], 4)
        return d


# Coarse weight candidates for walk-forward optimisation (normalised later).
def _weight_grid() -> list[dict]:
    presets = [
        (0.35, 0.30, 0.15, 0.20),   # balanced (default)
        (0.50, 0.30, 0.05, 0.15),   # trend-heavy
        (0.25, 0.45, 0.10, 0.20),   # momentum-heavy
        (0.40, 0.20, 0.25, 0.15),   # mean-reversion tilt
        (0.30, 0.30, 0.20, 0.20),   # even-ish
        (0.45, 0.35, 0.10, 0.10),   # trend+momentum
        (0.20, 0.30, 0.30, 0.20),   # volatility-aware
        (0.35, 0.25, 0.15, 0.25),   # volume-aware
    ]
    out = []
    for t, m, v, vol in presets:
        s = t + m + v + vol
        out.append(
            {"trend": t / s, "momentum": m / s, "volatility": v / s, "volume": vol / s}
        )
    return out


class SignalBacktester:
    def __init__(self, config: dict):
        self.config = config
        self.engine = SignalEngine(config)
        cfg = config.get("signal", {})
        bt = cfg.get("backtest", {})
        self.warmup = bt.get("warmup", 210)        # need EMA-200 + buffer
        self.max_hold = bt.get("max_hold", 60)     # bars before time-stop
        self.min_trades = bt.get("min_trades", 8)  # for optimiser to trust a window
        self.params = self.engine.indicator_params
        self.p = self.engine.p

    # ---- preparation ----------------------------------------------------
    def prepare(self, entry_df: pd.DataFrame, htf_df: pd.DataFrame | None):
        """Compute indicators once and align an HTF trend score to each bar."""
        ent_ind = ind.compute_all(entry_df, self.params)

        htf_aligned = pd.Series(0.0, index=ent_ind.index)
        if htf_df is not None and len(htf_df) >= 60:
            htf_ind = ind.compute_all(htf_df, self.params)
            scores = []
            for j in range(60, len(htf_ind)):
                scores.append(
                    (htf_ind.index[j], score_timeframe(htf_ind.iloc[: j + 1])["trend"])
                )
            if scores:
                htf_series = pd.Series(
                    [s for _, s in scores], index=[t for t, _ in scores]
                )
                # forward-fill the most recent completed HTF trend onto each bar
                htf_aligned = htf_series.reindex(
                    htf_series.index.union(ent_ind.index)
                ).ffill().reindex(ent_ind.index).fillna(0.0)
        return ent_ind, htf_aligned

    # ---- single backtest over a range -----------------------------------
    def backtest_range(
        self,
        ent_ind: pd.DataFrame,
        htf_aligned: pd.Series,
        weights: dict,
        start: int,
        end: int,
        risk_per_trade_pct: float = 1.0,
    ) -> BacktestMetrics:
        trades = self._collect_trades(ent_ind, htf_aligned, weights, start, end)
        return self._metrics(trades, weights, risk_per_trade_pct)

    def _simulate(
        self, ent_ind, i, direction, entry, stop, tps, confidence
    ) -> Trade | None:
        is_long = direction == "LONG"
        risk = abs(entry - stop)
        if risk <= 0 or not tps:
            return None

        remaining = 1.0
        realized_r = 0.0
        cur_stop = stop
        moved_be = False
        hit = [False] * len(tps)
        n = len(ent_ind)
        last_j = i

        for j in range(i + 1, min(i + 1 + self.max_hold, n)):
            bar = ent_ind.iloc[j]
            last_j = j
            low, high = float(bar["low"]), float(bar["high"])

            # Stop checked first (conservative: assume the adverse touch came first)
            stop_hit = (is_long and low <= cur_stop) or (not is_long and high >= cur_stop)
            if stop_hit:
                r = ((cur_stop - entry) if is_long else (entry - cur_stop)) / risk
                realized_r += remaining * r
                outcome = "BREAKEVEN" if moved_be else "LOSS"
                return Trade(i, j, direction, entry, stop, realized_r,
                             outcome, confidence, j - i)

            # Take-profits
            for k, tp in enumerate(tps):
                if hit[k]:
                    continue
                tp_hit = (is_long and high >= tp.price) or (
                    not is_long and low <= tp.price
                )
                if tp_hit:
                    alloc = tp.allocation_pct / 100.0
                    realized_r += alloc * tp.r_multiple
                    remaining -= alloc
                    hit[k] = True
                    if not moved_be:           # move to breakeven after first TP
                        cur_stop = entry
                        moved_be = True

            if remaining <= 1e-9:
                return Trade(i, j, direction, entry, stop, realized_r,
                             "WIN", confidence, j - i)

        # Time stop: close remainder at last close
        last_close = float(ent_ind.iloc[last_j]["close"])
        r = ((last_close - entry) if is_long else (entry - last_close)) / risk
        realized_r += remaining * r
        return Trade(i, last_j, direction, entry, stop, realized_r,
                     "TIMEOUT", confidence, last_j - i)

    # ---- metrics --------------------------------------------------------
    def _metrics(self, trades, weights, risk_pct) -> BacktestMetrics:
        m = BacktestMetrics(weights=dict(weights))
        if not trades:
            return m
        rs = [t.realized_r for t in trades]
        m.trades = len(trades)
        m.wins = sum(1 for r in rs if r > 1e-9)
        m.losses = sum(1 for r in rs if r < -1e-9)
        m.win_rate = m.wins / m.trades
        m.total_r = sum(rs)
        m.avg_r = m.total_r / m.trades
        m.expectancy_r = m.avg_r
        gross_win = sum(r for r in rs if r > 0)
        gross_loss = abs(sum(r for r in rs if r < 0))
        m.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

        # Equity curves
        equity_r, peak_r, dd_r = 0.0, 0.0, 0.0
        equity_pct, peak_pct, dd_pct = 1.0, 1.0, 0.0
        rf = risk_pct / 100.0
        for r in rs:
            equity_r += r
            peak_r = max(peak_r, equity_r)
            dd_r = min(dd_r, equity_r - peak_r)
            equity_pct *= (1 + rf * r)
            peak_pct = max(peak_pct, equity_pct)
            dd_pct = min(dd_pct, equity_pct / peak_pct - 1)
        m.max_drawdown_r = dd_r
        m.return_pct = (equity_pct - 1) * 100
        m.max_drawdown_pct = dd_pct * 100
        return m

    # ---- walk-forward ---------------------------------------------------
    def walk_forward(
        self,
        entry_df: pd.DataFrame,
        htf_df: pd.DataFrame | None,
        train: int = 500,
        test: int = 250,
        risk_per_trade_pct: float = 1.0,
        objective: str = "expectancy_r",
    ) -> dict:
        ent_ind, htf_aligned = self.prepare(entry_df, htf_df)
        grid = _weight_grid()
        n = len(ent_ind)

        oos_trades_all: list[Trade] = []
        windows = []
        start = self.warmup
        while start + train + test <= n:
            tr_s, tr_e = start, start + train
            te_s, te_e = tr_e, tr_e + test

            # optimise on in-sample
            best, best_m = None, None
            for w in grid:
                m = self.backtest_range(ent_ind, htf_aligned, w, tr_s, tr_e, risk_per_trade_pct)
                if m.trades < self.min_trades:
                    continue
                score = getattr(m, objective)
                if best_m is None or score > getattr(best_m, objective):
                    best, best_m = w, m
            if best is None:
                best = DEFAULTS["weights"]

            # evaluate out-of-sample
            oos = self.backtest_range(ent_ind, htf_aligned, best, te_s, te_e, risk_per_trade_pct)
            windows.append({
                "train_range": [tr_s, tr_e],
                "test_range": [te_s, te_e],
                "chosen_weights": {k: round(v, 3) for k, v in best.items()},
                "oos": oos.to_dict(),
            })
            # re-run to collect raw trades for combined metrics
            oos_trades_all += self._collect_trades(ent_ind, htf_aligned, best, te_s, te_e)
            start += test

        combined = self._metrics(oos_trades_all, {}, risk_per_trade_pct)
        return {
            "windows": windows,
            "combined_oos": combined.to_dict(),
            "calibrated_win_rate": round(combined.win_rate, 3) if combined.trades else None,
        }

    def _collect_trades(self, ent_ind, htf_aligned, weights, start, end) -> list[Trade]:
        # Mirror backtest_range but return trades (kept separate to keep that hot
        # loop returning metrics only).
        trades: list[Trade] = []
        i = max(start, self.warmup)
        end = min(end, len(ent_ind) - 1)
        while i < end:
            scores = score_timeframe(ent_ind.iloc[: i + 1])
            composite = _clamp(sum(weights[k] * scores[k] for k in weights))
            threshold = self.p["entry_threshold"]
            if composite >= threshold:
                direction = "LONG"
            elif composite <= -threshold:
                direction = "SHORT"
            else:
                i += 1
                continue
            htf_trend = float(htf_aligned.iloc[i])
            confidence = abs(composite) * 70.0
            if (direction == "LONG" and htf_trend > 0.2) or (direction == "SHORT" and htf_trend < -0.2):
                confidence += 18
            elif (direction == "LONG" and htf_trend < -0.2) or (direction == "SHORT" and htf_trend > 0.2):
                confidence -= 25
            if scores["snapshot"]["rvol"] >= 1.3:
                confidence += 6
            confidence = max(0.0, min(100.0, confidence))
            if confidence < self.p["min_confidence"]:
                i += 1
                continue
            view = ent_ind.iloc[: i + 1]
            price = float(view["close"].iloc[-1])
            atr_val = float(view["atr"].iloc[-1])
            all_levels = lv.find_levels(view, price, atr_val)
            entry, _z, stop = self.engine._entry_and_stop(direction, price, atr_val, all_levels)
            tps = self.engine._take_profits(direction, entry, stop, all_levels)
            trade = self._simulate(ent_ind, i, direction, entry, stop, tps, confidence)
            if trade is not None:
                trades.append(trade)
                i = trade.exit_index + 1
            else:
                i += 1
        return trades

    # ---- simple (non-walk-forward) run ----------------------------------
    def run(
        self,
        entry_df: pd.DataFrame,
        htf_df: pd.DataFrame | None,
        weights: dict | None = None,
        risk_per_trade_pct: float = 1.0,
    ) -> BacktestMetrics:
        ent_ind, htf_aligned = self.prepare(entry_df, htf_df)
        w = weights or self.engine.weights
        return self.backtest_range(
            ent_ind, htf_aligned, w, self.warmup, len(ent_ind) - 1, risk_per_trade_pct
        )
