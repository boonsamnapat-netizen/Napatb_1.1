"""
Performance metrics: CAGR, Sharpe, Sortino, Calmar, max drawdown, win rate, etc.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any
from backtest.engine import Trade


def compute_metrics(
    equity_curve: List[dict],
    trades: List[Trade],
    initial_capital: float,
    benchmark: pd.Series = None,
) -> Dict[str, Any]:

    if not equity_curve:
        return {}

    eq_df   = pd.DataFrame(equity_curve).set_index('date')
    eq      = eq_df['equity']
    ret_d   = eq.pct_change().dropna()
    years   = max(len(eq) / 252, 0.01)

    total_ret  = eq.iloc[-1] / eq.iloc[0] - 1
    cagr       = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1

    rf_daily   = 0.04 / 252  # 4% risk-free rate
    excess     = ret_d - rf_daily
    sharpe     = excess.mean() / ret_d.std() * np.sqrt(252) if ret_d.std() > 0 else 0

    down       = ret_d[ret_d < 0]
    sortino    = excess.mean() / down.std() * np.sqrt(252) if len(down) > 0 and down.std() > 0 else 0

    peak       = eq.cummax()
    dd         = (eq - peak) / peak
    max_dd     = dd.min()
    calmar     = cagr / abs(max_dd) if max_dd < 0 else 0

    # Drawdown duration
    in_dd      = dd < 0
    dd_groups  = (in_dd != in_dd.shift()).cumsum()
    dd_dur     = in_dd.groupby(dd_groups).sum()
    max_dd_dur = int(dd_dur.max()) if len(dd_dur) > 0 else 0

    # Benchmark comparison
    alpha = beta = None
    if benchmark is not None:
        bret = benchmark.pct_change().dropna().reindex(ret_d.index).fillna(0)
        if len(bret) > 10:
            corr  = np.corrcoef(ret_d.values, bret.values)[0, 1]
            beta  = corr * ret_d.std() / bret.std() if bret.std() > 0 else 0
            bm_an = bret.mean() * 252
            alpha = cagr - (rf_daily * 252 + beta * (bm_an - rf_daily * 252))

    # Trade stats
    if trades:
        wins   = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        wr     = len(wins) / len(trades)
        avg_w  = np.mean([t.pnl_pct for t in wins])  if wins   else 0.0
        avg_l  = np.mean([t.pnl_pct for t in losses]) if losses else 0.0
        gp     = sum(t.pnl for t in wins)
        gl     = abs(sum(t.pnl for t in losses))
        pf     = gp / gl if gl > 0 else np.inf
        avg_dur = np.mean([t.duration_days for t in trades])
        expectancy = wr * avg_w + (1 - wr) * avg_l

        exit_counts = {}
        for t in trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        strat_stats = {}
        for t in trades:
            if t.strategy not in strat_stats:
                strat_stats[t.strategy] = []
            strat_stats[t.strategy].append(t)
    else:
        wr = avg_w = avg_l = pf = avg_dur = expectancy = 0.0
        gp = gl = 0.0
        exit_counts = {}
        strat_stats = {}

    return {
        # Returns
        'total_return': total_ret,
        'cagr': cagr,
        # Risk-adjusted
        'sharpe': sharpe,
        'sortino': sortino,
        'calmar': calmar,
        # Drawdown
        'max_drawdown': max_dd,
        'max_dd_days': max_dd_dur,
        # Trade metrics
        'win_rate': wr,
        'avg_win': avg_w,
        'avg_loss': avg_l,
        'profit_factor': pf,
        'expectancy': expectancy,
        'total_trades': len(trades),
        'avg_duration_days': avg_dur,
        'gross_profit': gp,
        'gross_loss': gl,
        # Other
        'final_equity': eq.iloc[-1],
        'alpha': alpha,
        'beta': beta,
        'exit_counts': exit_counts,
        'strat_stats': strat_stats,
        # Raw series (for plotting)
        '_equity': eq,
        '_drawdown': dd,
        '_daily_ret': ret_d,
        '_trades': trades,
    }


def _trade_stats(trades: List[Trade], initial_capital: float) -> Dict[str, Any]:
    """Aggregate return/win-rate/profit-factor for a subset of trades."""
    if not trades:
        return {'trades': 0, 'return': 0.0, 'win_rate': 0.0, 'profit_factor': 0.0}
    wins   = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gp     = sum(t.pnl for t in wins)
    gl     = abs(sum(t.pnl for t in losses))
    return {
        'trades':        len(trades),
        'return':        sum(t.pnl for t in trades) / initial_capital,
        'win_rate':      len(wins) / len(trades),
        'profit_factor': gp / gl if gl > 0 else np.inf,
    }


def compute_period_metrics(
    equity_curve: List[dict],
    trades: List[Trade],
    initial_capital: float,
    cutoff_date: str,
) -> Dict[str, Dict[str, Any]]:
    """Split trade stats by entry date around the AI training cutoff.

    Trades entered on/before the cutoff had no real AI filtering (a neutral
    score was assigned during warm-up); those after are AI-filtered.
    Return is expressed as summed PnL over the initial capital, so the two
    sub-periods are comparable rather than compounded.
    """
    cutoff = pd.Timestamp(cutoff_date)
    pre  = [t for t in trades if t.entry_date <= cutoff]
    post = [t for t in trades if t.entry_date >  cutoff]
    return {
        'pre-AI / warmup': _trade_stats(pre,  initial_capital),
        'AI-filtered':     _trade_stats(post, initial_capital),
    }


def print_period_split(periods: Dict[str, Dict[str, Any]]) -> None:
    """Pretty-print the pre-AI vs AI-filtered period comparison."""
    sep = '─' * 52
    print(f"\n{'═'*52}")
    print(f"  HONESTY SPLIT — PRE-AI WARMUP vs AI-FILTERED")
    print(f"{'═'*52}")
    for label, s in periods.items():
        pf = '∞' if s['profit_factor'] == np.inf else f"{s['profit_factor']:.2f}"
        print(f"  {label}")
        print(sep)
        print(f"  {'Trades':<30} {s['trades']}")
        print(f"  {'Return (PnL / capital)':<30} {s['return']:+.2%}")
        print(f"  {'Win Rate':<30} {s['win_rate']:.2%}")
        print(f"  {'Profit Factor':<30} {pf}")
        print()
    print(f"{'═'*52}\n")


def print_metrics(m: Dict[str, Any], spy_ret: float = None) -> None:
    """Pretty-print metrics to console."""

    sep = '─' * 52
    fmt_pct = lambda v: f"{v:+.2%}" if isinstance(v, float) else 'N/A'
    fmt_x   = lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else 'N/A'

    print(f"\n{'═'*52}")
    print(f"  NAPATB AI TRADING SYSTEM — PERFORMANCE REPORT")
    print(f"{'═'*52}")
    print(f"  {'Return Metrics':}")
    print(sep)
    print(f"  {'Total Return':<30} {fmt_pct(m['total_return'])}")
    print(f"  {'CAGR':<30} {fmt_pct(m['cagr'])}")
    if spy_ret is not None:
        print(f"  {'SPY 5-Year Return':<30} {fmt_pct(spy_ret)}")
    print()
    print(f"  {'Risk-Adjusted':}")
    print(sep)
    print(f"  {'Sharpe Ratio':<30} {fmt_x(m['sharpe'])}")
    print(f"  {'Sortino Ratio':<30} {fmt_x(m['sortino'])}")
    print(f"  {'Calmar Ratio':<30} {fmt_x(m['calmar'])}")
    if m.get('alpha') is not None:
        print(f"  {'Alpha (annualized)':<30} {fmt_pct(m['alpha'])}")
        print(f"  {'Beta':<30} {fmt_x(m['beta'])}")
    print()
    print(f"  {'Drawdown':}")
    print(sep)
    print(f"  {'Max Drawdown':<30} {fmt_pct(m['max_drawdown'])}")
    print(f"  {'Max DD Duration (days)':<30} {m['max_dd_days']}")
    print()
    print(f"  {'Trade Statistics':}")
    print(sep)
    print(f"  {'Total Trades':<30} {m['total_trades']}")
    print(f"  {'Win Rate':<30} {fmt_pct(m['win_rate'])}")
    print(f"  {'Avg Win':<30} {fmt_pct(m['avg_win'])}")
    print(f"  {'Avg Loss':<30} {fmt_pct(m['avg_loss'])}")
    print(f"  {'Profit Factor':<30} {m['profit_factor']:.2f}" if m['profit_factor'] != np.inf else f"  {'Profit Factor':<30} ∞")
    print(f"  {'Expectancy per Trade':<30} {fmt_pct(m['expectancy'])}")
    print(f"  {'Avg Duration (days)':<30} {m['avg_duration_days']:.0f}")
    print(f"  {'Final Equity':<30} ${m['final_equity']:>12,.0f}")
    print()
    print(f"  {'Exit Reasons':}")
    print(sep)
    for reason, cnt in m.get('exit_counts', {}).items():
        print(f"  {'  ' + reason:<30} {cnt}")
    print()
    print(f"  {'By Strategy':}")
    print(sep)
    for strat, strat_trades in m.get('strat_stats', {}).items():
        if not strat_trades:
            continue
        sw  = len([t for t in strat_trades if t.pnl > 0])
        swr = sw / len(strat_trades)
        sav = np.mean([t.pnl_pct for t in strat_trades])
        print(f"  {strat:<30} {len(strat_trades):3d} trades  WR {swr:.0%}  Avg {sav:+.1%}")
    print(f"{'═'*52}\n")
