"""
Telegram notifier — push ENTER signals (and portfolio plans) to your phone.

Configure with env vars TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (or signal.telegram
in config). With no token it runs in dry-run mode: it formats and prints the
message instead of sending, so you can preview exactly what would be delivered.

Get a token from @BotFather; get your chat id by messaging the bot then visiting
https://api.telegram.org/bot<TOKEN>/getUpdates
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_DIR_EMOJI = {"LONG": "\U0001F7E2", "SHORT": "\U0001F534", "NEUTRAL": "⚪"}
_DEC_EMOJI = {"ENTER": "✅", "WAIT": "⏸️", "AVOID": "\U0001F6AB"}


class TelegramNotifier:
    def __init__(self, config: dict):
        cfg = config.get("signal", {}).get("telegram", {})
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("bot_token", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("chat_id", "")
        self.enabled = bool(self.token and self.chat_id)

    # ---- transport ------------------------------------------------------
    def send(self, text: str) -> bool:
        """Send a message; in dry-run (no token) print it and return False."""
        if not self.enabled:
            logger.info("Telegram not configured (dry-run). Message:\n%s", text)
            print("\n----- TELEGRAM (dry-run) -----\n" + text +
                  "\n------------------------------")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urlencode({
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }).encode()
        try:
            urlopen(Request(url, data=data), timeout=10)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Telegram send failed: %s", e)
            return False

    # ---- formatting -----------------------------------------------------
    @staticmethod
    def format_signal(sig) -> str:
        d = sig.to_dict()
        de = _DEC_EMOJI.get(d["decision"], "")
        di = _DIR_EMOJI.get(d["direction"], "")
        lines = [
            f"{de} {d['symbol']} {di} {d['direction']} — {d['decision']}",
            f"TF {d['entry_timeframe']}/{d['htf_timeframe']} | confidence {d['confidence']}/100",
        ]
        if d.get("entry"):
            lines.append(f"Entry: {d['entry']:g}  (zone {d.get('entry_zone')})")
            lines.append(f"Stop:  {d['stop_loss']:g}")
            pp = d.get("position_plan", {})
            for tp in pp.get("take_profits", []):
                lines.append(
                    f"  {tp.get('label','TP')}: {tp['price']:g} "
                    f"({tp['r_multiple']}R, close {tp['allocation_pct']}%)"
                )
            lines.append(
                f"Risk {pp.get('risk_per_trade_pct')}% (~{pp.get('risk_amount')}) | "
                f"size {pp.get('position_size_units')} | lev {pp.get('suggested_leverage')}x"
            )
            lines.append(
                f"Blended R:R {pp.get('blended_rr')} | EV {pp.get('expected_value_r')}R"
            )
        if d.get("news", {}).get("summary"):
            lines.append(f"News: {d['news']['summary']}")
        for w in d.get("warnings", [])[:3]:
            lines.append(f"⚠️ {w}")
        lines.append("\nDecision-support only. Manage your risk.")
        return "\n".join(lines)

    @staticmethod
    def format_market_summary(overview: dict, top_rows, news=None, events=None) -> str:
        b = overview.get("breadth", {})
        c = overview.get("decisions", {})
        lines = [
            f"\U0001F4CA Daily Market Summary — {overview.get('date','')}",
            f"Regime: {overview.get('regime_label','n/a')}",
            f"Breadth: \U0001F7E2{b.get('bullish',0)} / \U0001F534{b.get('bearish',0)} / "
            f"⚪{b.get('neutral',0)} of {b.get('total',0)}  →  bias {overview.get('bias','—')}",
            f"Setups: {c.get('ENTER',0)} ENTER · {c.get('WAIT',0)} WAIT · {c.get('AVOID',0)} AVOID",
        ]
        if top_rows:
            lines.append("Top watch:")
            for r in top_rows:
                d = r.to_dict()
                di = _DIR_EMOJI.get(d["direction"], "")
                rr = f"R:R {d['blended_rr']}" if d.get("entry") else ""
                lines.append(
                    f"  {di} {d['symbol']} {d['direction']} · conf {d['confidence']} "
                    f"{rr} · {d['decision']}"
                )
        if news and news.get("summary"):
            s = news.get("sentiment_score", 0.0)
            mood = "bullish" if s > 0.15 else "bearish" if s < -0.15 else "neutral"
            line = f"\U0001F4F0 News: {mood} ({s:+.2f}) — {news['summary']}"
            if news.get("high_impact_event"):
                line += "  ⚠️ high-impact"
            lines.append(line)
        if events:
            lines.append("\U0001F4C5 Upcoming high-impact events:")
            for e in events[:4]:
                lines.append(f"  • {e.get('name')} @ {e.get('time')}")
        if c.get("ENTER", 0) == 0:
            lines.append("\nNo high-conviction ENTER today — stay patient.")
        lines.append("\nDecision-support only. Manage your risk.")
        return "\n".join(lines)

    @staticmethod
    def format_scan(rows, plan=None, top: int = 5) -> str:
        enters = [r for r in rows if r.decision == "ENTER"]
        if not enters:
            return "Scan complete: no ENTER setups right now."
        lines = [f"\U0001F4E1 Scan: {len(enters)} ENTER setup(s)"]
        for r in enters[:top]:
            d = r.to_dict()
            di = _DIR_EMOJI.get(d["direction"], "")
            lines.append(
                f"{di} {d['symbol']} {d['direction']} | conf {d['confidence']} | "
                f"entry {d['entry']:g} SL {d['stop_loss']:g} | "
                f"R:R {d['blended_rr']} EV {d['expected_value_r']}R"
            )
        if plan is not None and plan.allocations:
            lines.append(
                f"\nPortfolio: heat {plan.total_risk_pct:.1f}% "
                f"(L {plan.long_risk_pct:.1f}/S {plan.short_risk_pct:.1f}), "
                f"gross lev {plan.gross_leverage:.1f}x"
            )
            for a in plan.allocations:
                ad = a.to_dict()
                lines.append(
                    f"  {ad['symbol']} {a.direction}: risk {ad['risk_pct']}% "
                    f"size {ad['size_units']:g} (${ad['notional']:g})"
                )
        lines.append("\nDecision-support only. Manage your risk.")
        return "\n".join(lines)
