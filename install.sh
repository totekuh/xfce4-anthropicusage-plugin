#!/usr/bin/env bash
# Convenience wrapper — installs the widget onto the XFCE panel.
# All real logic lives in xfce-widget.sh (also usable via `make load`).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$DIR/xfce-widget.sh" load
