"""
Global configuration for NAPATB AI Trading System
Based on Minervini (VCP/SEPA), Zanger (breakout), and trend following
"""

# --- Universe ---
# ─────────────────────────────────────────────────────────────────────────────
# SURVIVORSHIP-BIAS NOTE (Phase 0, workstream C)
#
# This list is a CURRENT-MEMBERSHIP APPROXIMATION of a broad, liquid US universe.
# The original 37-name list was composed entirely of TODAY's mega-winners, which
# is severe survivorship bias: backtesting a momentum strategy only on names you
# already know went up massively overstates returns.
#
# Below we keep the original 37 but add ~50 names that suffered significant
# multi-year drawdowns or stagnation during 2018-2024 (e.g. INTC, BA, DIS, PYPL,
# NFLX, BABA, PFE, T, F, GE, cruise lines, etc.) plus a few sector ETFs for
# breadth. This only PARTIALLY mitigates the bias — every ticker here is still a
# company that survived to 2026. Names that were delisted, acquired, or went
# bankrupt (e.g. former index members that failed) are still absent.
#
# The PROPER fix is point-in-time index constituents + delisted-securities data
# (CRSP / Norgate / Sharadar). See docs/SURVIVORSHIP.md.
#
# SPY is kept LAST as the benchmark and is excluded from trading by main.py.
# ─────────────────────────────────────────────────────────────────────────────
UNIVERSE = [
    # --- Original 37 (today's mega-winners — kept for continuity) ---
    # Mega-cap Tech / FAANG+
    'AAPL', 'MSFT', 'NVDA', 'META', 'GOOGL', 'AMZN', 'TSLA', 'AMD', 'AVGO', 'ORCL',
    # High-growth / Momentum leaders
    'CRWD', 'PANW', 'DDOG', 'NET', 'MDB', 'TTD', 'CELH', 'LULU', 'ENPH', 'DECK',
    # Healthcare (winners)
    'LLY', 'UNH', 'ISRG', 'TMO',
    # Financials (winners)
    'JPM', 'V', 'MA', 'GS', 'SPGI',
    # Consumer (winners)
    'COST', 'HD', 'MCD', 'CMG', 'WMT',
    # Energy (winners)
    'XOM', 'CVX',

    # --- Added breadth: names with rough 2018-2024 stretches ---
    # Semis / hardware that lagged or fell
    'INTC', 'QCOM', 'MU', 'CSCO', 'IBM', 'TXN',
    # Software / internet that crashed from 2021 highs
    'PYPL', 'XYZ', 'ROKU', 'ZM', 'SNAP', 'PINS', 'NFLX', 'SHOP', 'UBER',
    # China / international large caps with deep drawdowns
    'BABA', 'JD', 'PDD',
    # Industrials / transports (cyclical, mixed decade)
    'BA', 'GE', 'CAT', 'DE', 'MMM', 'HON', 'UPS', 'FDX', 'EMR',
    # Autos
    'F', 'GM',
    # Telecom / media (long stagnation / decline)
    'T', 'VZ', 'DIS', 'CMCSA',
    # Consumer staples / retail (defensive, slow)
    'KO', 'PEP', 'PG', 'CL', 'NKE', 'SBUX', 'TGT', 'LOW', 'WBA',
    # Healthcare / pharma (mixed, some declines)
    'PFE', 'MRK', 'ABBV', 'JNJ', 'GILD', 'MRNA', 'CVS', 'BMY',
    # Financials / banks (rate-sensitive, drawdowns)
    'BAC', 'WFC', 'C', 'MS',
    # Travel / leisure (COVID-shocked)
    'UAL', 'DAL', 'CCL', 'RCL', 'MAR',
    # Sector ETFs for breadth
    'XLF', 'XLE', 'XLK', 'IWM',

    # Benchmark (not traded — must stay LAST)
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
TAKE_PROFIT_PCT  = 0.25          # +25% reference (kept for Telegram alert targets; NOT used for exits — see Phase 1B)
TRAILING_START   = 0.15          # Activate trailing stop after +15% gain
TRAILING_STOP    = 0.12          # Trail 12% below highest price
TIME_STOP_DAYS     = 35          # Exit if held > 35 calendar days with gain < threshold
TIME_STOP_MIN_GAIN = 0.03        # Must show at least +3% in TIME_STOP_DAYS or exit
COOLDOWN_DAYS      = 10          # No re-entry in same ticker for 10 days after stop-loss

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
