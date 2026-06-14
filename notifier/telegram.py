"""Telegram alert sender for NAPATB AI Trading."""

import os
import tempfile
import requests
import pandas as pd

_TOKEN   = None
_CHAT_ID = None


def _credentials():
    global _TOKEN, _CHAT_ID
    if _TOKEN is None:
        _TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
        _CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    return _TOKEN, _CHAT_ID


def send_message(text: str) -> bool:
    """Send plain HTML text via Telegram Bot API. Returns True on success."""
    token, chat_id = _credentials()
    if not token or not chat_id:
        print('[Telegram] Not configured — skipping message.')
        return False
    try:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        resp = requests.post(
            url,
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f'[Telegram] Error: {e}')
        return False


def _send_photo(photo_path: str, caption: str) -> bool:
    """Send a photo file via Telegram sendPhoto."""
    token, chat_id = _credentials()
    if not token or not chat_id:
        return False
    try:
        url = f'https://api.telegram.org/bot{token}/sendPhoto'
        with open(photo_path, 'rb') as f:
            resp = requests.post(
                url,
                data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
                files={'photo': f},
                timeout=30,
            )
        return resp.status_code == 200
    except Exception as e:
        print(f'[Telegram] Photo error: {e}')
        return False


def build_chart(ticker: str, df: pd.DataFrame, signal: dict) -> str:
    """
    Generate a price chart PNG and return the temp file path.
    Caller is responsible for deleting the file.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np

    entry  = signal.get('entry_price', 0.0)
    stop   = signal.get('stop_price',  0.0)
    target = signal.get('target_price', 0.0)

    # Last 90 trading days
    chart_df = df.tail(90).copy()
    dates    = list(range(len(chart_df)))
    closes   = chart_df['Close'].values
    volumes  = chart_df['Volume'].values if 'Volume' in chart_df else None

    BG    = '#0d1117'
    GRID  = '#21262d'
    WHITE = '#e6edf3'
    GREEN = '#3fb950'
    RED   = '#f85149'
    BLUE  = '#58a6ff'
    ORG   = '#d29922'

    fig = plt.figure(figsize=(10, 6), facecolor=BG)
    gs  = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.05)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    for ax in (ax1, ax2):
        ax.set_facecolor(BG)
        ax.tick_params(colors=WHITE, labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID)

    # Price line
    ax1.plot(dates, closes, color=WHITE, linewidth=1.2, zorder=3)

    # SMA50
    if 'sma50' in chart_df.columns:
        ax1.plot(dates, chart_df['sma50'].values, color=ORG,
                 linewidth=1.0, alpha=0.85, label='SMA50')

    # SMA200
    if 'sma200' in chart_df.columns:
        ax1.plot(dates, chart_df['sma200'].values, color=RED,
                 linewidth=1.0, alpha=0.85, label='SMA200')

    # Entry / Stop / Target horizontal lines
    last_x = dates[-1]
    ax1.axhline(entry,  color=GREEN, linestyle='--', linewidth=1.0, alpha=0.9)
    ax1.axhline(stop,   color=RED,   linestyle='--', linewidth=1.0, alpha=0.9)
    ax1.axhline(target, color=BLUE,  linestyle='--', linewidth=1.0, alpha=0.7)

    ax1.annotate(f'Entry ${entry:.2f}',  xy=(last_x, entry),  color=GREEN, fontsize=7, va='center')
    ax1.annotate(f'Stop  ${stop:.2f}',   xy=(last_x, stop),   color=RED,   fontsize=7, va='center')
    ax1.annotate(f'Tgt   ${target:.2f}', xy=(last_x, target), color=BLUE,  fontsize=7, va='center')

    # Signal triangle at last bar
    ax1.scatter([dates[-1]], [closes[-1]], marker='^', color=GREEN, s=80, zorder=5)

    ax1.legend(loc='upper left', fontsize=7, facecolor=BG, edgecolor=GRID,
               labelcolor=WHITE, framealpha=0.7)
    ax1.set_title(
        f'{ticker}  [{signal.get("strategy","N/A")}]  AI {signal.get("ai_prob", 0):.0%}',
        color=WHITE, fontsize=10, pad=6,
    )
    ax1.yaxis.tick_right()
    ax1.grid(color=GRID, linewidth=0.5, zorder=0)
    plt.setp(ax1.get_xticklabels(), visible=False)

    # Volume bars
    if volumes is not None:
        avg_vol = np.nanmean(volumes) if len(volumes) else 1
        bar_colors = [GREEN if v >= avg_vol else GRID for v in volumes]
        ax2.bar(dates, volumes, color=bar_colors, width=0.8, zorder=2)
        ax2.set_ylabel('Vol', color=WHITE, fontsize=7)
        ax2.yaxis.tick_right()
        ax2.grid(color=GRID, linewidth=0.4, zorder=0)

    # X-axis ticks: show a few date labels
    step = max(1, len(dates) // 6)
    tick_locs  = dates[::step]
    tick_labels = [str(chart_df.index[i].date()) for i in tick_locs]
    ax2.set_xticks(tick_locs)
    ax2.set_xticklabels(tick_labels, rotation=30, ha='right', fontsize=7, color=WHITE)

    fig.tight_layout(pad=0.5)

    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    fig.savefig(tmp.name, dpi=120, facecolor=BG, bbox_inches='tight')
    plt.close(fig)
    return tmp.name


def _stars(prob: float) -> str:
    if prob >= 0.65:
        return '⭐⭐⭐'
    if prob >= 0.50:
        return '⭐⭐'
    return '⭐'


def send_signal_card(signal: dict, market_ok: bool, df: pd.DataFrame = None) -> bool:
    """Format and send a signal card. If df is provided, attach a price chart."""
    entry      = signal.get('entry_price', 0.0)
    stop       = signal.get('stop_price',  0.0)
    target     = signal.get('target_price', 0.0)
    stop_pct   = abs((stop - entry) / entry * 100) if entry else 0.0
    target_pct = abs((target - entry) / entry * 100) if entry else 0.0
    ai_prob    = signal.get('ai_prob', 0.5)
    vol_ratio  = signal.get('vol_ratio', 1.0)
    strategy   = signal.get('strategy', 'N/A')
    ticker     = signal.get('ticker', 'N/A')
    date       = signal.get('date', '')
    stars      = _stars(ai_prob)

    caption = (
        f'🔔 <b>NAPATB Signal</b> — {date}\n\n'
        f'📈 <b>{ticker}</b>  [{strategy}]\n'
        f'   Entry : ${entry:.2f}\n'
        f'   Stop  : ${stop:.2f}  (-{stop_pct:.1f}%)\n'
        f'   Target: ${target:.2f}  (+{target_pct:.1f}%)\n'
        f'   AI Prob: {ai_prob:.2f}  {stars}\n'
        f'   Vol Surge: {vol_ratio:.1f}x avg\n\n'
        f'Market: SPY above 200MA {"✅" if market_ok else "❌"}'
    )

    if df is not None and len(df) >= 20:
        chart_path = None
        try:
            chart_path = build_chart(ticker, df, signal)
            return _send_photo(chart_path, caption)
        except Exception as e:
            print(f'[Telegram] Chart build failed for {ticker}: {e}')
        finally:
            if chart_path:
                try:
                    os.unlink(chart_path)
                except OSError:
                    pass

    return send_message(caption)


def send_daily_summary(signals: list, trades_placed: int, equity: float) -> bool:
    """Send end-of-day summary."""
    text = (
        f'📊 <b>NAPATB Daily Summary</b>\n\n'
        f'Signals found : {len(signals)}\n'
        f'Trades placed : {trades_placed}\n'
        f'Portfolio equity: ${equity:,.2f}'
    )
    return send_message(text)
