"""
Synthetic market data generator.
Uses Geometric Brownian Motion + realistic US market regimes:
  - COVID crash (Feb-Mar 2020) + recovery
  - 2021 tech bull market
  - 2022 rate-hike bear market
  - 2023-2024 AI/growth recovery

Correlates individual stocks to a synthetic SPY using beta.
Adds GARCH-like volatility clustering.
"""

import numpy as np
import pandas as pd

# Per-ticker parameters: (annual_mu, annual_sigma, beta, sector, start_price)
TICKER_PARAMS = {
    'AAPL':  (0.22, 0.28, 1.20, 'tech',     42.0),
    'MSFT':  (0.26, 0.26, 1.10, 'tech',     90.0),
    'NVDA':  (0.55, 0.58, 1.55, 'tech',     30.0),
    'META':  (0.22, 0.42, 1.30, 'tech',    180.0),
    'GOOGL': (0.22, 0.30, 1.10, 'tech',     55.0),
    'AMZN':  (0.22, 0.34, 1.20, 'tech',     60.0),
    'TSLA':  (0.38, 0.72, 1.80, 'tech',     20.0),
    'AMD':   (0.42, 0.62, 1.60, 'tech',     12.0),
    'AVGO':  (0.32, 0.34, 1.25, 'tech',    250.0),
    'ORCL':  (0.18, 0.24, 0.90, 'tech',     50.0),
    'CRWD':  (0.38, 0.56, 1.50, 'growth',   35.0),
    'PANW':  (0.32, 0.50, 1.40, 'growth',   40.0),
    'DDOG':  (0.36, 0.60, 1.60, 'growth',   35.0),
    'NET':   (0.32, 0.55, 1.50, 'growth',   20.0),
    'MDB':   (0.30, 0.60, 1.50, 'growth',   50.0),
    'TTD':   (0.26, 0.54, 1.40, 'growth',   40.0),
    'CELH':  (0.42, 0.65, 1.05, 'consumer',  4.0),
    'LULU':  (0.26, 0.38, 1.10, 'consumer', 90.0),
    'ENPH':  (0.36, 0.62, 1.30, 'energy',    5.0),
    'DECK':  (0.22, 0.34, 0.90, 'consumer', 75.0),
    'LLY':   (0.32, 0.28, 0.70, 'health',   80.0),
    'UNH':   (0.20, 0.22, 0.60, 'health',  220.0),
    'ISRG':  (0.20, 0.28, 0.80, 'health',  380.0),
    'TMO':   (0.18, 0.24, 0.70, 'health',  220.0),
    'JPM':   (0.16, 0.28, 1.30, 'finance', 110.0),
    'V':     (0.20, 0.22, 1.00, 'finance', 125.0),
    'MA':    (0.22, 0.23, 1.00, 'finance', 165.0),
    'GS':    (0.15, 0.30, 1.40, 'finance', 260.0),
    'SPGI':  (0.18, 0.24, 0.90, 'finance', 200.0),
    'COST':  (0.20, 0.20, 0.70, 'consumer',200.0),
    'HD':    (0.17, 0.24, 0.90, 'consumer',190.0),
    'MCD':   (0.15, 0.18, 0.70, 'consumer',165.0),
    'CMG':   (0.22, 0.30, 0.90, 'consumer',320.0),
    'WMT':   (0.14, 0.18, 0.50, 'consumer',100.0),
    'XOM':   (0.12, 0.30, 0.80, 'energy',   80.0),
    'CVX':   (0.12, 0.28, 0.80, 'energy',  120.0),
    'SPY':   (0.14, 0.17, 1.00, 'index',   270.0),
    'QQQ':   (0.17, 0.22, 1.15, 'index',   170.0),
}


def generate(
    tickers: list,
    start: str = '2018-01-01',
    end:   str = '2025-01-01',
    seed:  int = 2024,
) -> dict[str, pd.DataFrame]:

    rng   = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n     = len(dates)
    dt    = 1 / 252

    # ── 1. Generate SPY market returns (regime-aware) ─────────────────────
    spy_ret = _spy_returns(dates, rng)

    data = {}

    for ticker in tickers:
        if ticker not in TICKER_PARAMS:
            # Generic parameters for unknown tickers
            mu, sigma, beta, sector, p0 = 0.15, 0.30, 1.0, 'tech', 100.0
        else:
            mu, sigma, beta, sector, p0 = TICKER_PARAMS[ticker]

        # Idiosyncratic component (orthogonal to market)
        mkt_var    = (0.17 ** 2) * dt           # SPY daily variance
        sys_var    = (beta ** 2) * mkt_var
        total_var  = (sigma ** 2) * dt
        idio_std   = max(np.sqrt(total_var - sys_var * 0.8), 0.003)

        idio      = rng.normal(0, idio_std, n)
        alpha_d   = (mu - 0.14) / 252           # Daily alpha over market
        daily_ret = beta * spy_ret + alpha_d + idio

        # Sector regime overlays
        daily_ret = _sector_overlay(daily_ret, dates, sector, rng)

        # ── Build close price series ──────────────────────────────────────
        close = np.empty(n)
        close[0] = p0
        for i in range(1, n):
            close[i] = close[i - 1] * (1 + daily_ret[i])
            close[i] = max(close[i], 0.01)

        # ── Build OHLCV ───────────────────────────────────────────────────
        intra_vol = sigma * np.sqrt(dt)
        base_vol  = max(1_000_000, int(abs(hash(ticker)) % 30_000_000))

        opens  = np.empty(n)
        highs  = np.empty(n)
        lows   = np.empty(n)
        volume = np.empty(n, dtype=np.int64)

        opens[0] = p0
        for i in range(n):
            c = close[i]
            gap      = c * rng.normal(0, intra_vol * 0.25)
            o        = max(close[i - 1] + gap if i > 0 else p0, 0.01)
            rng_size = c * intra_vol * rng.uniform(0.5, 2.8)
            h = max(o, c) + rng_size * rng.uniform(0.05, 0.55)
            l = min(o, c) - rng_size * rng.uniform(0.05, 0.55)
            opens[i] = o
            highs[i] = max(h, o, c)
            lows[i]  = max(min(l, o, c), 0.001)

            # Volume spikes on big price moves
            move    = abs(daily_ret[i]) if i > 0 else 0
            v_mult  = 1.0 + 8.0 * move + rng.exponential(0.25)
            volume[i] = int(base_vol * v_mult * rng.uniform(0.6, 1.5))

        data[ticker] = pd.DataFrame(
            {'Open': opens, 'High': highs, 'Low': lows, 'Close': close, 'Volume': volume},
            index=dates,
        )

    return data


# ── Helpers ──────────────────────────────────────────────────────────────────

def _spy_returns(dates: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """Generate SPY-like daily returns with regime events."""
    n   = len(dates)
    ret = rng.normal(0.14 / 252, 0.17 / np.sqrt(252), n)

    # GARCH-like clustering
    vol_f = np.ones(n)
    for i in range(1, n):
        vol_f[i] = 0.93 * vol_f[i - 1] + 0.07 * (1 + 6 * abs(ret[i - 1]))
    ret = ret * vol_f

    for i, d in enumerate(dates):
        ds = str(d)[:10]
        if   '2020-02-24' <= ds <= '2020-03-23':  ret[i] -= 0.012 + rng.exponential(0.007)
        elif '2020-03-24' <= ds <= '2020-08-31':  ret[i] += 0.0014   # recovery
        elif '2021-01-01' <= ds <= '2021-12-31':  ret[i] += 0.0007   # bull
        elif '2022-01-01' <= ds <= '2022-12-31':  ret[i] -= 0.0016   # rate-hike bear
        elif '2023-01-01' <= ds <= '2023-12-31':  ret[i] += 0.0009   # recovery
        elif '2024-01-01' <= ds <= '2024-12-31':  ret[i] += 0.0011   # AI boom

    return ret


def _sector_overlay(
    ret: np.ndarray,
    dates: pd.DatetimeIndex,
    sector: str,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sector-specific regime adjustments."""
    r = ret.copy()
    for i, d in enumerate(dates):
        ds = str(d)[:10]
        if sector in ('tech', 'growth'):
            if '2020-04-01' <= ds <= '2021-11-15':  r[i] += 0.0018
            elif '2022-01-01' <= ds <= '2022-12-31': r[i] -= 0.0025
            elif '2023-06-01' <= ds <= '2024-12-31': r[i] += 0.0015
        elif sector == 'energy':
            if '2022-01-01' <= ds <= '2022-12-31':  r[i] += 0.0020
            elif '2023-01-01' <= ds <= '2024-12-31': r[i] -= 0.0010
        elif sector == 'health':
            if '2022-01-01' <= ds <= '2022-12-31':  r[i] += 0.0008
            if '2023-01-01' <= ds <= '2024-12-31':  r[i] += 0.0005
        elif sector == 'finance':
            if '2022-01-01' <= ds <= '2022-12-31':  r[i] -= 0.0010
            elif '2023-01-01' <= ds <= '2024-12-31': r[i] += 0.0010
    return r
