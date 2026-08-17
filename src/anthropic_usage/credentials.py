"""Reading the Claude Code OAuth access token off disk."""

import json
from typing import Optional, Tuple

from .config import Config


def read_credentials(cfg: Config) -> Tuple[str, Optional[float]]:
    """Return (access_token, expires_at_epoch_seconds).

    Claude Code stores expiresAt in milliseconds; older files may not have it
    at all, in which case the expiry is None ("unknown, just try the call").
    """
    with open(cfg.cred_path) as f:
        oauth = json.load(f)["claudeAiOauth"]
    token = oauth["accessToken"]
    raw = oauth.get("expiresAt")
    try:
        expires_at = float(raw) / 1000.0 if raw is not None else None
    except (TypeError, ValueError):
        expires_at = None
    return token, expires_at


def read_token(cfg: Config) -> str:
    return read_credentials(cfg)[0]
