# Platform Abstraction Layer

## Purpose

`ugaf.core` and game plugins must never call an operating-system API directly. Every
system-level concern (display, clipboard, file system, network, process management,
notifications, accessibility, device enumeration, screen input, screen capture) is
accessed through an abstract interface, with concrete adapters isolated behind it. This
is what lets the same plugin code run on Windows, Linux, macOS, or Android without
modification — only the adapter selected at runtime changes.

## Architecture

Two interfaces predate this layer and are **not** duplicated here:

| Subsystem | Interface | Location |
|---|---|---|
| Input (mouse/keyboard/touch) | `InputProvider` | `ugaf.input.provider` |
| Screenshot | `ScreenshotProvider` | `ugaf.vision.screenshot` |

The remaining eight subsystems live in the new `ugaf.platform` package, introduced in
Milestone 2 of the architecture hardening pass:

| Subsystem | Interface | Concrete adapter(s) | Status |
|---|---|---|---|
| Display | `DisplayProvider` | `WindowsDisplayProvider` (Win32 `user32`/`shcore` via `ctypes`) | Windows only |
| Clipboard | `ClipboardProvider` | `WindowsClipboardProvider` (Win32 clipboard API via `ctypes`) | Windows only |
| Notifications | `NotificationProvider` | `WindowsNotificationProvider` (`System.Windows.Forms.NotifyIcon` via PowerShell) | Windows only |
| File System | `FileSystemProvider` | `LocalFileSystemProvider` (`pathlib`) | Cross-platform |
| Network | `NetworkProvider` | `DefaultNetworkProvider` (`socket`) | Cross-platform |
| Process Management | `ProcessManager` | `DefaultProcessManager` (`subprocess`) | Cross-platform |
| Device enumeration | `DeviceProvider` | none yet | Interface only — Milestone 3 (Device Manager) |
| Accessibility | `AccessibilityProvider` | none yet | Interface only — Milestone 4 (Android Transport) |

File System, Network, and Process Management get a single default adapter rather than
per-OS variants because the underlying stdlib modules (`pathlib`, `socket`,
`subprocess`) are already portable at the level of operation this framework needs —
building bespoke per-OS adapters here would be complexity without a corresponding
capability gain. Display, Clipboard, and Notifications are genuinely OS-specific at the
Win32 API level, so they get real per-OS adapters as those platforms are supported.

## Adapter selection: `AdapterRegistry`

Every subsystem is backed by one `ugaf.platform.registry.AdapterRegistry[T]` instance —
a generic, thread-safe, name-to-class registry generalized from the pattern already
proven by `ugaf.input.registry.InputProviderRegistry`. `ugaf/platform/__init__.py`
exposes one module-level singleton per subsystem (`display_registry`,
`clipboard_registry`, etc.) with built-in adapters pre-registered:

```python
from ugaf.platform import display_registry

display = display_registry.create("windows")
info = display.get_display_info()
```

## Why Device and Accessibility ship as interfaces only

Building a real Device adapter now would mean building it twice: once shallow here,
then properly in Milestone 3 (Device Manager), which needs discovery, reconnection,
heartbeat, and health monitoring that span *multiple* `DeviceProvider` transports at
once — orchestration that doesn't belong at the single-adapter level this module
operates at. Similarly, Accessibility's only currently-planned adapter is Android's
Accessibility Service, which Milestone 4 (Android Transport) evaluates alongside
UIAutomator2/Scrcpy/gRPC as competing transports — picking an implementation before
that evaluation would risk locking in the wrong one.

## Platform-aware selection: closing a real gap

`ugaf.core.platform.detect_platform()` existed since Sprint 02 but was never consulted
by anything (confirmed during the repository audit — see `PROJECT_STATUS.md`).
`ugaf.input.manager.InputManager.connect()` now uses it: when `input.provider` is not
set in configuration, the manager picks `"windows"` on Windows and `"adb"` everywhere
else, instead of always defaulting to `"windows"`. The `ugaf.platform` registries do
not yet have an equivalent auto-selection helper — each subsystem currently has at most
one adapter per registry, so there is nothing to choose between yet; this will become
relevant once Linux/macOS Display/Clipboard/Notification adapters are added.

## Testing

Every adapter is exercised against the real OS where practical rather than fully mocked:

- `LocalFileSystemProvider`, `DefaultNetworkProvider` (loopback socket test),
  `DefaultProcessManager` (real short-lived subprocesses) run against the real
  implementation.
- `WindowsClipboardProvider` performs a real round-trip write/read against the live
  Windows clipboard — this is what caught a real bug during development: `ctypes`
  defaults to a 32-bit `c_int` return type, which silently truncated 64-bit
  `GlobalAlloc`/`GlobalLock` handles on Win64 until explicit `restype`/`argtypes` were
  set.
- `WindowsDisplayProvider`, `WindowsNotificationProvider` mock the `ctypes.windll`/
  `subprocess.run` boundary only, since they call real Win32/PowerShell surfaces that
  aren't safe to fully exercise unattended in CI (a live PowerShell toast, actual
  display metrics that vary per test machine).

## Known limitations

- Linux and macOS have no concrete adapters yet for Display, Clipboard, or
  Notifications — only the interfaces exist. Contributions should follow the existing
  `WindowsXProvider` naming and registration pattern.
- `AdapterRegistry` has no platform-aware auto-selection helper yet (see above) —
  callers must know which adapter name to request.
- `WindowsNotificationProvider` shells out to `powershell`/`pwsh` per call; there is no
  way to update or dismiss a notification once shown, and no click-callback support.
- `DeviceProvider`/`AccessibilityProvider` have zero concrete adapters — do not attempt
  to use them for real work until Milestones 3/4 land.
