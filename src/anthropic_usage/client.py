"""Fetching usage data from the Anthropic OAuth usage endpoint."""

import json
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

from . import cache
from .config import Config
from .credentials import read_credentials


def fetch_usage(cfg: Config) -> Tuple[Optional[dict], Optional[str]]:
    """Return (data_dict, error_str). error_str is None on success."""
    # honour a rate-limit back-off window without touching the network
    if cache.read_backoff(cfg) > time.time():
        return None, "backoff"

    try:
        token, expires_at = read_credentials(cfg)
    except Exception:
        cache.log_event(cfg, "no credentials at %s" % cfg.cred_path)
        return None, "no-token"

    # An expired token only ever earns a 401, and a run of 401s is what gets us
    # rate-limited into an hour-long back-off. Don't spend the request at all.
    if expires_at is not None and expires_at <= time.time():
        cache.log_event(cfg, "access token expired %ds ago; skipping the call"
                         % int(time.time() - expires_at))
        return None, "auth"

    req = urllib.request.Request(
        cfg.usage_url,
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "anthropic-usage-widget/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        cache.save_cache(cfg, data)
        cache.clear_backoff(cfg)
        u5 = (data.get("five_hour") or {}).get("utilization")
        u7 = (data.get("seven_day") or {}).get("utilization")
        cache.log_event(cfg, "200 ok  5h=%s%%  7d=%s%%" % (u5, u7))
        return data, None
    except urllib.error.HTTPError as e:
        retry_after = None
        try:
            retry_after = e.headers.get("Retry-After")
        except Exception:
            pass
        if e.code == 429:
            secs = int(retry_after) if (retry_after and retry_after.isdigit()) else 120
            secs = max(secs, cfg.backoff_floor)  # skip ticks after a 429 (>= poll period)
            cache.set_backoff(cfg, secs)
            cache.log_event(cfg, "HTTP 429 rate-limited; backing off %ds%s"
                             % (secs, " (Retry-After)" if retry_after else ""))
            return None, "http-429"
        if e.code in (401, 403):
            cache.log_event(cfg, "HTTP %d auth failure (token expired/invalid)" % e.code)
            return None, "auth"
        cache.log_event(cfg, "HTTP %d" % e.code)
        return None, "http-%d" % e.code
    except Exception as e:
        cache.log_event(cfg, "fetch error: %s" % e)
        return None, "offline"
