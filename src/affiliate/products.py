"""Product candidates, the finder interface, and the link-picking strategies."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

# Link strategies offered to the user after the clip is approved.
CHEAPEST = "cheapest"
BEST_SELLING = "best_selling"
TOP_COMMISSION = "top_commission"

STRATEGY_LABELS = {
    CHEAPEST: "💰 ถูกสุด",
    BEST_SELLING: "🔥 ขายดีสุด",
    TOP_COMMISSION: "💸 ค่าคอมเยอะสุด",
}


class ProviderNotConfigured(RuntimeError):
    """A finder needs credentials that are not set."""


@dataclass
class Product:
    """One listing to choose between. Optional fields disable strategies."""

    title: str
    url: str
    platform: str = "unknown"
    price: float | None = None
    sold: int | None = None
    commission_pct: float | None = None
    shop: str | None = None
    image_url: str | None = None

    @property
    def commission_value(self) -> float | None:
        """Estimated baht earned per sale — what 'most commission' really means."""
        if self.price is None or self.commission_pct is None:
            return None
        return self.price * self.commission_pct / 100.0

    def summary(self) -> str:
        bits = [f"<b>{self.title}</b>"]
        meta = []
        if self.price is not None:
            meta.append(f"฿{self.price:,.0f}")
        if self.sold is not None:
            meta.append(f"ขายแล้ว {self.sold:,}")
        if self.commission_pct is not None:
            earn = self.commission_value
            meta.append(
                f"คอม {self.commission_pct:g}%"
                + (f" (≈฿{earn:,.0f})" if earn is not None else "")
            )
        if meta:
            bits.append(" · ".join(meta))
        bits.append(f"{self.platform} · {self.url}")
        return "\n".join(bits)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Product":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


class ProductFinder(Protocol):
    """Turn a text query (derived from the photo) into candidate listings."""

    name: str

    def search(self, query: str, limit: int = 10) -> list[Product]:
        ...


class ManualFinder:
    """No API needed: the user pastes the listings they want compared.

    Accepted per line — a bare URL, or pipe-separated fields:
        ``ชื่อ | url | ราคา | ยอดขาย | คอม%``
    Missing numbers simply make the matching strategy unavailable.
    """

    name = "manual"

    def search(self, query: str, limit: int = 10) -> list[Product]:
        return []

    def parse(self, text: str, platform_hint: str = "manual") -> list[Product]:
        products: list[Product] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("/"):
                continue
            product = self._parse_line(line, platform_hint)
            if product:
                products.append(product)
        return products

    def _parse_line(self, line: str, platform_hint: str) -> Product | None:
        parts = [p.strip() for p in line.split("|")]
        url = next((p for p in parts if p.lower().startswith("http")), None)
        if not url:
            return None
        rest = [p for p in parts if p is not url]
        title = next((p for p in rest if not _is_number(p)), None) or "สินค้า"
        numbers = [p for p in rest if _is_number(p)]
        price = _to_float(numbers[0]) if len(numbers) > 0 else None
        sold = int(_to_float(numbers[1])) if len(numbers) > 1 else None
        commission = _to_float(numbers[2]) if len(numbers) > 2 else None
        return Product(
            title=title,
            url=url,
            platform=detect_platform(url) or platform_hint,
            price=price,
            sold=sold,
            commission_pct=commission,
        )


class LazadaFinder:
    """Lazada affiliate search — needs app credentials that are not set yet."""

    name = "lazada"

    def __init__(self, app_key: str = "", app_secret: str = "", endpoint: str = ""):
        self.app_key, self.app_secret, self.endpoint = app_key, app_secret, endpoint

    def search(self, query: str, limit: int = 10) -> list[Product]:
        raise ProviderNotConfigured(
            "Lazada affiliate API is not wired up: set affiliate.finders.lazada."
            "{app_key,app_secret,endpoint} in config/affiliate.yaml"
        )


class TikTokFinder:
    """TikTok Shop affiliate search — needs an approved developer app."""

    name = "tiktok"

    def __init__(self, app_key: str = "", app_secret: str = "", endpoint: str = ""):
        self.app_key, self.app_secret, self.endpoint = app_key, app_secret, endpoint

    def search(self, query: str, limit: int = 10) -> list[Product]:
        raise ProviderNotConfigured(
            "TikTok Shop affiliate API is not wired up: set affiliate.finders.tiktok."
            "{app_key,app_secret,endpoint} in config/affiliate.yaml"
        )


def detect_platform(url: str) -> str | None:
    lowered = url.lower()
    if "lazada" in lowered:
        return "lazada"
    if "tiktok" in lowered:
        return "tiktok"
    if "shopee" in lowered:
        return "shopee"
    return None


def pick(products: list[Product], strategy: str) -> Product | None:
    """Best listing for a strategy, or None when no candidate carries that field."""
    if not products:
        return None
    if strategy == CHEAPEST:
        scored = [p for p in products if p.price is not None]
        return min(scored, key=lambda p: p.price) if scored else None
    if strategy == BEST_SELLING:
        scored = [p for p in products if p.sold is not None]
        return max(scored, key=lambda p: p.sold) if scored else None
    if strategy == TOP_COMMISSION:
        # Rank by baht earned, not headline %, then fall back to raw % when
        # prices are unknown.
        scored = [p for p in products if p.commission_value is not None]
        if scored:
            return max(scored, key=lambda p: p.commission_value)
        scored = [p for p in products if p.commission_pct is not None]
        return max(scored, key=lambda p: p.commission_pct) if scored else None
    raise ValueError(f"unknown strategy: {strategy}")


def available_strategies(products: list[Product]) -> list[str]:
    """Strategies that at least one candidate has the data to support."""
    return [s for s in (CHEAPEST, BEST_SELLING, TOP_COMMISSION) if pick(products, s)]


_NUM = re.compile(r"^[\d,]+(\.\d+)?\s*%?$")


def _is_number(text: str) -> bool:
    return bool(_NUM.match(text.strip()))


def _to_float(text: str) -> float:
    return float(text.strip().rstrip("%").replace(",", ""))
