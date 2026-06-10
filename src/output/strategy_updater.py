"""
Write analysis results to the strategy repo and generate a full report.
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.ai_feedback import AIFeedback
from src.analysis.statistics import PerformanceStats
from src.backtest.backtest_engine import BacktestResult
from src.parser.discord_parser import TradeSetup

logger = logging.getLogger(__name__)


class StrategyUpdater:
    def __init__(self, config: dict):
        cfg = config.get("output", {})
        self.reports_dir = Path(cfg.get("reports_dir", "reports"))
        self.strategy_repo = cfg.get("strategy_repo_path", "")
        self.strategy_file = cfg.get("strategy_file", "strategy_insights.json")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    def save_report(
        self,
        setups: list[TradeSetup],
        results: list[BacktestResult],
        stats: PerformanceStats,
        feedback: AIFeedback,
        per_setup_feedback: list[dict],
    ) -> Path:
        ts = self._timestamp()
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_setups": stats.total_setups,
                "valid_setups": stats.valid_setups,
                "win_rate": stats.win_rate,
                "avg_rr_actual": stats.avg_rr_actual,
                "expectancy": stats.expectancy,
            },
            "statistics": stats.to_dict(),
            "ai_feedback": feedback.to_dict(),
            "per_setup_feedback": per_setup_feedback,
            "trade_setups": [s.to_dict() for s in setups],
            "backtest_results": [r.to_dict() for r in results],
        }

        report_path = self.reports_dir / f"analysis_{ts}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        logger.info("Report saved → %s", report_path)
        return report_path

    def save_markdown_report(
        self,
        stats: PerformanceStats,
        feedback: AIFeedback,
    ) -> Path:
        ts = self._timestamp()
        lines = [
            f"# Trade Setup Analysis Report",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Summary",
            feedback.summary,
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Setups | {stats.total_setups} |",
            f"| Valid (entered) | {stats.valid_setups} |",
            f"| Win Rate | {stats.win_rate:.1%} |",
            f"| Avg RR (planned) | {stats.avg_rr_planned:.2f} |",
            f"| Avg RR (actual) | {stats.avg_rr_actual:.2f} |",
            f"| Expectancy | {stats.expectancy:+.3f}% |",
            f"| Avg MFE | {stats.avg_mfe:.2f}% |",
            f"| Avg MAE | {stats.avg_mae:.2f}% |",
            "",
            "## Strengths",
            *[f"- {s}" for s in feedback.strengths],
            "",
            "## Weaknesses",
            *[f"- {w}" for w in feedback.weaknesses],
            "",
            "## Pattern Insights",
            *[f"- {p}" for p in feedback.pattern_insights],
            "",
            "## Strategy Recommendations",
            *[f"{i+1}. {r}" for i, r in enumerate(feedback.strategy_recommendations)],
            "",
            "## Filter Rules to Add",
            "```",
            *feedback.filter_rules,
            "```",
            "",
            "## Risk Management",
            feedback.risk_management_notes,
            "",
            "## Performance by Symbol",
        ]

        for sym, data in stats.by_symbol.items():
            lines.append(
                f"- **{sym}**: {data['wins']}W/{data['losses']}L "
                f"({data['win_rate']:.1%} WR) avg PnL {data['avg_pnl_pct']:+.2f}%"
            )

        md_path = self.reports_dir / f"report_{ts}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info("Markdown report → %s", md_path)
        return md_path

    def push_to_strategy_repo(self, feedback: AIFeedback, stats: PerformanceStats) -> bool:
        """Update strategy_insights.json in the strategy repo and commit."""
        if not self.strategy_repo:
            logger.info("No strategy_repo_path configured, skipping push")
            return False

        repo_path = Path(self.strategy_repo)
        if not repo_path.exists():
            logger.warning("Strategy repo not found: %s", repo_path)
            return False

        insights_path = repo_path / self.strategy_file
        existing = {}
        if insights_path.exists():
            with open(insights_path) as f:
                existing = json.load(f)

        existing["last_updated"] = datetime.now(timezone.utc).isoformat()
        existing["win_rate"] = stats.win_rate
        existing["avg_rr"] = stats.avg_rr_actual
        existing["expectancy"] = stats.expectancy
        existing["filter_rules"] = feedback.filter_rules
        existing["strategy_recommendations"] = feedback.strategy_recommendations
        existing["risk_management"] = feedback.risk_management_notes
        existing["best_symbol"] = stats.best_symbol
        existing["worst_symbol"] = stats.worst_symbol

        with open(insights_path, "w") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        try:
            subprocess.run(
                ["git", "-C", str(repo_path), "add", self.strategy_file],
                check=True, capture_output=True
            )
            subprocess.run(
                [
                    "git", "-C", str(repo_path), "commit", "-m",
                    f"chore: update strategy insights from discord analysis "
                    f"(WR={stats.win_rate:.1%})"
                ],
                check=True, capture_output=True
            )
            logger.info("Strategy repo updated and committed")
            return True
        except subprocess.CalledProcessError as e:
            logger.error("Git commit failed: %s", e.stderr.decode())
            return False
