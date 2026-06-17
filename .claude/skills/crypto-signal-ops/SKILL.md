---
name: crypto-signal-ops
description: Operational runbook for the Napatb crypto signal system (src/signal/, signal_*.py, auto_scan_alert workflow). Use when running scans/backtests, managing or debugging the daily Telegram alert workflow, tuning config, adding coins, or changing the schedule.
---

# Crypto signal system — operational runbook

Read `CLAUDE.md` first for the map. This is the how-to for common tasks.

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
- Test: run workflow with `test_notify=true`; preview a signal with `sample_signal=true`.
- Setup guide for the user: `docs/TELEGRAM_SETUP.md`.

## Guardrails
- Always report net-of-fees + out-of-sample numbers; the edge is modest (~+0.09R OOS).
- Risk is controlled by % per trade, NOT leverage. `min_stop_pct` floors stop distance
  so a collapsed ATR can't explode size/leverage.
- Reject flat/stale data (engine already AVOIDs O=H=L=C bars).
