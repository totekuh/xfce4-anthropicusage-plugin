from datetime import datetime, timedelta, timezone

from anthropic_usage.format import RED, TEAL, AMBER, empty_bars, extract, humanize_reset, pct_color


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
