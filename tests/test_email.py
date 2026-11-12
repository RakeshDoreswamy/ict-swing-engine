"""Daily email: subject format, scrutiny labels, message assembly (nothing is sent)."""
import numpy as np
import pandas as pd

from ict_engine.notify import daily_email, mailer
from ict_engine.scan.reasons import scrutinise

ROW = {"symbol": "TEST", "bucket": "waiting", "entry": 100.0, "stop": 95.0, "t1": 110.0, "t2": 120.0, "rr_t2": 4.0,
       "has_confluence": True, "confluence": [("FVG", 99.0, 101.0, 10)], "bias": "up", "sweep_type": "ITL",
       "sweep_level": 94.0, "mss_level": 104.0, "eq": 110.0, "last_close": 103.0, "zone": "daily bull FVG",
       "zone_atr": 0.4, "room_atr": 3.0, "rs_pct": 80.0, "tm_avg_R_filled": 0.3, "tm_fill_pct": 60.0,
       "tm_win_pct": 45.0, "base_rules": True, "qty_1pct": 1600, "ote_79": 98.0, "ote_62": 102.0}


def test_strong_when_everything_lines_up():
    s = scrutinise(dict(ROW), market_ok=True, cost_pct=0.32)
    assert s["conviction"] == "STRONG" and s["a_like"]
    assert any("A-like" in p for p in s["pros"]) and any("Time Machine" in p for p in s["pros"])


def test_weak_when_market_blocked_and_b_like_and_tm_negative():
    r = dict(ROW, has_confluence=False, bias="range", tm_avg_R_filled=-0.3, rr_t2=np.nan, base_rules=False)
    s = scrutinise(r, market_ok=False, cost_pct=0.32)
    assert s["conviction"] == "WEAK"
    joined = " ".join(s["cons"])
    for word in ("Market filter blocks", "B-like", "Wide-mode", "T2", "Time Machine"):
        assert word in joined


def test_tight_stop_cost_flag():
    s = scrutinise(dict(ROW, stop=99.8), market_ok=True, cost_pct=0.32)   # risk 0.2 on 100 → 1.6R of costs
    assert any("costs take" in c for c in s["cons"])


def test_subject_format():
    subj = daily_email.subject("2026-11-12", False, {"in_zone": 2, "waiting": 32, "leg_running": 15, "setting_up": 38},
                               {"STRONG": 1, "MODERATE": 4}, 107 * 60 + 5, "both")
    assert subj == ("NSE ICT Screener [WATCH-ONLY] 2026-11-12 — 2 IN ZONE + 32 WAITING + 15 LEG RUNNING + "
                    "38 SETTING UP | 1 STRONG · 4 MODERATE | 5-Stage ICT Framework (wide) | Scan 107m 05s")


def test_message_has_recipients_inline_images_and_attachments(tmp_path):
    png = tmp_path / "c.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    csv = tmp_path / "watchlist.csv"
    csv.write_text("symbol\nTEST\n")
    msg = mailer.build_message("S", '<img src="cid:chart_TEST">', "t", "me@gmail.com", ["a@x.com", "b@y.com"],
                               {"chart_TEST": png}, [csv])
    raw = bytes(msg).decode(errors="ignore")
    assert msg["To"] == "a@x.com, b@y.com" and "cid:chart_TEST" not in raw
    assert "watchlist.csv" in raw and "image/png" in raw


def test_env_loader(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nGMAIL_USER=me@gmail.com\nEMAIL_TO=a@x.com, b@y.com\n")
    env = mailer.load_env(p)
    assert env["GMAIL_USER"] == "me@gmail.com" and env["EMAIL_TO"] == "a@x.com, b@y.com"
