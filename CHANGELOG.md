# Changelog

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
