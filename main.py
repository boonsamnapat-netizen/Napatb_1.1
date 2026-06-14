#!/usr/bin/env python3
"""
NAPATB AI Trading System
========================
Combines three strategies inspired by the world's best traders:
  1. VCP + SEPA  (Mark Minervini) — breakout from tight base with volume
  2. Zanger Breakout               — chart pattern breakout on volume surge
  3. Trend Following               — momentum in confirmed uptrend

AI layer: RandomForest ranks signals by predicted forward-return probability.
Walk-forward split: train 2018-2021, trade 2022-2024.

Backtest: 2020-01-01 → 2025-01-01  (5 years, $100,000 start)
"""

import os, sys, time, warnings
import pandas as pd
import numpy as np
warnings.filterwarnings('ignore')

import config
from data.fetcher               import build_dataset
from indicators.technical       import compute_all_indicators
from strategies.vcp_minervini  import VCPMinerviniStrategy
from strategies.zanger_breakout import ZangerBreakoutStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.ensemble        import EnsembleRanker, FEATURE_COLS
from backtest.engine            import BacktestEngine
from backtest.metrics           import compute_metrics, print_metrics, compute_period_metrics, print_period_split
from report.visualizer          import plot_report


CACHE = 'market_data_cache.pkl'


# ── Data ─────────────────────────────────────────────────────────────────────

def download_data(tickers, start, end):
    if os.path.exists(CACHE):
        print(f'  Loading cached data ({CACHE})...')
        return pd.read_pickle(CACHE)

    print(f'  Fetching data for {len(tickers)} tickers...')
    print('  (Real 2020 data from GitHub for AAPL/MSFT/GOOGL/AMZN/TSLA; calibrated GBM for rest)')
    data = build_dataset(tickers, full_start=start, full_end=end, seed=42, verbose=True)
    print(f'  Dataset ready: {len(data)} tickers')

    pd.to_pickle(data, CACHE)
    return data


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()

    print('═' * 60)
    print('  NAPATB AI TRADING SYSTEM')
    print(f'  Backtest: {config.BACKTEST_START} → {config.BACKTEST_END}')
    print(f'  Universe: {len(config.UNIVERSE)} stocks')
    print(f'  Capital : ${config.INITIAL_CAPITAL:,.0f}')
    print('═' * 60)

    # ── 1. Download ──────────────────────────────────────────────────────
    print('\n[1/6] Downloading data...')
    raw = download_data(config.UNIVERSE, config.DATA_START, config.BACKTEST_END)
    if not raw:
        print('ERROR: no data downloaded'); sys.exit(1)

    spy_raw = raw.get('SPY', pd.DataFrame())

    # ── 2. Indicators ────────────────────────────────────────────────────
    print('\n[2/6] Computing technical indicators...')
    stock_data = {}
    for ticker, df in raw.items():
        try:
            stock_data[ticker] = compute_all_indicators(df)
        except Exception as e:
            print(f'  {ticker}: {e}')

    market_df = stock_data.get('SPY')
    tradeable = {k: v for k, v in stock_data.items() if k != 'SPY'}

    print(f'  Indicators ready for {len(tradeable)} tradeable stocks + SPY')

    # ── 3. Train AI Model ────────────────────────────────────────────────
    print(f'\n[3/6] Training AI Ensemble (train cutoff: {config.ML_TRAIN_CUTOFF})...')
    ranker = EnsembleRanker()

    X, y = ranker.build_training_set(tradeable, config.ML_TRAIN_CUTOFF)
    if X is not None and len(X) >= 200:
        ranker.train(X, y)
        pos_rate = y.mean()
        print(f'  Trained on {len(X):,} samples  |  positive rate: {pos_rate:.1%}')
        print('  Top features:')
        for feat, imp in ranker.top_features(6):
            print(f'    {feat:<28} {imp:.4f}')
        # Build annual models for expanding-window scoring
        ranker.build_annual_models(tradeable, start_year=2020, end_year=2024)
        trained_years = sorted(ranker.annual_models.keys())
        print(f'  Annual models built for years: {trained_years}')
        for yr, pr in sorted(ranker.annual_pos_rates.items()):
            print(f'    {yr}: pos_rate={pr:.1%}')
    else:
        print('  WARNING: insufficient training data — AI scoring disabled')

    # ── 4. Generate Signals ──────────────────────────────────────────────
    print('\n[4/6] Generating strategy signals...')

    strategies = [
        VCPMinerviniStrategy(),
        ZangerBreakoutStrategy(),
        TrendFollowingStrategy(),
    ]

    # signals_by_date[date] = list of {ticker, score, strategy}
    signals_by_date: dict = {}

    for ticker, df in tradeable.items():
        for strat in strategies:
            try:
                sig_series = strat.generate_signals(df, market_df)
            except Exception as e:
                print(f'  {ticker}/{strat.name()}: {e}')
                continue

            dates_with_signal = sig_series[sig_series == 1].index

            for date in dates_with_signal:
                # Only trade after backtest start
                if str(date)[:10] < config.BACKTEST_START:
                    continue

                row = df.loc[date]

                # AI score (only after training cutoff to avoid look-ahead)
                if ranker.is_trained and str(date)[:10] > config.ML_TRAIN_CUTOFF:
                    ai_prob = ranker.score_row_annual(row, str(date)[:10])
                else:
                    ai_prob = 0.55  # neutral score during warm-up period

                # Skip low-confidence signals
                if ai_prob < config.ML_MIN_PROB:
                    continue

                w     = config.STRATEGY_WEIGHTS.get(strat.name(), 0.33)
                score = w * ai_prob

                if date not in signals_by_date:
                    signals_by_date[date] = []

                # Deduplicate: keep highest score if same ticker appears twice
                existing = next((s for s in signals_by_date[date] if s['ticker'] == ticker), None)
                if existing:
                    if score > existing['score']:
                        existing['score']    = score
                        existing['strategy'] = strat.name()
                else:
                    signals_by_date[date].append({
                        'ticker':   ticker,
                        'score':    score,
                        'strategy': strat.name(),
                    })

    total_sigs = sum(len(v) for v in signals_by_date.values())
    print(f'  Signals generated: {total_sigs} across {len(signals_by_date)} trading days')

    # Signal breakdown by strategy
    strat_counts: dict = {}
    for day_sigs in signals_by_date.values():
        for s in day_sigs:
            strat_counts[s['strategy']] = strat_counts.get(s['strategy'], 0) + 1
    for strat_name, cnt in sorted(strat_counts.items()):
        print(f'    {strat_name:<30} {cnt:4d} signals')

    # ── 5. Backtest ──────────────────────────────────────────────────────
    print('\n[5/6] Running backtest simulation...')
    engine    = BacktestEngine(stock_data, market_df)
    portfolio = engine.run(signals_by_date)

    open_pos  = len(portfolio.positions)
    if open_pos:
        print(f'  NOTE: {open_pos} positions still open at end — marked at last close')

    # ── 6. Metrics & Report ──────────────────────────────────────────────
    print('\n[6/6] Computing metrics and generating report...')

    # SPY benchmark return
    spy_close = spy_raw['Close'] if not spy_raw.empty else pd.Series()
    spy_close_aligned = spy_close[
        (spy_close.index >= config.BACKTEST_START) &
        (spy_close.index <= config.BACKTEST_END)
    ] if not spy_close.empty else pd.Series()

    spy_total_ret = (
        spy_close_aligned.iloc[-1] / spy_close_aligned.iloc[0] - 1
        if len(spy_close_aligned) > 1 else None
    )

    metrics = compute_metrics(
        portfolio.equity_curve,
        portfolio.trades,
        config.INITIAL_CAPITAL,
        benchmark=spy_close_aligned if not spy_close_aligned.empty else None,
    )

    print_metrics(metrics, spy_ret=spy_total_ret)

    # Honest split: pre-AI warmup vs AI-filtered period
    periods = compute_period_metrics(
        portfolio.equity_curve,
        portfolio.trades,
        config.INITIAL_CAPITAL,
        config.ML_TRAIN_CUTOFF,
    )
    print_period_split(periods)

    # Visual report
    try:
        plot_report(
            metrics,
            spy_close_aligned if not spy_close_aligned.empty else spy_close,
            output_path='backtest_report.png',
            title=f'NAPATB AI Trading — {config.BACKTEST_START[:4]}–{config.BACKTEST_END[:4]} | $100k Start',
        )
    except Exception as e:
        print(f'  Chart error (non-fatal): {e}')

    elapsed = time.time() - t0
    print(f'\n  Done in {elapsed:.1f}s')
    print('═' * 60)

    return metrics, portfolio


if __name__ == '__main__':
    main()
