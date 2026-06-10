"""Telegram alert sender for NAPATB AI Trading."""

import os
import requests

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


def _stars(prob: float) -> str:
    if prob >= 0.65:
        return '⭐⭐⭐'
    if prob >= 0.50:
        return '⭐⭐'
    return '⭐'


def send_signal_card(signal: dict, market_ok: bool) -> bool:
    """Format and send a signal card for one ticker."""
    entry      = signal.get('entry_price', 0.0)
    stop       = signal.get('stop_price',  0.0)
    target     = signal.get('target_price', 0.0)
    stop_pct   = abs((stop - entry) / entry * 100) if entry else 0.0
    ai_prob    = signal.get('ai_prob', 0.5)
    vol_ratio  = signal.get('vol_ratio', 1.0)
    strategy   = signal.get('strategy', 'N/A')
    ticker     = signal.get('ticker', 'N/A')
    date       = signal.get('date', '')
    stars      = _stars(ai_prob)

    text = (
        f'🔔 <b>NAPATB Signal</b> — {date}\n\n'
        f'📈 <b>{ticker}</b>  [{strategy}]\n'
        f'   Entry : ${entry:.2f}\n'
        f'   Stop  : ${stop:.2f}  ({stop_pct:.1f}%)\n'
        f'   Target: ${target:.2f}  (+25%)\n'
        f'   AI Prob: {ai_prob:.2f}  {stars}\n'
        f'   Vol Surge: {vol_ratio:.1f}x avg\n\n'
        f'Market: SPY above 200MA {"✅" if market_ok else "❌"}'
    )
    return send_message(text)


def send_daily_summary(signals: list, trades_placed: int, equity: float) -> bool:
    """Send end-of-day summary."""
    text = (
        f'📊 <b>NAPATB Daily Summary</b>\n\n'
        f'Signals found : {len(signals)}\n'
        f'Trades placed : {trades_placed}\n'
        f'Portfolio equity: ${equity:,.2f}'
    )
    return send_message(text)
