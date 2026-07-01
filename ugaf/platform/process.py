"""Process management abstraction."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DefaultProcessManager",
    "ProcessHandle",
    "ProcessManager",
]


@dataclass(frozen=True)
class ProcessHandle:
    """Opaque handle to a process started by a :class:`ProcessManager`.

    Attributes:
        pid: Operating system process identifier.
        command: The command that was executed.

    """

    pid: int
    command: list[str] = field(default_factory=list)


class ProcessManager(ABC):
    """Abstract interface for starting, monitoring, and stopping processes."""

    @abstractmethod
    def start(self, command: list[str], **kwargs: Any) -> ProcessHandle:
        """Start *command* as a new subprocess.

        Args:
            command: Argument vector to execute (no shell).
            **kwargs: Backend-specific extra options.

        Returns:
            A :class:`ProcessHandle` for the started process.

        """

    @abstractmethod
    def is_running(self, handle: ProcessHandle) -> bool:
        """Return whether the process referenced by *handle* is still running."""

    @abstractmethod
    def terminate(self, handle: ProcessHandle, timeout: float = 5.0) -> None:
        """Request graceful termination, escalating to a forced kill after *timeout*."""

    @abstractmethod
    def wait(self, handle: ProcessHandle, timeout: float | None = None) -> int:
        """Block until the process exits and return its exit code.

        Args:
            handle: The process handle to wait on.
            timeout: Maximum time in seconds to wait, or ``None`` to
                wait indefinitely.

        Raises:
            TimeoutError: If *timeout* elapses before the process
                exits.

        """


class DefaultProcessManager(ProcessManager):
    """Process manager backed by :mod:`subprocess`.

    ``subprocess.Popen`` is already cross-platform for the start/poll/
    terminate/wait operations exposed here, so a single default
    adapter is sufficient at this abstraction level. Keeps its own
    ``pid -> Popen`` mapping rather than attaching the live object to
    :class:`ProcessHandle`, so the handle stays a plain, serializable
    data value.
    """

    def __init__(self) -> None:
        """Initialize an empty pid-to-process mapping."""
        self._processes: dict[int, subprocess.Popen[bytes]] = {}

    def start(self, command: list[str], **kwargs: Any) -> ProcessHandle:
        """Start *command* via ``subprocess.Popen``."""
        popen = subprocess.Popen(command, **kwargs)  # noqa: S603
        self._processes[popen.pid] = popen
        return ProcessHandle(pid=popen.pid, command=list(command))

    def is_running(self, handle: ProcessHandle) -> bool:
        """Return whether the process has not yet exited."""
        popen = self._processes.get(handle.pid)
        if popen is None:
            return False
        return popen.poll() is None

    def terminate(self, handle: ProcessHandle, timeout: float = 5.0) -> None:
        """Send ``terminate()``, then ``kill()`` if it doesn't exit in time."""
        popen = self._processes.get(handle.pid)
        if popen is None:
            return
        popen.terminate()
        try:
            popen.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            popen.kill()
            popen.wait()

    def wait(self, handle: ProcessHandle, timeout: float | None = None) -> int:
        """Block until the process exits and return its exit code.

        Raises:
            TimeoutError: If *timeout* elapses first.
            KeyError: If *handle* was not created by this manager.

        """
        popen = self._processes[handle.pid]
        try:
            return popen.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Process {handle.pid} did not exit within {timeout}s") from exc
