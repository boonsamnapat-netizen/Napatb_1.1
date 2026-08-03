# CLAUDE.md — Napatb crypto signal system

Decision-support crypto signal system: scans the market, ranks setups, sizes them
with risk/MM, and pushes Thai-language alerts (+charts) to Telegram — runs
hands-off on GitHub Actions. Educational/decision-support only; no profit
guarantee — always quote honest, net-of-fees, out-of-sample numbers.

## Working rule — never guess (owner's standing instruction)
- Do NOT state guesses, predictions, or inferences as if they were findings —
  about this repo, the owner, results, or anything else. If it was not stated
  and cannot be verified, say "ไม่ได้บอกมา" / "ไม่รู้" and ask.
- Code in this repo is NOT evidence of what the owner knows — much of it was
  written by Claude in earlier sessions. Never infer the owner's skill,
  intent, or preferences from the codebase.
- Need information to proceed? Ask for it. Asking is expected, not a failure.

## Two codebases (don't confuse them)
- **`src/signal/` + `signal_*.py`** — THE live signal system (active work).
- `src/{parser,backtest,analysis,output}/` + `main.py` — legacy Discord
  trade-setup analyzer (pre-existing, separate; usually leave untouched).

## Branches
- Develop on **`claude/crypto-signal-system-kcf8vq`**.
- Default branch is `claude/discord-trade-setup-analysis-xzcetr`. Workflows only
  run from the default branch, so when editing a workflow, update BOTH copies
  (feature branch via git; default branch via GitHub MCP or a git worktree push).

## What's validated (real data, net of fees, walk-forward OOS)
- **Trade 4h/1d, NOT 1h** — fees kill tight-stop 1h (net −0.06R). In-sample 1d
  ≈ +0.20R, 4h ≈ +0.10R per trade.
- Majors combined **OOS ≈ +0.087R/trade**; maker (limit) exits/entries → ≈ +0.137R.
- Edge is real but modest (~45% win rate; positive expectancy from R-multiples).
  Per-coin drawdowns can be −10..−30%.
- Default config = the best A/B combo: 4h/1d + Supertrend + ATR trailing 2.5R +
  cooldown OFF + liquidity filter (majors) + BTC regime gate.

## Module map — `src/signal/`
`indicators` · `levels` · `market_data` (ccxt + CSV/URL + offline demo) ·
`signal_engine` (the brain) · `money_management` · `portfolio` (heat / per-
direction correlation caps) · `scanner` (rank a universe) · `backtester`
(walk-forward + fees) · `calendar` (event blackout) · `news` (RSS/keyword) ·
`notifier` (Telegram text/photo, Thai) · `charting` (matplotlib PNG)

## CLIs (sandbox can't reach exchanges → use CSVs or `--demo`)
- `python signal_cli.py BTCUSDT [--demo] [--notify]` — one-symbol signal
- `python signal_scan.py --csv-dir data/real/crypto --htf W [--portfolio --summary --notify --charts]`
- `python signal_backtest.py BTCUSDT --csv data/real/crypto/BTCUSDT.csv --htf-rule W [--optimize --apply]`

## Config — `config/config.yaml` (`signal:` block)
Account $100, risk 2%/trade, leverage 10 (display/margin only — risk is set by
%/trade, not leverage). Calendar in `config/economic_calendar.yaml`.

## Data & deploy
- Data fetched by Actions via yfinance → `data/real/crypto/*.csv` (1d),
  `data/real/crypto_1h/` (1h). Universe: `data/crypto_universe.txt`.
- **`.github/workflows/auto_scan_alert.yml`** — daily 01:00 UTC (08:00 TH):
  fetch → scan → Telegram summary + per-signal compact alerts (+charts).
  Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Inputs: `test_notify`,
  `sample_signal`. Portfolio value: message the bot `/port 150` → `data/account.json`.

## Gotchas — don't re-research (these cost the most tokens to rediscover)
- **Sandbox network allows ONLY `raw.githubusercontent.com`.** Exchanges (Binance/
  Kraken/Bybit/OKX), Yahoo, CoinGecko, gist, api.github are all blocked — do NOT
  re-probe them. Real data comes from the Actions+yfinance workflow → committed
  CSVs in `data/real/`; for ad-hoc use `--csv*` or `--demo`.
- yfinance: 1d history is long (since 2018); 1h capped at ~730 days.
- Scheduled/dispatch workflows must live on the **default branch** to run; checkout
  inside the workflow uses the feature branch for code.
- GitHub MCP `list_workflow_runs` output is huge → saved to a file; parse with python.
- Full operational details + workarounds: skill `crypto-signal-ops`.

## More detail (read on demand, not by default)
- `docs/SIGNAL_SYSTEM.md` — concise system reference
- `docs/TELEGRAM_SETUP.md` — bot setup (token, chat id, /port)
- Skill `crypto-signal-ops` — operational runbook for common tasks
