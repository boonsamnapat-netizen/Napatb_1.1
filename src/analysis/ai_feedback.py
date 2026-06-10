"""
Use Claude to analyze trade setup patterns, identify strengths/weaknesses,
and generate actionable strategy improvement recommendations.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import anthropic

from src.backtest.backtest_engine import BacktestResult
from src.analysis.statistics import PerformanceStats

logger = logging.getLogger(__name__)


@dataclass
class AIFeedback:
    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    pattern_insights: list[str] = field(default_factory=list)
    strategy_recommendations: list[str] = field(default_factory=list)
    filter_rules: list[str] = field(default_factory=list)    # rules to add to strategy
    risk_management_notes: str = ""
    confidence_score: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


FEEDBACK_SYSTEM = """You are an expert trading performance analyst. Analyze trade setup data and provide specific, actionable feedback to improve a trading strategy.

Your analysis should be:
- Specific (mention exact patterns, symbols, metrics)
- Actionable (concrete rules, not vague advice)
- Data-driven (reference the statistics provided)
- Practical (implementable in a trading strategy)

Focus on:
1. What patterns/setups have high win rates
2. What conditions lead to losses (time of day, volatility, symbol)
3. Specific filter rules to add to the strategy
4. Risk management improvements based on MFE/MAE data
5. Entry optimization (better entry zones based on outcomes)
"""

FEEDBACK_PROMPT_TEMPLATE = """
## Performance Statistics
{stats_json}

## Trade Outcomes Sample (first 50 resolved trades)
{sample_json}

## Raw Setup Examples
{examples_json}

Based on this data, provide a comprehensive trading strategy analysis and improvement recommendations.

Return ONLY valid JSON with this schema:
{{
  "summary": "2-3 sentence overall assessment",
  "strengths": ["strength 1", "strength 2", ...],
  "weaknesses": ["weakness 1", "weakness 2", ...],
  "pattern_insights": [
    "Specific pattern X has Y% win rate when Z condition is met",
    ...
  ],
  "strategy_recommendations": [
    "Concrete recommendation 1",
    ...
  ],
  "filter_rules": [
    "Only trade LONG when price > 200 EMA",
    "Skip setups where SL distance > 3%",
    ...
  ],
  "risk_management_notes": "Specific risk sizing and management notes based on data",
  "confidence_score": 0.0-1.0
}}
"""


class AIFeedbackEngine:
    def __init__(self, config: dict):
        self.client = anthropic.Anthropic()
        self.model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
        self.max_tokens = config.get("anthropic", {}).get("max_tokens", 4096)

    def generate(
        self,
        stats: PerformanceStats,
        results: list[BacktestResult],
        setups_sample: list[dict],
    ) -> AIFeedback:
        resolved = [r for r in results if r.outcome in ("WIN", "LOSS", "PARTIAL")]
        sample = [r.to_dict() for r in resolved[:50]]

        prompt = FEEDBACK_PROMPT_TEMPLATE.format(
            stats_json=json.dumps(stats.to_dict(), indent=2),
            sample_json=json.dumps(sample, indent=2),
            examples_json=json.dumps(setups_sample[:10], indent=2),
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=FEEDBACK_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
        except Exception as e:
            logger.error("AI feedback generation failed: %s", e)
            return AIFeedback(
                summary=f"Analysis failed: {e}",
                confidence_score=0.0,
            )

        feedback = AIFeedback(
            summary=data.get("summary", ""),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            pattern_insights=data.get("pattern_insights", []),
            strategy_recommendations=data.get("strategy_recommendations", []),
            filter_rules=data.get("filter_rules", []),
            risk_management_notes=data.get("risk_management_notes", ""),
            confidence_score=float(data.get("confidence_score", 0.0)),
        )

        logger.info(
            "AI feedback: %d recommendations, %d filter rules",
            len(feedback.strategy_recommendations),
            len(feedback.filter_rules),
        )
        return feedback

    def generate_per_setup_feedback(
        self, results: list[BacktestResult], setups: list
    ) -> list[dict]:
        """Generate brief per-setup feedback for losses and edge cases."""
        losses = [
            (r, s)
            for r, s in zip(results, setups)
            if r.outcome == "LOSS" and r.hit_entry
        ][:20]  # limit to 20 to avoid excessive API calls

        if not losses:
            return []

        numbered = "\n\n".join(
            f"[{i}] Symbol:{r.symbol} Dir:{r.direction} Entry:{r.entry} "
            f"SL:{r.stop_loss} TPs:{r.take_profits} Pattern:{s.pattern}\n"
            f"MAE:{r.max_adverse_excursion}% MFE:{r.max_favorable_excursion}% "
            f"Exit:{r.exit_price} Candles:{r.candles_to_exit}\n"
            f"Message: {s.raw_content[:200]}"
            for i, (r, s) in enumerate(losses)
        )

        prompt = (
            f"For each losing trade below, give a brief reason it failed and one "
            f"specific improvement. Return JSON array with objects: "
            f"{{\"index\": N, \"failure_reason\": \"...\", \"improvement\": \"...\"}}\n\n"
            f"{numbered}"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system="You are a trading coach. Be specific and brief.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            return json.loads(raw)
        except Exception as e:
            logger.warning("Per-setup feedback failed: %s", e)
            return []
