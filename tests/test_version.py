"""Guards against the version drift that made the User-Agent lie.

Three numbers had come apart: `pyproject.toml` said 0.3.4,
`__init__.__version__` said 0.1.0, and `config.USER_AGENT` said 0.3.1 — the
value Lobbywatch's server logs actually saw.

These tests fail if anyone reintroduces a literal.
"""

import tomllib
from pathlib import Path

import lobbywatch_mcp
from lobbywatch_mcp import config

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def test_version_matches_pyproject():
    assert lobbywatch_mcp.__version__ == _pyproject_version()


def test_user_agent_carries_the_real_version():
    expected = (
        f"lobbywatch-mcp/{_pyproject_version()} "
        "(+https://github.com/malkreide/lobbywatch-mcp)"
    )
    assert config.USER_AGENT == expected


def test_user_agent_is_not_a_source_checkout_marker():
    assert "+source" not in config.USER_AGENT
