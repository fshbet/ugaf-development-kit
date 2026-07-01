"""Tests for the process management abstraction.

Uses real, short-lived Python subprocesses rather than mocking
``subprocess.Popen`` everywhere, since the whole point of this adapter
is correct process lifecycle handling (start/poll/terminate/wait) and
that's cheapest to verify against the real OS scheduler.
"""

from __future__ import annotations

import sys
import time

import pytest

from ugaf.platform.process import DefaultProcessManager


@pytest.fixture
def manager() -> DefaultProcessManager:
    return DefaultProcessManager()


def test_start_and_wait_returns_exit_code(manager: DefaultProcessManager) -> None:
    handle = manager.start([sys.executable, "-c", "import sys; sys.exit(7)"])
    code = manager.wait(handle, timeout=5.0)
    assert code == 7


def test_is_running_true_while_alive_false_after_exit(manager: DefaultProcessManager) -> None:
    handle = manager.start([sys.executable, "-c", "import time; time.sleep(0.5)"])
    assert manager.is_running(handle) is True
    manager.wait(handle, timeout=5.0)
    assert manager.is_running(handle) is False


def test_is_running_false_for_unknown_handle(manager: DefaultProcessManager) -> None:
    from ugaf.platform.process import ProcessHandle

    assert manager.is_running(ProcessHandle(pid=999999, command=[])) is False


def test_terminate_stops_long_running_process(manager: DefaultProcessManager) -> None:
    handle = manager.start([sys.executable, "-c", "import time; time.sleep(30)"])
    assert manager.is_running(handle) is True
    manager.terminate(handle, timeout=5.0)
    time.sleep(0.2)
    assert manager.is_running(handle) is False


def test_terminate_unknown_handle_is_noop(manager: DefaultProcessManager) -> None:
    from ugaf.platform.process import ProcessHandle

    manager.terminate(ProcessHandle(pid=999999, command=[]))  # should not raise


def test_wait_unknown_handle_raises_key_error(manager: DefaultProcessManager) -> None:
    from ugaf.platform.process import ProcessHandle

    with pytest.raises(KeyError):
        manager.wait(ProcessHandle(pid=999999, command=[]))


def test_wait_timeout_expired_raises_timeout_error(manager: DefaultProcessManager) -> None:
    handle = manager.start([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with pytest.raises(TimeoutError):
            manager.wait(handle, timeout=0.1)
    finally:
        manager.terminate(handle, timeout=5.0)
