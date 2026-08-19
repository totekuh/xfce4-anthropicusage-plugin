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

    for b in bars:
        rline = "%s: %d%%" % (b["label"], round(b["pct"]))
        if b["reset"]:
            rline += "  (resets in %s)" % b["reset"]
        lines.append(rline)

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
