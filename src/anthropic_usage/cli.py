"""Entry point.

Widget (what genmon runs):
  anthropic-usage            # emit genmon XML
  anthropic-usage --png      # just (re)render the PNG, print its path
  anthropic-usage --json     # print the raw usage JSON (debug)

Panel management:
  anthropic-usage panel install [--period MS] [--panel NAME]
  anthropic-usage panel uninstall
  anthropic-usage panel status
  anthropic-usage panel reload | restart
  anthropic-usage panel logs [-n N]

Environment overrides (optional):
  ANTHRO_CRED   path to Claude Code credentials (default ~/.claude/.credentials.json)
  ANTHRO_W      total image width  in px (default 330)
  ANTHRO_H      image height       in px (default 26)
  ANTHRO_LABELS "5h,Weekly"        the two bar labels
"""

import argparse
import json
import os
import sys
import time
from typing import Optional, Sequence

from . import cache, client, panel as panel_mod
from .config import load_config
from .format import empty_bars, extract
from .genmon import emit_genmon
from .session import ensure_session_env


# --- widget ------------------------------------------------------------------
def _widget_main(argv: Sequence[str]) -> None:
    parser = argparse.ArgumentParser(prog="anthropic-usage")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--json", action="store_true", help="print the raw usage JSON")
    mode.add_argument("--png", action="store_true", help="render the PNG only, print its path")
    args = parser.parse_args(argv)

    cfg = load_config()

    data, err = client.fetch_usage(cfg)
    stale = data is None
    fetched_at = time.time()
    if stale:
        data, fetched_at = cache.load_cache(cfg)

    if args.json:
        print(json.dumps(data, indent=2) if data else "no data (%s)" % err)
        return

    bars = extract(cfg, data) if data else empty_bars(cfg)

    # Token dead/missing -> loud red banner, regardless of whether we have cache.
    # This is the case you must not miss, so it gets its own unmistakable look.
    if err in ("auth", "no-token"):
        from .render import render_alert
        msg = "⚠ Claude token expired — run: claude" if err == "auth" \
            else "⚠ no Claude login — run: claude"
        render_alert(cfg, msg)
        if args.png:
            print(cfg.png_path)
            return
        print(emit_genmon(cfg, bars, True, err, fetched_at))
        return

    from .render import render
    note = "n/a" if (stale and data is None) else None
    render(cfg, bars, stale=stale, note=note)

    if args.png:
        print(cfg.png_path)
        return

    print(emit_genmon(cfg, bars, stale, err, fetched_at))


# --- panel -------------------------------------------------------------------
def _panel_main(argv: Sequence[str]) -> None:
    # `or` rather than a get() default: make exports PERIOD/PANEL even when
    # they're unset, which hands us an empty string.
    parser = argparse.ArgumentParser(prog="anthropic-usage panel")
    parser.add_argument("--panel", default=os.environ.get("PANEL") or "panel-1",
                        help="target panel (default panel-1)")
    sub = parser.add_subparsers(dest="action", required=True)

    p_install = sub.add_parser("install", help="register the widget on the panel")
    p_install.add_argument("--period", type=int,
                           default=int(os.environ.get("PERIOD") or panel_mod.DEFAULT_PERIOD_MS),
                           help="refresh interval in ms (default 300000)")
    sub.add_parser("uninstall", help="remove our widget instance(s)")
    sub.add_parser("status", help="installed? panel running? which binary?")
    sub.add_parser("reload", help="reload the panel (starts it if it's down)")
    sub.add_parser("restart", help="quit + relaunch xfce4-panel")
    p_logs = sub.add_parser("logs", help="tail the fetch log")
    p_logs.add_argument("-n", type=int, default=40, help="lines to show (default 40)")

    args = parser.parse_args(argv)
    cfg = load_config()
    ensure_session_env()

    try:
        if args.action == "install":
            print(panel_mod.install(cfg, args.panel, args.period))
        elif args.action == "uninstall":
            print(panel_mod.uninstall(cfg, args.panel))
        elif args.action == "status":
            print(panel_mod.status(cfg, args.panel))
        elif args.action == "reload":
            print("panel reloaded." if panel_mod.reload_panel() else "panel not running.")
        elif args.action == "restart":
            print("panel restarted." if panel_mod.restart_panel()
                  else "start FAILED — run 'xfce4-panel' manually to see the error.")
        elif args.action == "logs":
            print(panel_mod.logs(cfg, args.n))
    except panel_mod.PanelError as e:
        raise SystemExit("error: %s" % e)


def main(argv: Optional[Sequence[str]] = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "panel":
        _panel_main(argv[1:])
    else:
        _widget_main(argv)


if __name__ == "__main__":
    main()
