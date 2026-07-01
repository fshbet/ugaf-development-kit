# Architecture

Core engine never depends on game plugins.
Games communicate through SDK interfaces.
Use dependency injection, event bus and configuration-driven design.

## Layers

- **Core** (`ugaf.core`): config, logging, event bus, DI container, health checks,
  application bootstrap/CLI. Owns a `PluginManager` but contains no game/plugin logic
  itself — see `PLUGIN_ARCHITECTURE.md`.
- **Platform Abstraction Layer** (`ugaf.platform`, plus `ugaf.input`/`ugaf.vision`'s
  existing `InputProvider`/`ScreenshotProvider`): OS-independent interfaces for every
  system-level concern (display, clipboard, file system, network, process management,
  notifications, accessibility, device enumeration, input, screenshot). Core and plugins
  depend only on these interfaces, never on `ctypes`/`subprocess`/OS APIs directly. See
  `PLATFORM_ABSTRACTION.md` for the full design and current per-subsystem adapter
  coverage.
- **Device Manager** (`ugaf.device`): the central orchestrator for every connected
  device. `ugaf.core.bootstrap.Application` and game plugins never talk to ADB (or any
  future transport) directly — they go through `ugaf.device.manager.DeviceManager`,
  which owns one or more `ugaf.platform.device.DeviceProvider` transports, polls them
  for discovery/health, publishes `device.*` lifecycle events, and retries command
  execution with transport-level recovery. `ugaf.device.adb_provider.AdbDeviceProvider`
  is the first (and currently only) transport. See `ANDROID_TRANSPORT_STRATEGY.md` for
  the research behind starting with ADB and the multi-transport roadmap (UIAutomator2,
  scrcpy, Accessibility Service).
- **ADB / Android Transport** (`ugaf.input.adb`, `ugaf.device.adb_provider`, expanding
  in Milestone 4): the current Android-specific transport implementation, consumed
  through the same `InputProvider`/`DeviceProvider` interfaces as any other transport —
  ADB is one transport choice, not the architecture.
- **Vision** (`ugaf.imaging`, `ugaf.vision`): OpenCV-backed image processing, template
  matching, feature detection; screen capture reachability is a known open gap (see
  `KNOWN_LIMITATIONS.md`).
- **Game SDK / Plugins** (`ugaf.sdk`, `ugaf.plugins`): the `GamePlugin` contract and its
  discovery/validation/lifecycle orchestration — the framework's only plugin system as
  of Milestone 1. `PluginManager` registers `DeviceManager` as a DI singleton in every
  plugin's `GameContext` when one is supplied, so a plugin resolves it and builds its
  own per-device `InputManager` instances rather than the framework prescribing a
  single global input target.

## Multi-device design (established Milestone 4)

`ugaf.input.manager.InputManager` targets exactly **one** input destination per
instance (one desktop, or one Android device) — deliberately, not as a limitation.
Driving N simultaneous Android devices means holding N `InputManager` instances (one
per `DeviceInfo` from `DeviceManager.list_devices()`), each optionally constructed with
an explicit `device_id` (overriding config) and a shared `device_manager` reference for
accurate online/offline/unauthorized pre-flight checks. This was a deliberate
architecture-first decision (see `ARCHITECTURE_DECISIONS.md` ADR-011): a global
multi-device-aware `InputManager` would conflate per-device state management with
device orchestration, which `DeviceManager` already owns.

## Platform priority

Android is the current implementation priority; Windows, Linux, and macOS follow. Every
subsystem in the Platform Abstraction Layer is designed so a new OS is supported by
adding one adapter class and registering it — no changes to `ugaf.core` or plugin code
should ever be required to add platform support.