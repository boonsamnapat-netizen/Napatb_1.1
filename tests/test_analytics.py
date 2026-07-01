"""Deterministic checks for the performance-analytics maths.

Run: pytest tests/test_analytics.py  (from repo root)
"""

import math

import pytest

from src.signal import analytics, dashboard


def _trades():
    # (r, outcome, symbol, direction, confidence, exit_date) — chronological
    rows = [
        (2.0, "WIN", "BTCUSDT", "LONG", 70, "2024-01-05"),
        (-1.0, "LOSS", "BTCUSDT", "LONG", 60, "2024-01-10"),
        (1.0, "WIN", "ETHUSDT", "SHORT", 80, "2024-02-01"),
        (-1.0, "LOSS", "ETHUSDT", "LONG", 58, "2024-02-15"),
        (3.0, "WIN", "BTCUSDT", "LONG", 75, "2024-03-01"),
    ]
    return [
        {"realized_r": r, "outcome": o, "symbol": s, "direction": d,
         "confidence": c, "exit_date": dt, "entry_date": dt}
        for r, o, s, d, c, dt in rows
    ]


def test_summary_core_metrics():
    m = analytics.summary_metrics(_trades(), risk_per_trade_pct=2.0)
    assert m["trades"] == 5
    assert m["wins"] == 3 and m["losses"] == 2 and m["breakeven"] == 0
    assert m["win_rate"] == pytest.approx(0.6)
    assert m["expectancy_r"] == pytest.approx(0.8)
    assert m["total_r"] == pytest.approx(4.0)
    assert m["median_r"] == pytest.approx(1.0)
    assert m["profit_factor"] == pytest.approx(3.0)      # 6 / 2
    assert m["avg_win_r"] == pytest.approx(2.0)
    assert m["avg_loss_r"] == pytest.approx(-1.0)
    assert m["payoff_ratio"] == pytest.approx(2.0)
    assert m["best_r"] == pytest.approx(3.0)
    assert m["worst_r"] == pytest.approx(-1.0)
    assert m["kelly_fraction"] == pytest.approx(0.4)     # 0.6 - 0.4/2


def test_streaks_and_drawdown():
    m = analytics.summary_metrics(_trades())
    # W L W L W  -> longest streaks are 1 each
    assert m["longest_win_streak"] == 1
    assert m["longest_loss_streak"] == 1
    # cumulative R: 2,1,2,1,4 -> peak-relative worst dip is -1R
    assert m["max_drawdown_r"] == pytest.approx(-1.0)


def test_sharpe_matches_manual():
    rs = [2, -1, 1, -1, 3]
    mean = sum(rs) / len(rs)
    var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)
    std = math.sqrt(var)
    m = analytics.summary_metrics(_trades())
    assert m["sharpe"] == pytest.approx(mean / std, rel=1e-3)


def test_equity_curve_and_compounding():
    eq = analytics.equity_curve(_trades(), risk_per_trade_pct=2.0)
    assert eq["equity_r"] == [2.0, 1.0, 2.0, 1.0, 4.0]
    # compounded equity risking 2% per trade on R multiples
    equity = 1.0
    for r in [2, -1, 1, -1, 3]:
        equity *= (1 + 0.02 * r)
    # module rounds the % curve to 4 dp
    assert eq["equity_pct"][-1] == pytest.approx((equity - 1) * 100, abs=1e-3)


def test_drawdown_series_zero_when_monotonic():
    up = [{"realized_r": 1.0, "exit_date": f"2024-01-0{i}"} for i in range(1, 6)]
    dd = analytics.drawdown_series(analytics.equity_curve(up))
    assert dd["max_dd_r"] == pytest.approx(0.0)


def test_group_breakdowns():
    by_sym = {r["key"]: r for r in analytics.by_symbol(_trades())}
    assert by_sym["BTCUSDT"]["total_r"] == pytest.approx(4.0)   # 2 -1 3
    assert by_sym["ETHUSDT"]["total_r"] == pytest.approx(0.0)   # 1 -1
    # sorted by total_r desc
    assert analytics.by_symbol(_trades())[0]["key"] == "BTCUSDT"

    by_conf = {r["key"]: r for r in analytics.by_confidence(_trades())}
    assert by_conf["55–65"]["trades"] == 2   # conf 60, 58
    assert by_conf["75+"]["trades"] == 2      # conf 80, 75


def test_r_histogram_counts_all_trades():
    h = analytics.r_histogram(_trades())
    assert sum(h["counts"]) == 5
    assert len(h["counts"]) == len(h["labels"])


def test_threshold_sweep_recommends_higher_when_better():
    # low-confidence trades lose, high-confidence trades win -> raising the
    # threshold should improve expectancy and be recommended.
    trades = []
    for i in range(40):
        trades.append({"realized_r": -1.0, "outcome": "LOSS", "confidence": 56,
                       "exit_date": f"2024-01-{i%28+1:02d}", "symbol": "X", "direction": "LONG"})
    for i in range(40):
        trades.append({"realized_r": 2.0, "outcome": "WIN", "confidence": 78,
                       "exit_date": f"2024-02-{i%28+1:02d}", "symbol": "X", "direction": "LONG"})
    sw = analytics.threshold_sweep(trades, thresholds=[55, 75], min_trades=10)
    assert sw["current"] == 55
    assert sw["recommended"] == 75
    rows = {r["threshold"]: r for r in sw["rows"]}
    assert rows[55]["trades"] == 80 and rows[75]["trades"] == 40
    assert rows[75]["expectancy_r"] > rows[55]["expectancy_r"]


def test_threshold_sweep_no_recommendation_when_flat():
    trades = [{"realized_r": 0.3, "outcome": "WIN", "confidence": 60 + (i % 20),
               "exit_date": f"2024-01-{i%28+1:02d}", "symbol": "X", "direction": "LONG"}
              for i in range(60)]
    sw = analytics.threshold_sweep(trades, thresholds=[55, 60, 65], min_trades=5)
    assert sw["recommended"] is None   # uniformly good -> no reason to raise


def test_forward_tracker_delta():
    fwd = {"total": 4, "open": 2, "closed": 2, "wins": 1,
           "win_rate": 0.5, "total_r": 0.5}
    t = analytics.forward_tracker(fwd, expectancy_r=0.8)
    assert t["live_avg_r"] == pytest.approx(0.25)   # 0.5 / 2
    assert t["delta_r"] == pytest.approx(0.25 - 0.8)


def test_empty_is_safe():
    assert analytics.summary_metrics([]) == {"trades": 0}
    rep = analytics.build_report([], generated_at="now")
    # renders without crashing even with no trades
    assert "ยังไม่มี trade" in dashboard.render_html(rep)


def test_build_report_and_render_html():
    rep = analytics.build_report(
        _trades(), risk_per_trade_pct=2.0,
        forward_summary={"total": 5, "open": 5, "closed": 0, "wins": 0,
                         "win_rate": None, "total_r": None},
        generated_at="2024-03-01",
    )
    assert rep["summary"]["trades"] == 5
    doc = dashboard.render_html(rep)
    assert doc.startswith("<!doctype html>")
    assert "Performance Dashboard" in doc
    assert "BTCUSDT" in doc          # per-coin table rendered
    assert "svg" in doc.lower()      # charts rendered
