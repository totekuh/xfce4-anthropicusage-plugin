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


def test_render_alert_writes_nonempty_png(cfg):
    path = render.render_alert(cfg, "⚠ Claude token expired — run: claude")
    assert path == cfg.png_path
    assert os.path.getsize(path) > 0
