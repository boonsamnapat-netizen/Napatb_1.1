---
name: crypto-signal-ops
description: Operational runbook for the Napatb crypto signal system (src/signal/, signal_*.py, auto_scan_alert workflow). Use when running scans/backtests, managing or debugging the daily Telegram alert workflow, tuning config, adding coins, or changing the schedule.
---

# Crypto signal system — operational runbook

Read `CLAUDE.md` first for the map. This is the how-to for common tasks.

## Hard-won findings — DON'T re-research (it costs many tokens)
- **Network**: the dev sandbox reaches ONLY `raw.githubusercontent.com`. Blocked:
  all exchanges (Binance/Kraken/Bybit/OKX/KuCoin…), Yahoo (query1/2), CoinGecko,
  CoinCap, gist, api.github.com. Don't re-probe them. → real data via the
  Actions+yfinance workflow (runner has internet) committed to `data/real/`.
- **Data**: yfinance 1d goes back to 2018; 1h is limited to ~730d. Crypto OHLCV on
  raw.github is mostly git-LFS (pointer only, unusable); coinmetrics csv is daily
  close-only (no OHLC).
- **Validated edge** (real data, net of fees, walk-forward OOS) — already measured,
  reuse don't redo: 1h is NEGATIVE after fees; 4h ≈ +0.10R, 1d ≈ +0.20R in-sample;
  majors OOS ≈ +0.087R; maker exits/entries → ≈ +0.137R; liquidity filter (majors)
  +0.108R vs alts +0.058R. A/B winners: Supertrend (small+), ATR trailing 2.5R
  (1.5R hurts), cooldown OFF, BTC regime gate (small+, protective). These are the
  current defaults in `config/config.yaml`.
- **OSS sources mined** (Freqtrade/Jesse): pairlist/liquidity filters, protections
  (cooldown/stoploss-guard/max-drawdown), ATR trailing, regime filter, Supertrend.
  Conclusion: edge is in risk/exit/universe, not the entry indicator.

## Run locally (sandbox: no exchange access → use CSV/demo)
```bash
python signal_cli.py BTCUSDT --demo                 # one signal, offline
python signal_scan.py --csv-dir data/real/crypto --htf W --portfolio --summary --notify --charts
python signal_backtest.py BTCUSDT --csv data/real/crypto/BTCUSDT.csv --htf-rule W --optimize
```
`--notify`/`--charts`/`--summary` dry-run (print) when no Telegram secrets are set.

## Edit the daily alert workflow (IMPORTANT: two copies)
`auto_scan_alert.yml` runs from the **default branch** (`claude/discord-trade-setup-analysis-xzcetr`).
1. Edit on feature branch `claude/crypto-signal-system-kcf8vq`, commit, push.
2. Mirror to default branch — GitHub MCP `create_or_update_file` (needs the file's
   current blob sha), or if MCP is down use a git worktree:
   ```bash
   git fetch origin <default-branch>
   git worktree add -f /tmp/defbr origin/<default-branch>
   cp .github/workflows/auto_scan_alert.yml /tmp/defbr/.github/workflows/
   cd /tmp/defbr && git add -A && git commit -m "ci: ..." && git push origin HEAD:<default-branch>
   cd /home/user/Napatb_1.1 && git worktree remove /tmp/defbr --force
   ```
The workflow `checkout` uses `ref:` the feature branch, so code changes need only
the feature branch; only workflow-yaml changes need the default-branch mirror.

## Trigger / verify a run (GitHub MCP)
- Trigger: `actions_run_trigger` method=run_workflow, workflow_id=`auto_scan_alert.yml`,
  ref=default branch. Inputs: `{"test_notify":"true"}` or `{"sample_signal":"true"}`.
- `list_workflow_runs` output is huge → it gets saved to a file; parse run id with
  `python3 -c "import json;d=json.load(open('<file>'));print(d['workflow_runs'][0]['id'])"`.
- `list_workflow_jobs` (resource_id=run id) for per-step status; `get_job_logs`
  (job_id, return_content, tail_lines) for output. Look for `configured & sent`,
  `Telegram summary: sent`, `Updated portfolio value: $N`.
- Don't poll with foreground sleep; use a background `sleep N` then check.

## Common changes
- **Add/remove coins**: edit `data/crypto_universe.txt` (yfinance tickers, e.g. `SUI-USD`).
- **Change run time**: `cron` in the workflow (e.g. `0 1,13 * * *` for twice daily).
- **Tune risk/edge**: `config/config.yaml` `signal:` — risk_per_trade_pct, min_confidence,
  trailing_r, scanner.quality_top_n, leverage (display only).
- **Calibrate win-rate**: `signal_backtest.py ... --optimize --apply` writes
  `calibrated_win_rate` into config (surgical edit, keeps comments).
- **Chart style**: `src/signal/charting.py` (`make_chart`).
- **Message wording (Thai)**: `src/signal/notifier.py` (format_signal_compact /
  format_market_summary / _advice).

## Telegram
- Secrets `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (repo → Settings → Actions secrets).
- Portfolio value: user messages the bot `/port 150`; `examples/update_account.py`
  reads it via getUpdates → `data/account.json` (committed by the workflow).
- Trade journal: user messages `/trade SYM dir entry stop [tp]`, `/close SYM exit`
  (auto-computes R), `/journal` (stats reply). `examples/update_journal.py` reads
  getUpdates → `data/trade_journal.json`; dedup by update_id; confirms each action.
- Signal log (auto): `src/signal/signal_log.py` records every ENTER pushed by the
  scan → `data/signals_log.json` (dedup date+symbol), grades open ones first-touch
  SL vs TP1 from later OHLC. `signal_scan.py` calls it each run; persisted by the
  workflow. Seed/backfill from run logs: `examples/seed_signals_from_log.py` (the
  live runs use the forming bar + yfinance revises, so end-of-day reproduction of
  exact sent entries drifts a few % — confidences are exact from the logs).
- Test: run workflow with `test_notify=true`; preview a signal with `sample_signal=true`.
- Setup guide for the user: `docs/TELEGRAM_SETUP.md`.

## Guardrails
- Always report net-of-fees + out-of-sample numbers; the edge is modest (~+0.09R OOS).
- Risk is controlled by % per trade, NOT leverage. `min_stop_pct` floors stop distance
  so a collapsed ATR can't explode size/leverage.
- Reject flat/stale data (engine already AVOIDs O=H=L=C bars).
