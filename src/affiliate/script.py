"""Build the 8-second clip script, caption and hashtags from a product.

Structure follows the four-beat short-form template:
    0.0-1.5s hook · 1.5-4.0s benefit · 4.0-6.5s price · 6.5-8.0s CTA
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .products import Product

DURATION = 8.0

# (start, end, role) — one row per on-screen beat.
BEATS: list[tuple[float, float, str]] = [
    (0.0, 1.5, "hook"),
    (1.5, 4.0, "benefit"),
    (4.0, 6.5, "price"),
    (6.5, 8.0, "cta"),
]

# TikTok down-ranks clips that say this; the basket sticker is the CTA.
CTA_TEXT = "กดตะกร้าเลย 👇"

BASE_HASHTAGS = ["#ของดีบอกต่อ", "#รีวิวของใช้", "#ติดตะกร้า", "#TikTokShop"]


@dataclass
class ClipScript:
    """On-screen text per beat, plus the post caption."""

    hook: str
    benefit: str
    price: str
    cta: str = CTA_TEXT
    voiceover: str = ""
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)

    def lines(self) -> list[tuple[float, float, str]]:
        """(start, end, text) tuples ready for a video renderer."""
        by_role = {"hook": self.hook, "benefit": self.benefit,
                   "price": self.price, "cta": self.cta}
        return [(start, end, by_role[role]) for start, end, role in BEATS]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook, "benefit": self.benefit, "price": self.price,
            "cta": self.cta, "voiceover": self.voiceover,
            "caption": self.caption, "hashtags": self.hashtags,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ClipScript":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


def build(product: Product, benefit: str | None = None,
          hook: str | None = None) -> ClipScript:
    """Compose a script for one product. Explicit hook/benefit override defaults."""
    name = product.title.strip() or "สินค้าชิ้นนี้"
    short = name if len(name) <= 28 else name[:27] + "…"
    price_line = f"เหลือ {product.price:,.0f} บาท" if product.price is not None \
        else "ราคาในตะกร้า"
    script = ClipScript(
        hook=hook or f"ยังไม่มี{short} อีกเหรอ?",
        benefit=benefit or "ใช้ง่าย เห็นผลตั้งแต่ครั้งแรก",
        price=price_line,
        voiceover=f"{short} {price_line} กดตะกร้าได้เลย",
    )
    script.caption = _caption(product, script)
    script.hashtags = hashtags(product)
    return script


def hashtags(product: Product, extra: list[str] | None = None) -> list[str]:
    tags = list(BASE_HASHTAGS)
    if product.platform == "lazada":
        tags.append("#Lazada")
    for word in product.title.split()[:2]:
        cleaned = _tag_safe(word)
        if len(cleaned) >= 3:
            tags.append(f"#{cleaned[:24]}")
    for tag in extra or []:
        tags.append(tag if tag.startswith("#") else f"#{tag}")
    # Preserve order while dropping repeats.
    return list(dict.fromkeys(tags))


def _tag_safe(word: str) -> str:
    """Strip punctuation for a hashtag while keeping Thai vowel and tone marks.

    ``str.isalnum()`` is False for combining marks (category Mn), so filtering
    on it alone turns "ตัวอย่าง" into "ตวอยาง".
    """
    return "".join(ch for ch in word
                   if ch.isalnum() or unicodedata.category(ch) == "Mn")


def _caption(product: Product, script: ClipScript) -> str:
    lines = [script.hook, script.benefit]
    if product.price is not None:
        lines.append(f"💰 {script.price}")
    lines.append(CTA_TEXT)
    return "\n".join(lines)


def storyboard(script: ClipScript) -> str:
    """Human-readable shot list for the Telegram approval message."""
    rows = [f"⏱ {start:.1f}–{end:.1f} วิ · {text}"
            for start, end, text in script.lines()]
    return "\n".join(rows)
