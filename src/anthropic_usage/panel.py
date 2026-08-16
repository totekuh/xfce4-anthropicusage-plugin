"""Registering/removing the genmon widget on the XFCE panel.

All the risky bits live here: editing the panel's plugin-ids array, and
restarting the panel. Two safety rules the code below never breaks:

  * before editing plugin-ids we snapshot the current array; if the edit fails,
    or would shrink the array, we restore the snapshot — a bug here must never
    be able to wipe someone's tray.
  * we never talk to the panel over D-Bus unless it's actually running,
    otherwise XFCE pops a "Failed to restart the panel" dialog.

Every external command goes through _run(), so tests can monkeypatch exactly
one function and assert on what we would have written.
"""

import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

from .config import Config

APP_NAME = "anthropic-usage"
CHANNEL = "xfce4-panel"
DEFAULT_PERIOD_MS = 300000  # 5 min — the usage endpoint is tightly rate-limited


class PanelError(Exception):
    """Something went wrong that the user needs to hear about."""


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _xfconf(*args: str) -> subprocess.CompletedProcess:
    return _run(["xfconf-query", "-c", CHANNEL, *args])


# --- plugin-ids array --------------------------------------------------------
def _array_prop(panel: str) -> str:
    return "/panels/%s/plugin-ids" % panel


def get_array(panel: str) -> List[int]:
    """Plugin ids from xfconf.

    Must match whole lines, never bare whitespace tokens: xfconf prefixes the
    values with a header line ("Value is an array with 28 items:") whose item
    *count* would otherwise be parsed as a plugin id and written back into the
    array — which corrupts the panel with a "(null)" plugin.
    """
    res = _xfconf("-p", _array_prop(panel))
    ids = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    return ids


def set_array(panel: str, ids: List[int]) -> None:
    if not ids:
        raise PanelError("refusing to write an empty plugin-ids array")
    prop = _array_prop(panel)
    _xfconf("-p", prop, "-rR")
    args = []
    for v in ids:
        args += ["-t", "int", "-s", str(v)]
    res = _xfconf("-p", prop, "-n", *args)
    if res.returncode != 0:
        raise PanelError("failed to write plugin-ids: %s" % res.stderr.strip())


def _backup_path(cfg: Config) -> str:
    return os.path.join(cfg.cache_dir, "plugin-ids.bak")


def backup_array(cfg: Config, panel: str) -> None:
    ids = get_array(panel)
    if not ids:
        return
    os.makedirs(cfg.cache_dir, exist_ok=True)
    with open(_backup_path(cfg), "w") as f:
        f.write("\n".join(str(i) for i in ids))


def restore_array(cfg: Config, panel: str) -> None:
    try:
        with open(_backup_path(cfg)) as f:
            ids = [int(x) for x in f.read().split() if x.strip().isdigit()]
    except OSError:
        return
    if ids:
        set_array(panel, ids)


def _rollback(cfg: Config, panel: str) -> str:
    """Undo a half-finished edit. Never raises — the caller is already failing,
    and what matters is telling the user whether their panel is intact."""
    try:
        restore_array(cfg, panel)
        return "rolled back"
    except PanelError:
        return ("ROLLBACK ALSO FAILED — restore manually from %s"
                % _backup_path(cfg))


# --- finding our own plugin instances ----------------------------------------
def find_ours() -> List[str]:
    """xfconf paths of genmon plugins whose command runs our app."""
    listing = _xfconf("-lv").stdout.splitlines()
    found = []
    for line in listing:
        parts = line.split()
        if len(parts) < 2 or parts[1] != "genmon":
            continue
        # -lv also lists child properties (e.g. ".../text"), but those show a
        # parenthesised value, so the parts[1] == "genmon" check above already
        # leaves us with just plugin roots.
        root = parts[0]
        cmd = _xfconf("-p", "%s/command" % root).stdout.strip()
        if APP_NAME in cmd and root not in found:
            found.append(root)
    return found


def resolve_bin() -> Optional[str]:
    """Absolute path of the installed console script.

    We bake an absolute path into the genmon command rather than relying on
    PATH — genmon runs it outside any login shell that would set one up.
    """
    # abspath, not realpath: ~/.local/bin/anthropic-usage is a symlink into the
    # pipx venv, and the stable shim is what we want baked into the panel.
    argv0 = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if os.path.basename(argv0) == APP_NAME and os.access(argv0, os.X_OK):
        return argv0

    found = shutil.which(APP_NAME)
    if found:
        return os.path.abspath(found)

    res = _run(["pipx", "environment", "--value", "PIPX_BIN_DIR"])
    base = res.stdout.strip() if res.returncode == 0 and res.stdout.strip() \
        else os.path.expanduser("~/.local/bin")
    candidate = os.path.join(base, APP_NAME)
    return candidate if os.access(candidate, os.X_OK) else None


def require_bin() -> str:
    binary = resolve_bin()
    if not binary:
        raise PanelError("%s is not installed — run: make load" % APP_NAME)
    return binary


# --- panel lifecycle ---------------------------------------------------------
def panel_up() -> bool:
    return _run(["pgrep", "-x", "xfce4-panel"]).returncode == 0


def _wait_up(timeout: int = 8) -> bool:
    for i in range(timeout):
        if panel_up():
            return True
        if i + 1 < timeout:
            time.sleep(1)
    return False


def _start_panel() -> None:
    # start_new_session detaches us from the calling process group, so the
    # panel outlives this process (and the `make` that invoked it).
    subprocess.Popen(
        ["xfce4-panel"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(2)


def reload_panel() -> bool:
    if panel_up():
        _run(["xfce4-panel", "-r"])
        # -r re-execs in place. Sleep through that window before checking:
        # the *old* pid lingers for a moment, so an immediate panel_up() would
        # report success even when the panel is about to die on us.
        time.sleep(2)
    if not _wait_up():
        _start_panel()
    return panel_up()


def restart_panel() -> bool:
    if panel_up():
        if _run(["xfce4-panel", "-q"]).returncode != 0:
            _run(["pkill", "-x", "xfce4-panel"])
        time.sleep(1)
    _start_panel()
    return panel_up()


# --- commands ----------------------------------------------------------------
def _next_plugin_id() -> int:
    ids = []
    for line in _xfconf("-l").stdout.splitlines():
        part = line.strip().split("/plugins/plugin-")
        if len(part) > 1:
            num = part[1].split("/")[0]
            if num.isdigit():
                ids.append(int(num))
    return (max(ids) if ids else 0) + 1


def install(cfg: Config, panel: str, period: int = DEFAULT_PERIOD_MS) -> str:
    binary = require_bin()

    ours = find_ours()
    if ours:
        # Already registered — just re-point it, in case the path moved.
        for path in ours:
            _xfconf("-p", "%s/command" % path, "-n", "-t", "string", "-s", binary)
        reload_panel()
        return "already loaded (%s); refreshed command -> %s" % (", ".join(ours), binary)

    backup_array(cfg, panel)
    current = get_array(panel)
    if not current:
        raise PanelError(
            "could not read %s (is the panel configured?)" % _array_prop(panel))

    num = _next_plugin_id()
    new = "/plugins/plugin-%d" % num
    _xfconf("-p", new, "-n", "-t", "string", "-s", "genmon")
    _xfconf("-p", "%s/command" % new, "-n", "-t", "string", "-s", binary)
    _xfconf("-p", "%s/update-period" % new, "-n", "-t", "int", "-s", str(period))
    _xfconf("-p", "%s/use-label" % new, "-n", "-t", "bool", "-s", "false")
    _xfconf("-p", "%s/enable-single-row" % new, "-n", "-t", "bool", "-s", "true")

    try:
        set_array(panel, current + [num])
    except PanelError:
        raise PanelError("failed to attach to panel; %s" % _rollback(cfg, panel))

    if len(get_array(panel)) < len(current) + 1:
        raise PanelError("plugin-ids array shrank; %s" % _rollback(cfg, panel))

    reload_panel()
    return "loaded as %s -> %s" % (new, binary)


def uninstall(cfg: Config, panel: str) -> str:
    ours = find_ours()
    if not ours:
        return "not loaded — nothing to remove"

    backup_array(cfg, panel)
    drop = {int(p.rsplit("-", 1)[1]) for p in ours if p.rsplit("-", 1)[1].isdigit()}
    keep = [i for i in get_array(panel) if i not in drop]
    if not keep:
        raise PanelError("refusing to remove the last plugin from the panel")

    try:
        set_array(panel, keep)
    except PanelError:
        raise PanelError("failed to detach from panel; %s" % _rollback(cfg, panel))

    for path in ours:
        _xfconf("-p", path, "-rR")
    reload_panel()
    return "removed %s" % ", ".join(ours)


def status(cfg: Config, panel: str) -> str:
    ours = find_ours()
    lines = ["INSTALLED: %s" % ", ".join(ours) if ours else "NOT installed"]
    lines.append("panel: %s" % ("running" if panel_up() else "not running"))
    lines.append("binary: %s" % (resolve_bin() or "not found"))
    return "\n".join(lines)


def logs(cfg: Config, count: int = 40) -> str:
    try:
        with open(cfg.log_path) as f:
            return "".join(f.readlines()[-count:]).rstrip()
    except OSError:
        return "no log yet at %s" % cfg.log_path
