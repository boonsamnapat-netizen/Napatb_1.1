"""Telegram delivery + Thai-language message formatting for divergence signals.

If TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are not set the notifier runs in
dry-run mode: it formats and prints the message but does not hit the network
(handy in the sandbox, which cannot reach api.telegram.org anyway).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from .signal_engine import Signal

# Side -> emoji, kept minimal so the alert stays readable on mobile.
_SIDE_EMOJI = {"LONG": "🟢", "SHORT": "🔴"}


def format_signal(sig: Signal) -> str:
    """Render a signal in the requested compact format (Thai-friendly)."""
    coin = sig.symbol.replace("USDT", "").replace("USD", "")
    emoji = _SIDE_EMOJI.get(sig.side, "")
    lines = [
        f"{emoji} เหรียญ {coin}",
        f"Signal: {sig.kind}",
        f"Indicator status: {sig.status}",
        f"Entry: {sig.entry}",
        f"SL: {sig.sl}",
        f"TP1: {sig.tp1}",
        f"TP2: {sig.tp2}",
        f"TP3: {sig.tp3}",
        f"RR: {sig.rr_text}",
    ]
    return "\n".join(lines)


def format_summary(signals: list[Signal]) -> str:
    if not signals:
        return "ไม่พบสัญญาณ divergence ในรอบนี้"
    longs = sum(1 for s in signals if s.side == "LONG")
    shorts = sum(1 for s in signals if s.side == "SHORT")
    return (
        f"📡 สรุปสัญญาณ divergence: {len(signals)} เหรียญ "
        f"(LONG {longs} / SHORT {shorts})"
    )


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        """Send a text message. Returns True if delivered, False on dry-run/fail."""
        if not self.configured:
            print("[DRY-RUN] Telegram not configured — message below:\n" + text)
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": "true"}
        ).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
                return bool(payload.get("ok"))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"[telegram] send failed: {exc}")
            return False

    def send_signal(self, sig: Signal) -> bool:
        return self.send(format_signal(sig))
