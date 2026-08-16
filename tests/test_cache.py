import time

from anthropic_usage import cache


def test_save_and_load_cache_round_trip(cfg):
    cache.save_cache(cfg, {"five_hour": {"utilization": 42}})
    data, fetched_at = cache.load_cache(cfg)
    assert data == {"five_hour": {"utilization": 42}}
    assert fetched_at > 0


def test_load_cache_missing_returns_none(cfg):
    data, fetched_at = cache.load_cache(cfg)
    assert data is None
    assert fetched_at == 0


def test_load_cache_corrupt_file_returns_none(cfg):
    import os
    os.makedirs(cfg.cache_dir, exist_ok=True)
    with open(cfg.cache_json, "w") as f:
        f.write("not json")
    data, fetched_at = cache.load_cache(cfg)
    assert data is None
    assert fetched_at == 0


def test_backoff_default_is_zero(cfg):
    assert cache.read_backoff(cfg) == 0.0


def test_backoff_set_then_read_is_in_the_future(cfg):
    cache.set_backoff(cfg, 300)
    until = cache.read_backoff(cfg)
    assert until > time.time()
    assert until <= time.time() + 301


def test_backoff_clear_resets_to_zero(cfg):
    cache.set_backoff(cfg, 300)
    cache.clear_backoff(cfg)
    assert cache.read_backoff(cfg) == 0.0


def test_backoff_clear_when_absent_does_not_raise(cfg):
    cache.clear_backoff(cfg)  # no .backoff file exists yet


def test_log_event_writes_a_line(cfg):
    cache.log_event(cfg, "hello world")
    with open(cfg.log_path) as f:
        content = f.read()
    assert "hello world" in content


def test_log_event_rotates_when_over_cap(cfg):
    import dataclasses
    small_cfg = dataclasses.replace(cfg, log_cap=100)
    for i in range(50):
        cache.log_event(small_cfg, "line %d - padding to grow the file" % i)
    with open(small_cfg.log_path) as f:
        lines = f.readlines()
    # rotation halves the file, so we shouldn't have accumulated all 50 lines
    assert len(lines) < 50
    assert "line 49" in lines[-1]
