#!/usr/bin/env python3
"""
Anthropic usage panel widget for XFCE (via xfce4-genmon-plugin).

Renders two pill-shaped progress bars into a PNG and emits genmon XML:
  - "5h"     -> the 5-hour rolling session limit
  - "Weekly" -> the 7-day limit

Data comes from the same OAuth usage endpoint Claude Code's /usage uses,
authenticated with the local Claude Code access token. No fake numbers.

Usage:
  anthropic_usage.py            # emit genmon XML (default; this is what genmon runs)
  anthropic_usage.py --png      # just (re)render the PNG, print its path
  anthropic_usage.py --json     # print the raw usage JSON (debug)

Environment overrides (optional):
  ANTHRO_W      total image width  in px (default 330)
  ANTHRO_H      image height       in px (default 26)
  ANTHRO_LABELS "5h,Weekly"        the two bar labels
"""

import os
import sys
import json
import time
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
# ANTHRO_CRED lets you point at an alternate credentials file (handy for
# testing the auth-failure path without touching the real one).
CRED_PATH = os.environ.get("ANTHRO_CRED", os.path.expanduser("~/.claude/.credentials.json"))
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "anthropic-usage",
)
CACHE_JSON = os.path.join(CACHE_DIR, "last.json")
PNG_PATH = os.path.join(CACHE_DIR, "widget.png")

W = int(os.environ.get("ANTHRO_W", "330"))
H = int(os.environ.get("ANTHRO_H", "26"))
LABELS = os.environ.get("ANTHRO_LABELS", "5h,Weekly").split(",")

# Colours (RGB 0..1)
BG        = (0.0, 0.0, 0.0, 0.0)          # transparent (panel shows through)
TRACK     = (0.18, 0.20, 0.26, 1.0)       # empty bar
TRACK_BRD = (0.30, 0.33, 0.40, 1.0)
TEAL      = (0.25, 0.72, 0.63, 1.0)       # normal  (<75%)
AMBER     = (0.88, 0.65, 0.23, 1.0)       # warn    (75-90%)
RED       = (0.88, 0.28, 0.23, 1.0)       # high    (>=90%)
TXT       = (1.0, 1.0, 1.0, 1.0)          # % text
STALE     = (0.55, 0.58, 0.66, 1.0)       # dimmed when data is stale (transient)
ALERT_BG  = (0.86, 0.20, 0.18, 1.0)       # loud red banner (token dead)
ALERT_TX  = (1.0, 1.0, 1.0, 1.0)          # banner text


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
def read_token():
    with open(CRED_PATH) as f:
        return json.load(f)["claudeAiOauth"]["accessToken"]


def fetch_usage():
    """Return (data_dict, error_str). error_str is None on success."""
    try:
        token = read_token()
    except Exception as e:
        return None, "no-token"

    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "anthropic-usage-widget/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        os.makedirs(CACHE_DIR, exist_ok=True)
        payload = {"fetched_at": time.time(), "data": data}
        tmp = CACHE_JSON + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.replace(tmp, CACHE_JSON)
        return data, None
    except urllib.error.HTTPError as e:
        return None, "auth" if e.code in (401, 403) else "http-%d" % e.code
    except Exception:
        return None, "offline"


def load_cache():
    try:
        with open(CACHE_JSON) as f:
            p = json.load(f)
        return p["data"], p.get("fetched_at", 0)
    except Exception:
        return None, 0


def humanize_reset(iso):
    """Return a short 'time until reset' string like '4h50m' or '2d'."""
    if not iso:
        return ""
    try:
        # resets_at looks like '2026-08-16T17:49:59.819517+00:00'
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = (dt - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return ""
    if secs <= 0:
        return "now"
    d = int(secs // 86400)
    h = int((secs % 86400) // 3600)
    m = int((secs % 3600) // 60)
    if d >= 1:
        return "%dd" % d if h == 0 else "%dd%dh" % (d, h)
    if h >= 1:
        return "%dh%02dm" % (h, m) if m else "%dh" % h
    return "%dm" % max(m, 1)


def extract(data):
    """Pull the two utilisation values + reset strings out of the payload."""
    fh = (data or {}).get("five_hour") or {}
    sd = (data or {}).get("seven_day") or {}
    return [
        {
            "label": LABELS[0].strip() if len(LABELS) > 0 else "5h",
            "pct": float(fh.get("utilization") or 0.0),
            "reset": humanize_reset(fh.get("resets_at")),
            "reset_iso": fh.get("resets_at"),
        },
        {
            "label": LABELS[1].strip() if len(LABELS) > 1 else "Weekly",
            "pct": float(sd.get("utilization") or 0.0),
            "reset": humanize_reset(sd.get("resets_at")),
            "reset_iso": sd.get("resets_at"),
        },
    ]


def pct_color(pct, stale):
    if stale:
        return STALE
    if pct >= 90:
        return RED
    if pct >= 75:
        return AMBER
    return TEAL


# ----------------------------------------------------------------------------
# Rendering (cairo + PangoCairo)
# ----------------------------------------------------------------------------
def render(bars, stale=False, note=None):
    import cairo
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    os.makedirs(CACHE_DIR, exist_ok=True)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surface)
    cr.set_source_rgba(*BG)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)

    def text(x, y, s, color, size, bold=False, align_center=None, valign_mid=True):
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription("Sans %s %d" % ("Bold" if bold else "", size))
        # FontDescription string parsing: build cleanly
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
    seg_w = (W - gap * (n - 1)) / float(n)
    label_size = max(7, int(H * 0.36))
    pct_size = max(7, int(H * 0.40))
    bar_h = max(10, int(H * 0.62))
    bar_y = (H - bar_h) / 2.0

    x = 0.0
    for b in bars:
        # label sits left of the bar
        lbl = b["label"]
        lbl_color = pct_color(b["pct"], stale)
        lw = text(x, H / 2.0, lbl, lbl_color, label_size, bold=True)
        bar_x = x + lw + 6
        bar_w = x + seg_w - bar_x
        if bar_w < 20:  # not enough room: skip label
            bar_x = x
            bar_w = seg_w

        # track
        rounded(bar_x, bar_y, bar_w, bar_h, bar_h / 2.0)
        cr.set_source_rgba(*TRACK)
        cr.fill_preserve()
        cr.set_source_rgba(*TRACK_BRD)
        cr.set_line_width(1)
        cr.stroke()

        # fill
        frac = max(0.0, min(1.0, b["pct"] / 100.0))
        fill_w = bar_w * frac
        if fill_w > 1:
            fill_w = max(fill_w, bar_h)  # keep pill shape readable at low %
            fill_w = min(fill_w, bar_w)
            rounded(bar_x, bar_y, fill_w, bar_h, bar_h / 2.0)
            cr.set_source_rgba(*pct_color(b["pct"], stale))
            cr.fill()

        # overlay text: "17% · 4h50m"
        rt = ("%d%%" % round(b["pct"]))
        if b["reset"]:
            rt += " · " + b["reset"]
        if stale:
            rt = "· " + rt  # subtle stale marker
        text(bar_x + bar_w / 2.0, H / 2.0, rt, TXT if not stale else STALE,
             pct_size, bold=True, align_center=True)

        x += seg_w + gap

    if note:
        text(2, H / 2.0, note, RED, label_size, bold=True)

    tmp = PNG_PATH + ".tmp"
    surface.write_to_png(tmp)
    os.replace(tmp, PNG_PATH)
    return PNG_PATH


def render_alert(message):
    """Unmissable red banner shown when the token is dead / missing."""
    import cairo
    import gi
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    os.makedirs(CACHE_DIR, exist_ok=True)
    size = max(8, int(H * 0.46))

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
    tw, th = layout.get_pixel_size()

    pad = 12
    w = max(int(tw + pad * 2), 120)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, H)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)

    # red pill
    r = H / 2.0
    cr.new_sub_path()
    cr.arc(w - r, r, r, -math.pi / 2, math.pi / 2)
    cr.arc(r, r, r, math.pi / 2, 1.5 * math.pi)
    cr.close_path()
    cr.set_source_rgba(*ALERT_BG)
    cr.fill()

    # centered white text
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(desc)
    lay.set_text(message, -1)
    tw2, th2 = lay.get_pixel_size()
    cr.move_to((w - tw2) / 2.0, (H - th2) / 2.0)
    cr.set_source_rgba(*ALERT_TX)
    PangoCairo.show_layout(cr, lay)

    tmp = PNG_PATH + ".tmp"
    surface.write_to_png(tmp)
    os.replace(tmp, PNG_PATH)
    return PNG_PATH


# ----------------------------------------------------------------------------
# genmon output
# ----------------------------------------------------------------------------
def emit_genmon(bars, stale, err, fetched_at):
    when = ""
    if fetched_at:
        when = datetime.fromtimestamp(fetched_at).strftime("%H:%M:%S")

    if err == "auth":
        lines = ["<b>⚠ Claude token expired</b>", "Run <tt>claude</tt> to refresh it."]
    elif err == "no-token":
        lines = ["<b>⚠ No Claude login found</b>", "Log into Claude Code."]
    else:
        lines = ["<b>Anthropic usage</b>"]

    for b in bars:
        rline = "%s: %d%%" % (b["label"], round(b["pct"]))
        if b["reset"]:
            rline += "  (resets in %s)" % b["reset"]
        lines.append(rline)

    if stale:
        lines.append("")
        if err not in ("auth", "no-token"):
            reason = {"offline": "network unreachable"}.get(err, err or "stale")
            lines.append("⚠ showing cached data (%s)" % reason)
        else:
            lines.append("values above are last-known (may be stale)")
        if when:
            lines.append("last good fetch: %s" % when)
    elif when:
        lines.append("")
        lines.append("updated %s" % when)
    tool = "\n".join(lines)

    print("<img>%s</img>" % PNG_PATH)
    print("<tool>%s</tool>" % tool)
    print("<txt></txt>")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    data, err = fetch_usage()
    stale = data is None
    fetched_at = time.time()
    if stale:
        data, fetched_at = load_cache()

    if arg == "--json":
        print(json.dumps(data, indent=2) if data else "no data (%s)" % err)
        return

    bars = extract(data) if data else [
        {"label": LABELS[0].strip() if LABELS else "5h", "pct": 0, "reset": "", "reset_iso": None},
        {"label": (LABELS[1].strip() if len(LABELS) > 1 else "Weekly"), "pct": 0, "reset": "", "reset_iso": None},
    ]

    # Token dead/missing -> loud red banner, regardless of whether we have cache.
    # This is the case you must not miss, so it gets its own unmistakable look.
    if err in ("auth", "no-token"):
        msg = "⚠ Claude token expired — run: claude" if err == "auth" \
              else "⚠ no Claude login — run: claude"
        render_alert(msg)
        if arg == "--png":
            print(PNG_PATH)
            return
        emit_genmon(bars, True, err, fetched_at)
        return

    note = None
    if stale and data is None:
        note = "n/a"

    render(bars, stale=stale, note=note)

    if arg == "--png":
        print(PNG_PATH)
        return

    emit_genmon(bars, stale, err, fetched_at)


if __name__ == "__main__":
    main()
