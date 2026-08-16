# Anthropic Usage — XFCE panel widget

Two pill bars in the XFCE panel showing your Claude usage: **5h** (rolling session limit) and **Weekly** (7-day limit).
Same data source as Claude Code's `/usage`. Teal < 75%, amber 75–90%, red ≥ 90%.

![example](example.png)

## Requirements

```
sudo apt install pipx xfce4-genmon-plugin python3-gi python3-cairo gir1.2-pango-1.0
```
Logged into Claude Code (`~/.claude/.credentials.json`).

## Install / uninstall

```
make load      # installs (pipx, editable) + adds to panel
make unload    # removes it from the panel, safely
make uninstall # unload + remove the package
make status    # installed? which binary?
make test      # pytest
```

`make` only does the pipx bootstrap — everything else is the installed CLI:
`anthropic-usage panel install|uninstall|status|reload|restart|logs`.

## Config

Env vars on the genmon command: `ANTHRO_W`, `ANTHRO_H`, `ANTHRO_LABELS`, `ANTHRO_CRED`. 

Refresh period: `PERIOD=<ms> make load` (default 300000 — don't go much lower, the endpoint will rate-limit you).

## License

MIT — see [LICENSE](LICENSE).
