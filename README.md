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

## NSE-wide ICT scanner (45-minute OTE)
A funnel from ~2,500 NSE equities to a short ranked list, with an annotated 45m chart for each finalist.

| Stage | Data | What it checks |
|---|---|---|
| 0 Market | NIFTY 500, India VIX, breadth | daily structure not down, breadth ≥ 40%, VIX ≤ 22 → longs allowed |
| 1 Universe | daily, all symbols | 20d turnover ≥ 10 Cr, price ≥ 50, ATR% 1–6, history, exclude list, earnings |
| 2 Daily ICT | daily | bias up/range, in discount, within 1 ATR of a PD array, ≥ 2 ATR room to buy-side liquidity, RS |
| 3 45m OTE | 15m → 45m (09:15-anchored, last candle 14:30–15:30) | sell-side sweep → bullish MSS → pullback into 62–79%, R:R to T2 ≥ 2 |
| 4 Rank | | grade A/B/C, score, quantity at 1% risk, charts, HTML |

```bash
pip install -r requirements.txt
python -m scripts.fetch_data --all          # NSE list + bhavcopy daily (official) + indices (Yahoo); needs internet
python -m scripts.scan                      # downloads 15m only for stage-2 survivors, then ranks
open reports/scans/<date>/index.html
python -m scripts.scan --date 2026-11-12 --no-fetch   # replay an earlier day from the cache
```
Free data: daily from NSE bhavcopy (official end-of-day files), indices and 15m from Yahoo Finance.
Yahoo keeps only 60 days of 15m bars, so every download is cached in `data/store/m15` and the history grows.
All thresholds are in `config.yaml → scan:`. Rules for each stage are documented at the top of
`ict_engine/scan/stages.py` and `ict_engine/scan/ote.py`.

### Daily email on GitHub Actions
`.github/workflows/daily-screener.yml` runs `python -m scripts.daily --fetch --require-today --email`
at 19:37 IST, Monday to Friday, and on demand (Actions → Daily screener → Run workflow; choose a date,
mode, or a preview without email). NSE holidays are skipped automatically: NIFTY's daily bar shows whether
the exchange traded. If the stock bars for today are missing, the run fails and GitHub notifies you.
Market data is kept between runs in the Actions cache; the first run builds it, which takes longer.
Add repository secrets `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO` (and optionally `EMAIL_FROM_NAME`),
for example with `gh secret set -f .env`. Never put them in the repo: it is public.
GitHub pauses scheduled workflows in public repos after 60 days without a commit; re-enable it on the Actions tab.

## Concept website (25 pages)
`docs/` is a static site, one page per concept. Each page has the idea, the exact rule, a schematic,
a **real NIFTY 15-minute or daily example found by the engine**, common mistakes and an exercise.

```bash
open docs/index.html                 # view locally
python -m scripts.build_site         # rebuild after updating data/raw/NIFTY.csv or NIFTY_15m.csv
```
Publish: GitHub → Settings → Pages → Branch `main`, folder `/docs`, then visit
https://rakeshdoreswamy.github.io/ict-swing-engine/

## Learn the concepts
* **Study guide:** [`docs/CONCEPTS.md`](docs/CONCEPTS.md) covers all 24 concepts: the idea, the exact rule, why it matters, and an exercise.
* **Walkthroughs on real charts:**
  ```bash
  python -m scripts.learn                                # list concepts
  python -m scripts.learn swings                         # last 30 NIFTY daily bars, step by step
  python -m scripts.learn swings --bars 120 --tf weekly  # bigger picture
  ```
  Each walkthrough prints why every bar qualifies, when it was confirmed, and the open liquidity
  above and below price, then saves an annotated chart in `reports/learn_<concept>.png`.

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
