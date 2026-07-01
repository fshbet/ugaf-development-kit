"""Clipboard abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import ModuleType
from typing import Any

from ugaf.platform.exceptions import AdapterNotAvailableError

__all__ = [
    "ClipboardProvider",
    "WindowsClipboardProvider",
]

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


class ClipboardProvider(ABC):
    """Abstract interface for reading and writing the system clipboard."""

    @abstractmethod
    def read_text(self) -> str:
        """Return the current text contents of the clipboard.

        Returns:
            The clipboard text, or an empty string if the clipboard
            does not currently hold text.

        Raises:
            AdapterNotAvailableError: If the underlying OS API is
                unavailable on this host.

        """

    @abstractmethod
    def write_text(self, text: str) -> None:
        """Replace the clipboard contents with *text*.

        Args:
            text: The text to place on the clipboard.

        Raises:
            AdapterNotAvailableError: If the underlying OS API is
                unavailable on this host.

        """


class WindowsClipboardProvider(ClipboardProvider):
    """Clipboard provider backed by the Win32 clipboard API via ``ctypes``.

    Uses ``CF_UNICODETEXT`` exclusively; no dependency beyond the
    Python standard library. Handle-returning Win32 functions
    (``GlobalAlloc``, ``GlobalLock``, ``GetClipboardData``) must have
    an explicit pointer-sized ``restype`` — ``ctypes``' default
    ``c_int`` restype truncates 64-bit handles on Win64 and silently
    corrupts them.
    """

    def read_text(self) -> str:
        """Read ``CF_UNICODETEXT`` from the Windows clipboard.

        Raises:
            AdapterNotAvailableError: If not running on Windows or the
                clipboard cannot be opened.

        """
        ctypes = self._require_ctypes()
        user32, kernel32 = self._configure_prototypes(ctypes)

        if not user32.OpenClipboard(None):
            raise AdapterNotAvailableError("Unable to open the Windows clipboard")
        try:
            handle = user32.GetClipboardData(_CF_UNICODETEXT)
            if not handle:
                return ""
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            try:
                return str(ctypes.wstring_at(pointer))
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def write_text(self, text: str) -> None:
        """Write *text* to the Windows clipboard as ``CF_UNICODETEXT``.

        Raises:
            AdapterNotAvailableError: If not running on Windows, the
                clipboard cannot be opened, or memory allocation
                fails.

        """
        ctypes = self._require_ctypes()
        user32, kernel32 = self._configure_prototypes(ctypes)

        data = (text + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not handle:
            raise AdapterNotAvailableError("GlobalAlloc failed while writing to the clipboard")

        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise AdapterNotAvailableError("GlobalLock failed while writing to the clipboard")
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)

        if not user32.OpenClipboard(None):
            raise AdapterNotAvailableError("Unable to open the Windows clipboard")
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(_CF_UNICODETEXT, handle)
        finally:
            user32.CloseClipboard()

    @staticmethod
    def _require_ctypes() -> ModuleType:
        """Return the ``ctypes`` module, verifying Windows is available."""
        import ctypes

        if getattr(ctypes, "windll", None) is None:
            raise AdapterNotAvailableError(
                "WindowsClipboardProvider requires Windows (ctypes.windll)"
            )
        return ctypes

    @staticmethod
    def _configure_prototypes(ctypes_module: ModuleType) -> tuple[Any, Any]:
        """Set explicit ``argtypes``/``restype`` for the Win32 calls used here.

        Without this, ``ctypes`` assumes a 32-bit ``c_int`` return
        type for every function, which truncates pointer-sized handles
        on 64-bit Windows and causes ``GlobalLock``/``GetClipboardData``
        to silently receive corrupted handles.
        """
        user32 = ctypes_module.windll.user32
        kernel32 = ctypes_module.windll.kernel32

        user32.OpenClipboard.argtypes = [ctypes_module.c_void_p]
        user32.OpenClipboard.restype = ctypes_module.c_int
        user32.CloseClipboard.restype = ctypes_module.c_int
        user32.EmptyClipboard.restype = ctypes_module.c_int
        user32.GetClipboardData.argtypes = [ctypes_module.c_uint]
        user32.GetClipboardData.restype = ctypes_module.c_void_p
        user32.SetClipboardData.argtypes = [ctypes_module.c_uint, ctypes_module.c_void_p]
        user32.SetClipboardData.restype = ctypes_module.c_void_p

        kernel32.GlobalAlloc.argtypes = [ctypes_module.c_uint, ctypes_module.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes_module.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes_module.c_void_p]
        kernel32.GlobalLock.restype = ctypes_module.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes_module.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes_module.c_int

        return user32, kernel32
