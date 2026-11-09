# ICT Swing Engine: TradingView indicator (Pine Script v6)

`ict_swing_engine.pine` draws every concept from the study guide on any symbol and timeframe,
using the same rules as the Python engine. Nothing repaints: each object appears only once
closed bars confirm its rule.

## Install
1. In TradingView, open the **Pine Editor**, click **Open → New blank indicator**, and paste the whole file.
2. Click **Save** and name it `ICT Swing Engine`.
3. Click **Add to chart**. Recommended: CNX500 / NIFTY / a large cap on 15m, 1H or D.
4. Optionally, create alerts: **Alerts → Condition: ICT Swing Engine →** pick an event.

## What it draws
| # | Concept | On the chart |
|---|---|---|
| 1 | Swing points | ▲▼ under/over each confirmed 3-bar swing (offset to the swing bar) |
| 2 | ITH/LTH/ITL/LTL | blue / purple labels when a swing is promoted |
| 3 | Open float | dashed line + "open ITH 19,432" until broken, then a grey dotted line and ✕ |
| 4 | Liquidity pools | "BSL pool ×3" / "SSL pool ×4" (N nearest untouched per side), plus previous day and week high/low |
| 5 | Sweeps | "◆ BSL sweep" / "◆ SSL sweep" |
| 6 | Displacement | shaded candle background |
| 7 | FVG / inverse FVG | green/red box with dotted CE; turns grey when closed through |
| 8-9 | Order block / breaker | blue/purple box with dotted mean threshold; recoloured "breaker" when closed through |
| 10-11 | Premium/discount, OTE | shaded halves, EQ line and OTE band (redrawn on the last bar) |
| 12 | IPDA 20/40/60 | lines at the right edge (completed daily bars) |
| 13 | Quarterly shift | "shift up/down" label |
| 14 | MSS | line from the swing to the closing bar, "MSS ↑/↓" |
| 15 | Setup engine | ① sweep ② MSS ③ FVG ④ entry ⑤ stop ⑥ target, +1R line, result and grade |
| 16 | Dashboard | bias, ranges, nearest liquidity, counts, last MSS, last setup, running stats |

## Inputs ↔ `config.yaml`
| Pine input | config.yaml key | Default |
|---|---|---|
| Fractal bars left / right | `swings.fractal_left` / `fractal_right` | 1 / 1 |
| Strict | `swings.strict` | true |
| A level is broken by | `swings.break_on` | Wick |
| ATR length | `liquidity.atr_period` (simple mean of TR) | 14 |
| Equal tolerance % / × ATR | `liquidity.equal_tolerance_pct` / `equal_tolerance_atr` | 0.15 / 0.25 |
| Displacement × ATR | `pd_arrays.displacement_atr_mult` | 1.2 |
| FVG minimum × ATR | `pd_arrays.fvg_min_size_atr` (practice images: 0.3) | 0.3 |
| OB lookback | `pd_arrays.ob_lookback_bars` | 5 |
| OTE from / to / sweet | `premium_discount.ote_low` / `ote_high` / `ote_sweet` | 0.62 / 0.79 / 0.705 |
| IPDA 1/2/3 | `ipda.lookbacks` | 20/40/60 |
| Quarterly shift range | `ipda.quarterly_shift_range` | 60 |
| MSS × ATR | `confirmation.mss_displacement_atr_mult` | 1.0 |
| Limit order expiry | `entry.limit_expiry_bars` | 10 |
| Stop buffer × ATR | `entry.stop_buffer_atr` | 0.25 |
| Minimum stop × ATR | `entry.min_stop_atr` | 0.5 |
| Minimum R:R | `entry.min_rr` | 1.5 |
| Breakeven at +R | `management.breakeven_at_r` | 1.0 |
| Time stop (bars) | `management.time_stop_bars` × 4 (practice run) | 100 |

## Check it against the Python engine (CNX500, 15m, 06 Nov 2026)
Compare with `reports/CNX500/02_live_15m_all_concepts.png` and `00_summary.png`:

- [ ] open ITH **19,432** (06 Nov 09:15) and ITH 19,439 (02 Nov 12:30) above price
- [ ] ITL **19,343** (06 Nov 14:30), LTL **19,322** (06 Nov 13:00) and LTL 19,299 below price
- [ ] bear FVG 19,391–19,399 with CE **19,395**
- [ ] bull OB **19,330–19,351** (06 Nov 12:45)
- [ ] 04 Nov 10:30 bearish MSS → short setup: entry **19,410**, stop **19,428**, target **19,382**, result target, grade A
- [ ] dashboard bias = DOWN on the daily

For the pool lines to match the practice image exactly, set **Equal tolerance %** to 0. The image used only 0.25 × median ATR.

## Known differences from the Python run
- **Discount/premium grade check.** Pine uses only the intermediate swings that had been *confirmed* by the MSS bar. `analysis/practice.py` uses swing levels from the final table, which can include a promotion confirmed a little later. Pine is the stricter, no-lookahead version; the Python side will be aligned in Module 7.
- **Bias.** The dashboard bias uses a 3-bar fractal on the bias timeframe, the same rule as the daily swing table.
- **HTF data.** It uses the documented non-repainting form `request.security(..., expr[1], lookahead_on)`, which returns the last completed HTF bar.

Education only, not financial advice.
