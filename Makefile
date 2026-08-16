# Makefile — Anthropic usage genmon widget for the XFCE panel.
#
# Only two things live here that aren't in the Python package: the pipx
# bootstrap (you can't run `anthropic-usage panel install` before the package
# is installed) and the dev venv for tests. Everything else forwards to the
# `anthropic-usage panel` subcommand.
#
# Overrides:  PERIOD=<ms>  refresh interval (default 300000)
#             PANEL=<name> target panel (default panel-1)

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV := $(ROOT)/.venv
BIN := anthropic-usage
export PERIOD
export PANEL

.PHONY: help load install unload uninstall reload restart status render-check test coverage logs deps

help:
	@echo "Anthropic usage widget"
	@echo
	@echo "  make load          install the package + add the widget to the panel"
	@echo "  make unload        remove the widget from the panel"
	@echo "  make uninstall     unload, then remove the package too"
	@echo "  make reload        reload the panel (start if down)"
	@echo "  make restart       quit + relaunch xfce4-panel"
	@echo "  make status        installed? + which binary?"
	@echo "  make render-check  render the widget PNG once"
	@echo "  make test          run the pytest suite"
	@echo "  make coverage      run the suite with a coverage report"
	@echo "  make logs          tail the fetch log (429s, errors, successes)"
	@echo "  make deps          check dependencies"
	@echo
	@echo "  overrides: PERIOD=<ms> PANEL=<name>"

deps:
	@fail=0; \
	command -v python3      >/dev/null || { echo "MISSING python3"; fail=1; }; \
	command -v pipx         >/dev/null || { echo "MISSING pipx"; fail=1; }; \
	command -v xfce4-panel  >/dev/null || { echo "MISSING xfce4-panel"; fail=1; }; \
	command -v xfconf-query >/dev/null || { echo "MISSING xfconf-query"; fail=1; }; \
	python3 -c "import gi, cairo; gi.require_version('PangoCairo','1.0')" 2>/dev/null \
	  || { echo "MISSING python3-gi / python3-cairo / gir1.2-pango-1.0"; fail=1; }; \
	dpkg -l xfce4-genmon-plugin 2>/dev/null | grep -q '^ii' \
	  || { echo "MISSING xfce4-genmon-plugin"; fail=1; }; \
	test -f "$$HOME/.claude/.credentials.json" \
	  || echo "WARN  ~/.claude/.credentials.json not found (widget shows n/a until you log into Claude Code)"; \
	if [ $$fail -eq 0 ]; then echo "deps OK"; else \
	  echo "install: sudo apt install pipx xfce4-genmon-plugin python3-gi python3-cairo gir1.2-pango-1.0"; exit 1; fi

# --system-site-packages so the venv can see apt's pycairo/gi, which aren't
# pip-installable on Debian/Kali (and so aren't pyproject dependencies).
load: deps
	@pipx install -e "$(ROOT)" --force --system-site-packages >/dev/null
	@$(BIN) panel install $(if $(PERIOD),--period $(PERIOD),)

install: load
unload: ; @$(BIN) panel uninstall
reload: ; @$(BIN) panel reload
restart: ; @$(BIN) panel restart
status: ; @$(BIN) panel status
logs: ; @$(BIN) panel logs
render-check: ; @$(BIN) --png

# Order matters: drop the panel entry while the binary still exists, then
# remove the package (which deletes that binary).
uninstall:
	-@$(BIN) panel uninstall
	@pipx uninstall $(BIN)

# Dev/test venv, separate from the pipx runtime install `make load` uses —
# Kali/Debian's system pip is PEP 668 externally-managed and refuses plain
# `pip install`. --system-site-packages so the render tests can still see
# apt's pycairo/gi if present (they're skipped otherwise), and so an
# apt-installed pytest satisfies the dev extra without a redundant copy.
$(VENV)/bin/python:
	python3 -m venv "$(VENV)" --system-site-packages
	"$(VENV)/bin/pip" install -q --upgrade pip
	"$(VENV)/bin/pip" install -q -e "$(ROOT)[dev]"

test: $(VENV)/bin/python
	@"$(VENV)/bin/python" -m pytest -q

coverage: $(VENV)/bin/python
	@"$(VENV)/bin/python" -m pytest -q --cov=anthropic_usage --cov-report=term-missing
