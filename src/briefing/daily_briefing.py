"""
Daily pre-market briefing for a US stock watchlist.

Pipeline:
  1. Load the watchlist (config inline list, or data/universe.txt)
  2. Pull recent daily OHLCV per symbol (CSV cache → yfinance fallback)
  3. Compute technical context (trend vs SMAs, 52w range, RSI, volume, moves)
  4. Ask Claude to write a concise morning digest of what needs attention today
  5. Save a markdown report and optionally post a summary to a Discord webhook

Designed to run unattended on a cron so the investor only reads one short digest
instead of scanning the whole watchlist by hand.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.briefing.indicators import attention_score, compute_context

logger = logging.getLogger(__name__)


BRIEFING_SYSTEM = """You are the pre-market analyst for a seasoned full-time US stock investor.
You are given a JSON snapshot of their watchlist with technical context per symbol.

Write a SHORT, scannable morning briefing in Markdown. Be concrete and reference
the numbers. The reader wants to spend 2-3 minutes and know exactly what, if
anything, needs a decision today. Do not give generic advice or disclaimers.

Structure:
## TL;DR
- 2-4 bullets: the single most important things across the whole list today.

## Needs Attention
- Only the names with a real signal (big move, volume spike, near 52w high/low,
  overbought/oversold, trend change). One line each: `**TICKER** — what + the number + why it matters`.

## Trend Health
- 1-2 lines on the overall posture of the list (mostly above/below key MAs, risk-on/off).

Keep the whole thing under ~250 words. Skip sections that have nothing to report."""


def load_watchlist(config: dict) -> list[str]:
    cfg = config.get("briefing", {})
    inline = cfg.get("watchlist") or []
    if inline:
        return [s.strip().upper() for s in inline if s.strip()]

    path = Path(cfg.get("watchlist_file", "data/universe.txt"))
    if not path.exists():
        logger.warning("Watchlist file %s not found; using empty list", path)
        return []

    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.upper())
    return out


def gather_snapshots(symbols: list[str], lookback_days: int) -> list[dict]:
    from src.data.equity_data import get_ohlcv

    snaps = []
    for sym in symbols:
        try:
            df = get_ohlcv(sym, interval="1d", limit=lookback_days)
            snap = compute_context(sym, df)
        except Exception as e:
            logger.warning("Snapshot failed for %s: %s", sym, e)
            snap = {"symbol": sym, "error": str(e)}
        snap["attention"] = attention_score(snap)
        snaps.append(snap)
    snaps.sort(key=lambda s: s.get("attention", 0), reverse=True)
    return snaps


def generate_ai_digest(snapshots: list[dict], config: dict) -> str:
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic not installed — using fallback digest")
        return ""

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — using fallback digest")
        return ""

    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-6")
    max_tokens = config.get("anthropic", {}).get("max_tokens", 4096)

    # Only send symbols with data; trim noise.
    payload = [s for s in snapshots if not s.get("error")]
    prompt = (
        "Watchlist snapshot (sorted by attention score, all % values are "
        "percentages):\n\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Write the morning briefing now."
    )

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=BRIEFING_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error("AI digest generation failed: %s", e)
        return ""


def _fallback_digest(snapshots: list[dict], top_n: int) -> str:
    """Rules-based digest when Claude is unavailable, so the cron never fails."""
    lines = ["## Needs Attention", ""]
    movers = [s for s in snapshots if not s.get("error") and s.get("tags")][:top_n]
    if not movers:
        lines.append("- Nothing notable on the watchlist today.")
    for s in movers:
        tag_str = ", ".join(s["tags"])
        lines.append(
            f"- **{s['symbol']}** — {s['last']} "
            f"({s['chg_1d_pct']:+}% 1d) · RSI {s.get('rsi14')} · {tag_str}"
        )
    return "\n".join(lines)


def render_table(snapshots: list[dict], top_n: int) -> str:
    rows = [s for s in snapshots if not s.get("error")][:top_n]
    header = (
        "| Ticker | Last | 1d% | 5d% | vs 50d | vs 200d | RSI | Vol× | Off 52wH | Tags |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    out = [header]
    for s in rows:
        out.append(
            f"| {s['symbol']} | {s.get('last')} | {s.get('chg_1d_pct')} | "
            f"{s.get('chg_5d_pct')} | {s.get('vs_sma50_pct')} | "
            f"{s.get('vs_sma200_pct')} | {s.get('rsi14')} | "
            f"{s.get('vol_vs_avg20')} | {s.get('pct_off_52w_high')} | "
            f"{', '.join(s.get('tags', []))} |"
        )
    return "\n".join(out)


def post_to_discord(text: str, env_var: str = "DISCORD_WEBHOOK_URL") -> bool:
    url = os.environ.get(env_var)
    if not url:
        return False
    import urllib.error
    import urllib.request

    # Discord caps message content at 2000 chars.
    content = text if len(text) <= 1900 else text[:1900] + "\n…(truncated)"
    data = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.URLError as e:
        logger.warning("Discord post failed: %s", e)
        return False


def build_briefing(config: dict, use_ai: bool = True) -> tuple[str, list[dict]]:
    cfg = config.get("briefing", {})
    lookback = int(cfg.get("lookback_days", 260))
    top_n = int(cfg.get("top_movers", 12))

    symbols = load_watchlist(config)
    if not symbols:
        return "# Daily Briefing\n\nNo symbols in watchlist.", []

    logger.info("Building briefing for %d symbols", len(symbols))
    snapshots = gather_snapshots(symbols, lookback)

    digest = generate_ai_digest(snapshots, config) if use_ai else ""
    if not digest:
        digest = _fallback_digest(snapshots, top_n)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    valid = [s for s in snapshots if not s.get("error")]
    flagged = [s for s in valid if s.get("tags")]

    report = (
        f"# Daily Pre-Market Briefing — {date_str}\n\n"
        f"_Watchlist: {len(symbols)} symbols · {len(valid)} with data · "
        f"{len(flagged)} flagged_\n\n"
        f"{digest}\n\n"
        f"## Watchlist Snapshot (top {top_n} by attention)\n\n"
        f"{render_table(snapshots, top_n)}\n"
    )
    return report, snapshots


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daily US stock pre-market briefing")
    parser.add_argument("--config", "-c", default="config/config.yaml")
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude digest")
    parser.add_argument("--no-post", action="store_true", help="Skip Discord post")
    parser.add_argument("--out-dir", default="reports/briefings")
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    import yaml
    config_path = Path(args.config)
    config = {}
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    report, snapshots = build_briefing(config, use_ai=not args.no_ai)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / f"briefing_{date_str}.md"
    out_path.write_text(report, encoding="utf-8")
    logger.info("Saved briefing → %s", out_path)
    print(report)

    if not args.no_post:
        env_var = config.get("briefing", {}).get(
            "discord_webhook_env", "DISCORD_WEBHOOK_URL"
        )
        if post_to_discord(report, env_var):
            logger.info("Posted briefing to Discord")

    return 0


if __name__ == "__main__":
    sys.exit(main())
