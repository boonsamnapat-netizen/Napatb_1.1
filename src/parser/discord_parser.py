"""
Parse Discord chat exports from discordchatexporter (JSON format).
Extracts trade setups using regex pre-filter + Claude LLM extraction.
"""

import json
import re
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

TRADE_KEYWORDS = re.compile(
    r"\b(long|short|buy|sell|entry|enter|sl|stop.?loss|tp|take.?profit|target|"
    r"scalp|swing|setup|signal|alert|breakout|support|resistance|"
    r"btc|eth|sol|bnb|xrp|ada|doge|avax|matic|link|dot|uni|usdt)\b",
    re.IGNORECASE,
)

PRICE_PATTERN = re.compile(r"\b\d{1,6}(?:[.,]\d{1,6})?\b")


@dataclass
class TradeSetup:
    message_id: str
    timestamp: str
    author: str
    raw_content: str
    symbol: str = ""
    direction: str = ""          # LONG / SHORT
    entry: Optional[float] = None
    entry_zone: list[float] = field(default_factory=list)
    stop_loss: Optional[float] = None
    take_profits: list[float] = field(default_factory=list)
    timeframe: str = ""
    pattern: str = ""
    notes: str = ""
    confidence: float = 0.0      # 0-1 LLM confidence
    extraction_error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


EXTRACTION_SYSTEM = """You are a trading signal parser. Extract trade setup details from Discord messages.

Return ONLY valid JSON with this exact schema:
{
  "symbol": "BTC" or "BTCUSDT" etc (uppercase, empty if unclear),
  "direction": "LONG" or "SHORT" or "" (empty if unclear),
  "entry": null or single float,
  "entry_zone": [] or [float, float] (low, high),
  "stop_loss": null or float,
  "take_profits": [] or [float, ...] (ordered nearest to farthest),
  "timeframe": "" or "1m"/"5m"/"15m"/"1h"/"4h"/"1d" etc,
  "pattern": "" or short description like "breakout", "pullback", "BOS", "OB", etc,
  "notes": "" or brief extra context,
  "confidence": float 0.0-1.0 (how confident this is a real trade setup)
}

Rules:
- confidence < 0.5 means this is NOT a trade setup (discussion, meme, etc.)
- Normalize symbol to base/USDT pair name without slash, e.g. "BTCUSDT"
- If only base given (BTC), append USDT → "BTCUSDT"
- Parse Thai text too if present
"""


class DiscordExportParser:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
        self.max_tokens = config.get("anthropic", {}).get("max_tokens", 4096)
        self.min_confidence = config.get("parser", {}).get("min_confidence", 0.6)
        self.authors_blacklist = set(
            config.get("parser", {}).get("authors_blacklist", [])
        )
        self.symbols_whitelist = set(
            s.upper() for s in config.get("parser", {}).get("symbols_whitelist", [])
        )

    def load_export(self, path: str | Path) -> list[dict]:
        """Load discordchatexporter JSON export."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        logger.info("Loaded %d messages from %s", len(messages), path.name)
        return messages

    def _is_candidate(self, content: str) -> bool:
        """Quick regex pre-filter before sending to LLM."""
        if not content or len(content) < 10:
            return False
        has_keyword = bool(TRADE_KEYWORDS.search(content))
        has_price = len(PRICE_PATTERN.findall(content)) >= 2
        return has_keyword or has_price

    def _extract_author(self, msg: dict) -> str:
        author = msg.get("author", {})
        return author.get("name", author.get("nickname", "unknown"))

    def _batch_extract(self, messages: list[dict]) -> list[TradeSetup]:
        """Send messages to Claude in batches for extraction."""
        results = []
        batch_size = 10

        candidates = [
            m for m in messages
            if self._is_candidate(m.get("content", ""))
            and self._extract_author(m) not in self.authors_blacklist
        ]
        logger.info(
            "%d / %d messages pass pre-filter", len(candidates), len(messages)
        )

        for i in range(0, len(candidates), batch_size):
            batch = candidates[i : i + batch_size]
            batch_results = self._extract_batch(batch)
            results.extend(batch_results)
            logger.debug("Processed batch %d-%d", i, i + len(batch))

        return results

    def _extract_batch(self, messages: list[dict]) -> list[TradeSetup]:
        numbered = "\n\n".join(
            f"[{j}] {msg.get('content', '')}"
            for j, msg in enumerate(messages)
        )
        prompt = (
            f"Extract trade setups from each numbered message below.\n"
            f"Return a JSON array with one object per message (same order).\n\n"
            f"{numbered}"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=EXTRACTION_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fence if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            parsed = json.loads(raw)
        except Exception as e:
            logger.warning("Batch extraction failed: %s", e)
            parsed = [{}] * len(messages)

        setups = []
        for j, (msg, extracted) in enumerate(zip(messages, parsed)):
            if not isinstance(extracted, dict):
                extracted = {}
            confidence = float(extracted.get("confidence", 0.0))
            symbol = extracted.get("symbol", "").upper()

            if self.symbols_whitelist and symbol and symbol not in self.symbols_whitelist:
                continue

            setup = TradeSetup(
                message_id=str(msg.get("id", "")),
                timestamp=msg.get("timestamp", ""),
                author=self._extract_author(msg),
                raw_content=msg.get("content", ""),
                symbol=symbol,
                direction=extracted.get("direction", "").upper(),
                entry=_to_float(extracted.get("entry")),
                entry_zone=_to_float_list(extracted.get("entry_zone", [])),
                stop_loss=_to_float(extracted.get("stop_loss")),
                take_profits=_to_float_list(extracted.get("take_profits", [])),
                timeframe=extracted.get("timeframe", ""),
                pattern=extracted.get("pattern", ""),
                notes=extracted.get("notes", ""),
                confidence=confidence,
            )
            setups.append(setup)

        return setups

    def parse(self, export_path: str | Path) -> list[TradeSetup]:
        """Full parse pipeline: load → pre-filter → LLM extract → filter by confidence."""
        messages = self.load_export(export_path)
        all_setups = self._batch_extract(messages)
        valid = [s for s in all_setups if s.confidence >= self.min_confidence]
        logger.info(
            "Extracted %d valid trade setups (confidence >= %.1f)",
            len(valid), self.min_confidence,
        )
        return valid


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _to_float_list(val) -> list[float]:
    if not isinstance(val, list):
        return []
    result = []
    for v in val:
        f = _to_float(v)
        if f is not None:
            result.append(f)
    return result
