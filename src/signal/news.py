"""
News & sentiment overlay.

News is used as a *risk gate and tilt*, never as the primary trigger:
  - Extreme one-sided sentiment near a level often marks exhaustion (fade-able).
  - Scheduled high-impact events (CPI, FOMC, major unlocks/listings) mean wider
    stops or standing aside — the crowd gets liquidated on these.

The module is intentionally pluggable and degrades gracefully:
  1. Headlines can be passed in manually (always works, offline).
  2. Optionally fetched from RSS feeds if `feedparser` + network are available.
  3. Scored either by Claude (if ANTHROPIC_API_KEY set) or a keyword fallback.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

_BULLISH = re.compile(
    r"\b(surge|soar|rally|breakout|all.?time.high|ath|adoption|approv\w*|inflow|"
    r"bullish|institutional|partnership|upgrade|listing|halving|buy\w*)\b",
    re.IGNORECASE,
)
_BEARISH = re.compile(
    r"\b(crash|plunge|dump|hack|exploit|lawsuit|sec\b|ban|outflow|liquidat\w*|"
    r"bearish|selloff|sell.?off|downgrade|delisting|fraud|fud|fear)\b",
    re.IGNORECASE,
)
_HIGH_IMPACT = re.compile(
    r"\b(fomc|cpi|fed|interest.rate|rate.cut|rate.hike|inflation|unlock|"
    r"etf.decision|sec.ruling|jobs.report|nfp)\b",
    re.IGNORECASE,
)


@dataclass
class NewsAssessment:
    sentiment_score: float = 0.0      # -1 (very bearish) .. +1 (very bullish)
    confidence: float = 0.0           # 0..1 how much signal in the news
    high_impact_event: bool = False   # scheduled volatility risk nearby
    headline_count: int = 0
    summary: str = "No news evaluated."
    headlines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "sentiment_score": round(self.sentiment_score, 3),
            "confidence": round(self.confidence, 3),
            "high_impact_event": self.high_impact_event,
            "headline_count": self.headline_count,
            "summary": self.summary,
            "headlines": self.headlines[:15],
        }


class NewsProvider:
    def __init__(self, config: dict):
        cfg = config.get("signal", {}).get("news", {})
        self.enabled = cfg.get("enabled", True)
        self.feeds = cfg.get("feeds", DEFAULT_FEEDS)
        self.max_headlines = cfg.get("max_headlines", 25)
        self.use_llm = cfg.get("use_llm", True) and bool(
            os.environ.get("ANTHROPIC_API_KEY")
        )
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")

    # ---- fetching -------------------------------------------------------
    def _fetch_rss(self, symbol_terms: list[str]) -> list[str]:
        try:
            import feedparser  # type: ignore
        except ImportError:
            logger.info("feedparser not installed; skipping RSS fetch")
            return []

        headlines: list[str] = []
        for url in self.feeds:
            try:
                parsed = feedparser.parse(url)
                for entry in parsed.entries[: self.max_headlines]:
                    title = getattr(entry, "title", "").strip()
                    if title:
                        headlines.append(title)
            except Exception as e:  # noqa: BLE001
                logger.warning("RSS fetch failed for %s: %s", url, e)

        if symbol_terms:
            terms = re.compile("|".join(re.escape(t) for t in symbol_terms), re.I)
            focused = [h for h in headlines if terms.search(h)]
            # Keep some macro headlines too — they move the whole market.
            macro = [h for h in headlines if _HIGH_IMPACT.search(h)]
            merged = list(dict.fromkeys(focused + macro))
            if merged:
                return merged[: self.max_headlines]
        return headlines[: self.max_headlines]

    # ---- scoring --------------------------------------------------------
    def _score_keywords(self, headlines: list[str]) -> NewsAssessment:
        if not headlines:
            return NewsAssessment(summary="No headlines available.")
        bull = sum(len(_BULLISH.findall(h)) for h in headlines)
        bear = sum(len(_BEARISH.findall(h)) for h in headlines)
        high_impact = any(_HIGH_IMPACT.search(h) for h in headlines)
        total = bull + bear
        score = (bull - bear) / total if total else 0.0
        conf = min(1.0, total / max(5, len(headlines)))
        summary = (
            f"Keyword scan of {len(headlines)} headlines: "
            f"{bull} bullish vs {bear} bearish cues"
            + (", high-impact event detected" if high_impact else "")
        )
        return NewsAssessment(
            sentiment_score=score,
            confidence=conf,
            high_impact_event=high_impact,
            headline_count=len(headlines),
            summary=summary,
            headlines=headlines,
        )

    def _score_llm(self, symbol: str, headlines: list[str]) -> NewsAssessment | None:
        try:
            import json

            import anthropic

            client = anthropic.Anthropic()
            joined = "\n".join(f"- {h}" for h in headlines[:25])
            system = (
                "You are a crypto market news analyst. Given recent headlines, "
                "assess near-term sentiment for the asset. Return ONLY JSON: "
                '{"sentiment_score": float -1..1, "confidence": float 0..1, '
                '"high_impact_event": bool, "summary": "one sentence"}'
            )
            resp = client.messages.create(
                model=self.model,
                max_tokens=400,
                system=system,
                messages=[
                    {
                        "role": "user",
                        "content": f"Asset: {symbol}\nHeadlines:\n{joined}",
                    }
                ],
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r"^```(?:json)?\n?|\n?```$", "", raw)
            data = json.loads(raw)
            return NewsAssessment(
                sentiment_score=float(data.get("sentiment_score", 0.0)),
                confidence=float(data.get("confidence", 0.0)),
                high_impact_event=bool(data.get("high_impact_event", False)),
                headline_count=len(headlines),
                summary=str(data.get("summary", "")),
                headlines=headlines,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM news scoring failed, falling back: %s", e)
            return None

    # ---- public ---------------------------------------------------------
    def assess(
        self,
        symbol: str,
        manual_headlines: list[str] | None = None,
    ) -> NewsAssessment:
        if not self.enabled:
            return NewsAssessment(summary="News overlay disabled.")

        base = symbol.upper().replace("/USDT", "").replace("USDT", "")
        terms = [base, symbol.upper()]

        headlines = list(manual_headlines or [])
        if not headlines:
            headlines = self._fetch_rss(terms)

        if not headlines:
            return NewsAssessment(summary="No news available (offline/neutral).")

        if self.use_llm:
            llm = self._score_llm(symbol, headlines)
            if llm is not None:
                return llm
        return self._score_keywords(headlines)
