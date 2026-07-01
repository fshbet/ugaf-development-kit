"""Network abstraction.

Reachability and address queries are portable through :mod:`socket`
on every OS this framework targets; the abstraction exists for
injectability (mockable in tests, swappable for a future
device-relative network check, e.g. "is this reachable from the
Android device's network namespace") rather than per-OS variation.
"""

from __future__ import annotations

import socket
from abc import ABC, abstractmethod

__all__ = [
    "DefaultNetworkProvider",
    "NetworkProvider",
]


class NetworkProvider(ABC):
    """Abstract interface for basic network queries."""

    @abstractmethod
    def is_reachable(self, host: str, port: int, timeout: float = 3.0) -> bool:
        """Return whether a TCP connection to ``host:port`` can be established.

        Args:
            host: Hostname or IP address.
            port: TCP port number.
            timeout: Maximum time in seconds to wait for the connection.

        """

    @abstractmethod
    def get_local_ip(self) -> str:
        """Return the local host's primary outbound IP address."""


class DefaultNetworkProvider(NetworkProvider):
    """Network provider backed by :mod:`socket`.

    Works identically on every platform this framework targets, so a
    single default adapter (rather than per-OS variants) is
    sufficient at this abstraction level.
    """

    def is_reachable(self, host: str, port: int, timeout: float = 3.0) -> bool:
        """Attempt a TCP connection to ``host:port`` within *timeout* seconds."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def get_local_ip(self) -> str:
        """Determine the local outbound IP by opening a UDP socket to a public address.

        No packets are actually sent (UDP ``connect`` only performs
        local routing table resolution).
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.connect(("8.8.8.8", 80))
                return str(sock.getsockname()[0])
            except OSError:
                return "127.0.0.1"
