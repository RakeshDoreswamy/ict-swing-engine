"""Text for every concept page. Each entry: slug, part, title, short, status, lede, body sections.

Body sections are HTML snippets; '{fig:name}' placeholders are replaced by figures.
"""

PARTS = [
    ("A", "Where is the liquidity?", "Swing points, open float, pools and sweeps: the map of where orders rest."),
    ("B", "Where will price react?", "Displacement, FVGs, order blocks, breakers, premium/discount, OTE and HTF zones."),
    ("C", "When to pull the trigger", "Market structure shift, the setup sequence and the two entry models."),
    ("D", "Survive and manage", "Position sizing, trade management and the filters that keep you out of trouble."),
    ("E", "Slow context", "IPDA ranges, quarterly shifts, seasonality and intermarket checks."),
    ("F", "Prove it", "Grading, R-multiples and an honest backtest."),
]


def rule(text):
    return f'<div class="card rule"><b>Exact rule in the engine</b><pre>{text}</pre></div>'


def mistakes(items):
    return '<div class="card warn"><b>Common mistakes</b><ul>' + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>"


def exercise(text):
    return f'<div class="card tip"><b>Exercise</b><p>{text}</p></div>'


def steps(items):
    return '<ol class="steps">' + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


CONCEPTS = [
    # ------------------------------------------------------------------ PART A
    dict(slug="swing-points", part="A", title="Swing points (STH / STL)", status="ok", module="M1",
         short="The 3-bar highs and lows every other concept is built on.",
         lede="A swing high is a peak, a swing low is a trough. ICT's whole model starts here, because stop-loss orders cluster just beyond them.",
         body=[
             "<h2>The idea</h2><p>Every trader who is long puts a stop below the most recent low. Every short seller puts a stop above the most recent high. "
             "So the market's turning points are also its <b>order clusters</b>. ICT calls those clusters liquidity. Before you can find liquidity, you need an exact, "
             "repeatable definition of a turning point.</p>",
             "{fig:swings_schematic}",
             rule("STH at bar i:  high[i] > high[i-1]  AND  high[i] > high[i+1]\n"
                  "STL at bar i:  low[i]  < low[i-1]   AND  low[i]  < low[i+1]\n"
                  "Confirmed at:  close of bar i+1   (config: fractal_left / fractal_right / strict)"),
             "<h2>How to spot it</h2>" + steps([
                 "Look at three candles side by side.",
                 "If the middle one has the highest high, it is a short-term high. If it has the lowest low, it is a short-term low. One candle can be both.",
                 "Do not mark it until the third candle has <b>closed</b>. Until then the middle bar is only a candidate; the next bar could still make a higher high.",
             ]),
             "{fig:swings_real}",
             "<h2>Why it matters in a trade</h2><ul><li><b>Stops</b> go beyond a swing point.</li><li><b>Targets</b> are the next swing on the other side.</li>"
             "<li><b>Structure</b>: higher highs and higher lows mean up, lower highs and lower lows mean down, and a break of the last swing is a market structure shift.</li></ul>",
             mistakes(["Marking a swing on the day it forms. That is lookahead: in real time you do not know yet.",
                       "Using 5-bar or 'eyeballed' swings and then wondering why your backtest disagrees with your chart.",
                       "Treating every short-term swing as important. Most are noise; the next page shows how to rank them."]),
             exercise("Open NIFTY 15-minute on TradingView. Mark every STH and STL by hand on the last 60 bars, then run "
                      "<code>python -m scripts.learn swings --bars 60</code> and compare. Every difference teaches you something about the rule."),
         ]),
    dict(slug="institutional-swings", part="A", title="Institutional swings (ITH / LTH)", status="ok", module="M1",
         short="Ranking swings: short-term, intermediate-term and long-term.",
         lede="Not all swings are equal. A swing that stands out against its neighbouring swings is where larger players act.",
         body=[
             "<h2>The idea</h2><p>ICT's 'Defining Institutional Swing Points' lesson ranks swings in three tiers. The trick is that the <b>same 3-point test</b> is applied "
             "again, but to the list of swings instead of the list of bars.</p>",
             "{fig:levels_schematic}",
             rule("ITH: an STH whose previous STH and next STH are both LOWER\n"
                  "LTH: an ITH whose previous ITH and next ITH are both LOWER\n"
                  "ITL / LTL mirror this on lows.\n"
                  "ITH confirmed when the NEXT STH is confirmed; LTH when the next ITH is confirmed."),
             "<h2>How to spot it</h2>" + steps([
                 "List the short-term highs in order: e.g. 103, 105, 104, 108, 106.",
                 "A value higher than both neighbours in that list is an ITH: here 105 and 108.",
                 "Now list the ITHs (105, 108, …) and repeat: a value higher than both neighbouring ITHs is an LTH.",
             ]),
             "{fig:levels_real}",
             "<h2>The delay is the lesson</h2><p>An ITH needs the next STH to exist, which can take days. An LTH can take weeks. "
             "The higher the tier, the more reliable, and the later you know. A strategy that uses LTHs 'as they form' is using information it did not have. "
             "The engine stores a separate confirmation date for each tier and the <code>swings_as_of()</code> view only shows what was known then.</p>",
             "<h2>How a swing trader uses each tier</h2><table><tr><th>Tier</th><th>Use</th></tr>"
             "<tr><td>STH / STL</td><td>Entry timing: the MSS trigger, tight stops.</td></tr>"
             "<tr><td>ITH / ITL</td><td>The dealing range, stops and first targets for a daily swing trade.</td></tr>"
             "<tr><td>LTH / LTL</td><td>Major turning points, weekly bias, final targets.</td></tr></table>",
             mistakes(["Calling every big-looking peak an ITH. If it is not higher than the STH on both sides, it is not.",
                       "Forgetting that a swing can be promoted later: today's STH may be next week's ITH."]),
             exercise("On NIFTY daily, take your STH list from the previous page and circle the ITHs. Then run "
                      "<code>python -m scripts.learn swings --bars 120</code> and read STEP 2, which shows each promotion and the date it became known."),
         ]),
    dict(slug="open-float", part="A", title="Open float", status="ok", module="M1",
         short="Old highs and lows price has not traded back through yet.",
         lede="A swing level that has never been revisited still has orders resting beyond it. Once price trades through, those orders are filled and the level is spent.",
         body=[
             "<h2>The idea</h2><p>Think of every unbroken swing as an unpaid bill. Stops above an old high are buy orders waiting to be triggered. "
             "Price 'pays the bill' by trading through it. ICT's Open Float lessons focus on the levels <b>still unpaid</b>, because those are where the market is likely to go next.</p>",
             "{fig:open_float_schematic}",
             rule("A swing high is BROKEN on the first later bar whose high > swing price\n"
                  "(or whose close > swing price, if config break_on: close).\n"
                  "Open float = all swings not yet broken.\n"
                  "Open highs above price = BUY-SIDE liquidity. Open lows below = SELL-SIDE liquidity."),
             "{fig:open_float_real}",
             "<h2>Why it matters</h2><ul><li>The nearest strong open level above and below price frames the <b>draw on liquidity</b>: where price is likely heading.</li>"
             "<li>An open level is a natural <b>target</b>. A spent level is not.</li>"
             "<li>Higher-tier open levels (ITH/LTH) carry more orders than short-term ones.</li></ul>",
             mistakes(["Using a level that was already taken as a target.", "Ignoring old weekly levels far away. They stay open for months and act like magnets."]),
             exercise("On NIFTY weekly, list 5 open highs above price and 5 open lows below. Check them against the dotted lines in "
                      "<code>reports/NIFTY_weekly_swings.png</code> after running <code>python -m scripts.run_swings NIFTY</code>."),
         ]),
    dict(slug="liquidity-pools", part="A", title="Liquidity pools", status="plan", module="M2",
         short="Equal highs/lows, clusters and previous week/month levels.",
         lede="Liquidity collects where many traders put stops at the same place. Those clusters are the market's targets.",
         body=[
             "<h2>The idea</h2><p>Retail traders are taught that a double top is 'strong resistance'. So they short under it and put their stops just above it, "
             "while breakout traders put buy-stops there too. The result is a dense pool of buy orders a few points above the equal highs. ICT teaches that price is "
             "<b>engineered</b> towards such pools.</p>",
             "{fig:pools_schematic}",
             "<h2>Types of pool</h2><table><tr><th>Pool</th><th>Where the stops are</th></tr>"
             "<tr><td>Equal highs / relative equal highs</td><td>Just above them (buy-side)</td></tr>"
             "<tr><td>Equal lows</td><td>Just below them (sell-side)</td></tr>"
             "<tr><td>Cluster of open swing points</td><td>Beyond the outermost one</td></tr>"
             "<tr><td>Previous day / week / month high and low</td><td>Beyond each; watched by everyone</td></tr>"
             "<tr><td>Old ITH / LTH (open float)</td><td>Beyond it; larger than short-term ones</td></tr></table>",
             rule("Equal: two or more swing prices within max(equal_tolerance_pct × price, equal_tolerance_atr × ATR)\n"
                  "Rank score = 0.4 × closeness + 0.35 × swing tier + 0.25 × touches   (config: liquidity.rank_weights)\n"
                  "Draw on liquidity = highest-ranked pool in the direction of bias"),
             "{fig:pools_real}",
             "<h2>How to use it</h2>" + steps(["Mark the pools above and below price.", "Ask: which one is price more likely to reach first, given the weekly bias?",
                                               "That pool is your <b>target</b>. The pool on the other side is where a sweep could set up a reversal."]),
             mistakes(["Placing your own stop exactly at the obvious equal low. You become the liquidity.", "Treating 'equal' too strictly: relative equal highs a few points apart work the same way."]),
             exercise("For RELIANCE, HDFCBANK and INFY, mark one pool above and one below today's price. Write down which you expect first and why, then check in two weeks."),
         ]),
    dict(slug="liquidity-sweep", part="A", title="Liquidity sweep (stop hunt)", status="plan", module="M2",
         short="A wick through a pool that closes back inside.",
         lede="Price pokes beyond a pool, triggers the stops, then reverses. The wick takes the liquidity; the close rejects the level.",
         body=[
             "<h2>The idea</h2><p>Large players need the other side to fill big orders. To buy a lot, they need many sellers, and the stops under a low are exactly that: "
             "sell orders. Running price through the low fills the big buy order against those stops. Once filled, there is nothing left to push price lower, so it "
             "snaps back. That is the sweep.</p>",
             "{fig:sweep_schematic}",
             rule("Sell-side sweep at bar j: low[j] < open swing low  AND  close[j] > that swing low\n"
                  "Buy-side sweep at bar j:  high[j] > open swing high AND close[j] < that swing high\n"
                  "Only swings confirmed before bar j count."),
             "{fig:sweep_real}",
             "<h2>Sweep vs breakout</h2><table><tr><th></th><th>Sweep</th><th>Breakout</th></tr>"
             "<tr><td>Close</td><td>Back inside the level</td><td>Beyond the level</td></tr>"
             "<tr><td>Next bars</td><td>Move away, often fast</td><td>Hold beyond, retest</td></tr>"
             "<tr><td>Meaning</td><td>Liquidity taken, reversal likely</td><td>Level genuinely broken</td></tr></table>",
             "<p>A sweep alone is not a trade. It becomes one when it is followed by a <a href='market-structure-shift.html'>market structure shift</a>.</p>",
             mistakes(["Buying the moment price wicks below a low, before the close. Many 'sweeps' become breakdowns.",
                       "Ignoring which level was swept: an LTL sweep matters more than a minor STL."]),
             exercise("Find 3 NIFTY daily bars that wicked below an old swing low and closed back above it. Record what happened over the next 10 bars."),
         ]),
    # ------------------------------------------------------------------ PART B
    dict(slug="displacement", part="B", title="Displacement", status="plan", module="M3",
         short="A strong, fast candle: an institution committing.",
         lede="Displacement is a large-bodied candle that moves price decisively. It creates FVGs, defines order blocks and confirms structure shifts.",
         body=[
             "<h2>The idea</h2><p>Normal candles overlap and drift. When a large player commits, price moves so fast that one candle covers ground several normal candles would. "
             "ICT reads that energy as intent. Without displacement, an FVG is weak, an order block is just a candle, and a structure break is just noise.</p>",
             "{fig:displacement_schematic}",
             rule("Displacement candle: |close − open| > displacement_atr_mult × ATR(14) of the PRIOR bars\n"
                  "Default multiplier: 1.2 for zones (pd_arrays), 1.0 for MSS (confirmation)"),
             "{fig:displacement_real}",
             "<h2>What displacement tells you</h2><ul><li>Direction: the side institutions are pushing.</li><li>The candle before it is the <a href='order-block.html'>order block</a>.</li>"
             "<li>The gap it leaves is the <a href='fair-value-gap.html'>FVG</a>.</li><li>When it closes through a swing, it is an <a href='market-structure-shift.html'>MSS</a>.</li></ul>",
             mistakes(["Calling a big candle on a high-volatility day displacement. Measure against ATR, not your eye.", "Chasing the displacement candle itself. Wait for the pullback into what it left behind."]),
             exercise("On NIFTY 15m, find the 5 largest-bodied candles of the last week. For each, mark the candle before it (order block) and any gap it left (FVG)."),
         ]),
    dict(slug="fair-value-gap", part="B", title="Fair value gap (FVG) and inverse FVG", status="plan", module="M3",
         short="The 3-candle imbalance price tends to revisit.",
         lede="When candle 2 moves so fast that candles 1 and 3 do not overlap, the empty space is a fair value gap: one-sided trading that price often comes back to rebalance.",
         body=[
             "<h2>The idea</h2><p>In the gap, only buyers (bullish FVG) or only sellers (bearish FVG) were active. ICT teaches that the market's algorithm returns to "
             "'offer fair value' on the other side. In practice, an FVG is a high-probability <b>entry zone</b> on a pullback.</p>",
             "{fig:fvg_schematic}",
             rule("Bullish FVG (middle bar i): low[i+1] > high[i-1]   zone = [high[i-1], low[i+1]]\n"
                  "Bearish FVG (middle bar i): high[i+1] < low[i-1]   zone = [high[i+1], low[i-1]]\n"
                  "CE (consequent encroachment) = 50% of the zone\n"
                  "Filled: a later bar trades through the far edge\n"
                  "Inverse FVG: a later bar CLOSES through the far edge; the zone now works from the other side\n"
                  "Minimum size: fvg_min_size_atr × ATR"),
             "{fig:fvg_real}",
             "<h2>How to trade it</h2>" + steps([
                 "Only use FVGs created by <b>displacement</b> in the direction of your bias.",
                 "Prefer an FVG inside <a href='premium-discount.html'>discount</a> (for longs) and near an HTF zone.",
                 "Place a limit at the CE (50%). The stop goes beyond the swing that started the move, not just beyond the gap.",
                 "If price closes through the whole gap, it has failed. Treat it as an inverse FVG, and stop looking for longs there.",
             ]),
             mistakes(["Trading every FVG. Most small ones on 15m are noise; filter by size and context.", "Putting the stop just under the FVG. It gets taken by normal pullbacks."]),
             exercise("On NIFTY daily, mark the last 5 FVGs. For each, record: was it filled, did the CE hold, and did it become an inverse FVG?"),
         ]),
    dict(slug="order-block", part="B", title="Order block", status="plan", module="M3",
         short="The last opposite candle before displacement.",
         lede="A bullish order block is the last down-close candle before a strong move up: in ICT's reading, where the big buy programme was loaded.",
         body=[
             "<h2>The idea</h2><p>Institutions cannot fill a large order in one candle. The last down candle before the explosion is where they absorbed sellers. "
             "If price returns there, ICT argues they defend it, adding to positions near their average price. The 50% level of the candle, the <b>mean threshold</b>, "
             "should not be closed through.</p>",
             "{fig:ob_schematic}",
             rule("Bullish OB: the last down-close candle within ob_lookback_bars before a bullish displacement candle\n"
                  "Bearish OB: the last up-close candle before a bearish displacement candle\n"
                  "Zone = that candle's [low, high]; mean threshold = 50%\n"
                  "Invalid (becomes a breaker) when a later bar CLOSES beyond the far side"),
             "{fig:ob_real}",
             "<h2>Quality checklist</h2><ul><li>Did the move away <b>displace</b> and leave an FVG?</li><li>Did it break a swing (structure)?</li>"
             "<li>Is it in discount (bull OB) or premium (bear OB)?</li><li>Is it fresh, i.e. not yet revisited?</li></ul>",
             mistakes(["Picking any down candle. It must be followed by displacement.", "Ignoring the mean threshold: a close below the OB's 50% is a warning."]),
             exercise("For 3 large caps, find the bullish OB under the most recent rally on the daily chart. Did price return to it? Did the mean threshold hold?"),
         ]),
    dict(slug="breaker-block", part="B", title="Breaker block", status="plan", module="M3",
         short="A failed order block that flips sides.",
         lede="When an order block fails after a liquidity sweep, the same zone tends to act from the other side: old support becomes resistance.",
         body=[
             "<h2>The idea</h2><p>A breaker tells a story in three acts. First, a high is swept (liquidity taken). Then price displaces down, through the bullish order block "
             "that launched the last leg up. Those trapped longs now want out at breakeven, so when price comes back up into the zone, their selling plus the new shorts "
             "make it resistance.</p>",
             "{fig:breaker_schematic}",
             rule("Bearish breaker: a bullish OB where a later bar CLOSES below its low (ideally after a buy-side sweep)\n"
                  "Bullish breaker: a bearish OB where a later bar CLOSES above its high (ideally after a sell-side sweep)\n"
                  "Entry: retest of the zone from the new side"),
             "{fig:breaker_real}",
             mistakes(["Calling any broken OB a breaker. The strongest ones follow a sweep and a displacement through the zone.", "Entering on the break itself instead of the retest."]),
             exercise("On NIFTY daily, find one bullish OB that later failed. Did price retest it from below, and did it hold as resistance?"),
         ]),
    dict(slug="premium-discount", part="B", title="Premium, discount and equilibrium", status="plan", module="M4",
         short="Buy below half price, sell above it.",
         lede="Split the current dealing range in half. The top half is premium (expensive), the bottom half is discount (cheap). The middle is equilibrium.",
         body=[
             "<h2>The idea</h2><p>Institutions are price-sensitive buyers. ICT's rule is simple: in an uptrend, buy only in discount; in a downtrend, sell only in premium. "
             "This one filter removes most bad entries: chasing breakouts at the top of a range.</p>",
             "{fig:pd_schematic}",
             rule("Dealing range = most recent confirmed intermediate swing low → intermediate swing high\n"
                  "Equilibrium (EQ) = 50%\n"
                  "Long entries only below EQ; short entries only above EQ"),
             "{fig:pd_real}",
             "<h2>Picking the right range</h2><ul><li>For a daily swing trade, use the daily ITL–ITH, or the weekly range for context.</li>"
             "<li>When a new intermediate swing confirms, the range is redrawn.</li><li>Nested ranges: a discount inside a weekly discount is the best location.</li></ul>",
             mistakes(["Drawing the range from a tiny short-term swing, so 'discount' flips every few bars.", "Buying in discount when the weekly bias is down. Discount in a downtrend is not cheap; it is falling."]),
             exercise("For NIFTY daily, draw the current dealing range and write whether price is in premium or discount. Repeat on weekly. Do they agree?"),
         ]),
    dict(slug="ote", part="B", title="OTE: optimal trade entry", status="plan", module="M4",
         short="The 62 to 79% retracement sweet spot.",
         lede="After an impulse leg, the best-value pullback is the 62 to 79% retracement, with 70.5% as the sweet spot. It is deep in discount, near the stop and far from the target.",
         body=[
             "<h2>The idea</h2><p>OTE combines premium/discount with Fibonacci. A pullback that only reaches 30% is too shallow (bad R:R); one beyond 79% is at risk of "
             "becoming a full reversal. The 62 to 79% band balances fill probability and reward.</p>",
             "{fig:ote_schematic}",
             rule("For an up leg (low → high): OTE = high − [0.62, 0.79] × (high − low); sweet spot 0.705\n"
                  "For a down leg: low + [0.62, 0.79] × (high − low)\n"
                  "Config: premium_discount.ote_low / ote_high / ote_sweet"),
             "{fig:ote_real}",
             "<h2>R:R arithmetic</h2><p>Leg 100 → 200. Buy at 70.5% = 129.5, stop below 100 at 98: risk 31.5. Target the leg's high, 200: reward 70.5. R:R ≈ 2.2. "
             "Buying the same leg at 50% (150) would give risk 52 and reward 50: under 1.</p>",
             mistakes(["Drawing the fib on a leg that did not displace.", "Using OTE without a reason the level should hold (FVG/OB inside the band)."]),
             exercise("On 3 historical NIFTY swing moves, draw the fib on the impulse leg and mark whether price reached OTE before continuing."),
         ]),
    dict(slug="htf-pd-arrays", part="B", title="HTF PD arrays", status="plan", module="M3",
         short="The full map of weekly/daily zones price reacts to.",
         lede="'Premium/discount arrays' is ICT's umbrella term for every zone price reacts to. On weekly and daily charts they are your trade locations.",
         body=[
             "<h2>The idea</h2><p>Instead of hunting for setups everywhere, a swing trader builds a map once a week: all the higher-timeframe zones above and below price. "
             "Then they wait for price to reach one of them. Everything else is noise.</p>",
             "{fig:pd_arrays_real}",
             "<h2>The arrays, ranked roughly by ICT's order</h2><table><tr><th>Array</th><th>Page</th></tr>"
             "<tr><td>Old high / old low (open float)</td><td><a href='open-float.html'>Open float</a></td></tr>"
             "<tr><td>Rejection block / wick</td><td>(wick zones beyond swings)</td></tr>"
             "<tr><td>Order block</td><td><a href='order-block.html'>Order block</a></td></tr>"
             "<tr><td>Fair value gap</td><td><a href='fair-value-gap.html'>FVG</a></td></tr>"
             "<tr><td>Breaker</td><td><a href='breaker-block.html'>Breaker</a></td></tr>"
             "<tr><td>Previous week / month high & low</td><td><a href='liquidity-pools.html'>Pools</a></td></tr></table>",
             rule("Every zone stores: timeframe, top, bottom, created date, respected_before (bool),\n"
                  "age in bars (dropped after zone_max_age_bars), and a one-line 'reason it matters'"),
             mistakes(["Drawing so many zones that price is always 'at a zone'. Keep only fresh, displacement-created ones.", "Mixing 15m zones into a weekly map."]),
             exercise("Every Sunday, mark 3 weekly zones above and 3 below NIFTY, with a one-line reason each. That is your plan for the week."),
         ]),
    # ------------------------------------------------------------------ PART C
    dict(slug="market-structure-shift", part="C", title="Market structure shift (MSS)", status="plan", module="M7",
         short="A displacement close through the last opposite swing.",
         lede="After a sweep, price closes beyond the last opposite short-term swing with displacement. The short-term trend has flipped, and this is the trigger.",
         body=[
             "<h2>The idea</h2><p>A downtrend is a series of lower highs. The moment price <b>closes</b> above the most recent lower high, with force, the sequence is broken. "
             "Combined with a sweep of sell-side liquidity just before, it is ICT's core reversal confirmation.</p>",
             "{fig:mss_schematic}",
             rule("Bullish MSS at bar j:\n"
                  "  close[j] > most recent confirmed STH\n"
                  "  AND body[j] > mss_displacement_atr_mult × ATR\n"
                  "  AND the prior swing lows were falling (it is a shift, not a continuation)\n"
                  "A wick above the STH does NOT count. Known only at the close of bar j."),
             "{fig:mss_real}",
             "<h2>MSS vs BOS</h2><p>A <b>break of structure (BOS)</b> is a close beyond a swing <i>in the direction of the trend</i>: continuation. "
             "A <b>market structure shift</b> is the first break <i>against</i> the trend: potential reversal. The engine requires the prior trend leg to be the other way.</p>",
             mistakes(["Accepting a wick as an MSS.", "Taking an MSS that did not follow a sweep or happen at an HTF zone. Without location it is just noise."]),
             exercise("On NIFTY daily, find the last 3 bullish MSS. For each, was there a sell-side sweep in the 10 bars before it?"),
         ]),
    dict(slug="setup-progression", part="C", title="Setup progression", status="plan", module="M6–M7",
         short="Bias → location → liquidity → MSS → entry.",
         lede="ICT's 'Trade Conditions and Setup Progressions': the order in which conditions must line up. Each step narrows the trade down.",
         body=[
             "{fig:progression_flow}",
             "<h2>The five steps</h2>" + steps([
                 "<b>Bias (weekly).</b> Up, down or range, written as one sentence. E.g. 'Weekly is in discount after sweeping the April low, drawing to the open ITH at 24,774.'",
                 "<b>Location.</b> Price is at a weekly/daily PD array, in discount for longs (premium for shorts).",
                 "<b>Liquidity.</b> A pool has just been swept, or there is a clear untouched pool as the target.",
                 "<b>Confirmation.</b> A daily (or lower-TF for timing) MSS by close.",
                 "<b>Entry.</b> The FVG / OB / OTE left by the MSS move, with a stop beyond the sweep and a target at the next pool.",
             ]),
             "{fig:mss_real_composite}",
             "<p>The chart above is the whole progression on real 15-minute data, found automatically by the engine. Steps 1 and 2 come from the daily/weekly charts.</p>",
             mistakes(["Starting at step 5 (seeing an FVG) and working backwards to justify it.", "Skipping the written bias. If you cannot write it in one sentence, you do not have one."]),
             exercise("Take one past NIFTY swing move and write the five steps for it in your journal, with dates and prices."),
         ]),
    dict(slug="entry-models", part="C", title="Entry models: limit vs stop", status="plan", module="M8",
         short="Resting order in the zone, or a buy-stop above the trigger.",
         lede="Two ways into the same setup. ICT's long-term trader lessons cover both; the engine runs them side by side so you can see which works better for you.",
         body=[
             "{fig:entries_schematic}",
             "<table><tr><th></th><th>Limit entry</th><th>Stop entry</th></tr>"
             "<tr><td>Order</td><td>Buy limit at FVG CE / OB mean / OTE 70.5%</td><td>Buy-stop above the swing high that confirmed the MSS</td></tr>"
             "<tr><td>Price</td><td>Better</td><td>Worse</td></tr>"
             "<tr><td>Fill</td><td>May be missed if price never pulls back</td><td>Fills on every real move</td></tr>"
             "<tr><td>R:R</td><td>Higher</td><td>Lower</td></tr>"
             "<tr><td>Best when</td><td>Strong HTF zone, patient</td><td>Strong momentum, no pullback</td></tr></table>",
             rule("Limit: expires after limit_expiry_bars if not filled\n"
                  "Stop-loss: beyond the sweep extreme or the zone, + stop_buffer_atr × ATR\n"
                  "Target: next opposing liquidity pool\n"
                  "Reject if (target − entry) / (entry − stop) < min_rr (1.5)"),
             mistakes(["Moving a limit order to 'chase' after price leaves without you.", "Placing the stop at the exact sweep low, where the next sweep will take it."]),
             exercise("For 3 historical setups, write both entries with stop, target and R:R. Which model would have filled? Which made more R?"),
         ]),
    # ------------------------------------------------------------------ PART D
    dict(slug="money-management", part="D", title="Money management", status="plan", module="M9",
         short="1% risk, position size and drawdown control.",
         lede="Risk a fixed small fraction of capital per trade. It is the only part of trading you fully control, and it decides whether you survive a losing streak.",
         body=[
             "<h2>Position size calculator</h2><div class='card'><div class='calc'>"
             "<div><label>Capital (Rs)</label><input id='cap' type='number' value='1000000'></div>"
             "<div><label>Risk %</label><input id='rp' type='number' value='1' step='0.25'></div>"
             "<div><label>Entry</label><input id='en' type='number' value='2450'></div>"
             "<div><label>Stop</label><input id='st' type='number' value='2390'></div>"
             "<div><label>Gap pad factor</label><input id='gp' type='number' value='1.25' step='0.05'></div>"
             "</div><div class='out' id='out'></div></div>"
             "<script>(function(){const $=id=>document.getElementById(id);function f(){const c=+$('cap').value,r=+$('rp').value,e=+$('en').value,s=+$('st').value,g=+$('gp').value;"
             "const risk=c*r/100,d=Math.abs(e-s)*g;const q=d>0?Math.floor(risk/d):0;$('out').innerHTML=`Risk amount <b>Rs ${risk.toLocaleString('en-IN')}</b> · padded stop distance <b>${d.toFixed(2)}</b> · "
             "quantity <b>${q.toLocaleString('en-IN')}</b> shares · position value <b>Rs ${(q*e).toLocaleString('en-IN')}</b> (${(q*e/c*100).toFixed(1)}% of capital)`;}"
             "['cap','rp','en','st','gp'].forEach(k=>$(k).addEventListener('input',f));f();})();</script>",
             rule("qty = floor( capital × risk% / (|entry − stop| × gap_slippage_factor) )\n"
                  "risk% = 1.0, cut to 0.5 after 3 consecutive losses or an 8% drawdown\n"
                  "Caps: max_open_trades 5, max_per_sector 2, max correlation 0.8"),
             "{fig:drawdown_chart}",
             mistakes(["Sizing by 'how confident I feel'.", "Forgetting gaps: Indian stocks gap through stops on results and news; the pad factor accounts for this.",
                       "Three bank stocks at 1% each is 3% on one idea. Sector caps exist for this."]),
             exercise("Use the calculator for your 3 setups from the entry-models exercise, on a Rs 10,00,000 account. Time yourself: aim for under 2 minutes per trade."),
         ]),
    dict(slug="trade-management", part="D", title="Position trade management", status="plan", module="M10",
         short="Breakeven, trailing, partials and time stops.",
         lede="Once in, the job is to protect capital first and let the winner pay. Every rule is written in advance so you do not improvise mid-trade.",
         body=[
             "{fig:management_schematic}",
             rule("Stop to breakeven at +breakeven_at_r (1R), or when a new daily swing forms in your favour\n"
                  "Trail the stop under each new intermediate swing low (above each high for shorts)\n"
                  "Take partial_exit_pct (50%) at the first internal pool; runner to the main target\n"
                  "Exit on a daily close back through the MSS swing (invalidation)\n"
                  "Time stop: exit after time_stop_bars (25) with no progress"),
             "<h2>Why each rule exists</h2><table><tr><th>Rule</th><th>Protects against</th></tr>"
             "<tr><td>Breakeven at 1R</td><td>A winner turning into a full loser</td></tr><tr><td>Trailing under swings</td><td>Giving back a large open profit</td></tr>"
             "<tr><td>Partial at first pool</td><td>Regret and emotional exits; it banks R</td></tr><tr><td>Invalidation close</td><td>Hoping a broken setup recovers</td></tr>"
             "<tr><td>Time stop</td><td>Capital stuck in a trade that is not working</td></tr></table>",
             mistakes(["Moving the stop to breakeven too early (before 1R), so normal pullbacks stop you out.", "Widening the stop. Never."]),
             exercise("Replay one historical NIFTY swing trade bar by bar on TradingView (Replay mode). Write your stop decision at every new swing."),
         ]),
    dict(slug="event-filters", part="D", title="Event and liquidity filters", status="plan", module="M11",
         short="Earnings, RBI, Budget, turnover and gap risk.",
         lede="Scheduled events can move price past your stop before you can react. The engine refuses entries when one falls inside the expected holding period.",
         body=[
             "{fig:gaps_real}",
             "<h2>Filters</h2><table><tr><th>Filter</th><th>Rule</th></tr>"
             "<tr><td>Earnings</td><td>No entry if the company reports within the expected holding period</td></tr>"
             "<tr><td>RBI policy</td><td>No new index/bank entries in the days around an MPC decision</td></tr>"
             "<tr><td>Union Budget</td><td>No entries across Budget day</td></tr>"
             "<tr><td>Index rebalancing</td><td>Avoid affected stocks around NSE rebalance dates</td></tr>"
             "<tr><td>Turnover</td><td>20-day average daily turnover ≥ min_avg_turnover_cr</td></tr>"
             "<tr><td>Gap risk</td><td>Flag stocks whose average overnight gap &gt; gap_risk_avg_gap_pct</td></tr></table>",
             rule("Events come from data/events/events.csv: date, type, symbol (or ALL)\n"
                  "Holding period estimate = time_stop_bars"),
             mistakes(["Assuming the stop protects you on a result day.", "Forgetting that event dates change; update the calendar CSV monthly from NSE/RBI announcements."]),
             exercise("Look up the next RBI MPC date and the next results dates for your 10 stocks. Put them in events.csv."),
         ]),
    # ------------------------------------------------------------------ PART E
    dict(slug="ipda-ranges", part="E", title="IPDA data ranges", status="plan", module="M5",
         short="20, 40 and 60-day highs and lows as reference liquidity.",
         lede="ICT's Interbank Price Delivery Algorithm idea: price refers back to the highs and lows of the last 20, 40 and 60 trading days.",
         body=[
             "{fig:ipda_real}",
             "<h2>How to read it</h2><ul><li>The 20-day range is short-term context: where is price inside the last month?</li>"
             "<li>The 40 and 60-day highs/lows are the next liquidity targets beyond the short-term range.</li>"
             "<li>When price is in the lower part of the 60-day range with a bullish weekly bias, the 60-day high is a reasonable draw.</li></ul>",
             rule("For N in [20, 40, 60]: high/low of the N bars BEFORE today (today excluded, no lookahead)"),
             mistakes(["Treating the 60-day high as a precise reversal level. It is a target, not a wall."]),
             exercise("Each Monday, write NIFTY's 20/40/60-day high and low and note which ones price reached by Friday."),
         ]),
    dict(slug="quarterly-shifts", part="E", title="Quarterly shifts", status="plan", module="M5",
         short="Direction changes roughly every 3 to 4 months.",
         lede="ICT observes that markets tend to change their dominant direction roughly every quarter. The engine detects it as a close through the prior 60-day range in the opposite direction.",
         body=[
             "{fig:quarterly_real}",
             rule("Shift up at bar i: close[i] > max(high of prior 60 bars) AND the last shift was down\n"
                  "Shift down mirrors it. Used only as a slow bias layer."),
             "<p>This is the slowest filter in the engine. It does not time entries; it tells you which side of the market to favour for the next few months.</p>",
             mistakes(["Expecting shifts on a calendar schedule. 'Quarterly' is approximate."]),
             exercise("Mark the shifts on NIFTY weekly over the last 5 years. How regular are they?"),
         ]),
    dict(slug="seasonal-tendencies", part="E", title="Seasonal tendencies", status="plan", module="M13",
         short="Test, do not trust: NIFTY's monthly patterns.",
         lede="ICT's seasonal lessons use forex and US data. For India, the engine tests NIFTY's own monthly returns and only uses them if the evidence is strong.",
         body=[
             "{fig:seasonal_real}",
             rule("For each calendar month: mean return, hit rate, t-stat over 10+ years\n"
                  "Seasonal filter allowed only if |t-stat| ≥ bias.seasonality_min_tstat (2.0)"),
             "<p>The two years of data included here are far too few. Add a long NIFTY history CSV in <code>data/raw/</code> and the study becomes meaningful.</p>",
             mistakes(["Applying US seasonal patterns to NIFTY.", "Believing a pattern based on 5 data points."]),
             exercise("Get 15+ years of NIFTY monthly closes. Which months have a t-stat above 2? Probably none, and that is a useful finding."),
         ]),
    dict(slug="intermarket", part="E", title="Intermarket and yields", status="plan", module="M6",
         short="GIFT Nifty, VIX, USD/INR, DXY, crude, FII/DII and yields.",
         lede="Background context only. These never trigger a trade; they can make you more cautious or confirm a bias.",
         body=[
             "<table><tr><th>Input</th><th>What it tells you</th><th>Typical read for NIFTY longs</th></tr>"
             "<tr><td>GIFT Nifty</td><td>Overnight sentiment before NSE opens</td><td>Big gap expected: be careful with tight stops</td></tr>"
             "<tr><td>India VIX</td><td>Expected volatility</td><td>Spiking VIX: smaller size</td></tr>"
             "<tr><td>USD/INR</td><td>Rupee pressure, FII appetite</td><td>Sharp rupee weakness is often a headwind</td></tr>"
             "<tr><td>US dollar index (DXY)</td><td>Global risk appetite</td><td>Rising DXY often pressures emerging markets</td></tr>"
             "<tr><td>Brent crude</td><td>India imports most of its oil</td><td>Sharp crude rally: inflation and fiscal worry</td></tr>"
             "<tr><td>FII / DII net flows</td><td>Who is buying</td><td>Persistent FII selling with DII absorption: choppy</td></tr>"
             "<tr><td>India 10Y / US 10Y yields</td><td>Cost of money</td><td>Rising yields: pressure on valuations</td></tr></table>",
             rule("Each input is a toggle in config (bias.use_intermarket, bias.use_yields), off by default.\n"
                  "When on, the reading is logged with every signal so the backtest can test whether it helped."),
             mistakes(["Turning background into a signal. These are filters, not triggers.", "Over-fitting: if you add 7 filters, you will always find a reason not to trade, or to trade."]),
             exercise("For one month, write the 7 readings each Monday next to NIFTY's weekly move. Do any line up?"),
         ]),
    # ------------------------------------------------------------------ PART F
    dict(slug="checklist-grading", part="F", title="Pre-trade checklist and grading", status="plan", module="M12",
         short="Twelve yes/no lines. Only grade A gets traded.",
         lede="The checklist turns the setup progression into booleans. Every no is a reason to skip, and skipped setups are logged too.",
         body=[
             "<h2>Try it</h2><div class='card' id='ck'></div>"
             "<script>(function(){const items=['Weekly price at or reacting to a marked HTF zone','A liquidity pool just swept, or a clear target','Bias written in one sentence',"
             "'Daily MSS by close (not a wick)','Entry zone exists: FVG / OB / breaker / OTE','Entry in discount (long) or premium (short)','Stop level known, beyond sweep or zone',"
             "'Target = next pool, R:R at least 1.5','Position size risks 1% or less','No earnings / RBI / Budget in holding period','Liquid instrument, delivery or ETF','Invalidation written down'];"
             "const el=document.getElementById('ck');el.innerHTML=items.map((t,i)=>`<label style='display:block;padding:3px 0'><input type=checkbox data-i=${i}> ${t}</label>`).join('')+\"<div class='out' id='gr'></div>\";"
             "function g(){const n=el.querySelectorAll('input:checked').length;const miss=[...el.querySelectorAll('input:not(:checked)')].map(x=>items[x.dataset.i]);"
             "const grade=n===12?'A: trade it':n>=10?'B: skip and log':'C: skip and log';document.getElementById('gr').innerHTML=`<b>${n}/12 → Grade ${grade}</b>`+(miss.length?`<br><small>Missing: ${miss.join('; ')}</small>`:'');}"
             "el.addEventListener('change',g);g();})();</script>",
             rule("grade = A if all 12 are true; B if 10–11; C otherwise\n"
                  "Only A is traded. B and C are written to the journal as 'skipped' with the missing lines."),
             "<p>Logging skipped setups matters: after 3 months you can check whether your B-grade skips would have worked. If they would have, a rule is too strict.</p>",
             mistakes(["Ticking a box because you want the trade.", "Not logging skips, so you can never test the checklist itself."]),
             exercise("Run this checklist on every setup you see this week, including the ones you do not take."),
         ]),
    dict(slug="r-multiples", part="F", title="R-multiples and expectancy", status="plan", module="M14",
         short="Measure every trade in units of risk.",
         lede="R is your initial risk. A trade that hits its stop is −1R; a trade that makes twice the risk is +2R. Measuring in R makes every trade comparable.",
         body=[
             "<h2>Expectancy calculator</h2><div class='card'><div class='calc'>"
             "<div><label>Win rate %</label><input id='wr' type='number' value='40'></div>"
             "<div><label>Average win (R)</label><input id='aw' type='number' value='2.2' step='0.1'></div>"
             "<div><label>Average loss (R)</label><input id='al' type='number' value='1' step='0.1'></div>"
             "<div><label>Trades per year</label><input id='tp' type='number' value='40'></div>"
             "<div><label>Risk per trade %</label><input id='rk' type='number' value='1' step='0.25'></div></div><div class='out' id='eo'></div></div>"
             "<script>(function(){const $=id=>document.getElementById(id);function f(){const w=+$('wr').value/100,a=+$('aw').value,l=+$('al').value,t=+$('tp').value,r=+$('rk').value;"
             "const e=w*a-(1-w)*l;$('eo').innerHTML=`Expectancy <b>${e>=0?'+':''}${e.toFixed(2)}R</b> per trade · about <b>${(e*t).toFixed(1)}R</b> a year · roughly <b>${(e*t*r).toFixed(1)}%</b> a year before costs`+(e<=0?' · <b>no edge: do not trade it</b>':'');}"
             "['wr','aw','al','tp','rk'].forEach(k=>$(k).addEventListener('input',f));f();})();</script>",
             rule("R = (exit − entry) / (entry − initial stop)   (sign flipped for shorts)\n"
                  "Expectancy = win% × avg win R − loss% × avg loss R\n"
                  "Graduation gate: ≥ 30 trades AND average R > 0, then start live at 25% size"),
             "<h2>Why 30 trades?</h2><p>With 10 trades, a 40% win-rate strategy can easily show 20% or 70% by luck. Thirty is the minimum to say anything; 100 is better. "
             "That is why the plan is 3 months of paper trading before real money.</p>",
             mistakes(["Measuring in rupees, which hides that you took bigger risk on some trades.", "Judging a strategy after 5 trades."]),
             exercise("Convert your last 10 trades (paper or real) to R. What is your expectancy?"),
         ]),
    dict(slug="backtest-honesty", part="F", title="Backtest honesty", status="plan", module="M13",
         short="No lookahead, real gaps, Indian costs, ablation.",
         lede="A backtest is only useful if it could not have known the future. Most ICT backtests online fail this test.",
         body=[
             "{fig:lookahead_schematic}",
             "<h2>The four rules</h2>" + steps([
                 "<b>No lookahead.</b> Swings exist only after confirmation; MSS only at the close. The engine has a test that recomputes on every data prefix and fails if anything changes.",
                 "<b>Gaps.</b> If price opens beyond your stop, you are filled at the open, not at your stop.",
                 "<b>Indian costs.</b> STT 0.1% each side on delivery, stamp duty on buys, exchange fees, SEBI fee, GST on charges, and slippage.",
                 "<b>Ablation.</b> Run with each ICT component off in turn. If removing 'order blocks' does not hurt results, order blocks are not adding edge.",
             ]),
             rule("tests/test_swings.py::test_no_lookahead_* : prefix-recompute equality on synthetic and NIFTY data\n"
                  "costs: block in config.yaml\n"
                  "Ablation: one run per toggle, reported side by side"),
             mistakes(["Backtesting on charts where you can see what happened next.", "Ignoring costs: at 20 round trips a year, STT alone is about 4% of position value."]),
             exercise("Run pytest -q and read tests/test_swings.py. Then break the rule on purpose (set fractal_right to 0) and watch the lookahead test fail."),
         ]),
]
