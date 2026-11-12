"""NSE-wide ICT scanner: market → universe → daily ICT → 45m OTE → ranked charts.

Usage:
    python -m scripts.scan                       # scan as of the latest daily bar in the store
    python -m scripts.scan --date 2026-11-12     # replay an earlier day (no lookahead)
    python -m scripts.scan --no-fetch            # use cached 15m bars only
    python -m scripts.scan --timemachine         # add Time Machine odds (2,000 replays) to each finalist
    python -m scripts.scan --strict              # stop at stage 0 when the market blocks longs
Outputs: reports/scans/<date>/index.html, scan.csv, funnel.csv, charts/, tradingview_watchlist.txt
"""
from __future__ import annotations

import argparse
import os

from ict_engine.config import load_config
from ict_engine.scan.runner import run_scan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--strict", action="store_true", help="stop at stage 0 when the market blocks longs")
    ap.add_argument("--top", type=int)
    ap.add_argument("--timemachine", action="store_true", help="add Time Machine odds to every finalist")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    cfg = load_config()
    if a.top:
        cfg["scan"]["stage4"]["top_n"] = a.top
    res = run_scan(cfg, a.date, fetch_intraday=not a.no_fetch, force="strict" if a.strict else False, workers=a.workers, timemachine=a.timemachine)
    print("\n" + " → ".join(f"{n} {t}" for t, n in res["steps"]))
    if len(res["final"]):
        print(res["final"][["symbol", "grade", "score", "state", "entry", "stop", "t1", "t2", "rr_t2"]]
              .round(2).to_string(index=False))
    print(f"\nOpen: {res['out'] / 'index.html'}")


if __name__ == "__main__":
    main()
