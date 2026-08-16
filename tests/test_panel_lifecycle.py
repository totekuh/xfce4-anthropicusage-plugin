"""Tests for starting/reloading the panel process.

This is the half of panel.py that isn't xfconf surgery, and it's where the
"reported success for a panel that was about to die" bug lived.
"""

import subprocess

import pytest

from anthropic_usage import panel


class FakePanelProcess:
    """Models whether xfce4-panel is running, and what `-r` does to it.

    `reload_outcome` decides what happens when someone runs `xfce4-panel -r`:
      "survives"  -> stays up (the normal case)
      "dies"      -> goes down and stays down (needs a fresh start)
      "lingers"   -> reports up for `linger` more checks, then dies; this is
                     the re-exec window that made reload_panel lie.
    """

    def __init__(self, running=True, reload_outcome="survives", linger=1):
        self.running = running
        self.reload_outcome = reload_outcome
        self.linger = linger
        self.spawns = 0
        self.reloads = 0
        self.quits = 0

    def run(self, cmd):
        if cmd[0] == "pgrep":
            up = self.running
            if up and self.reload_outcome == "lingers":
                if self.linger > 0:
                    self.linger -= 1
                else:
                    self.running = False
                    up = False
            return self._done(0 if up else 1)
        if cmd[:2] == ["xfce4-panel", "-r"]:
            self.reloads += 1
            if self.reload_outcome == "dies":
                self.running = False
            return self._done(0)
        if cmd[:2] == ["xfce4-panel", "-q"]:
            self.quits += 1
            self.running = False
            return self._done(0)
        return self._done(0)

    def spawn(self, *args, **kwargs):
        self.spawns += 1
        self.running = True
        # a freshly started panel is a healthy one: whatever ailed the process
        # we just re-execed doesn't carry over to the new one
        self.reload_outcome = "survives"
        return None

    @staticmethod
    def _done(rc):
        return subprocess.CompletedProcess([], rc, stdout="", stderr="")


@pytest.fixture
def nosleep(monkeypatch):
    monkeypatch.setattr(panel.time, "sleep", lambda _s: None)


def wire(monkeypatch, proc):
    monkeypatch.setattr(panel, "_run", proc.run)
    monkeypatch.setattr(panel.subprocess, "Popen", proc.spawn)
    return proc


# --- panel_up ----------------------------------------------------------------
def test_panel_up_true_when_pgrep_succeeds(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=True))
    assert panel.panel_up() is True


def test_panel_up_false_when_pgrep_fails(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=False))
    assert panel.panel_up() is False


# --- reload ------------------------------------------------------------------
def test_reload_uses_r_and_does_not_spawn_a_second_panel(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=True, reload_outcome="survives"))
    assert panel.reload_panel() is True
    assert proc.reloads == 1
    assert proc.spawns == 0  # two instances would fight and one would die


def test_reload_starts_the_panel_when_r_kills_it(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=True, reload_outcome="dies"))
    assert panel.reload_panel() is True
    assert proc.spawns == 1


def test_reload_does_not_believe_a_lingering_pid(monkeypatch, nosleep):
    """Regression: `-r` re-execs, the old pid lingers, and an immediate check
    reported success for a panel that then died. It must end up actually up."""
    proc = wire(monkeypatch, FakePanelProcess(
        running=True, reload_outcome="lingers", linger=1))
    assert panel.reload_panel() is True
    assert proc.spawns == 1  # noticed the death and started a fresh one
    assert proc.running is True


def test_reload_starts_panel_when_it_was_already_down(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=False))
    assert panel.reload_panel() is True
    assert proc.reloads == 0  # never talk to a panel that isn't there (no D-Bus dialog)
    assert proc.spawns == 1


def test_reload_reports_failure_when_panel_will_not_start(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=False))
    proc.spawn = lambda *a, **k: None  # spawn does nothing; panel stays down
    monkeypatch.setattr(panel.subprocess, "Popen", proc.spawn)
    assert panel.reload_panel() is False


# --- restart -----------------------------------------------------------------
def test_restart_quits_then_starts(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=True))
    assert panel.restart_panel() is True
    assert proc.quits == 1
    assert proc.spawns == 1


def test_restart_just_starts_when_panel_is_down(monkeypatch, nosleep):
    proc = wire(monkeypatch, FakePanelProcess(running=False))
    assert panel.restart_panel() is True
    assert proc.quits == 0
    assert proc.spawns == 1


def test_start_panel_detaches_from_our_process_group(monkeypatch, nosleep):
    """Without start_new_session the panel dies with the `make` that spawned it."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs

    monkeypatch.setattr(panel, "_run", FakePanelProcess(running=False).run)
    monkeypatch.setattr(panel.subprocess, "Popen", fake_popen)
    panel._start_panel()

    assert captured["cmd"] == ["xfce4-panel"]
    assert captured["kwargs"]["start_new_session"] is True


# --- resolve_bin -------------------------------------------------------------
def test_resolve_bin_prefers_argv0_when_it_is_us(monkeypatch, tmp_path):
    shim = tmp_path / panel.APP_NAME
    shim.write_text("#!/bin/sh\n")
    shim.chmod(0o755)
    monkeypatch.setattr(panel.sys, "argv", [str(shim), "panel", "status"])
    assert panel.resolve_bin() == str(shim)


def test_resolve_bin_does_not_resolve_symlinks(monkeypatch, tmp_path):
    """The ~/.local/bin shim is a symlink into the pipx venv; baking the venv
    path into the panel is more fragile than baking the shim."""
    real = tmp_path / "venv-anthropic-usage"
    real.write_text("#!/bin/sh\n")
    real.chmod(0o755)
    shim = tmp_path / panel.APP_NAME
    shim.symlink_to(real)

    monkeypatch.setattr(panel.sys, "argv", [str(shim)])
    assert panel.resolve_bin() == str(shim)


def test_resolve_bin_falls_back_to_path_lookup(monkeypatch, tmp_path):
    found = tmp_path / panel.APP_NAME
    found.write_text("#!/bin/sh\n")
    found.chmod(0o755)
    monkeypatch.setattr(panel.sys, "argv", ["/usr/bin/python3"])
    monkeypatch.setattr(panel.shutil, "which", lambda _n: str(found))
    assert panel.resolve_bin() == str(found)


def test_resolve_bin_none_when_nothing_is_installed(monkeypatch, tmp_path):
    # HOME must point somewhere empty, or we find the real install on this box
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(panel.sys, "argv", ["/usr/bin/python3"])
    monkeypatch.setattr(panel.shutil, "which", lambda _n: None)
    monkeypatch.setattr(panel, "_run",
                        lambda _c: subprocess.CompletedProcess([], 1, stdout="", stderr=""))
    assert panel.resolve_bin() is None


def test_require_bin_raises_when_missing(monkeypatch):
    monkeypatch.setattr(panel, "resolve_bin", lambda: None)
    with pytest.raises(panel.PanelError, match="not installed"):
        panel.require_bin()


# --- status / logs -----------------------------------------------------------
def test_status_reports_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(panel, "find_ours", lambda: [])
    monkeypatch.setattr(panel, "panel_up", lambda: True)
    monkeypatch.setattr(panel, "resolve_bin", lambda: "/bin/x")
    out = panel.status(_cfg(tmp_path), "panel-1")
    assert "NOT installed" in out
    assert "running" in out


def test_status_reports_installed_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(panel, "find_ours", lambda: ["/plugins/plugin-7"])
    monkeypatch.setattr(panel, "panel_up", lambda: False)
    monkeypatch.setattr(panel, "resolve_bin", lambda: "/bin/x")
    out = panel.status(_cfg(tmp_path), "panel-1")
    assert "/plugins/plugin-7" in out
    assert "not running" in out


def test_logs_tails_the_file(tmp_path):
    cfg = _cfg(tmp_path)
    import os
    os.makedirs(cfg.cache_dir, exist_ok=True)
    with open(cfg.log_path, "w") as f:
        f.write("".join("line %d\n" % i for i in range(100)))
    out = panel.logs(cfg, 5)
    assert out.splitlines() == ["line %d" % i for i in range(95, 100)]


def test_logs_when_no_file_yet(tmp_path):
    assert "no log yet" in panel.logs(_cfg(tmp_path))


def _cfg(tmp_path):
    from anthropic_usage.config import Config
    return Config(
        cred_path="/nonexistent", usage_url="https://example.invalid",
        cache_dir=str(tmp_path), width=330, height=26, labels=["5h", "Weekly"],
    )
