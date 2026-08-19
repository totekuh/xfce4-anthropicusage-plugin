import json

import pytest

from anthropic_usage.config import Config


@pytest.fixture
def cfg(tmp_path):
    cred_path = tmp_path / "credentials.json"
    cred_path.write_text(json.dumps({"claudeAiOauth": {"accessToken": "test-token"}}))
    return Config(
        cred_path=str(cred_path),
        usage_url="https://api.anthropic.com/api/oauth/usage",
        cache_dir=str(tmp_path / "cache"),
        width=330,
        height=26,
        labels=["5h", "Weekly"],
        user_agent="claude-cli/9.9.9 (external, cli)",
        client_app="cli",
        client_platform="claude_code_cli",
    )
