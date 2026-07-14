"""webharvest package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("webharvest")
except PackageNotFoundError:  # pragma: no cover - local source tree fallback
    __version__ = "0.0.0"
