import importlib.metadata

__all__ = ["__version__"]

try:
    __version__ = importlib.metadata.version("tracemap")
except importlib.metadata.PackageNotFoundError:
    __version__ = "unknown"
