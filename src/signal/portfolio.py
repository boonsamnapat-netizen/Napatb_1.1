"""
Portfolio-level risk management.

Per-trade risk is necessary but not sufficient: open ten 1%-risk longs in crypto
and you don't have ten independent bets — you have one ~10% bet on BTC beta,
because alts are highly correlated. This module sizes the *portfolio*:

  - cap total open risk ("portfolio heat"),
  - cap net risk per direction (correlation-aware: all-longs = one big bet),
  - cap the number of concurrent positions,
  - then distribute the risk budget across the best-ranked setups.

It consumes the scanner's ranked rows and returns a concrete allocation per
symbol (adjusted risk %, position size, notional, leverage).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Allocation:
    symbol: str
    direction: str
    risk_pct: float          # adjusted risk for this trade
    risk_amount: float
    entry: float
    stop_loss: float
    size_units: float
    notional: float
    leverage: float
    rank_score: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "risk_pct": round(self.risk_pct, 3),
            "risk_amount": round(self.risk_amount, 2),
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "size_units": round(self.size_units, 8),
            "notional": round(self.notional, 2),
            "leverage": round(self.leverage, 2),
            "rank_score": self.rank_score,
        }


@dataclass
class PortfolioPlan:
    account_size: float
    allocations: list[Allocation] = field(default_factory=list)
    total_risk_pct: float = 0.0
    long_risk_pct: float = 0.0
    short_risk_pct: float = 0.0
    gross_leverage: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "account_size": self.account_size,
            "allocations": [a.to_dict() for a in self.allocations],
            "total_risk_pct": round(self.total_risk_pct, 3),
            "long_risk_pct": round(self.long_risk_pct, 3),
            "short_risk_pct": round(self.short_risk_pct, 3),
            "gross_leverage": round(self.gross_leverage, 2),
            "notes": self.notes,
        }


class PortfolioRiskManager:
    def __init__(self, config: dict):
        cfg = config.get("signal", {}).get("portfolio", {})
        self.base_risk_pct = cfg.get("base_risk_pct", 1.0)
        self.max_heat_pct = cfg.get("max_portfolio_heat_pct", 6.0)
        self.max_dir_heat_pct = cfg.get("max_per_direction_heat_pct", 4.0)
        self.max_concurrent = cfg.get("max_concurrent", 5)
        self.max_gross_leverage = cfg.get("max_gross_leverage", 10.0)

    def allocate(self, rows, account_size: float) -> PortfolioPlan:
        """rows: scanner ScanRow objects, already ranked best-first."""
        plan = PortfolioPlan(account_size=account_size)

        enters = [
            r for r in rows
            if r.decision == "ENTER" and r.entry and r.stop_loss
            and abs(r.entry - r.stop_loss) > 0
        ]
        if not enters:
            plan.notes.append("No ENTER setups to allocate.")
            return plan

        take = enters[: self.max_concurrent]
        if len(enters) > self.max_concurrent:
            plan.notes.append(
                f"{len(enters)} ENTER setups; capping at {self.max_concurrent} "
                f"best by rank."
            )

        # Start everyone at base risk, then scale to respect the heat caps.
        risk = {r.symbol: self.base_risk_pct for r in take}

        def dir_sum(direction):
            return sum(risk[r.symbol] for r in take if r.direction == direction)

        # Per-direction cap (correlation: same-direction crypto trades cluster)
        for d in ("LONG", "SHORT"):
            members = [r for r in take if r.direction == d]
            s = dir_sum(d)
            if s > self.max_dir_heat_pct and members:
                scale = self.max_dir_heat_pct / s
                for r in members:
                    risk[r.symbol] *= scale
                plan.notes.append(
                    f"{d} exposure scaled x{scale:.2f} (correlation cap "
                    f"{self.max_dir_heat_pct}%)."
                )

        # Total heat cap
        total = sum(risk.values())
        if total > self.max_heat_pct:
            scale = self.max_heat_pct / total
            for k in risk:
                risk[k] *= scale
            plan.notes.append(
                f"Total heat scaled x{scale:.2f} to {self.max_heat_pct}% cap."
            )

        # Build allocations
        for r in take:
            rp = risk[r.symbol]
            risk_amount = account_size * rp / 100.0
            stop_dist = abs(r.entry - r.stop_loss)
            size = risk_amount / stop_dist if stop_dist > 0 else 0.0
            notional = size * r.entry
            plan.allocations.append(
                Allocation(
                    symbol=r.symbol,
                    direction=r.direction,
                    risk_pct=rp,
                    risk_amount=risk_amount,
                    entry=r.entry,
                    stop_loss=r.stop_loss,
                    size_units=size,
                    notional=notional,
                    leverage=notional / account_size if account_size else 0.0,
                    rank_score=r.rank_score,
                )
            )

        plan.total_risk_pct = sum(a.risk_pct for a in plan.allocations)
        plan.long_risk_pct = sum(a.risk_pct for a in plan.allocations if a.direction == "LONG")
        plan.short_risk_pct = sum(a.risk_pct for a in plan.allocations if a.direction == "SHORT")
        plan.gross_leverage = sum(a.leverage for a in plan.allocations)
        if plan.gross_leverage > self.max_gross_leverage:
            plan.notes.append(
                f"Gross leverage {plan.gross_leverage:.1f}x exceeds "
                f"{self.max_gross_leverage}x — reduce size or positions."
            )
        return plan
