# ICT swing-trading concepts: the study guide

Each concept below has five parts:

* **Idea**: what ICT means by it, in plain words.
* **Exact rule**: how this engine defines it in code, so there is no "eyeballing".
* **Why it matters**: its job in a trade.
* **See it**: the command that shows it on a real NIFTY chart.
* **Exercise**: what to do by hand before trusting the code.

The concepts are in the order you should learn them. Each one builds on the ones before it.

> Status: concepts marked ✅ are coded and have a `learn` command. The others are explained here and
> get their command when their module is built.

---

## Part A: Where is the liquidity? (Weeks 1 to 2)

### 1. Swing points: STH / STL ✅ (Module 1)

**Idea.** A swing high is a peak, and a swing low is a trough. ICT's view is that stop-loss orders
collect just beyond them: buyers put stops below swing lows, and short sellers put stops above swing highs.

**Exact rule.** A **short-term high (STH)** is a bar whose high is strictly above the high of the bar
before it and the bar after it (a 3-bar pattern). A **short-term low (STL)** is the mirror image, with
the low strictly below both neighbours.

**The confirmation trap.** You do not know bar *i* is a swing high until bar *i+1* has **closed** lower.
On the day it forms, it is only a candidate. The engine stores `confirm_date` for this reason, and a
backtest that ignores it is cheating.

**Why it matters.** Swing points are the raw material for everything else: liquidity pools, market
structure shifts, dealing ranges and stop placement.

**See it.** `python -m scripts.learn swings`

**Exercise.** On the last 30 NIFTY daily bars, mark every STH and STL by hand, then compare your marks
with `reports/learn_swings.csv`.

### 2. Institutional swing levels: ITH / LTH / ITL / LTL ✅ (Module 1)

**Idea.** Not all swings matter equally. A short-term swing is minor noise. A swing that stands out
against its *neighbouring swings* is where bigger players act.

**Exact rule.**
* **ITH**: an STH whose previous STH and next STH are both lower.
* **LTH**: an ITH whose previous ITH and next ITH are both lower.
* Lows mirror this (ITL, LTL).

So the same 3-bar rule is applied again, to the list of swings instead of the list of bars.

**The confirmation trap, larger.** An ITH is only confirmed when the *next STH* is confirmed, and an
LTH only when the next ITH is confirmed. That can take weeks. The higher the level, the later you know.

**Why it matters.** Intermediate swings define your dealing range (concept 9) and are the stops and
targets used on a swing trade. Long-term swings mark the major turning points.

**See it.** `python -m scripts.learn swings` shows the promotion from STH to ITH to LTH, step by step.

**Exercise.** From your 30-bar STH list, circle each STH that is higher than both of its neighbouring
STHs. Those are your ITHs.

### 3. Open float ✅ (Module 1 `unbroken` column, used in Module 2)

**Idea.** An old high or low that price has **never traded back through** still has orders resting
beyond it. Those are "open". Once price trades through a level, those orders are filled and the level is spent.

**Exact rule.** A swing high is *broken* on the first later bar whose high (or close, if `break_on: close`)
goes above it. Every swing not yet broken is open float.

**Why it matters.** Open highs above price are **buy-side liquidity** and open lows below are
**sell-side liquidity**. ICT teaches that price is drawn towards them.

**See it.** The dotted lines on `reports/NIFTY_daily_swings.png` are the unbroken ITH/LTH and ITL/LTL levels.

**Exercise.** On the NIFTY weekly chart, list 5 open highs and 5 open lows with their prices.

### 4. Liquidity pools (Module 2)

**Idea.** Liquidity clusters where many traders put stops at the same place:
* **Equal highs / equal lows**: two or more swings at almost the same price. They look like strong
  resistance or support to retail traders, so stops pile up beyond them.
* Clusters of open swing points.
* **The previous week's and previous month's high/low**: levels everyone watches.

**Exact rule (planned).** Highs count as "equal" when they are within `equal_tolerance_pct` (0.15%) or
`equal_tolerance_atr` × ATR of each other. Pools are ranked by distance from price, swing level and
number of touches.

**Why it matters.** The nearest strong pool is the **draw on liquidity**: the likely target, and so the place for your take-profit.

**Exercise.** For 3 large caps, mark one pool above price and one below. Write down which one you think
price will reach first, and why.

### 5. Liquidity sweep / stop hunt (Module 2)

**Idea.** Price pokes beyond a pool, triggers the stops, then reverses. The wick takes the liquidity,
and the close rejects the level.

**Exact rule (planned).** A bar's wick trades beyond the pool, **and the same bar closes back inside it**.

**Why it matters.** A sweep followed by a market structure shift (concept 11) is the core ICT reversal signal.

**Exercise.** Find 3 NIFTY daily bars that wicked below an old swing low and closed back above it.
Note what happened over the next 10 bars.

---

## Part B: Where will price react? (Week 2)

### 6. Displacement (Module 3)

**Idea.** A strong, fast candle in one direction, which ICT reads as an institution committing to a move.

**Exact rule (planned).** A candle whose body is more than `displacement_atr_mult` (1.2) × ATR(14).

### 7. Fair value gap (FVG) and inverse FVG (Module 3)

**Idea.** In a 3-candle sequence, a gap between candle 1's high and candle 3's low (bullish) that
candle 2 moved through so fast that no trading happened on both sides. Price often comes back to "fill" it.

**Exact rule (planned).** A bullish FVG exists when `low[i+1] > high[i-1]`. The zone runs from `high[i-1]` to `low[i+1]`.
**Consequent encroachment (CE)** is the 50% midpoint. Fill % is tracked bar by bar. A gap that price
closes fully through becomes an **inverse FVG**, which then acts from the opposite side.

### 8. Order block and breaker block (Module 3)

**Idea.** An **order block** is the last opposite-colour candle before a displacement, which ICT reads as where
the institution loaded its position. A bullish OB is the last down-close candle before a strong move up.
A **breaker** is an order block that *failed*: price ran through it after taking out a swing, and it now
acts as support or resistance from the other side.

**Exact rule (planned).** The OB zone runs from the candle's low to its high. The **mean threshold** is its 50% level.

### 9. Premium, discount and equilibrium (Module 4)

**Idea.** Take the current dealing range, from the most recent ITL to the ITH. The top half is **premium**
(expensive) and the bottom half is **discount** (cheap). The 50% line is **equilibrium**.
**Rule: buy only in discount, sell only in premium.**

### 10. OTE: optimal trade entry (Module 4)

**Idea.** After a move, the best-value pullback zone is the 62% to 79% retracement of the leg, with 70.5% as the sweet spot.
It sits deep in discount (for longs), which keeps the stop tight and the reward-to-risk ratio high.

### 11. HTF PD arrays (Module 3)

**Idea.** "Premium/discount arrays" is ICT's name for all the zones price reacts to: order blocks, FVGs,
breakers, old highs and lows, and the previous week's or month's high/low. On **weekly and daily** charts
these are your trade locations. Each zone is labelled with its timeframe, bounds, freshness, whether it
was respected before, and a one-line reason it matters.

---

## Part C: When to pull the trigger (Weeks 2 to 3)

### 12. Market structure shift (MSS) (Module 7)

**Idea.** After a sweep, price **closes** beyond the last opposite short-term swing with displacement. The
short-term trend has flipped.

**Exact rule (planned).** A daily **close** (not just a wick) above the last STH, for a long, with a body larger than
`mss_displacement_atr_mult` × ATR.

### 13. Setup progression: bias → zone → sweep → MSS → entry (Modules 6 and 7)

1. **Bias** (weekly): up, down or range, written as one sentence.
2. **Location**: price is at a weekly HTF zone, in discount for longs.
3. **Liquidity**: a pool has just been swept, or there is a clear target.
4. **Confirmation**: a daily MSS by close.
5. **Entry zone**: the FVG, order block, breaker or OTE left behind by the MSS move.

### 14. Entry models: limit vs stop (Module 8)

* **Limit**: a resting order inside the zone (at the FVG's CE, the OB's mean threshold, or OTE 70.5%), which
  expires after N bars. Better price, but you can miss the move.
* **Stop**: a buy-stop above the swing high that confirmed the MSS. You always get in on a real move,
  but at a worse price and with a wider stop.
* The engine runs both and reports their results side by side.

---

## Part D: Survive and manage (Weeks 3 to 4)

### 15. Money management (Module 9)
Risk 1% of capital per trade. Quantity = risk amount ÷ (entry − stop), with the stop distance padded
×1.25 to allow for gaps at the open. Cut risk to 0.5% after 3 losses in a row or an 8% drawdown. Cap open trades and sector exposure.

### 16. Position trade management (Module 10)
Move the stop to breakeven at +1R. Trail it under each new intermediate swing low. Take 50% off at the first
internal pool, and let the rest run to the main target. Exit on a close back through the MSS swing, or after 25 bars with no progress.

### 17. Event and liquidity filters (Module 11)
Do not enter if earnings, an RBI policy date, the Union Budget or index rebalancing falls inside the expected holding
period. Trade only instruments with enough turnover, and flag stocks that gap a lot overnight.

---

## Part E: Slow context (after the core)

### 18. IPDA data ranges (Module 5)
ICT's "Interbank Price Delivery Algorithm" idea: the highs and lows of the last **20, 40 and 60 trading days** act as reference liquidity.

### 19. Quarterly shifts (Module 5)
Roughly every 3 to 4 months, price breaks its 60-day range and the dominant direction changes. The engine uses this as a slow bias filter.

### 20. Seasonal tendencies (Module 13)
ICT's seasonal patterns come from forex and US data. The engine **tests** NIFTY's monthly returns over 10+ years
(hit rate and t-stat), and only lets seasonality influence bias if the test passes.

### 21. Intermarket and yields (Module 6, optional)
For India: GIFT Nifty, India VIX, USD/INR, the US dollar index (DXY), crude oil, FII/DII flows, and the India and US 10-year
yields. These are background only, switched on or off in config, and logged.

---

## Part F: Prove it (Modules 12 to 14)

### 22. Pre-trade checklist and grading
Twelve yes/no checks. Grade A means every check is a yes, and only grade A setups are traded. Skipped setups are logged with the reasons.

### 23. R-multiples and expectancy
R = profit or loss ÷ initial risk. A trade stopped out is −1R. Expectancy = average R per trade. Fewer than
30 trades is not enough evidence to judge.

### 24. Backtest honesty
* **No lookahead**: swings exist only after confirmation, and an MSS is known only at the close.
* **Gaps**: the fill is the open price if price gaps past your stop.
* **Indian costs**: STT, stamp duty, exchange fees, GST and slippage.
* **Ablation**: switch each ICT component off to see whether it actually adds edge.

---

## How to study with this repo

1. Read one concept above.
2. Do its **Exercise** by hand on TradingView.
3. Run its `learn` command and compare the engine's answer with yours.
4. Where they differ, decide whether you or the rule is wrong. If it's the rule, change `config.yaml` and rerun.
5. Run `pytest -q` to make sure the change didn't break anything.

> Education only, not financial advice. ICT concepts are not independently proven. Your journal is the evidence.
