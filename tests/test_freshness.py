"""Unattended runs: skip holidays, fail loudly when today's stock bars are missing."""
from ict_engine.data.freshness import status


def test_ok_when_panel_reaches_today():
    assert status("2026-11-12", "2026-11-12", "2026-11-12")[0] == "ok"


def test_closed_on_weekend_or_holiday():
    state, msg = status("2026-11-13", "2026-11-13", "2026-11-14")   # Saturday
    assert state == "closed" and "did not trade" in msg


def test_stale_when_bhavcopy_missing():
    state, msg = status("2026-11-11", "2026-11-12", "2026-11-12")
    assert state == "stale" and "11 Nov" in msg


def test_stale_without_index_or_panel():
    assert status(None, None, "2026-11-12")[0] == "stale"
    assert status(None, "2026-11-12", "2026-11-12")[0] == "stale"
