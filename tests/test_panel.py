"""Tests for the panel surgery — the code that must never wipe someone's tray."""

import subprocess

import pytest

from anthropic_usage import panel


BIN = "/home/u/.local/bin/anthropic-usage"


class FakeXfconf:
    """In-memory stand-in for xfconf-query + the panel process.

    Models just enough to exercise the array logic: a property store, the
    plugin-ids array, and a switch to make array writes fail on demand.
    """

    def __init__(self, array=None, props=None):
        self.array = list(array or [])
        self.props = dict(props or {})
        self.calls = []
        # how many upcoming array writes should fail; -1 means "all of them"
        self.fail_array_writes = 0
        self.array_prop = "/panels/panel-1/plugin-ids"

    def run(self, cmd):
        self.calls.append(cmd)
        if cmd[0] == "pgrep":
            return self._done(0, "1234\n")
        if cmd[0] in ("xfce4-panel", "pkill", "setsid"):
            return self._done(0, "")
        if cmd[0] == "pipx":
            return self._done(0, "/home/u/.local/bin\n")
        if cmd[0] != "xfconf-query":
            return self._done(0, "")
        return self._xfconf(cmd[3:])  # strip: xfconf-query -c xfce4-panel

    def _xfconf(self, args):
        if args and args[0] == "-lv":
            lines = ["%s   %s" % (p, v) for p, v in sorted(self.props.items())
                     if not p.endswith("/command")]
            return self._done(0, "\n".join(lines) + "\n")
        if args and args[0] == "-l":
            return self._done(0, "\n".join(sorted(self.props)) + "\n")

        prop = args[args.index("-p") + 1] if "-p" in args else None
        if prop is None:
            return self._done(1, "")

        if "-rR" in args:
            if prop == self.array_prop:
                self.array = []
            for key in [k for k in self.props if k == prop or k.startswith(prop + "/")]:
                del self.props[key]
            return self._done(0, "")

        if "-s" in args:  # a write
            values = [args[i + 1] for i, a in enumerate(args) if a == "-s"]
            if prop == self.array_prop:
                if self.fail_array_writes:
                    self.fail_array_writes -= 1
                    return self._done(1, "boom")
                self.array = [int(v) for v in values]
            else:
                self.props[prop] = values[0]
            return self._done(0, "")

        # a read
        if prop == self.array_prop:
            # real xfconf-query prints a header before the values, and its item
            # count must not be mistaken for a plugin id
            body = "\n".join(str(i) for i in self.array)
            header = "Value is an array with %d items:" % len(self.array)
            return self._done(0, "%s\n%s\n" % (header, body))
        if prop in self.props:
            return self._done(0, self.props[prop] + "\n")
        return self._done(1, "")

    @staticmethod
    def _done(rc, out):
        return subprocess.CompletedProcess([], rc, stdout=out, stderr="")


@pytest.fixture
def fake(monkeypatch):
    fx = FakeXfconf(array=[1, 2, 3])
    monkeypatch.setattr(panel, "_run", fx.run)
    monkeypatch.setattr(panel, "resolve_bin", lambda: BIN)
    monkeypatch.setattr(panel, "reload_panel", lambda: True)
    return fx


# --- array primitives --------------------------------------------------------
def test_get_array_parses_ints(fake):
    assert panel.get_array("panel-1") == [1, 2, 3]


def test_get_array_ignores_the_header_item_count(fake):
    # regression: the count in "Value is an array with N items:" was being
    # parsed as a plugin id, corrupting the panel with a "(null)" plugin
    fake.array = [11, 12, 13, 14, 15, 16, 17]
    assert panel.get_array("panel-1") == [11, 12, 13, 14, 15, 16, 17]


def test_install_does_not_inject_bogus_ids(fake, tmp_path):
    fake.array = [11, 12, 13, 14, 15, 16, 17]  # 7 items -> header says "7"
    panel.install(fake_cfg(tmp_path), "panel-1")
    assert fake.array[:7] == [11, 12, 13, 14, 15, 16, 17]
    assert len(fake.array) == 8  # exactly one new plugin, no header junk


def test_set_array_refuses_empty(fake):
    with pytest.raises(panel.PanelError, match="empty"):
        panel.set_array("panel-1", [])
    assert fake.array == [1, 2, 3]  # untouched


def test_set_array_writes_all_ids(fake):
    panel.set_array("panel-1", [4, 5])
    assert fake.array == [4, 5]


def test_set_array_raises_when_write_fails(fake):
    fake.fail_array_writes = 1
    with pytest.raises(panel.PanelError):
        panel.set_array("panel-1", [4, 5])


# --- install -----------------------------------------------------------------
def test_install_appends_without_dropping_existing(fake):
    msg = panel.install(fake_cfg(), "panel-1")
    assert fake.array[:3] == [1, 2, 3]
    assert len(fake.array) == 4
    assert "loaded as" in msg


def test_install_writes_genmon_properties(fake):
    panel.install(fake_cfg(), "panel-1")
    new = "/plugins/plugin-%d" % fake.array[-1]
    assert fake.props[new] == "genmon"
    assert fake.props["%s/command" % new] == BIN
    assert fake.props["%s/update-period" % new] == str(panel.DEFAULT_PERIOD_MS)


def test_install_honors_custom_period(fake):
    panel.install(fake_cfg(), "panel-1", period=600000)
    new = "/plugins/plugin-%d" % fake.array[-1]
    assert fake.props["%s/update-period" % new] == "600000"


def test_install_rolls_back_when_array_write_fails(fake, tmp_path):
    cfg = fake_cfg(tmp_path)
    fake.fail_array_writes = 1  # the attach fails; the rollback write succeeds
    with pytest.raises(panel.PanelError, match="rolled back"):
        panel.install(cfg, "panel-1")
    assert panel.get_array("panel-1") == [1, 2, 3]  # restored from the snapshot


def test_install_reports_loudly_when_rollback_also_fails(fake, tmp_path):
    cfg = fake_cfg(tmp_path)
    fake.fail_array_writes = -1  # every write fails, including the rollback
    with pytest.raises(panel.PanelError, match="ROLLBACK ALSO FAILED"):
        panel.install(cfg, "panel-1")


def test_install_refuses_when_array_unreadable(fake, tmp_path):
    fake.array = []
    with pytest.raises(panel.PanelError, match="could not read"):
        panel.install(fake_cfg(tmp_path), "panel-1")


def test_install_when_already_present_refreshes_command(fake, tmp_path):
    fake.props["/plugins/plugin-9"] = "genmon"
    fake.props["/plugins/plugin-9/command"] = "/old/path/anthropic-usage"
    fake.array = [1, 2, 9]

    msg = panel.install(fake_cfg(tmp_path), "panel-1")

    assert fake.props["/plugins/plugin-9/command"] == BIN
    assert fake.array == [1, 2, 9]  # no new plugin added
    assert "already loaded" in msg


# --- uninstall ---------------------------------------------------------------
def test_uninstall_drops_only_ours(fake, tmp_path):
    fake.props["/plugins/plugin-2"] = "genmon"
    fake.props["/plugins/plugin-2/command"] = BIN

    msg = panel.uninstall(fake_cfg(tmp_path), "panel-1")

    assert fake.array == [1, 3]
    assert "/plugins/plugin-2" in msg
    assert "/plugins/plugin-2" not in fake.props  # properties reset too


def test_uninstall_noop_when_not_installed(fake, tmp_path):
    msg = panel.uninstall(fake_cfg(tmp_path), "panel-1")
    assert "nothing to remove" in msg
    assert fake.array == [1, 2, 3]


def test_uninstall_refuses_to_empty_the_panel(fake, tmp_path):
    fake.array = [7]
    fake.props["/plugins/plugin-7"] = "genmon"
    fake.props["/plugins/plugin-7/command"] = BIN

    with pytest.raises(panel.PanelError, match="last plugin"):
        panel.uninstall(fake_cfg(tmp_path), "panel-1")
    assert fake.array == [7]


# --- find_ours ---------------------------------------------------------------
def test_find_ours_ignores_other_genmon_plugins(fake):
    fake.props["/plugins/plugin-2"] = "genmon"
    fake.props["/plugins/plugin-2/command"] = "/usr/bin/some-other-monitor"
    fake.props["/plugins/plugin-3"] = "genmon"
    fake.props["/plugins/plugin-3/command"] = BIN

    assert panel.find_ours() == ["/plugins/plugin-3"]


def test_find_ours_empty_when_none_match(fake):
    assert panel.find_ours() == []


# --- helpers -----------------------------------------------------------------
def fake_cfg(tmp_path=None):
    from anthropic_usage.config import Config
    import tempfile
    cache_dir = str(tmp_path) if tmp_path else tempfile.mkdtemp()
    return Config(
        cred_path="/nonexistent",
        usage_url="https://example.invalid",
        cache_dir=cache_dir,
        width=330, height=26, labels=["5h", "Weekly"],
    )
