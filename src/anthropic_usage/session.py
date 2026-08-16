"""Finding the running X session, so panel commands work from cron/systemd too.

xfconf-query and xfce4-panel both need DISPLAY and a session bus address. When
we're invoked from an interactive desktop shell those are already set; when
we're not (cron, a systemd unit, an ssh shell) we scrape them out of a process
that *is* part of the session.
"""

import os
import subprocess
from typing import Optional

_VARS = ("DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY")


def _session_pid() -> Optional[int]:
    for name in ("xfce4-session", "xfce4-panel"):
        try:
            out = subprocess.run(
                ["pgrep", "-u", str(os.getuid()), "-x", name],
                capture_output=True, text=True, check=False,
            ).stdout.split()
        except OSError:
            return None
        if out:
            return int(out[0])
    return None


def _environ_of(pid: int) -> dict:
    try:
        with open("/proc/%d/environ" % pid, "rb") as f:
            raw = f.read()
    except OSError:
        return {}
    env = {}
    for entry in raw.split(b"\0"):
        if b"=" in entry:
            k, _, v = entry.partition(b"=")
            env[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return env


def ensure_session_env() -> None:
    """Fill in any missing session vars, in place, in os.environ."""
    if all(os.environ.get(v) for v in _VARS):
        return

    pid = _session_pid()
    if pid is not None:
        env = _environ_of(pid)
        for var in _VARS:
            if not os.environ.get(var) and env.get(var):
                os.environ[var] = env[var]

    # last-resort defaults, same ones the old shell script used
    os.environ.setdefault("DISPLAY", ":0")
    os.environ.setdefault(
        "DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/user/%d/bus" % os.getuid()
    )
