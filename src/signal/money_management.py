"""
Money management & risk sizing.

This is the part that actually separates traders who survive from those who
don't. The signal engine decides *where* to trade; this module decides *how
much* so that a string of losses can never blow the account.

Core rule: fixed-fractional risk. Never risk more than `risk_per_trade_pct` of
equity on a single idea, and size the position from the stop distance — not from
how confident we feel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TakeProfit:
    price: float
    r_multiple: float       # reward in units of risk (R)
    allocation_pct: float   # % of position to close here
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "price": round(self.price, 8),
            "r_multiple": round(self.r_multiple, 2),
            "allocation_pct": self.allocation_pct,
            "label": self.label,
        }


@dataclass
class PositionPlan:
    direction: str
    entry: float
    stop_loss: float
    take_profits: list[TakeProfit] = field(default_factory=list)

    account_size: float = 0.0
    risk_per_trade_pct: float = 1.0
    risk_amount: float = 0.0          # currency at risk
    stop_distance_pct: float = 0.0
    position_size_units: float = 0.0  # quantity of the asset
    position_value: float = 0.0       # notional in quote currency
    suggested_leverage: float = 1.0
    max_leverage_cap: float = 10.0

    planned_rr: float = 0.0           # to final TP
    blended_rr: float = 0.0           # weighted by allocation
    expected_value_r: float = 0.0     # EV in R given assumed win rate
    liquidation_estimate: float | None = None

    def to_dict(self) -> dict:
        return {
            "direction": self.direction,
            "entry": round(self.entry, 8),
            "stop_loss": round(self.stop_loss, 8),
            "take_profits": [tp.to_dict() for tp in self.take_profits],
            "account_size": self.account_size,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "risk_amount": round(self.risk_amount, 2),
            "stop_distance_pct": round(self.stop_distance_pct, 3),
            "position_size_units": round(self.position_size_units, 8),
            "position_value": round(self.position_value, 2),
            "suggested_leverage": round(self.suggested_leverage, 2),
            "planned_rr": round(self.planned_rr, 2),
            "blended_rr": round(self.blended_rr, 2),
            "expected_value_r": round(self.expected_value_r, 3),
            "liquidation_estimate": (
                round(self.liquidation_estimate, 8)
                if self.liquidation_estimate is not None
                else None
            ),
        }


def build_position_plan(
    direction: str,
    entry: float,
    stop_loss: float,
    take_profits: list[TakeProfit],
    account_size: float,
    risk_per_trade_pct: float,
    confidence: float,
    assumed_win_rate: float,
    max_leverage_cap: float = 10.0,
    risk_multiplier: float = 1.0,
) -> PositionPlan:
    """
    risk_multiplier lets the caller scale risk down (e.g. news gate, low
    confidence) without changing the base policy. It is clamped to [0, 1.5].
    """
    risk_multiplier = max(0.0, min(1.5, risk_multiplier))
    effective_risk_pct = risk_per_trade_pct * risk_multiplier
    risk_amount = account_size * (effective_risk_pct / 100.0)

    stop_distance = abs(entry - stop_loss)
    stop_distance_pct = (stop_distance / entry * 100.0) if entry else 0.0

    size_units = (risk_amount / stop_distance) if stop_distance > 0 else 0.0
    position_value = size_units * entry
    suggested_leverage = (
        min(position_value / account_size, max_leverage_cap)
        if account_size > 0
        else 1.0
    )
    suggested_leverage = max(1.0, suggested_leverage)

    plan = PositionPlan(
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profits=take_profits,
        account_size=account_size,
        risk_per_trade_pct=round(effective_risk_pct, 3),
        risk_amount=risk_amount,
        stop_distance_pct=stop_distance_pct,
        position_size_units=size_units,
        position_value=position_value,
        suggested_leverage=suggested_leverage,
        max_leverage_cap=max_leverage_cap,
    )

    if take_profits:
        plan.planned_rr = max(tp.r_multiple for tp in take_profits)
        total_alloc = sum(tp.allocation_pct for tp in take_profits) or 1.0
        plan.blended_rr = sum(
            tp.r_multiple * tp.allocation_pct for tp in take_profits
        ) / total_alloc

    # Expected value in R: win_rate * blended_reward - (1-win_rate) * 1R
    wr = max(0.0, min(1.0, assumed_win_rate))
    plan.expected_value_r = wr * plan.blended_rr - (1 - wr) * 1.0

    return plan


def assumed_win_rate_from_confidence(confidence: float) -> float:
    """
    Map a 0-100 confidence score to a conservative assumed win-rate.
    Deliberately pessimistic: even a 'great' setup is capped well below
    certainty so position sizing and EV stay honest.
    """
    c = max(0.0, min(100.0, confidence))
    # 40% floor at 0 confidence, ~62% at 100 confidence.
    return 0.40 + 0.22 * (c / 100.0)
