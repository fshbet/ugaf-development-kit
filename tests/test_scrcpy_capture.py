"""Tests for ugaf.vision.scrcpy_capture.ScrcpyFrameProvider.

No real scrcpy server or `av` (PyAV) install is available in this
environment (see PROJECT_STATUS.md), so these tests exercise the wire
protocol (socket framing, header parsing) and error handling against a
fake in-memory socket and a fake `av` module injected via
``sys.modules`` — the same technique used for
``ugaf.vision.window_capture``'s optional pywin32/mss dependency.
"""

from __future__ import annotations

import struct
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.scrcpy_capture import ScrcpyFrameProvider, _read_exact


@pytest.fixture
def imaging() -> ImagingManager:
    mgr = MagicMock(spec=ImagingManager)
    mgr.backend = MagicMock(spec=ImageBackend)
    return mgr


class _FakeSocket:
    """A minimal in-memory stand-in for a connected TCP socket."""

    def __init__(self, data: bytes) -> None:
        self._buffer = data

    def recv(self, size: int) -> bytes:
        chunk, self._buffer = self._buffer[:size], self._buffer[size:]
        return chunk

    def close(self) -> None:
        pass


def _frame_meta_header(payload_size: int, *, config: bool = False) -> bytes:
    flag = (1 << 63) if config else 0
    return struct.pack(">QI", flag, payload_size)


def _install_fake_av(monkeypatch: pytest.MonkeyPatch, decoded_frame: numpy.ndarray) -> None:
    class _FakeFrame:
        def to_ndarray(self, format: str) -> numpy.ndarray:  # noqa: A002
            assert format == "bgr24"
            return decoded_frame

    class _FakeCodecContext:
        def parse(self, data: bytes) -> list[bytes]:
            return [data]

        def decode(self, packet: bytes) -> list[_FakeFrame]:
            return [_FakeFrame()]

    module = types.ModuleType("av")
    module.CodecContext = MagicMock()  # type: ignore[attr-defined]
    module.CodecContext.create.return_value = _FakeCodecContext()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "av", module)


class TestReadExact:
    def test_reads_exact_size_across_multiple_recv_calls(self) -> None:
        sock = _FakeSocket(b"abcdefgh")

        class _ChunkySocket(_FakeSocket):
            def recv(self, size: int) -> bytes:
                # Always return at most 3 bytes, to force multiple reads.
                return super().recv(min(size, 3))

        chunky = _ChunkySocket(b"abcdefgh")
        assert _read_exact(chunky, 8) == b"abcdefgh"
        del sock

    def test_raises_if_socket_closes_early(self) -> None:
        sock = _FakeSocket(b"ab")
        with pytest.raises(ScreenshotError, match="closed unexpectedly"):
            _read_exact(sock, 5)  # type: ignore[arg-type]


class TestDeviceNameHeader:
    def test_strips_null_padding(self) -> None:
        name = b"emulator-5554" + b"\x00" * (64 - len(b"emulator-5554"))
        sock = _FakeSocket(name)
        result = ScrcpyFrameProvider._read_device_name(sock)  # type: ignore[arg-type]
        assert result == "emulator-5554"


class TestCaptureFull:
    def test_decodes_one_frame_meta_packet(
        self, imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        expected = numpy.zeros((4, 4, 3), dtype=numpy.uint8)
        _install_fake_av(monkeypatch, expected)

        provider = ScrcpyFrameProvider(
            imaging, device_id="fake", server_jar_path=Path("unused-in-this-test")
        )
        payload = b"\x00\x01\x02\x03"
        provider._socket = _FakeSocket(_frame_meta_header(len(payload)) + payload)  # type: ignore[assignment]

        image = provider.capture_full()

        assert isinstance(image, Image)
        assert (image.data == expected).all()

    def test_raises_when_not_connected(self, imaging: ImagingManager) -> None:
        provider = ScrcpyFrameProvider(
            imaging, device_id="fake", server_jar_path=Path("unused")
        )
        with pytest.raises(ScreenshotError, match="not connected"):
            provider.capture_full()

    def test_missing_av_raises_actionable_error(
        self, imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "av", None)  # simulate ImportError
        provider = ScrcpyFrameProvider(
            imaging, device_id="fake", server_jar_path=Path("unused")
        )
        provider._socket = _FakeSocket(b"")  # type: ignore[assignment]
        with pytest.raises(ScreenshotError, match="'av'"):
            provider.capture_full()


class TestConnect:
    def test_missing_server_jar_raises_before_touching_adb(self, imaging: ImagingManager) -> None:
        provider = ScrcpyFrameProvider(
            imaging, device_id="fake", server_jar_path=Path("definitely-does-not-exist.jar")
        )
        with pytest.raises(ScreenshotError, match="server jar not found"):
            provider.connect()

    def test_missing_av_raises_before_pushing_server(
        self, imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        jar = tmp_path / "scrcpy-server"
        jar.write_bytes(b"not a real jar, just needs to exist")
        monkeypatch.setitem(sys.modules, "av", None)

        provider = ScrcpyFrameProvider(imaging, device_id="fake", server_jar_path=jar)
        with pytest.raises(ScreenshotError, match="'av'"):
            provider.connect()


def test_capture_region_crops_the_decoded_frame(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ugaf.vision.region import Region

    class _RealishBackend:
        def crop(self, data: numpy.ndarray, x: int, y: int, w: int, h: int) -> numpy.ndarray:
            return data[y : y + h, x : x + w]

        def width(self, data: numpy.ndarray) -> int:
            return data.shape[1]

        def height(self, data: numpy.ndarray) -> int:
            return data.shape[0]

    frame = numpy.arange(64, dtype=numpy.uint8).reshape(8, 8, 1).repeat(3, axis=2)
    _install_fake_av(monkeypatch, frame)

    imaging_real = MagicMock(spec=ImagingManager)
    imaging_real.backend = _RealishBackend()

    provider = ScrcpyFrameProvider(
        imaging_real, device_id="fake", server_jar_path=Path("unused")
    )
    payload = b"\x00"
    provider._socket = _FakeSocket(_frame_meta_header(len(payload)) + payload)  # type: ignore[assignment]

    image = provider.capture_region(Region(x=1, y=1, width=2, height=2))
    assert image.data.shape == (2, 2, 3)
