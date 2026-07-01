"""Tests for the network abstraction."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

from ugaf.platform.network import DefaultNetworkProvider


def test_is_reachable_true_on_successful_connection() -> None:
    provider = DefaultNetworkProvider()
    mock_socket = MagicMock()
    mock_socket.__enter__.return_value = mock_socket
    with patch("socket.create_connection", return_value=mock_socket) as mock_create:
        assert provider.is_reachable("example.com", 80, timeout=1.0) is True
    mock_create.assert_called_once_with(("example.com", 80), timeout=1.0)


def test_is_reachable_false_on_os_error() -> None:
    provider = DefaultNetworkProvider()
    with patch("socket.create_connection", side_effect=OSError("refused")):
        assert provider.is_reachable("example.com", 80, timeout=1.0) is False


def test_get_local_ip_returns_socket_address() -> None:
    provider = DefaultNetworkProvider()
    mock_socket = MagicMock()
    mock_socket.__enter__.return_value = mock_socket
    mock_socket.getsockname.return_value = ("192.168.1.42", 12345)
    with patch("socket.socket", return_value=mock_socket):
        assert provider.get_local_ip() == "192.168.1.42"


def test_get_local_ip_falls_back_on_os_error() -> None:
    provider = DefaultNetworkProvider()
    mock_socket = MagicMock()
    mock_socket.__enter__.return_value = mock_socket
    mock_socket.connect.side_effect = OSError("no network")
    with patch("socket.socket", return_value=mock_socket):
        assert provider.get_local_ip() == "127.0.0.1"


def test_real_loopback_is_reachable() -> None:
    """Sanity check against a real socket, not just mocks."""
    provider = DefaultNetworkProvider()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert provider.is_reachable("127.0.0.1", port, timeout=1.0) is True
