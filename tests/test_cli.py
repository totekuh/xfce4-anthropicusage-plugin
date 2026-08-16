import json

import pytest

from anthropic_usage import cli, client


@pytest.fixture
def use_cfg(cfg, monkeypatch):
    """Point cli.load_config() at the test Config instead of reading real env/files."""
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    return cfg


def test_json_mode_prints_raw_payload(use_cfg, monkeypatch, capsys):
    payload = {"five_hour": {"utilization": 1}}
    monkeypatch.setattr(client, "fetch_usage", lambda cfg: (payload, None))
    cli.main(["--json"])
    out = capsys.readouterr().out
    assert json.loads(out) == payload


def test_json_mode_no_data_prints_reason(use_cfg, monkeypatch, capsys):
    monkeypatch.setattr(client, "fetch_usage", lambda cfg: (None, "offline"))
    cli.main(["--json"])
    out = capsys.readouterr().out
    assert "offline" in out


def test_default_mode_emits_genmon_xml(use_cfg, monkeypatch, capsys):
    payload = {"five_hour": {"utilization": 4.0}, "seven_day": {"utilization": 30.0}}
    monkeypatch.setattr(client, "fetch_usage", lambda cfg: (payload, None))
    cli.main([])
    out = capsys.readouterr().out
    assert "<img>" in out
    assert "<tool>" in out
    assert "5h: 4%" in out
    assert "Weekly: 30%" in out


def test_png_mode_prints_png_path(use_cfg, monkeypatch, capsys):
    payload = {"five_hour": {"utilization": 4.0}, "seven_day": {"utilization": 30.0}}
    monkeypatch.setattr(client, "fetch_usage", lambda cfg: (payload, None))
    cli.main(["--png"])
    out = capsys.readouterr().out.strip()
    assert out == use_cfg.png_path


def test_auth_dead_token_renders_alert_and_reports_err(use_cfg, monkeypatch, capsys):
    monkeypatch.setattr(client, "fetch_usage", lambda cfg: (None, "auth"))
    cli.main([])
    out = capsys.readouterr().out
    assert "Claude token expired" in out


def test_no_token_renders_alert(use_cfg, monkeypatch, capsys):
    monkeypatch.setattr(client, "fetch_usage", lambda cfg: (None, "no-token"))
    cli.main([])
    out = capsys.readouterr().out
    assert "No Claude login found" in out


def test_json_and_png_are_mutually_exclusive(use_cfg):
    with pytest.raises(SystemExit):
        cli.main(["--json", "--png"])
