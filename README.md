# Anthropic Usage — XFCE panel widget

Two pill bars in the XFCE panel tracking your Claude subscription limits:

- **5h** — the 5-hour rolling session limit
- **Weekly** — the 7-day limit

![example](example.png)

Each bar shows `NN% · <time-until-reset>` and changes colour:
teal `< 75%`, amber `75–90%`, red `≥ 90%`. When the data can't be fetched it
dims to grey and shows the last cached values; the tooltip explains why.

## Where the numbers come from

The exact same source Claude Code's `/usage` uses: the Anthropic OAuth usage
endpoint (`/api/oauth/usage`), authenticated with the access token already on
disk at `~/.claude/.credentials.json`. These are the real server-side
utilisation figures, not an estimate from parsing local logs.

No API key, no config needed — if you're logged into Claude Code, it works.

## Requirements

- XFCE with `xfce4-genmon-plugin`
- `python3` with `python3-gi`, `python3-cairo`, `gir1.2-pango-1.0`
- A logged-in Claude Code (`~/.claude/.credentials.json`)

```
sudo apt install xfce4-genmon-plugin python3-gi python3-cairo gir1.2-pango-1.0
```

## Install

```
make load        # or: ./install.sh
```

This adds a genmon instance to the panel, points it at `anthropic_usage.py`,
sets a 3-minute refresh, and reloads the panel. The widget appears at the end of the
panel — right-click → **Move** to reposition, e.g. next to the system tray.

### Managing it

| command        | what it does                                  |
|----------------|-----------------------------------------------|
| `make load`    | add the widget to the panel                   |
| `make unload`  | remove it (safely — never wipes other plugins)|
| `make reload`  | reload the panel (starts it if it's down)     |
| `make restart` | quit + relaunch `xfce4-panel`                 |
| `make status`  | is it installed? + current live values        |
| `make test`    | render the PNG once                           |
| `make logs`    | tail the fetch log (successes, 429s, errors)  |

The panel logic lives in `xfce-widget.sh`; the Makefile is a thin wrapper.
Every panel edit snapshots the current plugin list first and rolls back on any
failure, so a bug can't nuke your tray, and it never pops a D-Bus dialog.

Refresh interval (default 180 000 ms = 3 min; the usage endpoint is
burst-rate-limited, so don't go much lower): `make unload && PERIOD=120000 make load`,
or right-click the widget → **Properties** → *Period (s)*.
Target a different panel with `PANEL=panel-2 make load`.

## How it works

`genmon` runs `anthropic_usage.py` every 3 minutes. The script:

1. reads the OAuth access token from `~/.claude/.credentials.json`
2. GETs `/api/oauth/usage`, caches the result to
   `~/.cache/anthropic-usage/last.json`
3. renders the two bars to `~/.cache/anthropic-usage/widget.png` (cairo + Pango)
4. prints genmon XML: `<img>`, a detailed `<tool>` tooltip

### Failure states (so you notice when it dies)

- **Transient (offline / network blip):** bars dim to grey and keep showing the
  last cached values. This self-heals on the next successful fetch.
- **Rate limited (HTTP 429):** the endpoint has a tight burst limit. On a 429
  the widget goes grey/stale and **backs off** (honouring `Retry-After`, floor
  60 s) so it stops hammering; it resumes on the next allowed tick. Every fetch
  outcome is recorded — check `make logs`.
- **Token expired / no login (HTTP 401/403):** the widget turns into a loud
  **red banner** — `⚠ Claude token expired — run: claude` — and the tooltip
  tells you what to do. Running `claude` refreshes the token on disk, and the
  widget goes back to normal on its next tick.

This split is deliberate: a network hiccup shouldn't cry wolf, but a dead token
is actionable and gets shown in red so you can't miss it.

## Tuning appearance

Environment variables (set them in the genmon **Command**, e.g.
`ANTHRO_H=28 python3 .../anthropic_usage.py`):

| var             | default    | meaning                          |
|-----------------|------------|----------------------------------|
| `ANTHRO_W`      | `330`      | total image width in px          |
| `ANTHRO_H`      | `26`       | image height in px               |
| `ANTHRO_LABELS` | `5h,Weekly`| the two bar labels               |
| `ANTHRO_CRED`   | `~/.claude/.credentials.json` | credentials file (override for testing) |

Colours and thresholds live near the top of `anthropic_usage.py`.

## Manual test

```
python3 anthropic_usage.py --json    # raw usage payload
python3 anthropic_usage.py --png     # render only, print PNG path
python3 anthropic_usage.py           # genmon XML (what the panel runs)

# force the dead-token red banner without touching your real credentials
# (isolated cache so the live widget PNG is not overwritten):
printf '{"claudeAiOauth":{"accessToken":"bogus"}}' > /tmp/bad.json
ANTHRO_CRED=/tmp/bad.json XDG_CACHE_HOME=/tmp/altcache python3 anthropic_usage.py --png
```

## Uninstall

`make unload`, or right-click the widget → **Remove**. Nothing else is installed
system-wide (cache lives in `~/.cache/anthropic-usage/`).
