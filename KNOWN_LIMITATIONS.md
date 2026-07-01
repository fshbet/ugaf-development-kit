# Known Limitations

## Configuration

- **No config schema**. `Config.load()` does not validate the shape or
  types of configuration values beyond requiring the top-level YAML node
  to be a mapping. Invalid keys or wrong types are silently accepted.
- **No config file watching**. Changes to YAML files after `Config()`
  construction are not picked up at runtime.
- **Environment variable override only supports dotted-flat keys**. Nested
  keys like `database.pool.size` require the env var `UGAF_DATABASE_POOL_SIZE`;
  there is no way to override a sub-tree with a single variable.
- **`Config.get()` returns `None` for missing dotted paths deeper than one
  level** — partial mid-level lookups may silently return `None` without
  warning.

## Plugin System

As of Milestone 1 of the architecture hardening pass, `ugaf.plugins`/`ugaf.sdk` (the Game SDK) is
the framework's only plugin system — the previously-coexisting legacy loader
(`ugaf/core/plugin_loader.py`, `ugaf/core/plugin.py`) has been removed. See
`PLUGIN_ARCHITECTURE.md` for the current design.

- **No hot-reload**. Plugins must be discovered at startup; adding,
  removing, or modifying plugin directories at runtime is not detected.
- **No dependency ordering between plugins**. `priority` controls start/stop order but there is no
  mechanism to declare "plugin A requires plugin B".
- **No process isolation**. Plugins share the same Python process and global
  interpreter state. A crashing plugin task running outside its lifecycle methods
  (e.g. a background `asyncio.Task` it spawns itself) can affect the whole
  application; lifecycle-method exceptions are caught and converted to `plugin.failed`
  events, but that only covers `initialize`/`start`/`pause`/`resume`/`stop`.
- **Manifest and in-code metadata are not kept in sync automatically**. `manifest.yaml` and the
  `metadata` object inside `plugin.py` are independent — nothing currently detects if they drift
  apart (this project's own `games/example_game/` shipped with a `capabilities` mismatch between
  the two before it was caught and fixed manually during Milestone 1).
- **Plugin discovery failures (bad manifest, missing `GamePlugin` subclass, import error) are
  logged and the plugin is skipped** rather than raising — this means a broken plugin does not
  prevent other plugins from loading, but also means a typo in a manifest can silently produce
  "0 plugins discovered" with no obvious error unless log output is inspected.

## Platform Abstraction Layer

- **No Linux or macOS adapters yet**. `ugaf.platform`'s Display, Clipboard, and
  Notifications interfaces have Windows-only concrete adapters. File System, Network,
  and Process Management have one cross-platform default adapter each (backed by
  portable stdlib modules), which is by design, not a gap.
- **`DeviceProvider` and `AccessibilityProvider` have no concrete adapters at all** —
  interfaces only, deferred to Milestone 3 (Device Manager) and Milestone 4 (Android
  Transport) respectively. Do not build against them expecting real behavior yet.
- **No platform-aware auto-selection in `AdapterRegistry`**. Callers must explicitly
  request an adapter by name (e.g. `display_registry.create("windows")`); there is no
  helper that picks the right adapter for the current OS the way
  `InputManager.connect()` now does for `InputProvider` (see `PLATFORM_ABSTRACTION.md`).
- **`WindowsNotificationProvider` shells out to `powershell`/`pwsh` per call** — no
  update/dismiss support, no click callbacks, and a real (if small) process-spawn cost
  per notification.

## Device Manager

- **Resolved (was here): `AdbInputProvider`'s device-state parsing duplication.**
  `AdbInputProvider` now delegates device enumeration and shell execution to
  `AdbDeviceProvider` (see `ARCHITECTURE_DECISIONS.md` ADR-012) — there is exactly one
  ADB device-state parser in the codebase now, and `AdbInputProvider.connect()` itself
  (not just `InputManager`'s optional pre-flight check) reports precise
  online/offline/unauthorized status.
- **No wireless ADB pairing support**. `AdbDeviceProvider` only shells out to a local
  `adb` binary already configured with whatever devices are paired/connected — it does
  not implement the Android 11+ QR-code/pairing-code TLS handshake itself.
- **No UIAutomator2, scrcpy, or Accessibility Service transports yet** — only ADB. See
  `ANDROID_TRANSPORT_STRATEGY.md` for the evaluation and why these are deferred to
  Milestones 4/5, not skipped.
- **`DeviceManager.execute_shell()`'s restart-and-retry recovery is ADB-specific in
  practice** — it works for any transport implementing the optional
  `restart_server()` capability, but only `AdbDeviceProvider` does so today.
- **No multi-device concurrent command execution helper** — `execute_shell()` targets
  one device per call; fanning out to multiple devices is the caller's responsibility.
- **Device capability discovery is limited to whatever `adb shell getprop` reports**
  in `DeviceInfo.extra` — there is no structured `DeviceCapabilities` taxonomy yet
  (deferred to Milestone 6, Capability-Based Architecture).

## Event Bus

- **No subscriber timeout**. A slow or hanging handler blocks all
  subsequent handlers for the same event topic.
- **No handler ordering**. When multiple handlers subscribe to the same
  topic, their execution order is undefined.
- **No event history/replay**. Past events cannot be replayed to
  late-joining subscribers.
- **No backpressure or rate limiting**. High-frequency publishers can
  overwhelm subscribers.

## Logging

- **No structured log shipping**. Structlog output goes to console and/or
  file; there is no built-in integration with log aggregators (ELK,
  Datadog, Grafana Loki).
- **No log sampling**. High-volume events cannot be sampled or throttled.
- **Logger configuration is read-once**. `configure_logger()` is designed
  to be called once at startup. Calling it again has undefined behavior.

## Platform

- **Windows signal handling is limited**. `loop.add_signal_handler` is
  partially supported on Windows. The `SIGINT`/`SIGTERM` fallback may not
  work in all Windows environments.
- **Python >= 3.13 only**. The project targets Python 3.13+ (using
  `X | Y` type union syntax and `Path.read_text`/`write_text` patterns).
  It will not install on older Python versions.
- **Alpha maturity**. This is an alpha release. APIs may change without
  notice. Not recommended for production workloads.
