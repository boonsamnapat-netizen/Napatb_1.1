#!/usr/bin/env python3
"""
Daily scanner: generates signals, sends Telegram alerts, places Alpaca paper trades.
Run at market open (9:30 AM ET on weekdays).
"""

import datetime
import pandas as pd

import config
from data.fetcher import build_dataset
from indicators.technical import compute_all_indicators
from strategies.vcp_minervini import VCPMinerviniStrategy
from strategies.zanger_breakout import ZangerBreakoutStrategy
from strategies.trend_following import TrendFollowingStrategy
from strategies.ensemble import EnsembleRanker
from notifier.telegram import send_message, send_signal_card, send_daily_summary


def _get_stock_data(verbose: bool) -> dict:
    """Fetch ~400 trading days of OHLCV data for the full universe."""
    today     = datetime.date.today()
    # ~560 calendar days ≈ 400 business days
    cal_start = today - datetime.timedelta(days=560)
    start_str = str(cal_start)
    end_str   = str(today + datetime.timedelta(days=1))  # exclusive upper bound

    if verbose:
        print(f'[Scanner] Fetching data {start_str} → {end_str}')

    stock_data = build_dataset(
        tickers   = config.UNIVERSE,
        full_start= start_str,
        full_end  = end_str,
        verbose   = verbose,
    )
    return stock_data


def _compute_indicators(stock_data: dict) -> dict:
    """Apply compute_all_indicators to every ticker DataFrame."""
    enriched = {}
    for ticker, df in stock_data.items():
        try:
            enriched[ticker] = compute_all_indicators(df)
        except Exception as e:
            print(f'[Scanner] Indicator error {ticker}: {e}')
    return enriched


def _train_ranker(stock_data: dict, verbose: bool) -> EnsembleRanker:
    """Train the AI ranker on data up to ML_TRAIN_CUTOFF."""
    ranker = EnsembleRanker()
    if verbose:
        print(f'[Scanner] Training EnsembleRanker (cutoff={config.ML_TRAIN_CUTOFF})')
    X, y = ranker.build_training_set(stock_data, train_end=config.ML_TRAIN_CUTOFF)
    if X is not None and len(X) >= 30:
        ranker.train(X, y)
        if verbose:
            print(f'[Scanner] Ranker trained on {len(X)} samples')
    else:
        if verbose:
            print('[Scanner] Not enough training data — using default scores')
    return ranker


def _collect_signals(
    stock_data: dict,
    ranker: EnsembleRanker,
    today: datetime.date,
    verbose: bool,
) -> list:
    """Run all strategies, score with AI, and return today's filtered signals."""
    strategies = [
        VCPMinerviniStrategy(),
        ZangerBreakoutStrategy(),
        TrendFollowingStrategy(),
    ]

    market_df = stock_data.get('SPY')
    signals   = []
    today_ts  = pd.Timestamp(today)

    for ticker, df in stock_data.items():
        if ticker == 'SPY':
            continue
        if len(df) < 50:
            continue

        for strat in strategies:
            try:
                sig_series = strat.generate_signals(df, market_df=market_df)
            except Exception as e:
                print(f'[Scanner] Signal error {ticker}/{strat.name()}: {e}')
                continue

            # Keep only rows where signal == 1 and date == today
            fired = sig_series[sig_series == 1]
            if fired.empty:
                continue

            # Filter to today only
            today_fired = fired[fired.index.normalize() == today_ts]
            if today_fired.empty:
                # Also accept the most recent signal date if today has no data yet
                latest_date = fired.index[-1].normalize()
                if latest_date != today_ts:
                    continue
                today_fired = fired[fired.index.normalize() == latest_date]

            if today_fired.empty:
                continue

            # Use the last row of today
            row_date = today_fired.index[-1]
            row      = df.loc[row_date]

            ai_prob = ranker.score_row(row)
            if ai_prob < config.ML_MIN_PROB:
                continue

            entry_price  = float(row['Close'])
            stop_price   = entry_price * (1 - config.STOP_LOSS_PCT)
            target_price = entry_price * (1 + config.TAKE_PROFIT_PCT)
            vol_ratio    = float(row.get('vol_ratio', 1.0))

            # Position sizing: risk RISK_PER_TRADE of equity
            # equity is unknown here; use INITIAL_CAPITAL as proxy
            risk_amount  = config.INITIAL_CAPITAL * config.RISK_PER_TRADE
            risk_per_sh  = entry_price - stop_price
            qty          = max(1, int(risk_amount / risk_per_sh)) if risk_per_sh > 0 else 1

            signals.append({
                'ticker':       ticker,
                'date':         str(row_date.date()),
                'strategy':     strat.name(),
                'entry_price':  entry_price,
                'stop_price':   stop_price,
                'target_price': target_price,
                'ai_prob':      ai_prob,
                'vol_ratio':    vol_ratio,
                'qty':          qty,
            })

    # Sort by ai_prob descending
    signals.sort(key=lambda s: s['ai_prob'], reverse=True)

    if verbose:
        print(f'[Scanner] {len(signals)} signals passed AI filter (min_prob={config.ML_MIN_PROB})')

    return signals


def _check_market_ok(stock_data: dict) -> bool:
    """Return True if SPY is above its 200-day SMA."""
    spy = stock_data.get('SPY')
    if spy is None or 'sma200' not in spy.columns:
        return True
    last = spy.iloc[-1]
    return float(last['Close']) > float(last['sma200'])


def run_daily_scan(paper_trade: bool = True, verbose: bool = True) -> list:
    """Main entry point: scan, alert, and optionally trade."""
    today      = datetime.date.today()
    if verbose:
        print(f'[Scanner] Starting daily scan for {today}')

    # 1. Fetch data
    raw_data = _get_stock_data(verbose)

    # 2. Compute indicators
    stock_data = _compute_indicators(raw_data)

    # 3. Train ranker
    ranker = _train_ranker(stock_data, verbose)

    # 4. Collect signals
    market_ok = _check_market_ok(stock_data)
    signals   = _collect_signals(stock_data, ranker, today, verbose)

    if verbose:
        print(f'[Scanner] Market OK: {market_ok}')
        for s in signals:
            print(
                f"  {s['ticker']:6s} [{s['strategy']:16s}]  "
                f"entry=${s['entry_price']:.2f}  "
                f"prob={s['ai_prob']:.2f}  "
                f"qty={s['qty']}"
            )

    # 5. Send Telegram alerts
    for sig in signals:
        send_signal_card(sig, market_ok)

    # 6. Paper trading via Alpaca
    trades_placed = 0
    equity        = config.INITIAL_CAPITAL

    if paper_trade:
        broker = None
        try:
            from broker.alpaca import AlpacaBroker
            broker = AlpacaBroker(paper=True)
            equity = broker.get_equity()
            if verbose:
                print(f'[Scanner] Alpaca connected — equity=${equity:,.2f}')
        except Exception as e:
            if verbose:
                print(f'[Scanner] Alpaca unavailable: {e}')

        if broker is not None:
            existing_tickers = {p['ticker'] for p in broker.get_positions()}
            open_count       = len(existing_tickers)

            for sig in signals:
                ticker = sig['ticker']

                if open_count >= config.MAX_POSITIONS:
                    if verbose:
                        print(f'[Scanner] Max positions ({config.MAX_POSITIONS}) reached — stopping')
                    break

                if ticker in existing_tickers:
                    if verbose:
                        print(f'[Scanner] Already holding {ticker} — skip')
                    continue

                # Recalculate qty using actual equity
                risk_amount = equity * config.RISK_PER_TRADE
                risk_per_sh = sig['entry_price'] - sig['stop_price']
                qty = max(1, int(risk_amount / risk_per_sh)) if risk_per_sh > 0 else 1

                order_id = broker.place_market_order(ticker, qty, side='buy')
                if order_id:
                    stop_id = broker.place_stop_order(ticker, qty, sig['stop_price'])
                    trades_placed += 1
                    open_count    += 1
                    existing_tickers.add(ticker)
                    if verbose:
                        print(f'[Scanner] Placed order {order_id} — {ticker} x{qty}  stop={sig["stop_price"]:.2f}')
                    send_message(
                        f'✅ <b>Order placed</b>: {ticker} x{qty} @ market\n'
                        f'   Stop: ${sig["stop_price"]:.2f}  |  order_id: <code>{order_id}</code>'
                    )

    # 7. Daily summary
    send_daily_summary(signals, trades_placed, equity)
    if verbose:
        print(f'[Scanner] Done — {trades_placed} trades placed.')

    return signals


def monitor_exits() -> None:
    """Check open positions and close any that have hit stop or target."""
    try:
        from broker.alpaca import AlpacaBroker
        broker = AlpacaBroker(paper=True)
    except Exception as e:
        print(f'[Monitor] Alpaca unavailable: {e}')
        return

    positions = broker.get_positions()
    if not positions:
        print('[Monitor] No open positions.')
        return

    # Gather current prices via yfinance if available
    prices = {}
    try:
        import yfinance as yf
        tickers = [p['ticker'] for p in positions]
        data    = yf.download(tickers, period='1d', progress=False, auto_adjust=True)
        if 'Close' in data.columns:
            last_row = data['Close'].iloc[-1]
            prices   = last_row.to_dict()
        elif hasattr(data, 'iloc'):
            # Single ticker returns Series
            if len(tickers) == 1:
                prices[tickers[0]] = float(data['Close'].iloc[-1])
    except Exception as e:
        print(f'[Monitor] yfinance error: {e}')

    for pos in positions:
        ticker      = pos['ticker']
        cost_basis  = pos['cost_basis'] / max(pos['qty'], 1)
        current     = prices.get(ticker, pos['current_price'])

        stop_price   = cost_basis * (1 - config.STOP_LOSS_PCT)
        target_price = cost_basis * (1 + config.TAKE_PROFIT_PCT)

        reason = None
        if current <= stop_price:
            reason = f'STOP hit (${current:.2f} <= ${stop_price:.2f})'
        elif current >= target_price:
            reason = f'TARGET hit (${current:.2f} >= ${target_price:.2f})'

        if reason:
            closed = broker.close_position(ticker)
            if closed:
                pnl = (current - cost_basis) * pos['qty']
                print(f'[Monitor] Closed {ticker}: {reason}  PnL=${pnl:+.2f}')
                send_message(
                    f'🔴 <b>Position closed</b>: {ticker}\n'
                    f'   Reason: {reason}\n'
                    f'   PnL: ${pnl:+.2f}'
                )
            else:
                print(f'[Monitor] Failed to close {ticker}')
        else:
            pnl_pct = (current - cost_basis) / cost_basis * 100
            print(f'[Monitor] {ticker}: ${current:.2f}  ({pnl_pct:+.1f}%)  — holding')
