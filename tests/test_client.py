import io
import json
import time
import urllib.error
from email.message import Message

import pytest

from anthropic_usage import cache, client


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(url, code, retry_after=None):
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError(url, code, "error", hdrs, None)


def test_fetch_usage_success_caches_and_clears_backoff(cfg, monkeypatch):
    payload = {"five_hour": {"utilization": 4.0}, "seven_day": {"utilization": 30.0}}
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: FakeResponse(json.dumps(payload).encode()))

    data, err = client.fetch_usage(cfg)

    assert err is None
    assert data == payload
    cached, fetched_at = cache.load_cache(cfg)
    assert cached == payload
    assert fetched_at > 0
    assert cache.read_backoff(cfg) == 0.0


def test_fetch_usage_sends_bearer_token(cfg, monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["auth"] = req.get_header("Authorization")
        return FakeResponse(b"{}")

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    client.fetch_usage(cfg)
    assert captured["auth"] == "Bearer test-token"


def test_fetch_usage_no_credentials_file(cfg, monkeypatch):
    import dataclasses
    missing_cfg = dataclasses.replace(cfg, cred_path=str(cfg.cache_dir) + "/nope.json")
    data, err = client.fetch_usage(missing_cfg)
    assert data is None
    assert err == "no-token"


def _write_creds(cfg, expires_at_ms):
    import pathlib
    pathlib.Path(cfg.cred_path).write_text(json.dumps(
        {"claudeAiOauth": {"accessToken": "test-token", "expiresAt": expires_at_ms}}))


def test_fetch_usage_expired_token_skips_network(cfg, monkeypatch):
    _write_creds(cfg, (time.time() - 60) * 1000)

    def fail_if_called(req, timeout):
        raise AssertionError("network should not be hit with an expired token")

    monkeypatch.setattr(client.urllib.request, "urlopen", fail_if_called)
    data, err = client.fetch_usage(cfg)
    assert data is None
    assert err == "auth"


def test_fetch_usage_unexpired_token_still_fetches(cfg, monkeypatch):
    _write_creds(cfg, (time.time() + 3600) * 1000)
    payload = {"five_hour": {"utilization": 4.0}}
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: FakeResponse(json.dumps(payload).encode()))
    data, err = client.fetch_usage(cfg)
    assert err is None
    assert data == payload


def test_fetch_usage_401_is_auth_error(cfg, monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: (_ for _ in ()).throw(http_error(cfg.usage_url, 401)))
    data, err = client.fetch_usage(cfg)
    assert data is None
    assert err == "auth"


def test_fetch_usage_403_is_auth_error(cfg, monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: (_ for _ in ()).throw(http_error(cfg.usage_url, 403)))
    data, err = client.fetch_usage(cfg)
    assert err == "auth"


def test_fetch_usage_429_sets_backoff_floor(cfg, monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: (_ for _ in ()).throw(http_error(cfg.usage_url, 429)))
    data, err = client.fetch_usage(cfg)
    assert data is None
    assert err == "http-429"
    until = cache.read_backoff(cfg)
    assert until >= time.time() + cfg.backoff_floor - 1


def test_fetch_usage_429_honors_larger_retry_after(cfg, monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: (_ for _ in ()).throw(http_error(cfg.usage_url, 429, retry_after=900)))
    client.fetch_usage(cfg)
    until = cache.read_backoff(cfg)
    assert until >= time.time() + 899


def test_fetch_usage_other_http_error(cfg, monkeypatch):
    monkeypatch.setattr(client.urllib.request, "urlopen",
                         lambda req, timeout: (_ for _ in ()).throw(http_error(cfg.usage_url, 500)))
    data, err = client.fetch_usage(cfg)
    assert data is None
    assert err == "http-500"


def test_fetch_usage_network_error_is_offline(cfg, monkeypatch):
    def boom(req, timeout):
        raise OSError("network unreachable")
    monkeypatch.setattr(client.urllib.request, "urlopen", boom)
    data, err = client.fetch_usage(cfg)
    assert data is None
    assert err == "offline"


def test_fetch_usage_active_backoff_skips_network_entirely(cfg, monkeypatch):
    cache.set_backoff(cfg, 300)

    def fail_if_called(req, timeout):
        raise AssertionError("network should not be hit during an active back-off window")

    monkeypatch.setattr(client.urllib.request, "urlopen", fail_if_called)
    data, err = client.fetch_usage(cfg)
    assert data is None
    assert err == "backoff"
