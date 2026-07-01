"""Performance analytics — turn a list of trades into honest, net-of-fees numbers.

Pure functions (no I/O, no plotting) so they are trivial to test. Feed it the
out-of-sample trades collected by
:meth:`src.signal.backtester.SignalBacktester.walk_forward_collect` (and/or the
forward-test log) and it returns the metrics the dashboard renders:

  - headline summary (win rate, expectancy, profit factor, Sharpe/Sortino, Kelly…)
  - equity curve + drawdown series (in R and compounded %)
  - R-multiple distribution histogram
  - breakdowns by coin / direction / confidence bucket / month

Every number is per-trade and out-of-sample by construction; annualised figures
are deliberately avoided because trade frequency is irregular. Sharpe here is the
per-trade information ratio (mean R / std R) — a shape metric, not an annual one.

A "trade" is a dict with at least: ``realized_r`` (net R, fees included),
``outcome`` (WIN/LOSS/BREAKEVEN/TIMEOUT), ``symbol``, ``direction``,
``confidence``, ``exit_date`` (``YYYY-MM-DD``; used to order the equity curve).
"""

from __future__ import annotations

import math
from collections import defaultdict

# Confidence buckets used for the "is higher conviction actually better?" table.
CONF_BUCKETS = [(0, 55, "<55"), (55, 65, "55–65"), (65, 75, "65–75"), (75, 101, "75+")]


def _r(t: dict) -> float:
    return float(t.get("realized_r") or 0.0)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _order(trades: list[dict]) -> list[dict]:
    """Chronological by exit date (stable) — the order the equity curve realises."""
    return sorted(trades, key=lambda t: (t.get("exit_date") or "", t.get("entry_date") or ""))


# ---------------------------------------------------------------- summary ----
def summary_metrics(trades: list[dict], risk_per_trade_pct: float = 2.0) -> dict:
    """Headline stats for a bag of trades. All R values are net of fees."""
    n = len(trades)
    if n == 0:
        return {"trades": 0}

    rs = [_r(t) for t in trades]
    wins = [x for x in rs if x > 1e-9]
    losses = [x for x in rs if x < -1e-9]
    breakeven = n - len(wins) - len(losses)

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = _mean(wins)
    avg_loss = _mean(losses)  # negative
    std = _std(rs)
    downside = _std([min(0.0, x) for x in rs])

    payoff = (avg_win / abs(avg_loss)) if losses else float("inf")
    win_rate = len(wins) / n
    # Kelly for R-multiple payoff: f* = W - (1-W)/payoff
    kelly = win_rate - (1 - win_rate) / payoff if payoff not in (0, float("inf")) else 0.0

    eq = equity_curve(trades, risk_per_trade_pct)
    dd = drawdown_series(eq)

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(_mean(rs), 4),          # mean R per trade = the edge
        "median_r": round(sorted(rs)[n // 2], 4),
        "total_r": round(sum(rs), 4),
        "avg_win_r": round(avg_win, 4),
        "avg_loss_r": round(avg_loss, 4),
        "payoff_ratio": round(payoff, 4) if payoff != float("inf") else None,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None,
        "std_r": round(std, 4),
        "sharpe": round(_mean(rs) / std, 4) if std else None,      # per-trade info ratio
        "sortino": round(_mean(rs) / downside, 4) if downside else None,
        "best_r": round(max(rs), 4),
        "worst_r": round(min(rs), 4),
        "max_drawdown_r": round(dd["max_dd_r"], 4),
        "max_drawdown_pct": round(dd["max_dd_pct"], 4),
        "return_pct": round((eq["equity_pct"][-1] if eq["equity_pct"] else 0.0), 4),
        "longest_win_streak": _longest_streak(rs, win=True),
        "longest_loss_streak": _longest_streak(rs, win=False),
        "kelly_fraction": round(kelly, 4),
        "risk_per_trade_pct": risk_per_trade_pct,
    }


def _longest_streak(rs: list[float], win: bool) -> int:
    best = cur = 0
    for x in rs:
        hit = (x > 1e-9) if win else (x < -1e-9)
        cur = cur + 1 if hit else 0
        best = max(best, cur)
    return best


# ------------------------------------------------------------ equity / dd ----
def equity_curve(trades: list[dict], risk_per_trade_pct: float = 2.0) -> dict:
    """Cumulative R and compounded % equity (risking ``risk_per_trade_pct`` of
    equity each trade), in chronological (exit-date) order."""
    ordered = _order(trades)
    cum_r = 0.0
    equity = 1.0  # normalised to 1.0 (=100%) start
    dates, eq_r, eq_pct = [], [], []
    for t in ordered:
        r = _r(t)
        cum_r += r
        equity *= (1 + (risk_per_trade_pct / 100.0) * r)
        dates.append(t.get("exit_date"))
        eq_r.append(round(cum_r, 4))
        eq_pct.append(round((equity - 1.0) * 100.0, 4))
    return {"dates": dates, "equity_r": eq_r, "equity_pct": eq_pct}


def drawdown_series(eq: dict) -> dict:
    """Peak-to-trough drawdown from an equity curve (both R and %)."""
    r_curve = eq.get("equity_r", [])
    pct_curve = eq.get("equity_pct", [])

    def _dd(curve: list[float]) -> tuple[list[float], float]:
        peak = -float("inf")
        series, worst = [], 0.0
        for v in curve:
            peak = max(peak, v)
            d = v - peak
            series.append(round(d, 4))
            worst = min(worst, d)
        return series, worst

    dd_r, max_dd_r = _dd(r_curve)
    dd_pct, max_dd_pct = _dd(pct_curve)
    return {"dd_r": dd_r, "dd_pct": dd_pct, "max_dd_r": max_dd_r, "max_dd_pct": max_dd_pct}


# ---------------------------------------------------------- distributions ----
def r_histogram(trades: list[dict], edges: list[float] | None = None) -> dict:
    """Bucket net-R outcomes for the distribution chart."""
    edges = edges or [-3, -2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 3, 5]
    counts = [0] * (len(edges) - 1)
    for t in trades:
        r = _r(t)
        for i in range(len(edges) - 1):
            if edges[i] <= r < edges[i + 1]:
                counts[i] += 1
                break
        else:
            if r >= edges[-1]:
                counts[-1] += 1
            elif r < edges[0]:
                counts[0] += 1
    labels = [f"{edges[i]}..{edges[i + 1]}" for i in range(len(edges) - 1)]
    return {"edges": edges, "labels": labels, "counts": counts}


def _group(trades: list[dict], keyfn, risk_pct: float) -> list[dict]:
    buckets: dict = defaultdict(list)
    for t in trades:
        buckets[keyfn(t)].append(t)
    out = []
    for k, group in buckets.items():
        m = summary_metrics(group, risk_pct)
        out.append({
            "key": k,
            "trades": m["trades"],
            "win_rate": m["win_rate"],
            "expectancy_r": m["expectancy_r"],
            "total_r": m["total_r"],
            "max_drawdown_r": m["max_drawdown_r"],
            "profit_factor": m["profit_factor"],
        })
    return out


def by_symbol(trades: list[dict], risk_pct: float = 2.0) -> list[dict]:
    rows = _group(trades, lambda t: t.get("symbol") or "?", risk_pct)
    return sorted(rows, key=lambda r: r["total_r"], reverse=True)


def by_direction(trades: list[dict], risk_pct: float = 2.0) -> list[dict]:
    return _group(trades, lambda t: t.get("direction") or "?", risk_pct)


def by_confidence(trades: list[dict], risk_pct: float = 2.0) -> list[dict]:
    def bucket(t: dict) -> str:
        c = float(t.get("confidence") or 0)
        for lo, hi, label in CONF_BUCKETS:
            if lo <= c < hi:
                return label
        return "75+"
    order = {label: i for i, (_, _, label) in enumerate(CONF_BUCKETS)}
    rows = _group(trades, bucket, risk_pct)
    return sorted(rows, key=lambda r: order.get(r["key"], 99))


def by_month(trades: list[dict], risk_pct: float = 2.0) -> list[dict]:
    rows = _group(trades, lambda t: (t.get("exit_date") or "????-??")[:7], risk_pct)
    return sorted(rows, key=lambda r: r["key"])


# ----------------------------------------------- confidence threshold sweep --
def threshold_sweep(
    trades: list[dict],
    thresholds: list[int] | None = None,
    risk_pct: float = 2.0,
    min_trades: int = 30,
) -> dict:
    """'What if we only took signals with confidence >= X?'

    Filters the *already-realised* OOS trades by confidence (their outcomes are
    unchanged) at each threshold — a first-order estimate of raising
    ``min_confidence``. It does NOT re-run the backtest, so it ignores the small
    knock-on effect of skipped trades on cooldown/sequencing (negligible while
    cooldown is off). Honest, actionable, and cheap.

    Returns the per-threshold rows plus a ``recommended`` threshold: the one with
    the best expectancy that still keeps a meaningful sample (>= ``min_trades``).
    """
    thresholds = thresholds or [55, 60, 65, 70, 75, 80]
    rows = []
    for th in thresholds:
        sub = [t for t in trades if float(t.get("confidence") or 0) >= th]
        m = summary_metrics(sub, risk_pct) if sub else {"trades": 0}
        rows.append({
            "threshold": th,
            "trades": m.get("trades", 0),
            "win_rate": m.get("win_rate"),
            "expectancy_r": m.get("expectancy_r"),
            "total_r": m.get("total_r"),
            "profit_factor": m.get("profit_factor"),
        })
    eligible = [r for r in rows if r["trades"] >= min_trades and r["expectancy_r"] is not None]
    base = rows[0] if rows else None
    best = max(eligible, key=lambda r: r["expectancy_r"]) if eligible else None
    rec = None
    if best and base and base.get("expectancy_r") is not None:
        # only recommend a change if it's a real improvement over the current floor
        if best["threshold"] != base["threshold"] and best["expectancy_r"] > base["expectancy_r"] + 0.02:
            rec = best["threshold"]
    return {"rows": rows, "recommended": rec,
            "current": base["threshold"] if base else None}


# --------------------------------------------------- forward-test tracking ---
def forward_tracker(forward_summary: dict, expectancy_r: float | None) -> dict:
    """Compare the live forward-test log (graded ENTER signals actually pushed)
    against the backtest expectation — the honest 'is it working live?' check."""
    closed = forward_summary.get("closed", 0)
    total_r = forward_summary.get("total_r")
    live_avg = (total_r / closed) if (closed and total_r is not None) else None
    return {
        "total": forward_summary.get("total", 0),
        "open": forward_summary.get("open", 0),
        "closed": closed,
        "wins": forward_summary.get("wins"),
        "win_rate": forward_summary.get("win_rate"),
        "total_r": total_r,
        "live_avg_r": round(live_avg, 4) if live_avg is not None else None,
        "backtest_expectancy_r": expectancy_r,
        "delta_r": round(live_avg - expectancy_r, 4)
        if (live_avg is not None and expectancy_r is not None) else None,
    }


# ------------------------------------------------------------- top report ----
def build_report(
    trades: list[dict],
    *,
    risk_per_trade_pct: float = 2.0,
    forward_summary: dict | None = None,
    config_label: str = "live default (4h/1d, Supertrend, ATR trail 2.5R, fees on)",
    generated_at: str | None = None,
) -> dict:
    """Assemble the full analytics payload the dashboard/Telegram render from."""
    summ = summary_metrics(trades, risk_per_trade_pct)
    eq = equity_curve(trades, risk_per_trade_pct)
    report = {
        "generated_at": generated_at,
        "config_label": config_label,
        "risk_per_trade_pct": risk_per_trade_pct,
        "summary": summ,
        "equity": eq,
        "drawdown": drawdown_series(eq),
        "r_histogram": r_histogram(trades),
        "by_symbol": by_symbol(trades, risk_per_trade_pct),
        "by_direction": by_direction(trades, risk_per_trade_pct),
        "by_confidence": by_confidence(trades, risk_per_trade_pct),
        "by_month": by_month(trades, risk_per_trade_pct),
        "threshold_sweep": threshold_sweep(trades, risk_pct=risk_per_trade_pct),
    }
    if forward_summary is not None:
        report["forward"] = forward_tracker(forward_summary, summ.get("expectancy_r"))
    return report
