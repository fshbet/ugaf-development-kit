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
  matching, feature detection, and screen capture. Screenshot capture is
  provider-based (`ugaf.vision.screenshot.ScreenshotProvider`), orchestrated by
  `ugaf.vision.screenshot_manager.ScreenshotManager` (provider selection via config,
  frame caching, bounded retry, async capture with timeout) — see
  `SCREENSHOT_CAPTURE_STRATEGY.md`. `ScreenshotManager` itself subclasses
  `ScreenshotProvider`, so it drops into `VisionManager` transparently.
- **Game SDK / Plugins** (`ugaf.sdk`, `ugaf.plugins`): the `GamePlugin` contract and its
  discovery/validation/lifecycle orchestration — the framework's only plugin system as
  of Milestone 1. `PluginManager` registers `DeviceManager` as a DI singleton in every
  plugin's `GameContext` when one is supplied, so a plugin resolves it and builds its
  own per-device `InputManager` instances rather than the framework prescribing a
  single global input target.
- **Automation stack** (`ugaf.automation`): Knowledge -> Strategy -> Executor —
  reusable, game-agnostic modules that let a plugin's actual behaviour live in YAML
  instead of Python. `ugaf.automation.knowledge.KnowledgeBase` loads a game's named
  moves (`knowledge/moves.yaml`, ordered generic action steps + metadata) and control
  layout (`knowledge/buttons.yaml`, screen positions as resolution-independent
  fractions). `ugaf.automation.strategy.StrategyEngine` evaluates a game's
  `strategies/*.yaml` (ordered condition -> move-name rules) each cycle to decide what
  to do. `ugaf.automation.executor.Executor` turns a move's step sequence into real
  `InputManager` calls (`tap`, `move`, `hold`, `wait`) — it has zero game-specific
  knowledge. None of these three modules know anything about any specific game; a
  plugin only wires them to a connected device. See `games/shadow_fight_3/README.md`
  for a worked example and ADR-014 in `ARCHITECTURE_DECISIONS.md`.
- **Application Manager** (`ugaf.apps`): reusable Android application lifecycle
  management, so no automation hand-rolls its own "is it installed, launch it, is it in
  the foreground" logic. `ugaf.apps.manager.ApplicationManager` talks only to
  `DeviceManager.execute_shell()` (never a transport directly) to check whether a
  package is installed, launch it (via an explicit `launch_activity`, or the app's own
  launcher intent when none is given — works for any installed app without knowing its
  activity), poll for it reaching the foreground, and optionally force-stop it. Each
  automation declares its target app as data (`app.yaml`: name, package, launch
  activity, timeout/retries, expected startup templates, shutdown behaviour) via
  `ugaf.apps.types.AppDefinition` — never hardcoded in Python. `PluginManager` registers
  one `ApplicationManager` as a DI singleton (alongside `DeviceManager`), so every
  plugin resolves the same instance for free. See `games/shadow_fight_3/app.yaml` for a
  worked example and ADR-015 in `ARCHITECTURE_DECISIONS.md`.
- **Web control panel** (`ugaf.webapp`): a FastAPI backend + static HTML/JS frontend
  that lets a user detect devices, view the live screen, tap/swipe/type, and run
  automations from a browser with no code, no ADB commands, and no developer
  terminology — "Automations" (not "plugins"), each showing its target application and
  live status. `AppSession` (`ugaf.webapp.session`) is a thin wrapper around one
  `Application` instance — every route in `ugaf.webapp.server` delegates to it; no
  automation logic lives in the web layer itself. One `InputManager`/`ScreenshotManager`
  pair per connected device, consistent with the multi-device design below. The frontend
  (`ugaf/webapp/static/`) has no build step (plain HTML/CSS/JS) but follows a real design
  system — see the "UI" note in `ugaf/webapp/static/style.css`'s design-token block.

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

## Startup workflow (established with the Application Manager)

An automation with a target app (`app.yaml` present) never assumes the app is already
open. `start()` runs, in order: resolve the target device (`DeviceManager.resolve_device`)
-> confirm the app is installed (`ApplicationManager.is_installed`) -> launch it
(`ApplicationManager.launch`) -> poll until it's confirmed in the foreground
(`ApplicationManager.wait_for_foreground`) -> only then is the plugin's own automation
loop started. A launch that never reaches the foreground retries up to
`app.yaml`'s `launch_retries`, then raises — the plugin's `start()` fails loudly (visible
as a clear error in the web UI) rather than silently beginning automation against the
wrong screen. See `games/shadow_fight_3/plugin.py` for the reference implementation.

## Future: automation recorder (design only, not yet implemented)

Planned capability, not yet built: a recorder that watches a user interact with a
connected device (tap/swipe/type events, screenshots at each step) and emits a YAML
step list — using the same executor verbs `ugaf.automation.executor.Executor` already
understands (`tap`, `move`/`swipe`, `hold`, `wait`), plus a `template_match`/`wait_for`
verb for screen-state-gated steps (e.g. "wait for the fight button, then tap it").
A recorded session becomes a `strategies/<name>.yaml` (or a new `knowledge/moves.yaml`
entry) that a user can immediately edit and replay — no Python required to go from "I
did this once" to "do this every time." Likely home: `ugaf.webapp` captures raw
tap/swipe events already sent through its existing `/api/devices/{id}/tap`|`/swipe`
routes; a record-mode toggle would log them (with the screenshot at time of action) to
a session buffer, then a "Save as automation" action would write the YAML. Vision-gated
waits would reuse `VisionManager.wait_until_visible`. Not started — flagged in
`ROADMAP.md` as the next major capability once vision-driven strategy conditions
(health/shadow-meter reading) are wired up.

## Platform priority

Android is the current implementation priority; Windows, Linux, and macOS follow. Every
subsystem in the Platform Abstraction Layer is designed so a new OS is supported by
adding one adapter class and registering it — no changes to `ugaf.core` or plugin code
should ever be required to add platform support.