"""
Backtest visualization: equity curve, drawdown, monthly heatmap, trade distribution.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mtick
from typing import Dict, Any, List
from backtest.engine import Trade


def plot_report(
    metrics: Dict[str, Any],
    spy_close: pd.Series,
    output_path: str = 'backtest_report.png',
    title: str = 'NAPATB AI Trading System — 5-Year Backtest',
) -> None:

    equity = metrics['_equity']
    dd     = metrics['_drawdown']
    trades: List[Trade] = metrics['_trades']

    fig = plt.figure(figsize=(20, 16), facecolor='#0d0d0d')
    fig.suptitle(title, fontsize=17, color='white', fontweight='bold', y=0.98)

    gs = gridspec.GridSpec(4, 3, figure=fig, hspace=0.45, wspace=0.35,
                           left=0.06, right=0.97, top=0.93, bottom=0.04)

    ACCENT  = '#00e5ff'
    ORANGE  = '#ff9800'
    GREEN   = '#69f0ae'
    RED     = '#ff5252'
    BG      = '#1a1a2e'
    TEXT    = '#e0e0e0'

    def style_ax(ax):
        ax.set_facecolor(BG)
        ax.tick_params(colors=TEXT, labelsize=8)
        for sp in ax.spines.values():
            sp.set_color('#444')
        ax.grid(True, alpha=0.15, color='#555')
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        ax.title.set_color(TEXT)

    # ── 1. Equity Curve (top full-width) ─────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    style_ax(ax1)

    eq_norm  = equity / equity.iloc[0] * 100
    spy_r    = spy_close.reindex(equity.index, method='ffill')
    spy_norm = spy_r / spy_r.iloc[0] * 100

    ax1.plot(eq_norm.index,  eq_norm.values,  color=ACCENT,  lw=2.2, label='AI Strategy',     zorder=3)
    ax1.plot(spy_norm.index, spy_norm.values, color=ORANGE,  lw=1.5, label='SPY Buy & Hold',  zorder=2, alpha=0.9, ls='--')
    ax1.fill_between(eq_norm.index, spy_norm.values, eq_norm.values,
                     where=eq_norm.values >= spy_norm.values, alpha=0.12, color=GREEN)
    ax1.fill_between(eq_norm.index, spy_norm.values, eq_norm.values,
                     where=eq_norm.values <  spy_norm.values, alpha=0.12, color=RED)
    ax1.axhline(100, color='#555', lw=0.7, ls=':')
    ax1.set_title('Portfolio Value vs SPY (Base = 100)', fontsize=11)
    ax1.legend(loc='upper left', fontsize=9, facecolor='#222', edgecolor='#555', labelcolor=TEXT)
    ax1.yaxis.set_major_formatter(mtick.FormatStrFormatter('%.0f'))

    # Annotate final values
    ax1.annotate(f"Strategy: {eq_norm.iloc[-1]:.0f}",
                 xy=(eq_norm.index[-1], eq_norm.iloc[-1]),
                 xytext=(-80, 8), textcoords='offset points',
                 color=ACCENT, fontsize=9, fontweight='bold')
    ax1.annotate(f"SPY: {spy_norm.iloc[-1]:.0f}",
                 xy=(spy_norm.index[-1], spy_norm.iloc[-1]),
                 xytext=(-60, -18), textcoords='offset points',
                 color=ORANGE, fontsize=9)

    # ── 2. Drawdown ───────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, :2])
    style_ax(ax2)

    ax2.fill_between(dd.index, dd.values * 100, 0, color=RED, alpha=0.65, zorder=2)
    spy_peak = spy_norm.cummax()
    spy_dd   = (spy_norm - spy_peak) / spy_peak * 100
    ax2.plot(spy_dd.index, spy_dd.values, color=ORANGE, lw=1.2, alpha=0.7, label='SPY DD', ls='--')
    ax2.set_title('Drawdown (%)', fontsize=11)
    ax2.set_ylabel('%', fontsize=9)
    ax2.legend(fontsize=8, facecolor='#222', edgecolor='#555', labelcolor=TEXT)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter())

    # ── 3. Monthly Returns Heatmap ────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 2])
    style_ax(ax3)
    ax3.set_facecolor('#111')

    ret_d = metrics['_daily_ret']
    try:
        monthly = (1 + ret_d).resample('ME').prod() - 1
        years   = sorted(monthly.index.year.unique())
        months  = list(range(1, 13))
        mat     = np.full((len(years), 12), np.nan)
        for idx, val in monthly.items():
            yi = years.index(idx.year)
            mat[yi, idx.month - 1] = val * 100

        im = ax3.imshow(mat, cmap='RdYlGn', aspect='auto', vmin=-10, vmax=10)
        ax3.set_xticks(range(12))
        ax3.set_xticklabels(['J','F','M','A','M','J','J','A','S','O','N','D'], fontsize=7, color=TEXT)
        ax3.set_yticks(range(len(years)))
        ax3.set_yticklabels(years, fontsize=7, color=TEXT)
        ax3.set_title('Monthly Returns (%)', fontsize=11)
        cbar = plt.colorbar(im, ax=ax3, shrink=0.85)
        cbar.ax.tick_params(colors=TEXT, labelsize=7)

        for yi in range(len(years)):
            for mi in range(12):
                v = mat[yi, mi]
                if not np.isnan(v):
                    ax3.text(mi, yi, f'{v:.0f}', ha='center', va='center', fontsize=6,
                             color='black' if abs(v) < 7 else 'white', fontweight='bold')
    except Exception:
        ax3.text(0.5, 0.5, 'N/A', ha='center', va='center', transform=ax3.transAxes, color=TEXT)

    # ── 4. Trade Return Distribution ──────────────────────────────────────
    ax4 = fig.add_subplot(gs[2, :2])
    style_ax(ax4)

    if trades:
        pnls = sorted([t.pnl_pct * 100 for t in trades])
        colors = [GREEN if p > 0 else RED for p in pnls]
        ax4.bar(range(len(pnls)), pnls, color=colors, alpha=0.8, width=1.0)
        ax4.axhline(0, color='white', lw=0.7)
        ax4.set_title(f'Individual Trade Returns ({len(trades)} trades)', fontsize=11)
        ax4.set_ylabel('Return (%)', fontsize=9)
        ax4.set_xlabel('Trade # (sorted)', fontsize=9)
        ax4.yaxis.set_major_formatter(mtick.PercentFormatter())

        # Win/loss annotation
        wins   = sum(1 for p in pnls if p > 0)
        losses = len(pnls) - wins
        ax4.text(0.02, 0.95, f'W:{wins}  L:{losses}  WR:{wins/len(pnls):.0%}',
                 transform=ax4.transAxes, color=TEXT, fontsize=9, va='top')

    # ── 5. Return Histogram ───────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 2])
    style_ax(ax5)

    if trades:
        pnl_vals = [t.pnl_pct * 100 for t in trades]
        ax5.hist(pnl_vals, bins=25, color=ACCENT, edgecolor='#333', alpha=0.85)
        ax5.axvline(0, color='white', lw=1.2)
        ax5.axvline(np.mean(pnl_vals), color=ORANGE, lw=1.5, ls='--', label=f'Mean {np.mean(pnl_vals):.1f}%')
        ax5.set_title('Trade Return Histogram', fontsize=11)
        ax5.set_xlabel('Return (%)', fontsize=9)
        ax5.legend(fontsize=8, facecolor='#222', edgecolor='#555', labelcolor=TEXT)

    # ── 6. Strategy Breakdown Bar ─────────────────────────────────────────
    ax6 = fig.add_subplot(gs[3, :2])
    style_ax(ax6)

    strat_stats = metrics.get('strat_stats', {})
    if strat_stats:
        labels, wr_vals, avg_vals, counts = [], [], [], []
        for s, st in strat_stats.items():
            if not st:
                continue
            wins = len([t for t in st if t.pnl > 0])
            labels.append(s.replace('_', '\n'))
            wr_vals.append(wins / len(st) * 100)
            avg_vals.append(np.mean([t.pnl_pct for t in st]) * 100)
            counts.append(len(st))

        x = np.arange(len(labels))
        w = 0.35
        b1 = ax6.bar(x - w/2, wr_vals,  w, label='Win Rate %', color=GREEN,  alpha=0.85)
        b2 = ax6.bar(x + w/2, avg_vals, w, label='Avg Return %', color=ACCENT, alpha=0.85)
        ax6.set_xticks(x)
        ax6.set_xticklabels(labels, fontsize=9, color=TEXT)
        ax6.set_title('Strategy Breakdown: Win Rate & Avg Return', fontsize=11)
        ax6.legend(fontsize=8, facecolor='#222', edgecolor='#555', labelcolor=TEXT)
        for i, (b, c) in enumerate(zip(b1, counts)):
            ax6.text(b.get_x() + b.get_width()/2, b.get_height() + 0.5,
                     f'n={c}', ha='center', fontsize=8, color=TEXT)

    # ── 7. Metrics Summary Table ──────────────────────────────────────────
    ax7 = fig.add_subplot(gs[3, 2])
    ax7.set_facecolor(BG)
    ax7.axis('off')

    rows = [
        ['Total Return',    f"{metrics['total_return']:+.1%}"],
        ['CAGR',            f"{metrics['cagr']:+.1%}"],
        ['Sharpe',          f"{metrics['sharpe']:.2f}"],
        ['Sortino',         f"{metrics['sortino']:.2f}"],
        ['Calmar',          f"{metrics['calmar']:.2f}"],
        ['Max Drawdown',    f"{metrics['max_drawdown']:.1%}"],
        ['Win Rate',        f"{metrics['win_rate']:.1%}"],
        ['Profit Factor',   f"{metrics['profit_factor']:.2f}" if metrics['profit_factor'] != np.inf else '∞'],
        ['Avg Win',         f"{metrics['avg_win']:+.1%}"],
        ['Avg Loss',        f"{metrics['avg_loss']:.1%}"],
        ['# Trades',        str(metrics['total_trades'])],
        ['Final Equity',    f"${metrics['final_equity']:,.0f}"],
    ]

    tbl = ax7.table(
        cellText=rows,
        colLabels=['Metric', 'Value'],
        cellLoc='center',
        loc='center',
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)

    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor('#111' if r == 0 else BG)
        cell.set_edgecolor('#333')
        cell.set_text_props(color=TEXT if r > 0 else ACCENT,
                            fontweight='bold' if r == 0 else 'normal')
        # Color value cells
        if r > 0 and c == 1:
            val_str = rows[r-1][1].replace('%', '').replace('$', '').replace(',', '').replace('+', '')
            try:
                v = float(val_str)
                if rows[r-1][0] in ('Max Drawdown', 'Avg Loss'):
                    cell.set_facecolor('#2a0a0a' if v < 0 else BG)
                elif v > 0:
                    cell.set_facecolor('#0a2a0a')
            except Exception:
                pass

    ax7.set_title('Key Metrics', color=TEXT, fontsize=11, pad=6)

    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#0d0d0d')
    print(f"  Chart saved → {output_path}")
