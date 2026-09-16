import os

import pytest

cairo = pytest.importorskip("cairo")
pytest.importorskip("gi")

from anthropic_usage import format, render  # noqa: E402


def test_render_writes_nonempty_png(cfg):
    bars = format.extract(cfg, {"five_hour": {"utilization": 12}, "seven_day": {"utilization": 90}})
    path = render.render(cfg, bars)
    assert path == cfg.png_path
    assert os.path.getsize(path) > 0


def test_stale_render_keeps_the_text_readable(cfg):
    """Stale dims the fill, not the text: white pixels must survive."""
    bars = format.extract(cfg, {"five_hour": {"utilization": 82}, "seven_day": {"utilization": 46}})
    path = render.render(cfg, bars, stale=True)

    surface = cairo.ImageSurface.create_from_png(path)
    data = surface.get_data()
    stride = surface.get_stride()
    white = 0
    for y in range(surface.get_height()):
        row = data[y * stride:(y + 1) * stride]
        for x in range(surface.get_width()):
            b, g, r, a = row[x * 4:x * 4 + 4]
            if a > 200 and min(r, g, b) > 230:
                white += 1
    assert white > 20, "no white text pixels — stale text is blending into the fill again"


def test_render_with_note(cfg):
    bars = format.extract(cfg, {"five_hour": {"utilization": 0}, "seven_day": {"utilization": 0}})
    path = render.render(cfg, bars, note="n/a")
    assert path == cfg.png_path
    assert os.path.getsize(path) > 0


def test_render_stale_marker(cfg):
    bars = format.extract(cfg, {"five_hour": {"utilization": 50}, "seven_day": {"utilization": 50}})
    path = render.render(cfg, bars, stale=True)
    assert os.path.getsize(path) > 0


def test_render_with_pace_dot(cfg):
    from datetime import datetime, timedelta, timezone
    iso_fast = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    data = {"five_hour": {"utilization": 80, "resets_at": iso_fast},
            "seven_day": {"utilization": 50, "resets_at": (datetime.now(timezone.utc) + timedelta(days=3, hours=12)).isoformat()}}
    bars = format.extract(cfg, data)
    assert bars[0]["pace"] == "fast"
    path = render.render(cfg, bars)
    assert os.path.getsize(path) > 0


def test_render_no_pace_dot_when_stale(cfg):
    from datetime import datetime, timedelta, timezone
    iso = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=30)).isoformat()
    data = {"five_hour": {"utilization": 50, "resets_at": iso},
            "seven_day": {"utilization": 50, "resets_at": (datetime.now(timezone.utc) + timedelta(days=3, hours=12)).isoformat()}}
    bars = format.extract(cfg, data)
    path = render.render(cfg, bars, stale=True)
    assert os.path.getsize(path) > 0


def test_render_narrow_widget(cfg):
    """Very narrow width forces bar_w < 20, triggering the skip-label path."""
    from anthropic_usage.config import Config
    narrow = Config(
        cred_path=cfg.cred_path, usage_url=cfg.usage_url,
        cache_dir=cfg.cache_dir, width=60, height=cfg.height,
        labels=cfg.labels,
    )
    bars = format.extract(narrow, {"five_hour": {"utilization": 50}, "seven_day": {"utilization": 50}})
    path = render.render(narrow, bars)
    assert os.path.getsize(path) > 0


def test_render_alert_writes_nonempty_png(cfg):
    path = render.render_alert(cfg, "⚠ Claude token expired — run: claude")
    assert path == cfg.png_path
    assert os.path.getsize(path) > 0
