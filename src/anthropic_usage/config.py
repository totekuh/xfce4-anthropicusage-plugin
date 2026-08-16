"""Runtime configuration, read from the environment once per invocation."""

import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Config:
    cred_path: str
    usage_url: str
    cache_dir: str
    width: int
    height: int
    labels: List[str]

    log_cap: int = 256 * 1024  # bytes; halve the log when it grows past this
    backoff_floor: int = 300   # seconds; floor for the 429 back-off window

    @property
    def cache_json(self) -> str:
        return os.path.join(self.cache_dir, "last.json")

    @property
    def png_path(self) -> str:
        return os.path.join(self.cache_dir, "widget.png")

    @property
    def log_path(self) -> str:
        return os.path.join(self.cache_dir, "widget.log")

    @property
    def backoff_path(self) -> str:
        return os.path.join(self.cache_dir, ".backoff")


def load_config() -> Config:
    cache_dir = os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
        "anthropic-usage",
    )
    return Config(
        cred_path=os.environ.get("ANTHRO_CRED", os.path.expanduser("~/.claude/.credentials.json")),
        usage_url="https://api.anthropic.com/api/oauth/usage",
        cache_dir=cache_dir,
        width=int(os.environ.get("ANTHRO_W", "330")),
        height=int(os.environ.get("ANTHRO_H", "26")),
        labels=os.environ.get("ANTHRO_LABELS", "5h,Weekly").split(","),
    )
