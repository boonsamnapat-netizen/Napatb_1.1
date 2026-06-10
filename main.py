#!/usr/bin/env python3
"""
Discord Trade Setup Analyzer
Usage: python main.py <export_file.json> [--config config/config.yaml]

Steps:
  1. Parse discord export → extract trade setups
  2. Backtest each setup against historical price data
  3. Compute performance statistics
  4. Generate AI feedback + recommendations
  5. Save report & optionally push to strategy repo
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def print_summary(stats, feedback):
    console.print("\n[bold cyan]═══ Analysis Complete ═══[/bold cyan]\n")

    t = Table(title="Performance Summary", box=box.ROUNDED)
    t.add_column("Metric", style="cyan")
    t.add_column("Value", style="white")
    t.add_row("Total Setups", str(stats.total_setups))
    t.add_row("Valid (hit entry)", str(stats.valid_setups))
    t.add_row("Wins / Losses", f"{stats.wins} / {stats.losses}")
    t.add_row("Win Rate", f"{stats.win_rate:.1%}")
    t.add_row("Avg RR (planned)", f"{stats.avg_rr_planned:.2f}")
    t.add_row("Avg RR (actual)", f"{stats.avg_rr_actual:.2f}")
    t.add_row("Expectancy", f"{stats.expectancy:+.3f}%")
    t.add_row("Avg MFE", f"{stats.avg_mfe:.2f}%")
    t.add_row("Avg MAE", f"{stats.avg_mae:.2f}%")
    if stats.best_symbol:
        t.add_row("Best Symbol", stats.best_symbol)
        t.add_row("Worst Symbol", stats.worst_symbol)
    console.print(t)

    console.print("\n[bold green]AI Summary[/bold green]")
    console.print(feedback.summary)

    if feedback.filter_rules:
        console.print("\n[bold yellow]Filter Rules to Add to Strategy[/bold yellow]")
        for rule in feedback.filter_rules:
            console.print(f"  • {rule}")

    if feedback.strategy_recommendations:
        console.print("\n[bold magenta]Strategy Recommendations[/bold magenta]")
        for i, rec in enumerate(feedback.strategy_recommendations, 1):
            console.print(f"  {i}. {rec}")


def main():
    parser = argparse.ArgumentParser(description="Discord Trade Setup Analyzer")
    parser.add_argument(
        "export_file",
        nargs="?",
        help="Path to discordchatexporter JSON export file",
    )
    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to config file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--no-backtest",
        action="store_true",
        help="Skip backtest (parse + AI analysis only)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI feedback (parse + backtest only)",
    )
    parser.add_argument(
        "--push-strategy",
        action="store_true",
        help="Push insights to strategy repo after analysis",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    config = load_config(args.config)
    setup_logging(config.get("logging", {}).get("level", args.log_level))

    if not args.export_file:
        console.print("[red]Error:[/red] Please provide a discord export file.")
        console.print("Usage: python main.py <export_file.json>")
        console.print("\nTo export from Discord, use:")
        console.print(
            "  discordchatexporter-cli export "
            "-c <TOKEN> -t <TYPE> -i <CHANNEL_ID> -o data/exports/"
        )
        sys.exit(1)

    export_path = Path(args.export_file)
    if not export_path.exists():
        console.print(f"[red]File not found:[/red] {export_path}")
        sys.exit(1)

    # Step 1: Parse
    console.print(f"\n[bold]Step 1/4[/bold] Parsing Discord export: [cyan]{export_path}[/cyan]")
    from src.parser.discord_parser import DiscordExportParser
    parser_engine = DiscordExportParser(config)
    setups = parser_engine.parse(export_path)

    if not setups:
        console.print("[yellow]No trade setups found in export.[/yellow]")
        sys.exit(0)

    console.print(f"  → Found [green]{len(setups)}[/green] trade setups")

    # Step 2: Backtest
    results = []
    if not args.no_backtest:
        console.print(f"\n[bold]Step 2/4[/bold] Running backtest on {len(setups)} setups...")
        from src.backtest.backtest_engine import BacktestEngine
        bt = BacktestEngine(config)
        results = bt.run(setups)
        wins = sum(1 for r in results if r.outcome in ("WIN", "PARTIAL"))
        losses = sum(1 for r in results if r.outcome == "LOSS")
        console.print(f"  → {wins} wins / {losses} losses")
    else:
        console.print("\n[bold]Step 2/4[/bold] Backtest skipped")

    # Step 3: Statistics
    console.print("\n[bold]Step 3/4[/bold] Computing statistics...")
    from src.analysis.statistics import compute_stats
    from src.backtest.backtest_engine import BacktestResult
    stats = compute_stats(results if results else [])

    # Step 4: AI Feedback
    feedback = None
    per_setup_feedback = []
    if not args.no_ai:
        console.print("\n[bold]Step 4/4[/bold] Generating AI feedback...")
        from src.analysis.ai_feedback import AIFeedbackEngine
        ai = AIFeedbackEngine(config)
        setups_sample = [s.to_dict() for s in setups[:10]]
        feedback = ai.generate(stats, results, setups_sample)
        if results:
            per_setup_feedback = ai.generate_per_setup_feedback(results, setups)
    else:
        console.print("\n[bold]Step 4/4[/bold] AI feedback skipped")
        from src.analysis.ai_feedback import AIFeedback
        feedback = AIFeedback(summary="AI feedback disabled")

    # Save reports
    console.print("\n[bold]Saving reports...[/bold]")
    from src.output.strategy_updater import StrategyUpdater
    updater = StrategyUpdater(config)
    report_path = updater.save_report(setups, results, stats, feedback, per_setup_feedback)
    md_path = updater.save_markdown_report(stats, feedback)
    console.print(f"  → JSON: [cyan]{report_path}[/cyan]")
    console.print(f"  → Markdown: [cyan]{md_path}[/cyan]")

    # Push to strategy repo
    if args.push_strategy:
        console.print("\n[bold]Pushing to strategy repo...[/bold]")
        success = updater.push_to_strategy_repo(feedback, stats)
        if success:
            console.print("  → [green]Strategy repo updated[/green]")
        else:
            console.print("  → [yellow]Skipped (configure strategy_repo_path in config)[/yellow]")

    # Print summary
    print_summary(stats, feedback)

    console.print(f"\n[bold green]Done![/bold green] Reports saved to [cyan]reports/[/cyan]\n")


if __name__ == "__main__":
    main()
