"""
Global configuration for NAPATB AI Trading System
Based on Minervini (VCP/SEPA), Zanger (breakout), and trend following
"""

# --- Universe ---
UNIVERSE = [
    # Mega-cap Tech / FAANG+
    'AAPL', 'MSFT', 'NVDA', 'META', 'GOOGL', 'AMZN', 'TSLA', 'AMD', 'AVGO', 'ORCL',
    # High-growth / Momentum leaders
    'CRWD', 'PANW', 'DDOG', 'NET', 'MDB', 'TTD', 'CELH', 'LULU', 'ENPH', 'DECK',
    # Healthcare
    'LLY', 'UNH', 'ISRG', 'TMO',
    # Financials
    'JPM', 'V', 'MA', 'GS', 'SPGI',
    # Consumer
    'COST', 'HD', 'MCD', 'CMG', 'WMT',
    # Energy
    'XOM', 'CVX',
    # Benchmark (not traded)
    'SPY',
]

# --- Date Range ---
DATA_START       = '2018-01-01'  # Extra warmup for 200-day MA
BACKTEST_START   = '2020-01-01'
BACKTEST_END     = '2025-01-01'

ML_TRAIN_CUTOFF  = '2021-12-31'  # Train on 2018-2021, score 2022-2024

# --- Portfolio ---
INITIAL_CAPITAL  = 100_000.0
MAX_POSITIONS    = 10
RISK_PER_TRADE   = 0.02          # 2% portfolio risk per trade
COMMISSION       = 0.001         # 0.1% each side
SLIPPAGE         = 0.0005        # 0.05% slippage

# --- Exit Rules (Minervini + Zanger combined) ---
STOP_LOSS_PCT    = 0.08          # -8% hard stop
TAKE_PROFIT_PCT  = 0.25          # +25% full exit
TRAILING_START   = 0.15          # Activate trailing stop after +15% gain
TRAILING_STOP    = 0.12          # Trail 12% below highest price

# --- Strategy weights ---
STRATEGY_WEIGHTS = {
    'VCP_Minervini':     0.40,
    'Zanger_Breakout':   0.30,
    'Trend_Following':   0.30,
}

# --- ML Config ---
ML_TARGET_DAYS      = 20     # Predict 20-day forward return
ML_TARGET_THRESHOLD = 0.08   # > 8% = positive label
ML_MIN_PROB         = 0.38   # Min AI probability to accept a signal
