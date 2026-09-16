from datetime import datetime, timedelta, timezone

from anthropic_usage.format import (
    RED, TEAL, AMBER, PACE_FAST, PACE_OK, PACE_SLOW,
    burn_pace, empty_bars, extract, humanize_reset, pace_color, pace_details, pct_color,
)


def iso_in(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def test_humanize_reset_empty():
    assert humanize_reset(None) == ""
    assert humanize_reset("") == ""


def test_humanize_reset_garbage():
    assert humanize_reset("not-a-date") == ""


def test_humanize_reset_past_is_now():
    assert humanize_reset(iso_in(seconds=-5)) == "now"


def test_humanize_reset_minutes():
    # +1s buffer: humanize_reset() calls now() a hair after iso_in() does,
    # so an exact boundary would flakily round down.
    assert humanize_reset(iso_in(minutes=7, seconds=1)) == "7m"


def test_humanize_reset_minutes_floor_at_one():
    assert humanize_reset(iso_in(seconds=10)) == "1m"


def test_humanize_reset_hours_and_minutes():
    assert humanize_reset(iso_in(hours=4, minutes=31, seconds=1)) == "4h31m"


def test_humanize_reset_exact_hours_no_minutes():
    assert humanize_reset(iso_in(hours=2, seconds=1)) == "2h"


def test_humanize_reset_days_and_hours():
    assert humanize_reset(iso_in(days=1, hours=5, seconds=1)) == "1d5h"


def test_humanize_reset_exact_days():
    assert humanize_reset(iso_in(days=2, seconds=1)) == "2d"


def test_extract_pulls_both_windows(cfg):
    data = {
        "five_hour": {"utilization": 12.5, "resets_at": iso_in(hours=1)},
        "seven_day": {"utilization": 88.0, "resets_at": iso_in(days=3)},
    }
    bars = extract(cfg, data)
    assert bars[0]["label"] == "5h"
    assert bars[0]["pct"] == 12.5
    assert bars[1]["label"] == "Weekly"
    assert bars[1]["pct"] == 88.0


def test_extract_missing_sections_default_to_zero(cfg):
    bars = extract(cfg, {})
    assert [b["pct"] for b in bars] == [0.0, 0.0]
    assert [b["reset"] for b in bars] == ["", ""]


def test_extract_none_data(cfg):
    bars = extract(cfg, None)
    assert [b["pct"] for b in bars] == [0.0, 0.0]


def test_empty_bars_uses_configured_labels(cfg):
    bars = empty_bars(cfg)
    assert [b["label"] for b in bars] == ["5h", "Weekly"]
    assert [b["pct"] for b in bars] == [0, 0]


def test_pct_color_thresholds():
    assert pct_color(0, stale=False) == TEAL
    assert pct_color(74.9, stale=False) == TEAL
    assert pct_color(75, stale=False) == AMBER
    assert pct_color(89.9, stale=False) == AMBER
    assert pct_color(90, stale=False) == RED
    assert pct_color(100, stale=False) == RED


def test_pct_color_stale_overrides_everything():
    from anthropic_usage.format import STALE
    assert pct_color(99, stale=True) == STALE


# --- burn pace ---

def test_burn_pace_on_track():
    # 50% used, 2.5h remaining of 5h window = 50% elapsed → on track
    reset = iso_in(hours=2, minutes=30)
    assert burn_pace(50.0, reset, 5 * 3600) == "ok"


def test_burn_pace_too_fast():
    # 80% used, 4h remaining of 5h = only 20% elapsed → way ahead
    reset = iso_in(hours=4)
    assert burn_pace(80.0, reset, 5 * 3600) == "fast"


def test_burn_pace_slow():
    # 10% used, 1h remaining of 5h = 80% elapsed → lots of headroom
    reset = iso_in(hours=1)
    assert burn_pace(10.0, reset, 5 * 3600) == "slow"


def test_burn_pace_too_early():
    # only 2% of window elapsed — not enough data
    reset = iso_in(hours=4, minutes=54)
    assert burn_pace(1.0, reset, 5 * 3600) is None


def test_burn_pace_no_reset():
    assert burn_pace(50.0, None, 5 * 3600) is None
    assert burn_pace(50.0, "", 5 * 3600) is None


def test_pace_color_values():
    assert pace_color("fast") == PACE_FAST
    assert pace_color("ok") == PACE_OK
    assert pace_color("slow") == PACE_SLOW
    assert pace_color(None) is None


def test_extract_includes_pace(cfg):
    data = {
        "five_hour": {"utilization": 50.0, "resets_at": iso_in(hours=2, minutes=30)},
        "seven_day": {"utilization": 10.0, "resets_at": iso_in(days=1)},
    }
    bars = extract(cfg, data)
    assert bars[0]["pace"] == "ok"
    assert bars[1]["pace"] == "slow"


def test_empty_bars_pace_is_none(cfg):
    bars = empty_bars(cfg)
    assert all(b["pace"] is None for b in bars)
    assert all(b["pace_details"] is None for b in bars)


def test_burn_pace_zero_usage_midwindow():
    reset = iso_in(hours=2, minutes=30)
    assert burn_pace(0.0, reset, 5 * 3600) == "slow"


def test_burn_pace_100_pct_early():
    reset = iso_in(hours=4)
    assert burn_pace(100.0, reset, 5 * 3600) == "fast"


def test_burn_pace_past_reset():
    # reset already passed — remaining clamped to 0, elapsed = full window
    reset = iso_in(seconds=-60)
    # 50% used but window done: 50/100 = 0.5 < 0.85 → slow
    assert burn_pace(50.0, reset, 5 * 3600) == "slow"
    # 100% used, window done: 100/100 = 1.0 → ok
    assert burn_pace(100.0, reset, 5 * 3600) == "ok"


def test_burn_pace_clearly_above_fast_threshold():
    # elapsed ~50%, pct 60 → ratio ~1.2 → clearly fast
    reset = iso_in(hours=2, minutes=30)
    assert burn_pace(60.0, reset, 5 * 3600) == "fast"


def test_burn_pace_clearly_below_slow_threshold():
    # elapsed ~50%, pct 35 → ratio ~0.7 → clearly slow
    reset = iso_in(hours=2, minutes=30)
    assert burn_pace(35.0, reset, 5 * 3600) == "slow"


def test_burn_pace_in_ok_band():
    # elapsed ~50%, pct 48 → ratio ~0.96 → ok
    reset = iso_in(hours=2, minutes=30)
    assert burn_pace(48.0, reset, 5 * 3600) == "ok"


def test_burn_pace_weekly_window():
    # 3.5 days remaining of 7 = 50% elapsed, 50% used → ok
    reset = iso_in(days=3, hours=12)
    assert burn_pace(50.0, reset, 7 * 86400) == "ok"
    # 1 day remaining = ~86% elapsed, 30% used → very slow
    reset = iso_in(days=1)
    assert burn_pace(30.0, reset, 7 * 86400) == "slow"


def test_burn_pace_garbage_reset_iso():
    assert burn_pace(50.0, "not-a-date", 5 * 3600) is None
    assert burn_pace(50.0, "2026-13-45T99:99:99", 5 * 3600) is None


def test_burn_pace_zero_window():
    reset = iso_in(hours=1)
    assert burn_pace(50.0, reset, 0) is None
    assert burn_pace(50.0, reset, -1) is None


def test_burn_pace_reset_far_future():
    # remaining > window_secs → elapsed negative → frac < 0.05 → None
    reset = iso_in(hours=10)
    assert burn_pace(50.0, reset, 5 * 3600) is None


def test_burn_pace_just_past_threshold():
    # 5% of 5h = 15min. At 14min elapsed → None, at 16min → has value
    reset_early = iso_in(hours=4, minutes=46)  # ~14min elapsed
    assert burn_pace(5.0, reset_early, 5 * 3600) is None
    reset_past = iso_in(hours=4, minutes=44)   # ~16min elapsed
    assert burn_pace(5.0, reset_past, 5 * 3600) is not None


# --- pace details ---

def test_pace_details_none_cases():
    assert pace_details(50.0, None, 5 * 3600) is None
    assert pace_details(50.0, "", 5 * 3600) is None
    assert pace_details(50.0, "garbage", 5 * 3600) is None
    assert pace_details(50.0, iso_in(hours=1), 0) is None
    # too early in window
    assert pace_details(1.0, iso_in(hours=4, minutes=50), 5 * 3600) is None


def test_pace_details_fast_has_cap_fields():
    # 80% used, 4h remaining of 5h = only 20% elapsed
    # burn rate = 80/3600 %/s, projected = 80 * 18000/3600 = 400%
    reset = iso_in(hours=4)
    pd = pace_details(80.0, reset, 5 * 3600)
    assert pd is not None
    assert pd["projected"] > 100
    assert "cap_in" in pd
    assert "dead_time" in pd
    assert pd["target_rate"] > 0
    assert pd["rate_unit"] == "h"


def test_pace_details_slow_has_spare():
    # 10% used, 1h remaining of 5h = 80% elapsed
    # projected = 10 * 5/4 = 12.5%
    reset = iso_in(hours=1)
    pd = pace_details(10.0, reset, 5 * 3600)
    assert pd is not None
    assert pd["projected"] < 95
    assert "spare" in pd
    assert pd["spare"] > 80
    assert pd["target_rate"] > pd["current_rate"]
    assert pd["rate_unit"] == "h"


def test_pace_details_ok_no_cap_or_spare():
    # 50% used, 2.5h remaining of 5h = 50% elapsed → projected ~100%
    reset = iso_in(hours=2, minutes=30)
    pd = pace_details(50.0, reset, 5 * 3600)
    assert pd is not None
    assert 95 <= pd["projected"] <= 105
    assert "cap_in" not in pd
    assert "spare" not in pd
    assert "target_rate" in pd


def test_pace_details_weekly_uses_day_rate():
    reset = iso_in(days=3, hours=12)
    pd = pace_details(50.0, reset, 7 * 86400)
    assert pd is not None
    assert pd["rate_unit"] == "d"


def test_pace_details_already_at_cap():
    # 100% used, 2h remaining — already capped
    reset = iso_in(hours=2)
    pd = pace_details(100.0, reset, 5 * 3600)
    assert pd is not None
    assert pd["projected"] > 100


def test_extract_includes_pace_details(cfg):
    data = {
        "five_hour": {"utilization": 80.0, "resets_at": iso_in(hours=4)},
        "seven_day": {"utilization": 10.0, "resets_at": iso_in(days=1)},
    }
    bars = extract(cfg, data)
    assert bars[0]["pace_details"] is not None
    assert bars[1]["pace_details"] is not None
    assert bars[0]["pace_details"]["rate_unit"] == "h"
    assert bars[1]["pace_details"]["rate_unit"] == "d"


def test_pace_details_remaining_zero():
    reset = iso_in(seconds=-30)
    pd = pace_details(80.0, reset, 5 * 3600)
    assert pd is not None
    assert pd["projected"] > 0
    assert "target_rate" not in pd  # remaining=0 so no target


def test_pace_details_projected_near_100():
    # projected between 95 and 105 → no cap_in, no spare
    reset = iso_in(hours=2, minutes=30)
    pd = pace_details(50.0, reset, 5 * 3600)
    assert pd is not None
    assert "cap_in" not in pd
    assert "spare" not in pd


def test_burn_pace_naive_datetime():
    # ISO string without timezone → should still work (treated as UTC)
    naive = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2, minutes=30)
    iso = naive.isoformat()
    result = burn_pace(50.0, iso, 5 * 3600)
    assert result == "ok"


def test_pace_details_naive_datetime():
    naive = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2, minutes=30)
    iso = naive.isoformat()
    pd = pace_details(50.0, iso, 5 * 3600)
    assert pd is not None
    assert 95 <= pd["projected"] <= 105


def test_humanize_reset_naive_datetime():
    naive = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2, minutes=30)
    iso = naive.isoformat()
    result = humanize_reset(iso)
    assert "2h" in result
