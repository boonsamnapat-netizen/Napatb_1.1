"""
Telegram notifier — push ENTER signals and a daily market summary (in Thai) to
your phone.

Configure with env vars TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (or signal.telegram
in config). With no token it runs in dry-run mode: it formats and prints the
message instead of sending, so you can preview exactly what would be delivered.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def _thai_time(iso: str) -> str:
    """ISO UTC -> 'DD/MM HH:MM น. (ไทย)' (UTC+7)."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")) + timedelta(hours=7)
        return dt.strftime("%d/%m %H:%M") + " น. (ไทย)"
    except Exception:  # noqa: BLE001
        return str(iso)

_DIR_EMOJI = {"LONG": "\U0001F7E2", "SHORT": "\U0001F534", "NEUTRAL": "⚪"}
_DEC_EMOJI = {"ENTER": "✅", "WAIT": "⏸️", "AVOID": "\U0001F6AB"}
# Thai labels
_DIR_TH = {"LONG": "ซื้อ (ขาขึ้น)", "SHORT": "ขาย (ขาลง)", "NEUTRAL": "ยังไม่ชัด"}
_DEC_TH = {"ENTER": "เข้าได้", "WAIT": "รอจังหวะ", "AVOID": "เลี่ยง"}
_DISCLAIMER = "⚠️ เป็นข้อมูลช่วยตัดสินใจ ไม่ใช่คำสั่งซื้อขาย — บริหารความเสี่ยงเองทุกครั้ง"


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

    # ---- single signal (ENTER alert) ------------------------------------
    @staticmethod
    def format_signal(sig) -> str:
        d = sig.to_dict()
        de = _DEC_EMOJI.get(d["decision"], "")
        di = _DIR_EMOJI.get(d["direction"], "")
        dec_th = _DEC_TH.get(d["decision"], d["decision"])
        dir_th = _DIR_TH.get(d["direction"], d["direction"])
        lines = [
            f"{de} {d['symbol']} {di} {dir_th} — {dec_th}",
            f"กรอบเวลา {d['entry_timeframe']}/{d['htf_timeframe']} | "
            f"ความมั่นใจ {d['confidence']}/100",
        ]
        if d.get("entry"):
            lines.append(f"จุดเข้า: {d['entry']:g}  (โซน {d.get('entry_zone')})")
            lines.append(f"จุดตัดขาดทุน (SL): {d['stop_loss']:g}")
            pp = d.get("position_plan", {})
            lines.append("เป้าทำกำไร (TP):")
            for tp in pp.get("take_profits", []):
                lines.append(
                    f"  • {tp['price']:g}  ({tp['r_multiple']} เท่าของความเสี่ยง, "
                    f"ปิดไม้ {tp['allocation_pct']}%)"
                )
            lines.append(
                f"ความเสี่ยงต่อไม้: {pp.get('risk_per_trade_pct')}% "
                f"(~{pp.get('risk_amount')}) | ขนาด {pp.get('position_size_units')} | "
                f"เลเวอเรจ {pp.get('suggested_leverage')}x"
            )
            lines.append(
                f"กำไรต่อขาดทุน {pp.get('blended_rr')} เท่า | "
                f"ค่าคาดหวัง {pp.get('expected_value_r')}R"
            )
        for w in d.get("warnings", [])[:3]:
            lines.append(f"⚠️ {w}")
        lines.append(
            "\n💡 ทำตามแผน: เข้าตามจุดเข้า ตั้ง SL/TP ทันที และอย่าเลื่อน SL หนีขาดทุน"
        )
        lines.append(_DISCLAIMER)
        return "\n".join(lines)

    # ---- daily market summary -------------------------------------------
    @staticmethod
    def _advice(overview, news, events, enters) -> list[str]:
        tips: list[str] = []
        risk_off = "Risk-OFF" in overview.get("regime_label", "") or \
                   "ลง" in overview.get("regime_label", "")
        bias = overview.get("bias", "")
        if risk_off:
            tips.append("เทรนด์ใหญ่ยังเป็นขาลง → ระวังการสวนซื้อ (long) ฝั่งขายได้เปรียบกว่า")
        elif "ON" in overview.get("regime_label", "") or "ขึ้น" in overview.get("regime_label", ""):
            tips.append("เทรนด์ใหญ่เป็นขาขึ้น → เน้นหาจังหวะซื้อตามเทรนด์ มากกว่าฝืนขาย")
        if enters == 0:
            tips.append("วันนี้ยังไม่มีจังหวะคุณภาพพอ → แนะนำ \"รอ\" อย่าฝืนเข้าเทรด")
        else:
            tips.append(f"มี {enters} สัญญาณเข้า → ดูรายละเอียดแต่ละไม้ ทำตามแผน SL/TP เสมอ")
        if events:
            names = ", ".join(e.get("name", "") for e in events[:2])
            tips.append(
                f"มีเหตุการณ์สำคัญใกล้นี้ ({names}) → ลดขนาดไม้ หรือรอหลังข่าว "
                f"เพราะตลาดมักผันผวนแรง"
            )
        if news and news.get("high_impact_event"):
            tips.append("ข่าวบอกว่ามีปัจจัยกระทบแรง → เพิ่มความระมัดระวังเป็นพิเศษ")
        return tips

    @staticmethod
    def format_market_summary(overview: dict, top_rows, news=None, events=None) -> str:
        b = overview.get("breadth", {})
        c = overview.get("decisions", {})
        enters = c.get("ENTER", 0)
        lines = [
            f"\U0001F4CA สรุปตลาดคริปโตวันนี้ — {overview.get('date','')}",
            "",
            f"🧭 ภาวะตลาด (เทรนด์ใหญ่): {overview.get('regime_label','ไม่ทราบ')}",
            f"📈 ทิศทางเหรียญ: ขึ้น \U0001F7E2{b.get('bullish',0)} / "
            f"ลง \U0001F534{b.get('bearish',0)} / กลางๆ ⚪{b.get('neutral',0)} "
            f"จาก {b.get('total',0)} เหรียญ  →  ภาพรวม {overview.get('bias','—')}",
            f"🎯 สัญญาณ: เข้าได้ {enters} · รอจังหวะ {c.get('WAIT',0)} · เลี่ยง {c.get('AVOID',0)}",
        ]
        if top_rows:
            lines.append("")
            lines.append("👀 เหรียญน่าจับตา:")
            for r in top_rows:
                d = r.to_dict()
                di = _DIR_EMOJI.get(d["direction"], "")
                dir_th = _DIR_TH.get(d["direction"], d["direction"])
                dec_th = _DEC_TH.get(d["decision"], d["decision"])
                rr = f" · กำไร:ขาดทุน {d['blended_rr']} เท่า" if d.get("entry") else ""
                lines.append(
                    f"  {di} {d['symbol']} {dir_th} · มั่นใจ {d['confidence']}{rr} · {dec_th}"
                )
        if news and news.get("summary"):
            s = news.get("sentiment_score", 0.0)
            mood = "ค่อนข้างบวก" if s > 0.15 else "ค่อนข้างลบ" if s < -0.15 else "เป็นกลาง"
            lines.append("")
            lines.append(f"📰 อารมณ์ข่าว: {mood} ({s:+.2f})")
        if events:
            lines.append("📅 เหตุการณ์สำคัญใกล้นี้:")
            for e in events[:4]:
                lines.append(f"  • {e.get('name')} — {_thai_time(e.get('time'))}")
        tips = TelegramNotifier._advice(overview, news, events, enters)
        if tips:
            lines.append("")
            lines.append("💡 คำแนะนำวันนี้:")
            for t in tips:
                lines.append(f"  • {t}")
        lines.append("")
        lines.append(_DISCLAIMER)
        return "\n".join(lines)

    # ---- scan ENTER digest ----------------------------------------------
    @staticmethod
    def format_scan(rows, plan=None, top: int = 5) -> str:
        enters = [r for r in rows if r.decision == "ENTER"]
        if not enters:
            return "สแกนเสร็จแล้ว: ตอนนี้ยังไม่มีสัญญาณเข้า (ENTER) — แนะนำรอจังหวะ"
        lines = [f"\U0001F4E1 พบสัญญาณเข้า {len(enters)} เหรียญ"]
        for r in enters[:top]:
            d = r.to_dict()
            di = _DIR_EMOJI.get(d["direction"], "")
            dir_th = _DIR_TH.get(d["direction"], d["direction"])
            lines.append(
                f"{di} {d['symbol']} {dir_th} | มั่นใจ {d['confidence']} | "
                f"เข้า {d['entry']:g} ตัดขาดทุน {d['stop_loss']:g} | "
                f"กำไร:ขาดทุน {d['blended_rr']} เท่า"
            )
        if plan is not None and plan.allocations:
            lines.append(
                f"\nพอร์ต: ความเสี่ยงรวม {plan.total_risk_pct:.1f}% "
                f"(ซื้อ {plan.long_risk_pct:.1f}/ขาย {plan.short_risk_pct:.1f}), "
                f"เลเวอเรจรวม {plan.gross_leverage:.1f}x"
            )
            for a in plan.allocations:
                ad = a.to_dict()
                lines.append(
                    f"  {ad['symbol']} {_DIR_TH.get(a.direction, a.direction)}: "
                    f"เสี่ยง {ad['risk_pct']}% ขนาด {ad['size_units']:g} (${ad['notional']:g})"
                )
        lines.append("\n" + _DISCLAIMER)
        return "\n".join(lines)
