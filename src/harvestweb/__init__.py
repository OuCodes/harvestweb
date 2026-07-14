"""harvestweb package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("harvestweb")
except PackageNotFoundError:  # pragma: no cover - local source tree fallback
    __version__ = "0.0.0"
