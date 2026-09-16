"""Building the genmon XML block xfce4-genmon-plugin expects on stdout."""

from datetime import datetime
from typing import List, Optional

from .config import Config


def emit_genmon(cfg: Config, bars: List[dict], stale: bool, err: Optional[str], fetched_at: float) -> str:
    when = ""
    if fetched_at:
        when = datetime.fromtimestamp(fetched_at).strftime("%H:%M:%S")

    if err == "auth":
        lines = ["<b>⚠ Claude token expired</b>", "Run <tt>claude</tt> to refresh it."]
    elif err == "no-token":
        lines = ["<b>⚠ No Claude login found</b>", "Log into Claude Code."]
    else:
        lines = ["<b>Anthropic usage</b>"]

    pace_labels = {
        "slow": '<span color="#40B8A0">▲ room to use more</span>',
        "ok":   '<span color="#B3B3B3">● on track</span>',
        "fast": '<span color="#E04A3A">▼ ease off</span>',
    }
    for i, b in enumerate(bars):
        if i > 0:
            lines.append("")
        header = "<b>%s</b>  %d%%" % (b["label"], round(b["pct"]))
        if b["reset"]:
            header += "  <small>(resets in %s)</small>" % b["reset"]
        pace = b.get("pace")
        if pace:
            header += "  %s" % pace_labels[pace]
        lines.append(header)

        pd = b.get("pace_details")
        if pd:
            u = pd["rate_unit"]
            lines.append('<small>  rate  <b>%.1f%%/%s</b>    projected  <b>%g%%</b></small>' % (pd["current_rate"], u, pd["projected"]))
            if "cap_in" in pd:
                lines.append('<small>  <span color="#E04A3A">⚠ cap in %s</span>  (%s idle)</small>' % (pd["cap_in"], pd["dead_time"]))
                lines.append('<small>  target  <b>%.1f%%/%s</b> to land at 100%%</small>' % (pd["target_rate"], u))
            elif "spare" in pd:
                lines.append('<small>  <span color="#40B8A0">~%g%% headroom</span>    can push to  <b>%.1f%%/%s</b></small>' % (pd["spare"], pd["target_rate"], u))
            elif "target_rate" in pd:
                lines.append('<small>  sustain  <b>%.1f%%/%s</b> to land at 100%%</small>' % (pd["target_rate"], u))

    if stale:
        lines.append("")
        if err not in ("auth", "no-token"):
            reason = {
                "offline": "network unreachable",
                "http-429": "rate limited — backing off",
                "backoff": "rate limited — waiting to retry",
                "forbidden": "usage API refused the request (403)",
            }.get(err, err or "stale")
            lines.append("⚠ showing cached data (%s)" % reason)
        else:
            lines.append("values above are last-known (may be stale)")
        if when:
            lines.append("last good fetch: %s" % when)
    elif when:
        lines.append("")
        lines.append("updated %s" % when)
    tool = "\n".join(lines)

    return "<img>%s</img>\n<tool>%s</tool>\n<txt></txt>" % (cfg.png_path, tool)
