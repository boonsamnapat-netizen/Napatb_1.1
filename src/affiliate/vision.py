"""Turn a product photo into a search query.

Uses the Anthropic API when ``ANTHROPIC_API_KEY`` is set; otherwise the bot
asks the user to type the product name, which keeps the pipeline usable with
no credentials at all.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

PROMPT = (
    "ดูรูปสินค้านี้แล้วตอบสั้น ๆ 2 บรรทัดเท่านั้น:\n"
    "บรรทัด 1: คำค้นหาสินค้าภาษาไทย (ยี่ห้อ+ประเภท+รุ่น ถ้าเห็น) ไม่เกิน 12 คำ\n"
    "บรรทัด 2: จุดขายเด่นที่สุด 1 ข้อ สั้น ๆ ไม่เกิน 10 คำ\n"
    "ห้ามเดายี่ห้อถ้าอ่านไม่ออก ให้บอกแค่ประเภทสินค้า"
)


@dataclass
class Description:
    """What the model read off the photo."""

    query: str
    benefit: str | None = None
    source: str = "model"


class ProductVision:
    """Describe a product photo, or report that no model is available."""

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def describe(self, image_path: str) -> Description | None:
        """Return a query for the photo, or None when unavailable."""
        if not self.configured:
            return None
        try:
            import anthropic
        except ImportError:
            log.warning("anthropic package not installed; skipping photo description")
            return None
        media_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        with open(image_path, "rb") as fh:
            data = base64.b64encode(fh.read()).decode()
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64",
                                                     "media_type": media_type,
                                                     "data": data}},
                        {"type": "text", "text": PROMPT},
                    ],
                }],
            )
        except Exception as exc:  # any API/network problem falls back to manual
            log.warning("photo description failed: %s", exc)
            return None
        return self._parse("".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ))

    @staticmethod
    def _parse(text: str) -> Description | None:
        lines = [ln.strip(" -•\t") for ln in text.strip().splitlines() if ln.strip()]
        if not lines:
            return None
        return Description(query=lines[0], benefit=lines[1] if len(lines) > 1 else None)
