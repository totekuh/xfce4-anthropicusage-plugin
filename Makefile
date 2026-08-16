# Makefile — Anthropic usage genmon widget for the XFCE panel.
# Thin wrapper over xfce-widget.sh (which holds the safe panel logic).
#
#   make load      register the widget on the panel + reload
#   make unload    remove our widget instance(s) + reload
#   make reload    reload the panel (starts it if it's down)
#   make restart   quit + relaunch xfce4-panel
#   make status    installed? + live usage values
#   make test      render the widget PNG once
#   make deps      check dependencies
#
# Overrides:  PERIOD=<ms>  refresh interval (default 180000)
#             PANEL=<name> target panel (default panel-1)

SH := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/xfce-widget.sh)
export PERIOD
export PANEL

.PHONY: help load install unload uninstall reload restart status test logs deps

help:
	@echo "Anthropic usage widget — panel plugin management"
	@echo
	@echo "  make load      register on panel + reload"
	@echo "  make unload    remove our instance(s) + reload"
	@echo "  make reload    reload the panel (start if down)"
	@echo "  make restart   quit + relaunch xfce4-panel"
	@echo "  make status    installed? + live values"
	@echo "  make test      render the widget PNG once"
	@echo "  make logs      tail the fetch log (429s, errors, successes)"
	@echo "  make deps      check dependencies"
	@echo
	@echo "  overrides: PERIOD=<ms> PANEL=<name>"

deps:
	@fail=0; \
	command -v python3      >/dev/null || { echo "MISSING python3"; fail=1; }; \
	command -v xfce4-panel  >/dev/null || { echo "MISSING xfce4-panel"; fail=1; }; \
	command -v xfconf-query >/dev/null || { echo "MISSING xfconf-query"; fail=1; }; \
	python3 -c "import gi, cairo; gi.require_version('PangoCairo','1.0')" 2>/dev/null \
	  || { echo "MISSING python3-gi / python3-cairo / gir1.2-pango-1.0"; fail=1; }; \
	dpkg -l xfce4-genmon-plugin 2>/dev/null | grep -q '^ii' \
	  || { echo "MISSING xfce4-genmon-plugin"; fail=1; }; \
	test -f "$$HOME/.claude/.credentials.json" \
	  || echo "WARN  ~/.claude/.credentials.json not found (widget shows n/a until you log into Claude Code)"; \
	if [ $$fail -eq 0 ]; then echo "deps OK"; else \
	  echo "install: sudo apt install xfce4-genmon-plugin python3-gi python3-cairo gir1.2-pango-1.0"; exit 1; fi

install: load
uninstall: unload
load: deps ; @bash "$(SH)" load
unload: ; @bash "$(SH)" unload
reload: ; @bash "$(SH)" reload
restart: ; @bash "$(SH)" restart
status: ; @bash "$(SH)" status
test: ; @bash "$(SH)" test
logs: ; @bash "$(SH)" logs
