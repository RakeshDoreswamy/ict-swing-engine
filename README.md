# ICT Swing Engine (Indian equities)

A rules-based engine that turns ICT (Inner Circle Trader) Month 5 swing-trading concepts into
precise, testable code for NSE stocks and ETFs: scan, score, backtest, paper trade, journal.
Weekly bars for context, daily bars for confirmation and entry. Cash delivery / ETFs only.

> ICT concepts are not independently proven. This engine exists to **test** them.
> Education only, not financial advice. Check current SEBI/exchange rules and consider a
> SEBI-registered advisor before using real capital.

## Layout
```
config.yaml                 every threshold (no magic numbers in code)
ict_engine/
  data/loader.py            pluggable data layer (CSV, yfinance) + weekly resample
  detectors/swings.py       M1  institutional swing points (STH/ITH/LTH, STL/ITL/LTL)   [done]
  detectors/liquidity.py    M2  open float, liquidity pools, sweeps                    [next]
  detectors/pd_arrays.py    M3  order blocks, FVG/iFVG, breakers, old highs/lows
  analysis/premium_discount.py  M4  dealing range, equilibrium, OTE
  analysis/ipda.py          M5  20/40/60-day IPDA ranges, quarterly shifts
  analysis/bias.py          M6  weekly bias + optional intermarket/yield/seasonal filters
  strategy/confirmation.py  M7  HTF zone, sweep, MSS by close, entry zone
  strategy/entries.py       M8  limit / stop entry models, stop & target, min R:R
  risk/sizing.py            M9  1% risk sizing, portfolio caps, drawdown control
  strategy/management.py    M10 breakeven, trailing, partials, time stop
  strategy/filters.py       M11 event calendar, turnover, gap risk
  strategy/grader.py        M12 pre-trade checklist -> grade A/B/C
  backtest/                 M13 event-driven backtest, Indian costs, seasonality, ablation
  journal/                  M14 journal, stats, graduation gate, weekly review
  report/                   HTML/markdown reports
pine/                       TradingView Pine v6 overlay
scripts/                    command-line entry points
tests/                      pytest, synthetic fixtures + no-lookahead tests
data/raw/                   OHLCV CSVs (one file per symbol)
data/events/events.csv      earnings / RBI / Budget / rebalancing calendar
```

## Quick start
```bash
pip install -r requirements.txt
pytest -q
python -m scripts.run_swings NIFTY      # writes reports/NIFTY_{daily,weekly}_swings.{csv,png}
```

## Module 1 rules (swing points)
* **STH/STL**: 3-bar fractal (configurable left/right bars), confirmed only after the right bar closes.
* **ITH/ITL**: an STH with a lower STH either side (lows mirror).
* **LTH/LTL**: an ITH with a lower ITH either side.
* **Unbroken**: no later bar has traded through it (wick or close, configurable) = open float.
* Every level carries its own confirmation date; `swings_as_of()` gives the point-in-time view.
  A test recomputes on every data prefix to prove there is no lookahead.
