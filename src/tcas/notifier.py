"""ส่งข้อความเข้า Telegram.

อ่าน token/chat id จาก environment เท่านั้น (ไม่เก็บใน repo):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

ถ้าไม่มี secret จะเข้าโหมด dry-run — พิมพ์ข้อความออกหน้าจอแทนการส่ง
ทำให้รันในแซนด์บ็อกซ์/เครื่องตัวเองได้โดยไม่ต้องตั้งค่าอะไรเลย

ตั้งค่า bot ครั้งแรก: ดู docs/TELEGRAM_SETUP.md (ใช้ bot ตัวเดิมกับระบบ crypto ได้)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

API_BASE = "https://api.telegram.org"

# Telegram ตัดข้อความที่ยาวเกิน 4096 ตัวอักษร — เผื่อไว้เล็กน้อย
MAX_MESSAGE_CHARS = 4000


class TelegramNotifier:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        tg = ((cfg or {}).get("telegram")) or {}
        self.enabled = bool(tg.get("enabled", True))
        self.parse_mode = tg.get("parse_mode", "HTML")
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.token and self.chat_id)

    def send(self, text: str, quiet: bool = False) -> bool:
        """ส่งข้อความ คืน True ถ้าส่งสำเร็จจริง (dry-run คืน False)."""
        if not self.configured:
            if not quiet:
                reason = "ปิดการแจ้งเตือนใน config" if not self.enabled else "ไม่ได้ตั้ง TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID"
                print(f"[dry-run] {reason} — ข้อความที่จะส่ง:\n")
                print(text)
            return False

        ok = True
        for chunk in _split(text, MAX_MESSAGE_CHARS):
            ok = self._post(chunk) and ok
        return ok

    def _post(self, text: str) -> bool:
        url = f"{API_BASE}/bot{self.token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": self.parse_mode,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if not body.get("ok"):
                    print(f"[telegram] ส่งไม่สำเร็จ: {body.get('description')}")
                    return False
                return True
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            print(f"[telegram] HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"[telegram] ต่อไม่ได้: {exc}")
        return False


def _split(text: str, limit: int) -> list:
    """ซอยข้อความยาวเป็นหลายก้อน โดยพยายามตัดที่ขึ้นบรรทัดใหม่."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        # บรรทัดเดียวยาวเกิน limit — จำเป็นต้องหั่นกลางบรรทัด
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks
