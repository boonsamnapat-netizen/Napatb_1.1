"""
Calculate win rate, RR ratio, and performance metrics from backtest results.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from src.backtest.backtest_engine import BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class PerformanceStats:
    total_setups: int = 0
    valid_setups: int = 0         # hit entry
    wins: int = 0
    losses: int = 0
    partials: int = 0
    pending: int = 0
    win_rate: float = 0.0
    avg_rr_planned: float = 0.0
    avg_rr_actual: float = 0.0
    avg_pnl_pct: float = 0.0
    avg_candles_to_exit: float = 0.0
    avg_mfe: float = 0.0          # max favorable excursion
    avg_mae: float = 0.0          # max adverse excursion
    expectancy: float = 0.0       # win_rate * avg_win - loss_rate * avg_loss
    by_symbol: dict = field(default_factory=dict)
    by_direction: dict = field(default_factory=dict)
    by_pattern: dict = field(default_factory=dict)
    by_timeframe: dict = field(default_factory=dict)
    best_symbol: str = ""
    worst_symbol: str = ""

    def to_dict(self) -> dict:
        return {
            "total_setups": self.total_setups,
            "valid_setups": self.valid_setups,
            "wins": self.wins,
            "losses": self.losses,
            "partials": self.partials,
            "pending": self.pending,
            "win_rate": round(self.win_rate, 4),
            "avg_rr_planned": round(self.avg_rr_planned, 3),
            "avg_rr_actual": round(self.avg_rr_actual, 3),
            "avg_pnl_pct": round(self.avg_pnl_pct, 3),
            "avg_candles_to_exit": round(self.avg_candles_to_exit, 1),
            "avg_mfe": round(self.avg_mfe, 3),
            "avg_mae": round(self.avg_mae, 3),
            "expectancy": round(self.expectancy, 4),
            "by_symbol": self.by_symbol,
            "by_direction": self.by_direction,
            "by_pattern": self.by_pattern,
            "by_timeframe": self.by_timeframe,
            "best_symbol": self.best_symbol,
            "worst_symbol": self.worst_symbol,
        }


def _group_stats(results: list[BacktestResult], key_fn) -> dict:
    groups = defaultdict(list)
    for r in results:
        k = key_fn(r)
        if k:
            groups[k].append(r)

    out = {}
    for k, group in groups.items():
        resolved = [r for r in group if r.outcome in ("WIN", "LOSS", "PARTIAL")]
        wins = sum(1 for r in resolved if r.outcome in ("WIN", "PARTIAL"))
        losses = sum(1 for r in resolved if r.outcome == "LOSS")
        wr = wins / len(resolved) if resolved else 0.0
        avg_pnl = (
            sum(r.pnl_pct for r in resolved) / len(resolved) if resolved else 0.0
        )
        out[k] = {
            "count": len(group),
            "resolved": len(resolved),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wr, 4),
            "avg_pnl_pct": round(avg_pnl, 3),
        }
    return dict(sorted(out.items(), key=lambda x: -x[1]["win_rate"]))


def compute_stats(results: list[BacktestResult]) -> PerformanceStats:
    stats = PerformanceStats()
    stats.total_setups = len(results)

    resolved = [r for r in results if r.outcome in ("WIN", "LOSS", "PARTIAL")]
    entered = [r for r in results if r.hit_entry]
    wins = [r for r in resolved if r.outcome in ("WIN", "PARTIAL")]
    losses = [r for r in resolved if r.outcome == "LOSS"]

    stats.valid_setups = len(entered)
    stats.wins = len(wins)
    stats.losses = len(losses)
    stats.partials = sum(1 for r in resolved if r.outcome == "PARTIAL")
    stats.pending = sum(1 for r in results if r.outcome == "PENDING")

    if resolved:
        stats.win_rate = len(wins) / len(resolved)
        stats.avg_pnl_pct = sum(r.pnl_pct for r in resolved) / len(resolved)

    rr_planned = [r.risk_reward_planned for r in resolved if r.risk_reward_planned > 0]
    rr_actual = [r.risk_reward_actual for r in resolved if r.risk_reward_actual > 0]
    stats.avg_rr_planned = sum(rr_planned) / len(rr_planned) if rr_planned else 0.0
    stats.avg_rr_actual = sum(rr_actual) / len(rr_actual) if rr_actual else 0.0

    candles = [r.candles_to_exit for r in resolved if r.candles_to_exit > 0]
    stats.avg_candles_to_exit = sum(candles) / len(candles) if candles else 0.0

    mfe_vals = [r.max_favorable_excursion for r in entered]
    mae_vals = [r.max_adverse_excursion for r in entered]
    stats.avg_mfe = sum(mfe_vals) / len(mfe_vals) if mfe_vals else 0.0
    stats.avg_mae = sum(mae_vals) / len(mae_vals) if mae_vals else 0.0

    # Expectancy = WR * avg_win - LR * avg_loss
    if wins and losses:
        avg_win = sum(r.pnl_pct for r in wins) / len(wins)
        avg_loss = abs(sum(r.pnl_pct for r in losses) / len(losses))
        loss_rate = 1 - stats.win_rate
        stats.expectancy = stats.win_rate * avg_win - loss_rate * avg_loss

    stats.by_symbol = _group_stats(results, lambda r: r.symbol)
    stats.by_direction = _group_stats(results, lambda r: r.direction)
    stats.by_pattern = _group_stats(results, lambda r: r.outcome)
    stats.by_timeframe = _group_stats(results, lambda r: "")

    if stats.by_symbol:
        best = max(stats.by_symbol.items(), key=lambda x: x[1]["win_rate"])
        worst = min(stats.by_symbol.items(), key=lambda x: x[1]["win_rate"])
        stats.best_symbol = best[0]
        stats.worst_symbol = worst[0]

    logger.info(
        "Stats: %d setups | WR=%.1f%% | avg RR=%.2f | expectancy=%.3f%%",
        stats.total_setups,
        stats.win_rate * 100,
        stats.avg_rr_actual,
        stats.expectancy,
    )
    return stats
