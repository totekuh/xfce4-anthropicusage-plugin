"""Turning the raw usage payload into render-ready bar data."""

from datetime import datetime, timezone
from typing import List, Optional

from .config import Config

TEAL = (0.25, 0.72, 0.63, 1.0)   # normal (<75%)
AMBER = (0.88, 0.65, 0.23, 1.0)  # warn   (75-90%)
RED = (0.88, 0.28, 0.23, 1.0)    # high   (>=90%)
STALE = (0.55, 0.58, 0.66, 1.0)  # dimmed when data is stale (transient)

PACE_SLOW = TEAL                  # under pace — room to burn
PACE_OK = (0.70, 0.70, 0.70, 1.0)  # on track
PACE_FAST = RED                   # ahead of pace — ease off

WINDOW_SECS = {"five_hour": 5 * 3600, "seven_day": 7 * 86400}


def burn_pace(pct: float, reset_iso: Optional[str], window_secs: int) -> Optional[str]:
    """Compare current usage against ideal linear pace through the window.

    Returns 'slow' (headroom), 'ok' (on track), or 'fast' (ease off).
    None when there's not enough data (too early or missing reset).
    """
    if not reset_iso or window_secs <= 0:
        return None
    try:
        dt = datetime.fromisoformat(reset_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        remaining = (dt - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return None
    remaining = max(remaining, 0)
    elapsed = window_secs - remaining
    elapsed_frac = elapsed / window_secs
    if elapsed_frac < 0.05:
        return None
    ideal_pct = elapsed_frac * 100.0
    ratio = pct / ideal_pct if ideal_pct > 0 else 0
    if ratio > 1.15:
        return "fast"
    if ratio < 0.85:
        return "slow"
    return "ok"


def pace_color(pace: Optional[str]):
    if pace == "fast":
        return PACE_FAST
    if pace == "slow":
        return PACE_SLOW
    if pace == "ok":
        return PACE_OK
    return None


def _humanize_secs(secs: float) -> str:
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


def _remaining_secs(reset_iso: Optional[str]) -> Optional[float]:
    if not reset_iso:
        return None
    try:
        dt = datetime.fromisoformat(reset_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((dt - datetime.now(timezone.utc)).total_seconds(), 0)
    except Exception:
        return None


def pace_details(pct: float, reset_iso: Optional[str], window_secs: int) -> Optional[dict]:
    """Compute burn-rate stats for the tooltip.

    Returns dict with: projected (end-of-window %), current_rate, target_rate,
    rate_unit ('h' or 'd'), and for fast: cap_in/dead_time; for slow: spare.
    None when not enough data.
    """
    remaining = _remaining_secs(reset_iso)
    if remaining is None or window_secs <= 0:
        return None
    elapsed = window_secs - remaining
    if elapsed < window_secs * 0.05 or elapsed <= 0:
        return None

    burn_rate = pct / elapsed
    projected = pct + burn_rate * remaining

    if window_secs < 86400:
        rate_unit, rate_mul = "h", 3600.0
    else:
        rate_unit, rate_mul = "d", 86400.0

    current_rate = burn_rate * rate_mul

    result = {
        "projected": round(projected, 1),
        "current_rate": round(current_rate, 1),
        "rate_unit": rate_unit,
    }

    if remaining > 0:
        target_rate = (100.0 - pct) / remaining * rate_mul
        result["target_rate"] = round(target_rate, 1)

    if projected > 105 and burn_rate > 0:
        time_to_cap = (100.0 - pct) / burn_rate if pct < 100 else 0
        result["cap_in"] = _humanize_secs(time_to_cap)
        result["dead_time"] = _humanize_secs(remaining - time_to_cap)
    elif projected < 95:
        result["spare"] = round(100.0 - projected, 1)

    return result


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
    fh_pct = float(fh.get("utilization") or 0.0)
    sd_pct = float(sd.get("utilization") or 0.0)
    fh_iso = fh.get("resets_at")
    sd_iso = sd.get("resets_at")
    return [
        {
            "label": cfg.labels[0].strip() if len(cfg.labels) > 0 else "5h",
            "pct": fh_pct,
            "reset": humanize_reset(fh_iso),
            "reset_iso": fh_iso,
            "pace": burn_pace(fh_pct, fh_iso, WINDOW_SECS["five_hour"]),
            "pace_details": pace_details(fh_pct, fh_iso, WINDOW_SECS["five_hour"]),
        },
        {
            "label": cfg.labels[1].strip() if len(cfg.labels) > 1 else "Weekly",
            "pct": sd_pct,
            "reset": humanize_reset(sd_iso),
            "reset_iso": sd_iso,
            "pace": burn_pace(sd_pct, sd_iso, WINDOW_SECS["seven_day"]),
            "pace_details": pace_details(sd_pct, sd_iso, WINDOW_SECS["seven_day"]),
        },
    ]


def empty_bars(cfg: Config) -> List[dict]:
    """Placeholder bars used when there's no data at all (no cache, dead token)."""
    return [
        {"label": cfg.labels[0].strip() if cfg.labels else "5h", "pct": 0, "reset": "", "reset_iso": None, "pace": None, "pace_details": None},
        {"label": (cfg.labels[1].strip() if len(cfg.labels) > 1 else "Weekly"), "pct": 0, "reset": "", "reset_iso": None, "pace": None, "pace_details": None},
    ]


def pct_color(pct: float, stale: bool):
    if stale:
        return STALE
    if pct >= 90:
        return RED
    if pct >= 75:
        return AMBER
    return TEAL
