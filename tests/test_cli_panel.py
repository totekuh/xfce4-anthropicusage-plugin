"""Tests for the `anthropic-usage panel ...` argument handling and dispatch."""

import pytest

from anthropic_usage import cli, panel as panel_mod


@pytest.fixture
def stub(monkeypatch, cfg):
    """Neutralise everything the panel subcommands actually touch."""
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    monkeypatch.setattr(cli, "ensure_session_env", lambda: None)
    calls = {}
    monkeypatch.setattr(panel_mod, "install",
                        lambda c, p, period=None: calls.update(install=(p, period)) or "installed")
    monkeypatch.setattr(panel_mod, "uninstall",
                        lambda c, p: calls.update(uninstall=p) or "uninstalled")
    monkeypatch.setattr(panel_mod, "status", lambda c, p: "status-output")
    monkeypatch.setattr(panel_mod, "logs", lambda c, n: "logs-output-%d" % n)
    monkeypatch.setattr(panel_mod, "reload_panel", lambda: True)
    monkeypatch.setattr(panel_mod, "restart_panel", lambda: True)
    return calls


def test_bare_invocation_is_still_the_widget(monkeypatch, cfg, capsys):
    """genmon runs the binary with no arguments; that must not become a
    subcommand parse error."""
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    from anthropic_usage import client
    monkeypatch.setattr(client, "fetch_usage",
                        lambda c: ({"five_hour": {"utilization": 1}}, None))
    cli.main([])
    assert "<img>" in capsys.readouterr().out


def test_install_dispatches_with_defaults(stub, capsys):
    cli.main(["panel", "install"])
    assert stub["install"] == ("panel-1", panel_mod.DEFAULT_PERIOD_MS)
    assert "installed" in capsys.readouterr().out


def test_install_accepts_explicit_period_and_panel(stub):
    cli.main(["panel", "--panel", "panel-2", "install", "--period", "600000"])
    assert stub["install"] == ("panel-2", 600000)


def test_empty_env_vars_fall_back_to_defaults(stub, monkeypatch):
    """Regression: `make` exports PERIOD/PANEL even when unset, handing us an
    empty string, which int('') used to blow up on."""
    monkeypatch.setenv("PERIOD", "")
    monkeypatch.setenv("PANEL", "")
    cli.main(["panel", "install"])
    assert stub["install"] == ("panel-1", panel_mod.DEFAULT_PERIOD_MS)


def test_env_vars_are_honoured_when_set(stub, monkeypatch):
    monkeypatch.setenv("PERIOD", "60000")
    monkeypatch.setenv("PANEL", "panel-3")
    cli.main(["panel", "install"])
    assert stub["install"] == ("panel-3", 60000)


def test_uninstall_dispatches(stub, capsys):
    cli.main(["panel", "uninstall"])
    assert stub["uninstall"] == "panel-1"
    assert "uninstalled" in capsys.readouterr().out


def test_status_dispatches(stub, capsys):
    cli.main(["panel", "status"])
    assert "status-output" in capsys.readouterr().out


def test_logs_default_count(stub, capsys):
    cli.main(["panel", "logs"])
    assert "logs-output-40" in capsys.readouterr().out


def test_logs_custom_count(stub, capsys):
    cli.main(["panel", "logs", "-n", "5"])
    assert "logs-output-5" in capsys.readouterr().out


def test_reload_and_restart_report_success(stub, capsys):
    cli.main(["panel", "reload"])
    cli.main(["panel", "restart"])
    out = capsys.readouterr().out
    assert "panel reloaded." in out
    assert "panel restarted." in out


def test_restart_reports_failure(stub, monkeypatch, capsys):
    monkeypatch.setattr(panel_mod, "restart_panel", lambda: False)
    cli.main(["panel", "restart"])
    assert "FAILED" in capsys.readouterr().out


def test_panel_error_exits_nonzero_with_a_message(stub, monkeypatch):
    def boom(cfg, panel, period=None):
        raise panel_mod.PanelError("could not read plugin-ids")
    monkeypatch.setattr(panel_mod, "install", boom)

    with pytest.raises(SystemExit) as exc:
        cli.main(["panel", "install"])
    assert "could not read plugin-ids" in str(exc.value)


def test_panel_requires_an_action(stub):
    with pytest.raises(SystemExit):
        cli.main(["panel"])
