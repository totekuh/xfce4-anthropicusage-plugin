"""Tests for scraping session vars out of a running XFCE process."""

import subprocess

import pytest

from anthropic_usage import session


def fake_pgrep(pid=None):
    def run(cmd, **kwargs):
        out = "%d\n" % pid if pid is not None else ""
        return subprocess.CompletedProcess(cmd, 0 if pid else 1, stdout=out, stderr="")
    return run


def write_environ(tmp_path, pid, mapping):
    """Lay down a fake /proc/<pid>/environ and point the module at it."""
    proc_dir = tmp_path / str(pid)
    proc_dir.mkdir(parents=True)
    blob = b"\0".join(b"%s=%s" % (k.encode(), v.encode()) for k, v in mapping.items())
    (proc_dir / "environ").write_bytes(blob + b"\0")
    return str(proc_dir / "environ")


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY"):
        monkeypatch.delenv(var, raising=False)


def test_does_nothing_when_everything_is_already_set(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":9")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/keep/me")
    monkeypatch.setenv("XAUTHORITY", "/keep/xauth")

    def explode(*a, **k):
        raise AssertionError("should not have gone looking for a session")
    monkeypatch.setattr(session.subprocess, "run", explode)

    session.ensure_session_env()
    import os
    assert os.environ["DISPLAY"] == ":9"


def test_scrapes_missing_vars_from_the_session_process(monkeypatch, tmp_path, clean_env):
    path = write_environ(tmp_path, 4242, {
        "DISPLAY": ":1",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "XAUTHORITY": "/home/u/.Xauthority",
        "IRRELEVANT": "ignored",
    })
    monkeypatch.setattr(session.subprocess, "run", fake_pgrep(4242))
    monkeypatch.setattr(session, "_environ_of",
                        lambda pid: session._parse_environ(open(path, "rb").read()))

    session.ensure_session_env()

    import os
    assert os.environ["DISPLAY"] == ":1"
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"
    assert os.environ["XAUTHORITY"] == "/home/u/.Xauthority"


def test_does_not_overwrite_a_var_we_already_have(monkeypatch, tmp_path, clean_env):
    monkeypatch.setenv("DISPLAY", ":mine")
    path = write_environ(tmp_path, 1, {"DISPLAY": ":theirs",
                                       "DBUS_SESSION_BUS_ADDRESS": "unix:path=/theirs"})
    monkeypatch.setattr(session.subprocess, "run", fake_pgrep(1))
    monkeypatch.setattr(session, "_environ_of",
                        lambda pid: session._parse_environ(open(path, "rb").read()))

    session.ensure_session_env()

    import os
    assert os.environ["DISPLAY"] == ":mine"
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/theirs"


def test_falls_back_to_defaults_when_no_session_process(monkeypatch, clean_env):
    monkeypatch.setattr(session.subprocess, "run", fake_pgrep(None))
    session.ensure_session_env()

    import os
    assert os.environ["DISPLAY"] == ":0"
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"].startswith("unix:path=/run/user/")


def test_survives_an_unreadable_proc_entry(monkeypatch, clean_env):
    monkeypatch.setattr(session.subprocess, "run", fake_pgrep(999999))
    session.ensure_session_env()  # /proc/999999/environ won't exist

    import os
    assert os.environ["DISPLAY"] == ":0"


def test_survives_pgrep_being_absent(monkeypatch, clean_env):
    def no_pgrep(*a, **k):
        raise OSError("no pgrep here")
    monkeypatch.setattr(session.subprocess, "run", no_pgrep)

    session.ensure_session_env()

    import os
    assert os.environ["DISPLAY"] == ":0"


# --- environ parsing ---------------------------------------------------------
def test_parse_environ_splits_nul_separated_pairs():
    blob = b"A=1\0B=two\0"
    assert session._parse_environ(blob) == {"A": "1", "B": "two"}


def test_parse_environ_keeps_values_containing_equals():
    blob = b"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus\0"
    parsed = session._parse_environ(blob)
    assert parsed["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/run/user/1000/bus"


def test_parse_environ_ignores_entries_without_equals():
    assert session._parse_environ(b"JUNK\0A=1\0") == {"A": "1"}
