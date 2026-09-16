import time
from datetime import datetime, timedelta, timezone

from anthropic_usage.format import extract
from anthropic_usage.genmon import emit_genmon


def iso_in(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def test_pace_slow_shown_in_tooltip(cfg):
    data = {
        "five_hour": {"utilization": 50.0, "resets_at": iso_in(hours=2, minutes=30)},
        "seven_day": {"utilization": 10.0, "resets_at": iso_in(days=1)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "room to use more" in out


def test_pace_fast_shown_in_tooltip(cfg):
    data = {
        "five_hour": {"utilization": 80.0, "resets_at": iso_in(hours=4)},
        "seven_day": {"utilization": 90.0, "resets_at": iso_in(days=6)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "ease off" in out


def test_pace_ok_shown_in_tooltip(cfg):
    data = {
        "five_hour": {"utilization": 50.0, "resets_at": iso_in(hours=2, minutes=30)},
        "seven_day": {"utilization": 50.0, "resets_at": iso_in(days=3, hours=12)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "on track" in out


def test_pace_none_no_label_in_tooltip(cfg):
    data = {
        "five_hour": {"utilization": 1.0, "resets_at": iso_in(hours=4, minutes=50)},
        "seven_day": {"utilization": 0.0},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "room to use more" not in out
    assert "ease off" not in out
    assert "on track" not in out


def test_tooltip_structure_preserved(cfg):
    data = {
        "five_hour": {"utilization": 30.0, "resets_at": iso_in(hours=2)},
        "seven_day": {"utilization": 60.0, "resets_at": iso_in(days=2)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "<img>" in out
    assert "<tool>" in out
    assert "<b>5h</b>" in out
    assert "30%" in out
    assert "<b>Weekly</b>" in out
    assert "60%" in out


def test_fast_tooltip_shows_cap_warning(cfg):
    data = {
        "five_hour": {"utilization": 80.0, "resets_at": iso_in(hours=4)},
        "seven_day": {"utilization": 50.0, "resets_at": iso_in(days=3, hours=12)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "cap in" in out
    assert "idle" in out
    assert "target" in out


def test_slow_tooltip_shows_spare(cfg):
    data = {
        "five_hour": {"utilization": 10.0, "resets_at": iso_in(hours=1)},
        "seven_day": {"utilization": 10.0, "resets_at": iso_in(days=1)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "headroom" in out
    assert "can push to" in out


def test_ok_tooltip_shows_sustain_rate(cfg):
    data = {
        "five_hour": {"utilization": 50.0, "resets_at": iso_in(hours=2, minutes=30)},
        "seven_day": {"utilization": 50.0, "resets_at": iso_in(days=3, hours=12)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "sustain" in out
    assert "projected" in out


def test_no_details_when_too_early(cfg):
    data = {
        "five_hour": {"utilization": 1.0, "resets_at": iso_in(hours=4, minutes=50)},
        "seven_day": {"utilization": 1.0, "resets_at": iso_in(days=6, hours=20)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "projected" not in out
    assert "cap in" not in out


def test_auth_error_tooltip(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="auth", fetched_at=time.time())
    assert "Claude token expired" in out
    assert "last-known" in out


def test_no_token_error_tooltip(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="no-token", fetched_at=time.time())
    assert "No Claude login" in out


def test_stale_offline_tooltip(cfg):
    data = {
        "five_hour": {"utilization": 30.0, "resets_at": iso_in(hours=2)},
        "seven_day": {"utilization": 50.0, "resets_at": iso_in(days=3)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=True, err="offline", fetched_at=time.time())
    assert "cached data" in out
    assert "network unreachable" in out
    assert "last good fetch" in out


def test_stale_rate_limited_tooltip(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="http-429", fetched_at=time.time())
    assert "rate limited" in out


def test_stale_backoff_tooltip(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="backoff", fetched_at=time.time())
    assert "waiting to retry" in out


def test_stale_forbidden_tooltip(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="forbidden", fetched_at=time.time())
    assert "403" in out


def test_stale_unknown_error_tooltip(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="http-500", fetched_at=time.time())
    assert "http-500" in out


def test_stale_no_fetched_at(cfg):
    from anthropic_usage.format import empty_bars
    bars = empty_bars(cfg)
    out = emit_genmon(cfg, bars, stale=True, err="offline", fetched_at=0)
    assert "last good fetch" not in out


def test_fresh_with_timestamp(cfg):
    data = {
        "five_hour": {"utilization": 30.0, "resets_at": iso_in(hours=2)},
        "seven_day": {"utilization": 50.0, "resets_at": iso_in(days=3)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    assert "updated" in out


def test_blank_line_between_bars(cfg):
    data = {
        "five_hour": {"utilization": 30.0, "resets_at": iso_in(hours=2)},
        "seven_day": {"utilization": 50.0, "resets_at": iso_in(days=3)},
    }
    bars = extract(cfg, data)
    out = emit_genmon(cfg, bars, stale=False, err=None, fetched_at=time.time())
    tool = out.split("<tool>")[1].split("</tool>")[0]
    sections = tool.split("\n\n")
    assert len(sections) >= 3  # header, 5h block, weekly block (+updated)
