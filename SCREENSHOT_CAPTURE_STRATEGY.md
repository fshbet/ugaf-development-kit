# Screenshot Capture Strategy

Research conducted before implementing the Screenshot Capture subsystem, per the
directive treating it as foundational infrastructure — the framework cannot become a
reliable Android automation platform until it can consistently acquire screen images.

## Candidates evaluated

### 1. `adb exec-out screencap -p`

Captures a full-resolution PNG and streams it directly to the host over the existing
ADB connection, using ADB's binary-safe `exec-out` mode.

- **Latency/throughput:** One full PNG encode + transfer per call — adequate for
  occasional screenshots (menu detection, state checks), inadequate for a continuous
  high-FPS vision loop.
- **Reliability:** High — no extra moving parts beyond ADB itself, which the framework
  already depends on for the Device Manager.
- **Image quality:** Full resolution, lossless PNG.
- **Permissions:** None beyond USB/wireless debugging already required for ADB.
- **Portability:** Works on any device with ADB shell v2 (Android 5.0+).
- **Implementation complexity:** Trivial — one subprocess call, one PNG decode.

### 2. `adb shell screencap -p` (+ `adb pull`)

The older two-step approach: write the PNG to device storage, then pull it.

- **Weaknesses:** `adb shell screencap -p` mangles binary output — the shell PTY
  converts `\n` to `\r\n`, corrupting the PNG unless manually un-mangled. `exec-out`
  exists specifically to avoid this. The two-step write-then-pull is also strictly
  slower than a direct stream (unnecessary on-device I/O) and requires the device to
  have writable external storage.
- **Verdict:** Strictly worse than `exec-out` for this framework's needs — rejected in
  favor of #1.

### 3. scrcpy protocol (H.264 stream over ADB)

Already evaluated for the Android transport in `ANDROID_TRANSPORT_STRATEGY.md`: pushes
a small server over ADB, captures via `MediaCodec`, streams H.264 back over the
existing ADB connection.

- **Latency/throughput:** 35–70ms, 30–120fps — the only option here that can sustain a
  real-time vision loop.
- **Reliability:** High in practice (used in production by scrcpy/Genymotion/Android
  Studio's own screen mirroring).
- **Permissions:** None beyond ADB.
- **Implementation complexity:** Real but bounded — requires an H.264 decoder on the
  desktop side (FFmpeg or a pure-Python binding) and a persistent frame-stream
  connection rather than one-shot request/response.
- **Verdict:** The right choice for high-frequency capture — but a materially bigger
  lift than a one-shot ADB screenshot. Documented here as the next provider to add
  (interface is ready for it now), not implemented in this milestone.

### 4. Android `MediaProjection` API

An on-device API (`android.media.projection.MediaProjection`) that lets an app capture
the screen to a `Surface`, requiring the user to grant a one-time capture permission via
a system dialog.

- **Permissions:** Requires an active foreground app with a granted `MediaProjection`
  token — meaning a companion Android app must be installed and running on the target
  device, and a user must interact with the permission dialog at least once per
  session (Android does not allow silently granting this).
- **Reliability/latency:** Not independently benchmarked in the sources found (no
  public 2026 latency figures) — in practice its throughput characteristics are
  similar to scrcpy's, since scrcpy's own server uses conceptually the same capture
  path (`MediaCodec` + a virtual display Surface) internally.
- **Verdict:** Rejected as a *direct* implementation target — it requires shipping and
  maintaining our own on-device companion app (a new distribution/signing surface),
  which scrcpy already solves without needing UGAF to own an APK. Revisit only if a
  concrete capability gap emerges that scrcpy can't cover.

### 5. UI Automator screenshots (`UiDevice.takeScreenshot()` / `activeWindow().takeScreenshot()`)

Google's own instrumentation-test screenshot API, callable via `am instrument` or the
`uiautomator2` Python wrapper (already evaluated in `ANDROID_TRANSPORT_STRATEGY.md`).

- **Permissions/complexity:** Requires either a running instrumentation test process
  or the `uiautomator2` on-device JSON-RPC agent (`atx-agent`) — another moving part,
  same tradeoff already identified when evaluating UIAutomator2 for input.
- **Verdict:** Only worth adopting alongside a broader UIAutomator2 adoption for input
  (Milestone 4's remaining scope), not in isolation just for screenshots — using it
  purely for screen capture would mean carrying the on-device agent's overhead for no
  benefit over plain ADB.

### 6. Android Emulator console screenshot (`adb emu screenrecord screenshot`)

An emulator-only console command available through the AVD console, not applicable to
physical devices.

- **Verdict:** Useful exclusively for CI/emulator-based testing scenarios, not a
  general Android transport. Not implemented as a distinct provider now; the existing
  `AdbScreenshotProvider` already works unmodified against an emulator (emulators show
  up as ordinary ADB devices), so no separate "Emulator Provider" is needed to *use*
  the emulator today — a dedicated adapter would only be justified if we specifically
  wanted the emulator console's extra capabilities (arbitrary display resolution
  overrides, etc.), which nothing currently requires.

### 7. minicap (openstf/DeviceFarmer)

An open-source (Apache-2.0), widely-used project purpose-built for fast Android screen
capture: pushes a small native binary over ADB that streams raw frames over a socket,
only sending frames when the screen actually changes (Android 4.2+), reaching 30–40fps
on modern devices without root.

- **Verdict:** A legitimate, proven prior-art alternative to scrcpy for this exact
  problem. Not selected as the primary high-frequency provider because scrcpy is
  actively maintained (minicap's upstream has seen much less activity in recent years)
  and already chosen for the transport layer in `ANDROID_TRANSPORT_STRATEGY.md` — using
  the same underlying mechanism for both screen capture and any future streaming needs
  avoids maintaining two separate native on-device binaries for overlapping purposes.

## Recommended architecture

**Provider-based, matching the pattern already established by `InputProvider`/
`DeviceProvider`.** `ScreenshotProvider` (defined since Milestone 2 in
`ugaf.vision.screenshot`) is the stable interface; the Core Engine and game plugins
depend only on it, never on a specific capture mechanism.

| Provider | Status this milestone |
|---|---|
| `AdbScreenshotProvider` | **Implemented** — `adb exec-out screencap -p`, per research above the correct default given no new dependencies and reuse of the existing ADB transport |
| `MockScreenshotProvider` | **Implemented** — synthetic/static images for tests and development without a device |
| `ImageReplayProvider` | **Implemented** — replays a directory of pre-captured images, for deterministic tests and offline development |
| `ScrcpyScreenshotProvider` | Interface-ready, not implemented — next provider to add once continuous high-FPS capture is a concrete plugin requirement |
| `MediaProjectionProvider` | Deferred — would require shipping and maintaining an on-device companion app |
| `EmulatorProvider` | Not planned as a separate provider — `AdbScreenshotProvider` already works against emulators unmodified |
| `UiAutomatorScreenshotProvider` | Deferred — only worth it bundled with broader UIAutomator2 adoption (Milestone 4 remainder) |

Each `ScreenshotProvider` is scoped to a single target, mirroring `AdbInputProvider`'s
existing per-device design (ADR-011) rather than being internally multi-device-aware —
multiple devices means multiple `ScreenshotManager`/provider instances, exactly like
`InputManager`.

## `ScreenshotManager`: selection, caching, and async capture

A new `ugaf.vision.screenshot_manager.ScreenshotManager` chooses a provider from
`vision.screenshot_provider` in config (a key that already existed, unused, since
Sprint 05 — closing that gap) via a dedicated `AdapterRegistry[ScreenshotProvider]`,
mirroring `InputManager`'s provider selection. It adds:

- **Frame caching**: `capture_full(use_cache=True, max_age=0.0)` returns the
  last-captured frame if younger than `max_age` seconds, avoiding a redundant capture
  when a caller (e.g. multiple vision checks per game tick) asks for the screen more
  than once within a short window. Default `max_age=0.0` disables caching (always
  captures fresh) — callers opt in.
- **No unnecessary copies**: cached frames are returned by reference (`Image` is
  already an immutable-by-convention wrapper around a numpy array whose transform
  methods return new instances — see `ugaf/imaging/image.py`), not copied on cache hit.
- **Async capture with timeout**: `capture_full_async(timeout=...)` wraps the
  (synchronous, provider-level) capture in `asyncio.to_thread` with
  `asyncio.wait_for`, matching the pattern already established by
  `DeviceManager.execute_shell`.
- **Retry**: bounded retry on capture failure, mirroring `InputManager.connect()`'s
  retry loop — a single dropped ADB call shouldn't be fatal to a vision loop.
- **Recovery/monitoring**: capture failures are logged with attempt count; a
  `last_capture_error` property exposes the most recent failure for a caller (or future
  telemetry, Priority #7) to inspect without needing to catch every exception itself.

## What this milestone does not implement

Explicitly deferred, consistent with the "no placeholder code" principle — these are
documented as the next steps, not stubbed classes:

- Continuous/streaming capture (scrcpy-backed) — the interface supports adding it
  without any `ScreenshotManager`/Core Engine change.
- Frame diffing / incremental updates — meaningful once a streaming provider exists;
  premature against a one-shot `exec-out screencap` provider where every capture is
  already a full frame.
- Compression tuning — PNG from `screencap` is already reasonably sized for one-shot
  capture; revisit once streaming is added.

## Sources

- [Capturing Binary Screen Data Using ADB - Repeato](https://www.repeato.app/efficiently-capturing-screenshots-on-android-devices-via-adb/)
- [Note to Self: Fast Android Screen Capture](https://blog.macuyiko.com/post/2017/note-to-self-fast-android-screen-capture.html)
- [Android Debug Bridge (adb) | Android Developers](https://developer.android.com/tools/adb)
- [GitHub - Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)
- [MediaProjection | API reference | Android Developers](https://developer.android.com/reference/android/media/projection/MediaProjection)
- [Media projection | Android media | Android Developers](https://developer.android.com/media/grow/media-projection)
- [Write automated tests with UI Automator | Android Developers](https://developer.android.com/training/testing/other-components/ui-automator)
- [Take screenshots | Android Studio | Android Developers](https://developer.android.com/studio/run/emulator-take-screenshots)
- [GitHub - openstf/minicap](https://github.com/openstf/minicap)
- [GitHub - DeviceFarmer/minicap](https://github.com/DeviceFarmer/minicap)
