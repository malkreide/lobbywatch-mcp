"""Single source of truth for the package version.

A separate module on purpose: `__init__.py` imports `client`, which imports
`config` — deriving the version in `__init__` and reading it back from `config`
would mean reasoning about a partially initialised package. This module imports
nothing from the package, so both can depend on it without a cycle.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    # Read from the installed distribution metadata, built from pyproject.toml.
    # Hand-maintained literals had drifted: pyproject said 0.3.4, __init__ said
    # 0.1.0 and the User-Agent said 0.3.1. A value nobody has to remember to
    # bump cannot go stale.
    PACKAGE_VERSION = _distribution_version("lobbywatch-mcp")
except PackageNotFoundError:
    # Source tree without an install. Deliberately not a plausible-looking
    # number: an obviously non-release marker beats a wrong version on the wire.
    PACKAGE_VERSION = "0.0.0+source"
