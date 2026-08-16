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


def test_render_alert_writes_nonempty_png(cfg):
    path = render.render_alert(cfg, "⚠ Claude token expired — run: claude")
    assert path == cfg.png_path
    assert os.path.getsize(path) > 0
