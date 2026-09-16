"""Rendering the widget PNG with cairo + PangoCairo (imported lazily: these are
apt packages, not pip dependencies of this package — see pyproject.toml)."""

import math
import os
from typing import List, Optional

from .config import Config
from .format import RED, pace_color, pct_color

BG = (0.0, 0.0, 0.0, 0.0)          # transparent (panel shows through)
TRACK = (0.18, 0.20, 0.26, 1.0)    # empty bar
TRACK_BRD = (0.30, 0.33, 0.40, 1.0)
TXT = (1.0, 1.0, 1.0, 1.0)         # % text (readable on every fill colour)
ALERT_BG = (0.86, 0.20, 0.18, 1.0)  # loud red banner (token dead)
ALERT_TX = (1.0, 1.0, 1.0, 1.0)


def render(cfg: Config, bars: List[dict], stale: bool = False, note: Optional[str] = None) -> str:
    import cairo
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    os.makedirs(cfg.cache_dir, exist_ok=True)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, cfg.width, cfg.height)
    cr = cairo.Context(surface)
    cr.set_source_rgba(*BG)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)

    def text(x, y, s, color, size, bold=False, align_center=None, valign_mid=True):
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription()
        desc.set_family("Sans")
        desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
        desc.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(desc)
        layout.set_text(s, -1)
        tw, th = layout.get_pixel_size()
        tx = x - tw / 2.0 if align_center else x
        ty = y - th / 2.0 if valign_mid else y
        cr.move_to(tx, ty)
        cr.set_source_rgba(*color)
        PangoCairo.show_layout(cr, layout)
        return tw

    def rounded(x, y, w, h, r):
        r = min(r, h / 2.0, w / 2.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

    n = len(bars)
    gap = 10
    seg_w = (cfg.width - gap * (n - 1)) / float(n)
    label_size = max(8, int(cfg.height * 0.48))
    pct_size = max(7, int(cfg.height * 0.40))
    bar_h = max(10, int(cfg.height * 0.62))
    bar_y = (cfg.height - bar_h) / 2.0

    x = 0.0
    for b in bars:
        lbl = b["label"]
        lbl_color = pct_color(b["pct"], stale)
        lw = text(x, cfg.height / 2.0, lbl, lbl_color, label_size, bold=True)
        bar_x = x + lw + 6
        bar_w = x + seg_w - bar_x
        if bar_w < 20:  # not enough room: skip label
            bar_x = x
            bar_w = seg_w

        rounded(bar_x, bar_y, bar_w, bar_h, bar_h / 2.0)
        cr.set_source_rgba(*TRACK)
        cr.fill_preserve()
        cr.set_source_rgba(*TRACK_BRD)
        cr.set_line_width(1)
        cr.stroke()

        frac = max(0.0, min(1.0, b["pct"] / 100.0))
        fill_w = bar_w * frac
        if fill_w > 1:
            fill_w = max(fill_w, bar_h)  # keep pill shape readable at low %
            fill_w = min(fill_w, bar_w)
            rounded(bar_x, bar_y, fill_w, bar_h, bar_h / 2.0)
            cr.set_source_rgba(*pct_color(b["pct"], stale))
            cr.fill()

        rt = "%d%%" % round(b["pct"])
        if b["reset"]:
            rt += " · " + b["reset"]
        if stale:
            rt = "· " + rt  # subtle stale marker
        # Always white: the stale palette dims the *fill*, and reusing that same
        # grey for the text made it vanish wherever it overlapped the fill.
        tw = text(bar_x + bar_w / 2.0, cfg.height / 2.0, rt, TXT,
                  pct_size, bold=True, align_center=True)

        dot_color = pace_color(b.get("pace"))
        if dot_color and not stale:
            dot_r = max(2.5, pct_size * 0.22)
            dot_x = bar_x + bar_w / 2.0 + tw / 2.0 + dot_r + 3
            dot_y = cfg.height / 2.0
            if dot_x + dot_r < bar_x + bar_w:
                cr.arc(dot_x, dot_y, dot_r, 0, 2 * math.pi)
                cr.set_source_rgba(*dot_color)
                cr.fill()

        x += seg_w + gap

    if note:
        text(2, cfg.height / 2.0, note, RED, label_size, bold=True)

    tmp = cfg.png_path + ".tmp"
    surface.write_to_png(tmp)
    os.replace(tmp, cfg.png_path)
    return cfg.png_path


def render_alert(cfg: Config, message: str) -> str:
    """Unmissable red banner shown when the token is dead / missing."""
    import cairo
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    os.makedirs(cfg.cache_dir, exist_ok=True)
    size = max(8, int(cfg.height * 0.46))

    # measure the text first so the banner is exactly wide enough
    meas = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    mcr = cairo.Context(meas)
    layout = PangoCairo.create_layout(mcr)
    desc = Pango.FontDescription()
    desc.set_family("Sans")
    desc.set_weight(Pango.Weight.BOLD)
    desc.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(desc)
    layout.set_text(message, -1)
    tw, _th = layout.get_pixel_size()

    pad = 12
    w = max(int(tw + pad * 2), 120)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, cfg.height)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)

    # red pill
    r = cfg.height / 2.0
    cr.new_sub_path()
    cr.arc(w - r, r, r, -math.pi / 2, math.pi / 2)
    cr.arc(r, r, r, math.pi / 2, 1.5 * math.pi)
    cr.close_path()
    cr.set_source_rgba(*ALERT_BG)
    cr.fill()

    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(desc)
    lay.set_text(message, -1)
    tw2, th2 = lay.get_pixel_size()
    cr.move_to((w - tw2) / 2.0, (cfg.height - th2) / 2.0)
    cr.set_source_rgba(*ALERT_TX)
    PangoCairo.show_layout(cr, lay)

    tmp = cfg.png_path + ".tmp"
    surface.write_to_png(tmp)
    os.replace(tmp, cfg.png_path)
    return cfg.png_path
