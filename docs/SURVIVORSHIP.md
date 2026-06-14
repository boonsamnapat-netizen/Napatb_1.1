# Survivorship Bias in the NAPATB Universe

## What it is (in this context)

Survivorship bias is the error of testing a strategy only on assets that
"survived" to the present. The original 37-ticker universe in `config.py` was
composed entirely of **today's mega-winners** (NVDA, AAPL, TSLA, LLY, CRWD, ...).
Running a momentum/breakout strategy on names we *already know* went up for years
guarantees flattering results. The backtest learns to "buy stocks that went up"
on a sample hand-picked because they went up — circular and misleading. Reported
CAGR, Sharpe, and win-rate will be materially overstated versus live trading on a
universe chosen *before* the outcomes were known.

A system intended to survive 10+ years must be validated on a representative
cross-section, including names that stagnated or fell hard for multi-year stretches.

## What this change does (partial mitigation)

`config.py` and `data/universe.txt` now hold ~100 liquid US tickers:

- The original 37 winners (kept for continuity).
- ~50 names with significant 2018-2024 drawdowns or stagnation: INTC, BA, DIS,
  PYPL, NFLX, BABA, PFE, T, VZ, F, GE, INTC, the cruise lines (CCL/RCL), the 2021
  growth-crash cohort (ROKU, ZM, SNAP, PINS, XYZ), etc.
- A few sector ETFs (XLF, XLE, XLK, IWM) for breadth; SPY stays as the benchmark.

This makes the sample **more honest**, but only **partially** removes the bias:
**every ticker here still survived to 2026.** Companies that were delisted,
acquired at a loss, or went bankrupt are absent. Index membership is also
implicitly current — we are not reconstructing who was in the S&P 500 / NASDAQ on
any given historical date. So results will still skew optimistic.

## The proper fix

True elimination of survivorship bias requires **point-in-time data**:

1. **Point-in-time index constituents.** Know exactly which symbols were members
   of the target index on each historical rebalance date, and trade only those.
2. **Delisted / dead securities.** Include the full price history of names that
   were later delisted, merged, or went to zero, so losers are represented.
3. **Corporate-action-clean adjustments** (splits, spinoffs, ticker changes).

Vendors that provide this: **CRSP** (academic standard), **Norgate Data**
(retail, delisted-inclusive, point-in-time index membership), and
**Sharadar/Nasdaq Data Link** (SEP/SF1 with delisted history). `yfinance` does
**not** provide point-in-time membership or reliable delisted history, which is
why the list above is only an approximation.

## Prioritized recommendation

1. **Now (done):** broaden the universe to the ~100-name cross-section above so
   the backtest stops being an all-winners sample.
2. **Next:** integrate a delisted-inclusive, point-in-time vendor (Norgate or
   Sharadar are the most cost-effective for a retail/small-fund setup) and rebuild
   the dataset against historical index membership.
3. **Then:** run walk-forward validation on the point-in-time universe and compare
   metrics against the current approximation — the gap is the survivorship premium
   the strategy was silently collecting.
4. **Always:** treat any backtest run on the current `yfinance` universe as an
   **upper bound**, not an expected, on live performance.
