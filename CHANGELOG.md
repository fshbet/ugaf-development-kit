# Changelog

## Unreleased

### Data-driven automation architecture: Knowledge -> Strategy -> Executor

#### Added

- **`ugaf.automation`**: a new, reusable, game-agnostic automation stack, extracted
  from `games/shadow_fight_3`'s original hardcoded logic:
  - `ugaf.automation.knowledge.KnowledgeBase` loads a game's `knowledge/moves.yaml`
    (named moves — ordered generic action steps + metadata: cooldown, damage,
    shadow_cost, range, startup, recovery, priority, tags) and `knowledge/buttons.yaml`
    (named controls — screen positions as resolution-independent fractions).
  - `ugaf.automation.strategy.StrategyEngine` evaluates a `strategies/<name>.yaml`
    file's ordered `when -> do` rules each cycle to pick which moves run.
  - `ugaf.automation.executor.Executor` turns a move's step sequence into real
    `InputManager` calls (`tap`, `move`, `hold`, `wait`) — no game-specific knowledge.
  - See ADR-014 in `ARCHITECTURE_DECISIONS.md` for the full rationale.
- **`VisionManager.measure_bar_fill`/`wait_until_visible`/`wait_until_hidden`**: three
  new reusable vision primitives (any left-to-right bar gauge; polling for a template
  to appear/disappear) — game-agnostic infrastructure for the vision-driven strategy
  conditions this architecture is designed to support next.
- **`games/shadow_fight_3` restructured** into the new architecture:
  `knowledge/moves.yaml`, `knowledge/buttons.yaml`, `strategies/{balanced,aggressive,
  defensive}.yaml`, plus a `README.md` documenting how to add a move or strategy
  without touching Python. `plugin.py` shrank to a thin shell (connect, load
  knowledge/strategy, drive the executor loop, report status) — no move names,
  coordinates, or combo sequences remain in Python.

#### Fixed

- **Real bug found via this refactor**: `PluginManager.initialize_all()`/`start_all()`
  let one plugin's failure abort every other plugin's auto-start. Invisible until now
  because earlier test runs happened to have a real device connected; with no device,
  `shadow_fight_3` (which requires real ADB) failing during `Application.start()`'s
  default auto-start was aborting `demo_workflow` and `example_game` too, even though
  neither needs hardware. Fixed by making both methods fault-isolated per plugin (log
  a warning and continue, rather than propagate).

#### Validation

Full test suite (653 tests), ruff, and mypy pass with **no real device connected** —
closing the gap the fix above addresses. Re-validated live on the same physical
Xiaomi/HyperOS device afterward: the refactored plugin reproduced the exact same
cycle-by-cycle move rotation (shuriken at cycle 4/8/16, shadow ability at cycle 6/12,
alternating jab/heavy combo otherwise) as the pre-refactor hardcoded version, now
driven entirely by `strategies/balanced.yaml`, with real ADB taps confirmed via server
logs and a clean start/pause/resume/stop cycle through the web UI.

### First-run fixes + Shadow Fight 3 plugin (found via real-hardware use)

#### Fixed

- **Plugin "Run" button returned `400 Cannot transition from 'running' to 'initialized'`.**
  `Application.start()` unconditionally auto-initialized and started every discovered
  plugin at boot — correct for the CLI's `ugaf start` (a headless runner), but it meant
  every plugin was already `RUNNING` by the time the web UI's "Run" button called
  `initialize()` again. Fixed with a new `auto_start_plugins` parameter (default `True`,
  set to `False` by `AppSession.start()`), plus idempotent `AppSession.run_plugin()`/
  `stop_plugin()` that check the plugin's current `GameState` and pick the correct
  transition (or no-op if already running/stopped) instead of assuming a fresh plugin.
- **Live screen did not refresh after tap/swipe/text actions.** `app.js` only
  re-captured the screen after an action if the "Auto-refresh" checkbox was checked,
  and the checkbox defaulted unchecked. The checkbox now defaults checked, and action
  feedback (tap/swipe/text) always triggers an immediate re-capture regardless of the
  checkbox — the checkbox now only gates the passive 3s polling interval.

#### Added

- **`games/shadow_fight_3`**: an automated combat plugin for Shadow Fight 3, built from
  a user-supplied screenshot of the game's HUD (bottom-left 8-directional joystick;
  bottom-right 4-button cluster — shuriken above, shadow ability left, punch right,
  kick below). Control positions are stored as fractions of screen size in
  `config.yaml`, resolved to real pixels from the connected device's detected
  resolution, so the same config works across devices. Runs a background
  `asyncio.Task` combat loop (advance, rotate punch/kick combos, periodic shuriken and
  shadow-ability triggers) started in `start()` and cancelled in `stop()` — the first
  UGAF plugin to run as a genuine continuous background loop rather than a one-shot
  workflow. Validated live against the same physical Xiaomi/HyperOS device: real ADB
  taps executed for 14+ combat cycles, screen size auto-detected (1220×2712), and
  clean start/stop/double-run idempotency confirmed through the actual web UI.

### Web control panel + real-device validation

#### Added

- **`ugaf.webapp`**: a FastAPI backend (`server.py`, `session.py`) plus a static HTML/
  JS/CSS frontend (`static/`) — a browser-based control panel to detect devices, view
  the live screen, click to tap, drag to swipe, send text, run plugins, and view logs,
  with no code or ADB commands. Launch via `python -m ugaf.webapp`.
- **`Config.from_dict()`**: a new small, justified public API on `ugaf.core.config.Config`
  for building a config from an in-memory dict without a temp YAML file — needed by
  two independent call sites (the web session forcing `provider: adb` for device
  connections, replacing an earlier private-attribute workaround).
- 16 new FastAPI `TestClient` tests (`tests/test_webapp_server.py`), CI-safe (all ADB
  subprocess calls mocked — no real `adb` binary or device required).

#### Fixed (found via real-hardware testing)

- **`AppSession.list_plugins()`** used `PluginManager.discover()`, which only returns
  newly-found plugins — since plugins are already discovered once at
  `Application.start()`, the web UI's plugin panel was always empty. Fixed to read
  `PluginManager.registry.list()`.
- **Device connections from the web UI reused the shared framework config's
  `input.provider: windows` default** instead of forcing `adb`, so every real-device
  connect attempt failed. Fixed via `Config.from_dict({"input": {"provider": "adb"}})`.
- **`AdbInputProvider._adb_shell()` silently swallowed all failures**, including a
  real `SecurityException` from a test device's OS blocking ADB input injection
  entirely — the failure was completely invisible until raw `adb` was tested outside
  the framework. Now logged at warning level (still doesn't raise, since tap/swipe are
  fire-and-forget by design).

#### Real hardware validation

A physical Android device (Xiaomi/HyperOS, `peridot`) was connected via ADB.
Confirmed live: device detection, connection, and screenshot capture (visually
verified — a real captured screenshot of the device's home screen and Calculator
app). Tap was validated end-to-end through the actual web application: computed
button coordinates from a live screenshot, executed `2 + 2 = 4` on the device's real
Calculator via tap, and confirmed the result with a second real screenshot. Swipe was
confirmed to execute without error on real hardware (same underlying ADB path as
tap) but wasn't visually confirmed against a swipe-reactive UI element in this pass.
Uncovered a device-specific OS restriction (see README.md) requiring a Developer
Options change to permit ADB input injection at all — not a UGAF defect, but now
documented and (for the swallowed-failure case) surfaced in logs instead of silent.

### Version 0.1 reached: capture → find → tap → swipe → type, end to end

#### Added

- **`games/demo_workflow`**: a plugin demonstrating the full Version 0.1 workflow
  (capture the screen, find a template image, tap it, swipe, enter text) end to end,
  driven through the real `Application`/`PluginManager` discovery path. Runs against
  bundled demo assets (a rendered "screen" image + button template) with
  `ImageReplayProvider`/`MockInputProvider` — no real device required; switching
  `games/demo_workflow/config.yaml` to `adb` drives a real connected device instead,
  with no code changes.
- **`ugaf.input.mock.MockInputProvider`**: logs actions instead of performing them
  (the input-side counterpart to `MockScreenshotProvider`), registered as `"mock"`.
- **Template-matching reliability tests** (`tests/test_vision_matcher_reliability.py`):
  validates `TemplateMatcher` against realistic rendered images (gradients, noise,
  drawn UI elements) rather than the zero-filled arrays the original audit flagged —
  exact localization, noise tolerance, correct rejection of dissimilar templates, and
  multi-element discrimination.
- **`prompts/MASTER_PROMPT.md`**: single current entry point for future development
  sessions, consolidating the philosophy/architecture guidance that had accumulated
  across many directive messages. Historical per-sprint prompts are preserved as-is.
- 20 new tests (mock input provider, matcher reliability, demo plugin end-to-end).

#### Changed

- `README.md` and `ROADMAP.md` rewritten to reflect current reality (were stale
  one-line/phase-list stubs) — `ROADMAP.md` now tracks the Version 0.1 capability
  checklist directly; `PROJECT_STATUS.md` leads with the same checklist.

### Screenshot Capture subsystem (closes: "vision engine cannot see the screen")

#### Added

- **CI/CD**: `.github/workflows/ci.yml` running ruff, ruff format check, mypy, pytest
  with coverage, and a build-validation job, matrixed across `ubuntu-latest` and
  `windows-latest`. Added `.gitignore` (build/dist/egg-info/caches were previously
  untracked-but-ungitignored).
- **`ugaf.vision.adb_screenshot.AdbScreenshotProvider`**: real screenshot capture via
  `adb exec-out screencap -p` (chosen over `adb shell screencap` + `pull`, scrcpy,
  MediaProjection, UI Automator, emulator console, and minicap after comparing all six
  — see `SCREENSHOT_CAPTURE_STRATEGY.md`). Per-device scoped, mirroring
  `AdbInputProvider`'s design (ADR-011).
- **`ugaf.vision.mock_screenshot.MockScreenshotProvider`** and **`ImageReplayProvider`**:
  first-class providers for testing and offline plugin development without a device.
- **`ugaf.vision.screenshot_manager.ScreenshotManager`**: provider selection via
  `vision.screenshot_provider` config + a registry (mirroring `InputManager`), frame
  caching with configurable TTL (no unnecessary copies — cache hits return the same
  `Image` reference), bounded retry, and async capture with timeout
  (`capture_full_async`). Subclasses `ScreenshotProvider` itself (ADR-013) so it drops
  into `VisionManager` with zero API changes.
- **Wired end-to-end**: `PluginManager` now constructs and connects a
  `ScreenshotManager` and passes it to `VisionManager` — verified live that
  `VisionManager.screenshot()` returns real image data through the full DI chain, which
  never worked before this milestone.
- **38 new tests** across 4 new test files plus a lightweight cache-effectiveness
  benchmark, all screenshot modules at 100% coverage.

#### Documentation

- **`SCREENSHOT_CAPTURE_STRATEGY.md`**: research comparing all seven capture
  mechanisms evaluated, with sources.

### Governance audit fix: eliminated ADB device-parsing duplication

#### Fixed

- **`ugaf.input.adb.AdbInputProvider`** no longer has its own `adb devices` parser
  (which only recognized the literal `"device"` state, silently treating
  `offline`/`unauthorized` as "not found" — the exact defect the original repository
  audit flagged). It now delegates to `ugaf.device.adb_provider.AdbDeviceProvider` for
  device enumeration and shell execution, and accepts an optional `device_provider`
  constructor parameter to reuse an existing instance. See `ARCHITECTURE_DECISIONS.md`
  ADR-012. This was deferred twice already (Milestones 3 and 4) as documented "future
  cleanup" — fixed now per the new continuous technical-debt-elimination governance.
- **`docs/README.md` / `examples/README.md`**: replaced one-line placeholder stubs with
  real content pointing to the actual design docs and `games/example_game/`.

#### Changed (test migration)

- `tests/test_input_adb.py`: 32 tests updated to patch
  `ugaf.device.adb_provider.subprocess.run` (the new actual ADB call site) instead of
  `ugaf.input.adb.subprocess.run`; added tests for the precise
  online/offline/unauthorized status messages and the new `device_provider=` injection
  point.

### Milestone 4: Multi-device input architecture (prerequisite for Robust Android Transport)

#### Added

- **`InputManager(config, device_id=..., device_manager=...)`**: `InputManager` now
  accepts an explicit target `device_id` (overriding `input.adb.default_device`) and an
  optional `DeviceManager` reference, enabling multiple `InputManager` instances to
  share one `Config` while independently targeting different Android devices — see
  `ARCHITECTURE_DECISIONS.md` ADR-011.
- **Precise pre-flight device status checks**: when a `device_manager` is supplied,
  `InputManager.connect()` checks the target device's real status through
  `AdbDeviceProvider`'s accurate parsing before attempting to connect, raising
  `DeviceNotFoundError` with the actual state (`unauthorized`/`offline`/etc.) instead of
  a generic failure.
- **`PluginManager(..., device_manager=...)`**: registers `DeviceManager` as a DI
  singleton in every plugin's `GameContext`, so a plugin can resolve it and construct
  its own per-device `InputManager` instances — verified end-to-end (a plugin resolves
  the real `Application`-owned `DeviceManager` from its context).
- **17 new tests** across `test_input_manager.py` and `test_plugin_manager.py`.

#### Documentation

- Added an "Architecture Impact Analysis" precedent to `ARCHITECTURE_DECISIONS.md`
  (ADR-011) per the new architectural-planning directive requiring this analysis
  before every future milestone.

### Milestone 3: Device Manager

#### Added

- **`ugaf.device` package**: `DeviceManager` (central orchestrator — the Core Engine
  and plugins never talk to ADB directly), `AdbDeviceProvider` (real
  `adb devices -l` parsing that correctly distinguishes `online`/`offline`/
  `unauthorized`/unknown states, fixing a gap the original audit identified in
  `ugaf.input.adb.AdbInputProvider`'s narrower parsing), device lifecycle events
  (`device.discovered`, `device.online`, `device.offline`, `device.unauthorized`,
  `device.lost`), retrying command execution with ADB-server-restart recovery, and
  optional property enrichment via `adb shell getprop`.
- **`Application.device_manager`** / **`AppContext.device_manager`**: wired into
  bootstrap with a dedicated `device_manager` health check; `device.adb.executable`
  and `device.monitor.{enabled,interval}` added to `config/default.yaml`.
- **`ANDROID_TRANSPORT_STRATEGY.md`**: research comparing ADB, UIAutomator2,
  Accessibility Service, and scrcpy, with sources, informing why ADB is Milestone 3's
  transport and what the multi-transport roadmap looks like for Milestones 4/5.
- **38 new tests** (`test_device_adb_provider.py`, `test_device_manager.py`) — 98%
  coverage of the new package.

#### Fixed

- **Pre-existing circular import** (introduced in Milestone 1, latent):
  `from ugaf.plugins.manager import PluginManager` failed standalone due to
  `ugaf.core.__init__` eagerly importing `bootstrap.py`, which imported back into
  `ugaf.plugins`/`ugaf.device` while those packages were still initializing. Fixed by
  moving `PluginManager`/`DeviceManager` imports in `bootstrap.py`/`context.py` to
  `TYPE_CHECKING`-only + lazy runtime imports (ADR-009). Verified: all four previously
  broken standalone imports now succeed.

### Milestone 2: Platform Abstraction Layer

#### Added

- **Platform Abstraction Layer**: new `ugaf.platform` package with OS-independent
  interfaces for Display, Clipboard, File System, Network, Accessibility,
  Notifications, Process Management, and Device enumeration — `ugaf.core` and plugins
  no longer need to touch OS APIs directly for these concerns. See
  `PLATFORM_ABSTRACTION.md`.
- **Real adapters**: `WindowsDisplayProvider` and `WindowsClipboardProvider` (Win32 APIs
  via `ctypes`), `WindowsNotificationProvider` (`System.Windows.Forms.NotifyIcon` via
  PowerShell, no extra module required), `LocalFileSystemProvider` (`pathlib`),
  `DefaultNetworkProvider` (`socket`), `DefaultProcessManager` (`subprocess`) — all
  verified against the real OS, not just mocked.
- **`ugaf.platform.registry.AdapterRegistry[T]`**: generic, thread-safe adapter
  registry generalizing `ugaf.input.registry.InputProviderRegistry`'s pattern across
  all eight new subsystems (see `ARCHITECTURE_DECISIONS.md` ADR-008).
- **Platform-aware input provider selection**: `InputManager.connect()` now consults
  `ugaf.core.platform.detect_platform()` when `input.provider` is not explicitly
  configured, instead of always defaulting to `"windows"` — closes a gap identified
  during the repository audit (`detect_platform()` existed but was never consumed).
- **63 new tests** covering every new `ugaf.platform` module plus the platform-aware
  input provider default.
- **`PLATFORM_ABSTRACTION.md`**: new design document for the Platform Abstraction Layer.

#### Fixed

- **64-bit clipboard handle truncation**: an early version of `WindowsClipboardProvider`
  relied on `ctypes`' default `c_int` return type for `GlobalAlloc`/`GlobalLock`/
  `GetClipboardData`, which silently truncates 64-bit handles on Win64 and corrupted
  every clipboard operation. Fixed by setting explicit `argtypes`/`restype`
  (`c_void_p`) on every handle-returning Win32 call — caught by a real clipboard
  round-trip test, not a mock.

#### Known limitations (new)

- No Linux/macOS adapters yet for Display, Clipboard, or Notifications.
- `DeviceProvider`/`AccessibilityProvider` ship as interfaces only — no concrete
  adapters until Milestones 3 and 4.
- `AdapterRegistry` has no platform-aware auto-selection helper yet (each subsystem
  currently has at most one adapter, so there's nothing to choose between).

## 1.0.0a5 (2026-07-01)

### Removed (breaking)

- **Legacy plugin loader**: `ugaf/core/plugin_loader.py` (`PluginLoader`, `PluginInfo`,
  `PluginManifest`) and `ugaf/core/plugin.py` (`PluginInstance`, `PluginState`) have been deleted.
  This loader discovered `manifest.yaml`/`bot.py`/`vision.py`/`strategy.py` but never actually
  invoked any plugin code — `ugaf.plugins.manager.PluginManager` (the SDK-based system) is now the
  framework's only plugin system. See `ARCHITECTURE_DECISIONS.md` ADR-007.
- **`PluginLoaderError`, `PluginLifecycleError`**: removed from `ugaf.core.exceptions` (unused
  after the above removal — the SDK system uses `ugaf.sdk.exceptions.PluginValidationError` /
  `PluginStateError`).
- **`templates/bot.py`, `templates/strategy.py`, `templates/vision.py`**: removed. Replaced by a
  single `templates/plugin.py` implementing `GamePlugin`.

### Changed (breaking)

- **`Application.plugin_loader`** → **`Application.plugin_manager`** (`PluginManager` instead of
  `PluginLoader`). `Application.start()` now calls `discover()` → `initialize_all()` →
  `start_all()`; `Application.stop()` calls `stop_all()` → `shutdown_all()` — plugin lifecycle
  methods are now actually invoked (previously they were not).
- **`AppContext.plugin_loader`** → **`AppContext.plugin_manager`**.
- **`ugaf core.__init__.py`**: no longer re-exports `PluginInfo`/`PluginLoader`/
  `PluginLoaderError`/`PluginManifest` (plugin concerns now live entirely in `ugaf.plugins`/
  `ugaf.sdk`, not `ugaf.core`).
- **`ugaf plugins` CLI command**: now lists `PluginMetadata` (name, id, author, capabilities,
  priority) from the SDK registry instead of legacy bot/vision/strategy module flags.
- **`templates/manifest.yaml`**: rewritten to the SDK schema (`id`, `author`, `capabilities`,
  `priority`, `minimum_framework_version`) instead of the legacy flat `name`/`version` schema.
- **`games/example_game/manifest.yaml`**: fixed a `capabilities` mismatch against `plugin.py`
  (manifest said `[input]`, code said `[]`) found during the architecture audit — now both say
  `[]`, matching the plugin's actual (no-op) behavior.

### Added

- **`tests/test_cli.py`**: 8 new tests covering `build_parser`, and the `version`/`stop`/`health`/
  `plugins` CLI commands — `ugaf/core/cli.py` previously had 0% test coverage.
- **`plugin_manager` health check**: `Application` now reports the number of registered plugins
  via `ugaf health`.
- **`PROJECT_STATUS.md`, `BUILD_STATUS.md`**: source-verified repository audit reports (see
  Milestone 1 of the architecture hardening directive).

## 1.0.0a4 (2026-06-27)

### Added

- **Game SDK**: `ugaf.sdk` package with `Capability` enum (7 members),
  `GameState` enum (8 states + transition map), `PluginMetadata` (frozen
  dataclass), `GameContext` (dataclass with core services + extra dict),
  `GamePlugin` (abstract base class with 8 async lifecycle methods), and
  7 framework event topic constants.
- **Plugin framework**: `ugaf.plugins` package with `PluginRegistry`
  (thread-safe, duplicate-ID/name detection, capability-based lookup,
  priority-sorted listing), `PluginValidator` (required fields, semver,
  framework version compatibility, capability parsing), `PluginLifecycle`
  (state machine with event publishing, error handling, health checks),
  `PluginLoader` (filesystem discovery — 6 scenarios handled), and
  `PluginManager` (orchestrator for discover/load/initialize/start/stop/
  pause/shutdown operations on individual or all plugins).
- **Reference game**: `games/example_game/` with manifest, plugin class,
  and configuration for SDK verification.
- **Test coverage**: 43 tests across lifecycle (state transitions, event
  publishing, error handling, health), loader (6 discovery scenarios),
  and manager (orchestration, batch operations, error paths).

### Fixed

- **`_transition()`**: was validating state transitions but never assigning
  `self._state` — now correctly sets `self._state = target`.
- **`initialize_all()`**: was iterating over `PluginMetadata` objects as
  plugin IDs instead of `meta.id` strings.

## 1.0.0a3 (2026-06-27)

### Added

- **Input engine**: `ugaf.input` package with abstract `InputProvider`,
  `WindowsInputProvider`, `AdbInputProvider`, and `InputManager`.
- **Windows provider**: desktop automation via `pyautogui`, `keyboard`, and
  `mouse` — mouse movement, clicks, drags, scrolling, keyboard input,
  hotkeys, and screenshots.
- **ADB provider**: Android automation via ADB shell commands — tap, swipe,
  long press, text input, key events, screen-size detection, device
  discovery, and screenshot capture.
- **Input manager**: provider selection (YAML-driven), lifecycle management,
  coordinate validation, automatic retries with configurable count/delay,
  dry-run mode, verbose logging, and context-manager support.
- **Input exceptions**: `InputError`, `DeviceNotFound`, `ProviderNotAvailable`,
  `ConnectionFailed`, `CoordinateOutOfBounds`.
- **Type definitions**: `Point` (frozen dataclass), `Button` and `Key` type
  aliases.
- **Input configuration**: `config/default.yaml` with `input.*` settings
  (provider, delays, retry, ADB path, dry-run, verbose).
- **Optional input dependencies**: `[input]` extras group in `pyproject.toml`
  (`pyautogui`, `keyboard`, `mouse`).
- **Test coverage**: 80+ tests for exceptions, types, Windows provider
  (mocked), ADB provider (mocked), manager (mocked), coordinate validation,
  retry logic, dry-run mode, and context-manager protocol.

### Changed

- **`config/default.yaml`**: now includes default `input` section.

## 1.0.0a2 (2026-06-27)

### Added

- **Sprint 02 framework**: DI container (`DependencyContainer`), plugin
  lifecycle (`PluginInstance`), health checks (`HealthRegistry`), platform
  detection (`detect_platform`), application context (`AppContext`), and
  CLI framework (`build_parser`, `run_cli`).
- **Exception types**: `DependencyInjectionError`, `CircularDependencyError`,
  `PluginLifecycleError`, `HealthCheckError`, `PlatformError`, `CliError`.
- **Health check framework**: `HealthStatus`, `HealthResult`, `HealthRegistry`
  with concurrent check execution and exception isolation.
- **Plugin lifecycle**: `PluginState` enum with valid state transitions
  (CREATED → INITIALIZED → STARTED → PAUSED → STOPPED → SHUTDOWN).
- **Platform detection**: `PlatformInfo` frozen dataclass with WSL detection.
- **Dependency injection**: thread-safe container with singleton/transient
  lifetimes, constructor injection, and circular dependency detection.
- **Application context**: `AppContext` dataclass wiring all core services.
- **Default configuration**: `config/default.yaml` with logging defaults.

### Changed

- **Bootstrap**: `Application` gains `app.run_forever()`, `app.health()`,
  `app.context` property; fully backward-compatible.
- **`__init__.py`**: exports all new Sprint 02 types.

## 1.0.0a1 (2026-06-27)

### Added

- **Core framework**: config, logger, event bus, plugin loader, and bootstrap
  modules providing the foundation for UGAF-based game automation.
- **Base exception hierarchy**: `UGAFError` with typed subclasses
  (`ConfigError`, `EventBusError`, `PluginLoaderError`, `ApplicationError`)
  for predictable error handling. All subclasses can be caught as either
  the typed error or `RuntimeError` (backward-compatible).
- **Configuration validation**: YAML structure checking — non-dict top-level
  values (lists, scalars) are now rejected with a descriptive error.
- **Manifest validation**: plugin manifests missing `name` or `version` are
  now rejected with a clear error message.
- **MANIFEST.in**: source distribution metadata for PyPI publishing.
- **Packaging metadata**: `[project.urls]`, `[project.readme]`,
  classifiers, and keywords in `pyproject.toml`.
- **Test coverage**: YAML structure validation tests, manifest validation
  tests (empty name, missing version, None name).

### Changed

- **Exception refactor**: all custom exceptions now inherit from a common
  `UGAFError` base class instead of raw `Exception`.
- **Bootstrap errors**: `Application.initialize()`/`start()`/`stop()` now
  raise `ApplicationError` (inherits `UGAFError` and `RuntimeError`)
  instead of bare `RuntimeError`.
- **Error messages**: improved with file paths, field names, and context for
  all config, plugin loader, and bootstrap error paths.
- **Logging event names**: normalized dotted convention across all modules.
- **Explicit `__all__`**: added to all public modules for mypy strict mode
  compliance.

### Fixed

- **build-backend**: changed from `setuptools.backends._legacy:_Backend`
  (private, undocumented) to `setuptools.build_meta` (public API).
- **Import scope**: `import yaml` moved from lazy inside `Config.load()` to
  module level for consistency with `plugin_loader.py`.
- **Import style**: `import os` changed to `from os import environ` for
  precision.
- **Signal safety**: `signal.Signals(sig).name` guarded with
  `try/except ValueError` to handle unknown signal numbers gracefully.
- **Pattern matching bug**: greedy `**` wildcard in `_pattern_matches`
  fixed (was not exploring all topic-remainder positions).
- **Test hardening**: `test_json_format` now asserts parseable JSON,
  `test_rotation_behavior` validates `RotatingFileHandler` properties,
  bootstrap tests type-annotated for mypy strict mode.
