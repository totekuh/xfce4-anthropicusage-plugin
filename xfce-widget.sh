#!/usr/bin/env bash
# xfce-widget.sh — safely load/unload the Anthropic usage genmon widget on the
# XFCE panel. All the risky bits (panel array surgery, panel restart) live here
# so the Makefile can stay a thin wrapper.
#
# Safety guarantees:
#   * before editing the panel's plugin-ids array it snapshots the CURRENT
#     array; if the edit fails or would empty the array, it restores the
#     snapshot — so a bug can never wipe your tray.
#   * it never talks to the panel over D-Bus unless the panel is running
#     (no "Failed to restart the panel" dialog).
#   * after a reload it waits for the panel to actually come back, and starts
#     it if it doesn't.
set -uo pipefail

CH=xfce4-panel
ARR="/panels/${PANEL:-panel-1}/plugin-ids"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$DIR/anthropic_usage.py"
CMD="python3 $SCRIPT"
PERIOD="${PERIOD:-180000}"   # 3 min — the usage endpoint is burst-rate-limited
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/anthropic-usage"
BAK="$CACHE/plugin-ids.bak"

# --- make sure we can reach the running X session (works from cron too) ------
ensure_session_env() {
  if [ -z "${DISPLAY:-}" ] || [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    local pid
    pid=$(pgrep -u "$(id -u)" -x xfce4-session | head -1)
    [ -z "$pid" ] && pid=$(pgrep -u "$(id -u)" -x xfce4-panel | head -1)
    if [ -n "$pid" ] && [ -r "/proc/$pid/environ" ]; then
      local e
      e=$(tr '\0' '\n' < "/proc/$pid/environ")
      [ -z "${DISPLAY:-}" ]                  && export DISPLAY="$(sed -n 's/^DISPLAY=//p' <<<"$e" | head -1)"
      [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && export DBUS_SESSION_BUS_ADDRESS="$(sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' <<<"$e" | head -1)"
      [ -z "${XAUTHORITY:-}" ]               && export XAUTHORITY="$(sed -n 's/^XAUTHORITY=//p' <<<"$e" | head -1)"
    fi
  fi
  : "${DISPLAY:=:0}"
  : "${DBUS_SESSION_BUS_ADDRESS:=unix:path=/run/user/$(id -u)/bus}"
  export DISPLAY DBUS_SESSION_BUS_ADDRESS
}

# --- array helpers -----------------------------------------------------------
get_array() { xfconf-query -c "$CH" -p "$ARR" 2>/dev/null | grep -E '^[0-9]+$'; }

# set_array <id>...   (refuses to write an empty array)
set_array() {
  local ids=("$@") args=() v
  if [ "${#ids[@]}" -eq 0 ]; then
    echo "refusing to write an empty plugin-ids array" >&2; return 1
  fi
  for v in "${ids[@]}"; do args+=(-t int -s "$v"); done
  xfconf-query -c "$CH" -p "$ARR" -rR 2>/dev/null || true
  xfconf-query -c "$CH" -p "$ARR" -n "${args[@]}"
}

backup_array() { mkdir -p "$CACHE"; get_array > "$BAK" || true; }
restore_array() {
  if [ -s "$BAK" ]; then
    echo "restoring plugin-ids from backup" >&2
    # shellcheck disable=SC2046
    set_array $(cat "$BAK")
  fi
}

# genmon plugin xfconf paths whose command runs OUR script
find_ours() {
  local p cmd
  for p in $(xfconf-query -c "$CH" -lv 2>/dev/null | awk '$2=="genmon"{print $1}'); do
    cmd=$(xfconf-query -c "$CH" -p "$p/command" 2>/dev/null || true)
    [[ "$cmd" == *"$SCRIPT"* ]] && echo "$p"
  done
}

# --- panel lifecycle ---------------------------------------------------------
panel_up() { pgrep -x xfce4-panel >/dev/null 2>&1; }

wait_up() {  # wait up to ~8s for the panel process to exist
  local i
  for i in $(seq 1 8); do panel_up && return 0; sleep 1; done
  return 1
}

reload_panel() {
  if panel_up; then
    xfce4-panel -r >/dev/null 2>&1 || true
  fi
  # -r re-execs the panel (brief gap); wait for it, else start it fresh
  if ! wait_up; then
    setsid xfce4-panel >/dev/null 2>&1 < /dev/null &
    sleep 2
  fi
  panel_up
}

restart_panel() {
  if panel_up; then
    xfce4-panel -q >/dev/null 2>&1 || pkill -x xfce4-panel || true
    sleep 1
  fi
  setsid xfce4-panel >/dev/null 2>&1 < /dev/null &
  sleep 2
  panel_up
}

# --- commands ----------------------------------------------------------------
cmd_load() {
  chmod +x "$SCRIPT" 2>/dev/null || true
  local ours; ours=$(find_ours)
  if [ -n "$ours" ]; then
    echo "already loaded:"; echo "$ours" | sed 's/^/  /'
    reload_panel && echo "panel reloaded." || echo "WARN: panel not running"
    return 0
  fi

  backup_array
  local -a cur; mapfile -t cur < <(get_array)
  if [ "${#cur[@]}" -eq 0 ]; then
    echo "ERROR: could not read $ARR (is the panel configured?)" >&2; return 1
  fi

  local maxid newnum newid
  maxid=$(xfconf-query -c "$CH" -l 2>/dev/null | grep -oE '/plugins/plugin-[0-9]+' | grep -oE '[0-9]+$' | sort -n | tail -1)
  maxid=${maxid:-0}; newnum=$((maxid + 1)); newid="/plugins/plugin-$newnum"
  echo "creating $newid (genmon)"
  xfconf-query -c "$CH" -p "$newid"                   -n -t string -s genmon
  xfconf-query -c "$CH" -p "$newid/command"           -n -t string -s "$CMD"
  xfconf-query -c "$CH" -p "$newid/update-period"     -n -t int    -s "$PERIOD"
  xfconf-query -c "$CH" -p "$newid/use-label"         -n -t bool   -s false
  xfconf-query -c "$CH" -p "$newid/enable-single-row" -n -t bool   -s true

  if ! set_array "${cur[@]}" "$newnum"; then
    echo "ERROR: failed to attach to panel; rolling back" >&2
    restore_array; return 1
  fi
  # verify nothing was lost
  local -a now; mapfile -t now < <(get_array)
  if [ "${#now[@]}" -lt "$((${#cur[@]} + 1))" ]; then
    echo "ERROR: array shrank ( ${#cur[@]} -> ${#now[@]} ); rolling back" >&2
    restore_array; return 1
  fi
  reload_panel && echo "loaded as $newid. Right-click the widget -> Move to reposition." \
    || echo "loaded (config written) but panel is not running; start it with: make restart"
}

cmd_unload() {
  local -a ours; mapfile -t ours < <(find_ours)
  if [ "${#ours[@]}" -eq 0 ]; then echo "not loaded — nothing to remove"; return 0; fi

  backup_array
  local -a cur; mapfile -t cur < <(get_array)
  # build the numeric ids to drop
  local -a drop=() keep=() p num v
  for p in "${ours[@]}"; do drop+=("${p##*-}"); done
  for v in "${cur[@]}"; do
    local skip=0 d
    for d in "${drop[@]}"; do [ "$v" = "$d" ] && skip=1; done
    [ "$skip" -eq 0 ] && keep+=("$v")
  done

  if [ "${#keep[@]}" -eq 0 ]; then
    echo "refusing to remove the last plugin from the panel" >&2; return 1
  fi
  echo "removing: ${ours[*]}"
  if ! set_array "${keep[@]}"; then restore_array; return 1; fi
  for p in "${ours[@]}"; do xfconf-query -c "$CH" -p "$p" -rR 2>/dev/null || true; done
  reload_panel && echo "unloaded." || echo "unloaded (panel not running)"
}

cmd_reload()  { reload_panel  && echo "panel reloaded." || echo "panel started."; }
cmd_restart() { restart_panel && echo "panel restarted." || echo "start FAILED — run 'xfce4-panel' manually to see the error."; }

cmd_status() {
  local ours; ours=$(find_ours)
  if [ -n "$ours" ]; then echo "INSTALLED:"; echo "$ours" | sed 's/^/  /'; else echo "NOT installed"; fi
  echo "panel: $(panel_up && echo running || echo 'not running')"
  echo "--- live values ---"
  "$SCRIPT" --json 2>/dev/null | python3 -c "import sys,json
d=json.load(sys.stdin)
print('5h    ', d['five_hour']['utilization'], '%  resets', d['five_hour']['resets_at'])
print('weekly', d['seven_day']['utilization'], '%  resets', d['seven_day']['resets_at'])" 2>/dev/null \
    || echo "(could not fetch live usage)"
}

# -----------------------------------------------------------------------------
ensure_session_env
case "${1:-}" in
  load|install)    cmd_load ;;
  unload|uninstall) cmd_unload ;;
  reload)          cmd_reload ;;
  restart)         cmd_restart ;;
  status)          cmd_status ;;
  render|test)     chmod +x "$SCRIPT"; "$SCRIPT" --png ;;
  logs)            if [ -s "$CACHE/widget.log" ]; then tail -n "${2:-40}" "$CACHE/widget.log"; else echo "no log yet at $CACHE/widget.log"; fi ;;
  restore-array)   restore_array ;;
  *) echo "usage: $0 {load|unload|reload|restart|status|test|logs|restore-array}"; exit 2 ;;
esac
