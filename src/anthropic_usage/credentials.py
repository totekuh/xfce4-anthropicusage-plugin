"""Reading the Claude Code OAuth access token off disk."""

import json

from .config import Config


def read_token(cfg: Config) -> str:
    with open(cfg.cred_path) as f:
        return json.load(f)["claudeAiOauth"]["accessToken"]
