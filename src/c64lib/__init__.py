"""c64-tools: AI-oriented toolset for Commodore 64 development on VICE."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the version in pyproject.toml, read from the
    # installed package metadata. Nothing here to keep in sync by hand.
    __version__ = version("c64-tools")
except PackageNotFoundError:  # running from an uninstalled checkout
    __version__ = "0.0.0+unknown"
