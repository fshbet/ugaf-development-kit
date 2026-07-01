"""File system abstraction.

Most file-system operations are already portable through
:mod:`pathlib`; the abstraction here exists so that ``ugaf.core`` and
plugins depend on an injectable interface (mockable in tests, and
swappable for a future remote/virtual file system) rather than calling
``pathlib``/``os`` directly, not because every OS needs a bespoke
adapter at this level.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

__all__ = [
    "FileSystemProvider",
    "LocalFileSystemProvider",
]


class FileSystemProvider(ABC):
    """Abstract interface for file system operations."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Return whether *path* exists."""

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Read and return the full contents of *path*."""

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None:
        """Write *data* to *path*, creating parent directories as needed."""

    @abstractmethod
    def list_dir(self, path: str) -> list[str]:
        """Return the names of entries directly inside *path*."""

    @abstractmethod
    def make_dirs(self, path: str) -> None:
        """Create *path* and any missing parent directories."""

    @abstractmethod
    def remove(self, path: str) -> None:
        """Delete the file or directory at *path*.

        Directories are removed recursively.
        """


class LocalFileSystemProvider(FileSystemProvider):
    """File system provider backed by the local disk via :mod:`pathlib`."""

    def exists(self, path: str) -> bool:
        """Return whether *path* exists on the local file system."""
        return Path(path).exists()

    def read_bytes(self, path: str) -> bytes:
        """Read the full contents of *path* from the local file system."""
        return Path(path).read_bytes()

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write *data* to *path*, creating parent directories as needed."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def list_dir(self, path: str) -> list[str]:
        """Return sorted entry names directly inside *path*."""
        return sorted(entry.name for entry in Path(path).iterdir())

    def make_dirs(self, path: str) -> None:
        """Create *path* and any missing parent directories."""
        Path(path).mkdir(parents=True, exist_ok=True)

    def remove(self, path: str) -> None:
        """Delete the file or directory at *path*."""
        target = Path(path)
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
