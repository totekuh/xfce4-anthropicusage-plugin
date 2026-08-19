"""Runtime configuration, read from the environment once per invocation."""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

# Fallback when the local Claude Code install can't be found on disk.
FALLBACK_CLAUDE_VERSION = "2.1.235"


@dataclass(frozen=True)
class Config:
    cred_path: str
    usage_url: str
    cache_dir: str
    width: int
    height: int
    labels: List[str]
    # Claude Code's own client identity — the usage endpoint only answers
    # requests that carry it. Overridable via ANTHRO_UA (see load_config).
    user_agent: str = "claude-cli/%s (external, cli)" % FALLBACK_CLAUDE_VERSION
    client_app: str = "cli"
    client_platform: str = "claude_code_cli"

    log_cap: int = 256 * 1024   # bytes; halve the log when it grows past this
    backoff_floor: int = 300    # seconds; floor for the 429 back-off window
    forbidden_backoff: int = 1800  # seconds; sit out a 403 instead of retrying into a 429

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


def detect_claude_version() -> Optional[str]:
    """Newest version in the local Claude Code install, or None.

    Versions live one-file-per-release under ~/.local/share/claude/versions,
    named after the version itself, so the directory listing is the answer.
    """
    root = os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "claude", "versions",
    )
    try:
        names = [n for n in os.listdir(root) if re.match(r"^\d+(\.\d+)*$", n)]
    except OSError:
        return None
    if not names:
        return None
    return max(names, key=lambda n: tuple(int(x) for x in n.split(".")))


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
        user_agent=os.environ.get(
            "ANTHRO_UA",
            "claude-cli/%s (external, cli)" % (detect_claude_version() or FALLBACK_CLAUDE_VERSION),
        ),
        client_app="cli",
        client_platform="claude_code_cli",
    )
