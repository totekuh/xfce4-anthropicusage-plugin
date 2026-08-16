"""Turning the raw usage payload into render-ready bar data."""

from datetime import datetime, timezone
from typing import List, Optional

from .config import Config

TEAL = (0.25, 0.72, 0.63, 1.0)   # normal (<75%)
AMBER = (0.88, 0.65, 0.23, 1.0)  # warn   (75-90%)
RED = (0.88, 0.28, 0.23, 1.0)    # high   (>=90%)
STALE = (0.55, 0.58, 0.66, 1.0)  # dimmed when data is stale (transient)


def humanize_reset(iso: Optional[str]) -> str:
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


def extract(cfg: Config, data: Optional[dict]) -> List[dict]:
    """Pull the two utilisation values + reset strings out of the payload."""
    fh = (data or {}).get("five_hour") or {}
    sd = (data or {}).get("seven_day") or {}
    return [
        {
            "label": cfg.labels[0].strip() if len(cfg.labels) > 0 else "5h",
            "pct": float(fh.get("utilization") or 0.0),
            "reset": humanize_reset(fh.get("resets_at")),
            "reset_iso": fh.get("resets_at"),
        },
        {
            "label": cfg.labels[1].strip() if len(cfg.labels) > 1 else "Weekly",
            "pct": float(sd.get("utilization") or 0.0),
            "reset": humanize_reset(sd.get("resets_at")),
            "reset_iso": sd.get("resets_at"),
        },
    ]


def empty_bars(cfg: Config) -> List[dict]:
    """Placeholder bars used when there's no data at all (no cache, dead token)."""
    return [
        {"label": cfg.labels[0].strip() if cfg.labels else "5h", "pct": 0, "reset": "", "reset_iso": None},
        {"label": (cfg.labels[1].strip() if len(cfg.labels) > 1 else "Weekly"), "pct": 0, "reset": "", "reset_iso": None},
    ]


def pct_color(pct: float, stale: bool):
    if stale:
        return STALE
    if pct >= 90:
        return RED
    if pct >= 75:
        return AMBER
    return TEAL
