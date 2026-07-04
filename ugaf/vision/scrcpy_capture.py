"""scrcpy-based frame capture provider — a low-latency capture transport.

Talks directly to a `scrcpy <https://github.com/Genymobile/scrcpy>`_
server process running on the device over a raw H264 video socket,
decoding frames with PyAV, instead of round-tripping through
``adb exec-out screencap`` for every single frame. ADB remains the
transport for device discovery, input injection, application
lifecycle, and shell commands (including starting the scrcpy server
itself) — this provider only replaces the *frame source*, exactly like
:class:`~ugaf.vision.window_capture.WindowCaptureProvider` does for
emulator windows. ``VisionManager`` never knows the difference.

Requires:

* An installed `scrcpy` distribution (its bundled server jar; the
  ``scrcpy`` CLI binary itself is not required — only its server
  component is pushed to the device).
* The optional ``av`` (PyAV) dependency for H264 decoding
  (``pip install ugaf[scrcpy]``).

Protocol notes (frame-meta wire format, scrcpy server 1.19+ without a
control socket): after a fixed 64-byte device-name header, the stream
is a sequence of ``[8-byte big-endian PTS+config-flag][4-byte
big-endian packet size][raw H264 NAL unit bytes]`` frames — this
module parses exactly that framing. **This has not been validated
against a live scrcpy server in this environment** (no `scrcpy`
installation or Android emulator was available during development —
see `PROJECT_STATUS.md`); the frame-parsing logic is covered by unit
tests against synthetic byte streams built to this same spec, but
end-to-end validation against a real server remains outstanding.
"""

from __future__ import annotations

import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

__all__ = [
    "ScrcpyFrameProvider",
]

_DEVICE_NAME_HEADER_SIZE = 64
_FRAME_HEADER_SIZE = 12  # 8-byte PTS/flags + 4-byte packet size
_CONFIG_PACKET_FLAG = 1 << 63
_SOCKET_NAME = "localabstract:scrcpy"
_SERVER_MAIN_CLASS = "com.genymobile.scrcpy.Server"
_SERVER_DEVICE_PATH = "/data/local/tmp/ugaf-scrcpy-server.jar"


class ScrcpyFrameProvider(ScreenshotProvider):
    """Captures frames from a device via a locally-running scrcpy server.

    Usage::

        provider = ScrcpyFrameProvider(
            imaging, device_id="emulator-5554",
            server_jar_path=Path("C:/scrcpy/scrcpy-server"),
        )
        provider.connect()
        frame = provider.capture_full()
        provider.disconnect()

    """

    def __init__(
        self,
        imaging: ImagingManager,
        device_id: str,
        server_jar_path: str | Path,
        adb_executable: str = "adb",
        server_version: str = "2.4",
        local_port: int = 27183,
        connect_timeout: float = 10.0,
    ) -> None:
        """Configure (but do not yet start) a scrcpy-backed capture session.

        Args:
            imaging: Used to wrap decoded frames as :class:`Image`.
            device_id: Target device serial (as reported by ``adb
                devices``).
            server_jar_path: Path to a scrcpy distribution's server
                jar (typically named ``scrcpy-server``), pushed to the
                device on :meth:`connect`.
            adb_executable: Path to the ``adb`` binary.
            server_version: Version string passed to the server
                process — must match the jar's actual build; mismatches
                are rejected by the server itself.
            local_port: Local TCP port used for ``adb forward``.
            connect_timeout: Seconds to wait for the server process to
                start listening and the device-name header to arrive.

        """
        self._imaging = imaging
        self._device_id = device_id
        self._server_jar_path = Path(server_jar_path)
        self._adb_executable = adb_executable
        self._server_version = server_version
        self._local_port = local_port
        self._connect_timeout = connect_timeout
        self._server_process: subprocess.Popen[bytes] | None = None
        self._socket: socket.socket | None = None
        self._codec_context: Any = None
        self._device_name: str = ""

    @property
    def device_name(self) -> str:
        """Return the device name reported by the scrcpy server, once connected."""
        return self._device_name

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Push and start the scrcpy server, then open the video socket.

        Raises:
            ScreenshotError: If the server jar is missing, ``av`` is
                not installed, or the server never starts listening
                within ``connect_timeout``.

        """
        if not self._server_jar_path.is_file():
            raise ScreenshotError(f"scrcpy server jar not found: {self._server_jar_path}")
        _import_av()  # fail fast if the decoder dependency is missing

        self._push_server()
        self._forward_port()
        self._server_process = self._start_server()
        self._socket = self._open_socket()
        self._device_name = self._read_device_name(self._socket)

    def disconnect(self) -> None:
        """Stop the server process, remove the port forward, and close the socket."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._server_process is not None:
            self._server_process.terminate()
            self._server_process = None
        subprocess.run(
            [self._adb_executable, "-s", self._device_id, "forward", "--remove",
             f"tcp:{self._local_port}"],
            capture_output=True,
            check=False,
        )
        self._codec_context = None

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture_full(self) -> Image:
        """Read and decode the next available video frame.

        Raises:
            ScreenshotError: If not connected, or the stream ends/errors.

        """
        if self._socket is None:
            raise ScreenshotError("ScrcpyFrameProvider is not connected")

        av = _import_av()
        if self._codec_context is None:
            self._codec_context = av.CodecContext.create("h264", "r")

        packet_bytes = self._read_next_packet(self._socket)
        packets = self._codec_context.parse(packet_bytes)
        frame_array = None
        for packet in packets:
            for frame in self._codec_context.decode(packet):
                frame_array = frame.to_ndarray(format="bgr24")
        if frame_array is None:
            raise ScreenshotError("scrcpy stream produced no decodable frame")
        return Image(frame_array, self._imaging.backend)

    def capture_region(self, region: Region) -> Image:
        """Capture the next frame and crop to *region*."""
        return self.capture_full().crop(region.x, region.y, region.width, region.height)

    def capture_game_window(self, window_title: str) -> Image:
        """Return the next frame — scrcpy has no windowing concept; *window_title* is ignored."""
        return self.capture_full()

    # ------------------------------------------------------------------
    # Internal: server process management
    # ------------------------------------------------------------------

    def _push_server(self) -> None:
        result = subprocess.run(
            [self._adb_executable, "-s", self._device_id, "push",
             str(self._server_jar_path), _SERVER_DEVICE_PATH],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ScreenshotError(f"Failed to push scrcpy server: {result.stderr.strip()}")

    def _forward_port(self) -> None:
        result = subprocess.run(
            [self._adb_executable, "-s", self._device_id, "forward",
             f"tcp:{self._local_port}", _SOCKET_NAME],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ScreenshotError(f"Failed to forward scrcpy port: {result.stderr.strip()}")

    def _start_server(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                self._adb_executable, "-s", self._device_id, "shell",
                f"CLASSPATH={_SERVER_DEVICE_PATH}",
                "app_process", "/", _SERVER_MAIN_CLASS,
                self._server_version,
                "tunnel_forward=true",
                "audio=false",
                "control=false",
                "cleanup=false",
                "send_frame_meta=true",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _open_socket(self) -> socket.socket:
        deadline = time.monotonic() + self._connect_timeout
        last_exc: OSError | None = None
        while time.monotonic() < deadline:
            try:
                sock = socket.create_connection(("127.0.0.1", self._local_port), timeout=2.0)
                sock.settimeout(self._connect_timeout)
                return sock
            except OSError as exc:
                last_exc = exc
                time.sleep(0.2)
        raise ScreenshotError(
            f"Could not connect to scrcpy server on port {self._local_port}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Internal: wire protocol
    # ------------------------------------------------------------------

    @staticmethod
    def _read_device_name(sock: socket.socket) -> str:
        header = _read_exact(sock, _DEVICE_NAME_HEADER_SIZE)
        return header.rstrip(b"\x00").decode("utf-8", errors="replace")

    @staticmethod
    def _read_next_packet(sock: socket.socket) -> bytes:
        """Read one frame-meta-framed H264 packet: ``[pts+flags][size][data]``."""
        frame_header = _read_exact(sock, _FRAME_HEADER_SIZE)
        pts_and_flags, size = struct.unpack(">QI", frame_header)
        is_config = bool(pts_and_flags & _CONFIG_PACKET_FLAG)
        data = _read_exact(sock, size)
        # Config packets (SPS/PPS) carry no displayable frame but must
        # still be fed to the decoder — parse()/decode() handle that
        # transparently since callers only check the yielded frames.
        del is_config
        return data


def _import_av() -> Any:
    """Import PyAV, raising a clear :class:`ScreenshotError` if unavailable."""
    try:
        import av

        return av
    except ImportError as exc:
        raise ScreenshotError(
            "ScrcpyFrameProvider requires 'av' (PyAV) — install via `pip install ugaf[scrcpy]`"
        ) from exc


def _read_exact(sock: socket.socket, size: int) -> bytes:
    """Read exactly *size* bytes from *sock*, raising if the stream ends early."""
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ScreenshotError("scrcpy socket closed unexpectedly")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
