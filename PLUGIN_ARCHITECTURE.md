# Plugin Architecture

UGAF has exactly one plugin system: the **Game SDK** (`ugaf.sdk` + `ugaf.plugins`). There is no
alternative or legacy loader — a prior dual-implementation defect (`ugaf/core/plugin_loader.py` /
`ugaf/core/plugin.py`, which discovered plugins but never actually executed their code) was
removed in Milestone 1 of the architecture hardening pass. If you see documentation, examples, or
prompts referencing `bot.py`/`vision.py`/`strategy.py` per-plugin files, they are stale — see
`CHANGELOG.md` for the migration.

## Directory layout

Each plugin lives under `games/<plugin_id>/` and must contain:

- `manifest.yaml` — plugin descriptor (see below).
- `plugin.py` — a module exposing a module-level `metadata: PluginMetadata` and exactly one
  concrete subclass of `ugaf.sdk.game.GamePlugin`.
- `config.yaml` (optional) — plugin-specific configuration, loaded by the plugin itself via
  `GameContext.config`, not by the framework.

See `templates/manifest.yaml` and `templates/plugin.py` for a copy-paste starting point, and
`games/example_game/` for a minimal working reference plugin.

## `manifest.yaml` schema

Required fields: `name`, `id`, `author`, `version` (semver, e.g. `1.0.0`).
Optional fields: `description`, `supported_platforms` (list of strings), `capabilities` (list of
`ugaf.sdk.capabilities.Capability` values: `input`, `vision`, `ocr`, `screenshot`,
`multi_device`, `adb`, `windows`), `minimum_framework_version` (semver, default `1.0.0`),
`priority` (int 0–1000, default 100, lower loads first).

Validation is performed by `ugaf.plugins.validator.PluginValidator.validate_manifest()` — invalid
manifests (bad semver, unknown capability, missing required field, incompatible framework
version) raise `PluginValidationError` and the plugin is skipped with a logged warning rather than
crashing discovery of other plugins.

## Discovery, loading, and lifecycle

1. **`ugaf.plugins.loader.PluginLoader.discover()`** scans the games directory (default `games/`,
   configurable via `--games-dir` / `Application(games_dir=...)`) for subdirectories containing
   both `manifest.yaml` and `plugin.py`, parses and validates the manifest, dynamically imports
   `plugin.py`, and locates the `GamePlugin` subclass inside it.
2. **`ugaf.plugins.registry.PluginRegistry`** is a thread-safe store of `(metadata, plugin_class)`
   pairs, keyed by `id`, rejecting duplicate IDs or duplicate display names.
3. **`ugaf.plugins.lifecycle.PluginLifecycle`** wraps a single plugin instance and drives it
   through `ugaf.sdk.state.GameState` (`CREATED → INITIALIZED → RUNNING → PAUSED/STOPPED →
   SHUTDOWN`, with an `ERROR` state on lifecycle-method exceptions), publishing
   `plugin.initialized` / `plugin.started` / `plugin.paused` / `plugin.stopped` /
   `plugin.shutdown` / `plugin.failed` events on the application event bus as it does.
4. **`ugaf.plugins.manager.PluginManager`** is the orchestrator: `discover()` populates the
   registry; `initialize_all()` / `start_all()` / `pause_all()` / `resume_all()` / `stop_all()` /
   `shutdown_all()` drive every registered plugin's lifecycle in priority order. It also builds
   the shared `GameContext` (config, logger, event bus, DI container) and wires the imaging/vision
   DI services into that container.

## Application wiring

`ugaf.core.bootstrap.Application` owns a single `PluginManager` instance
(`Application.plugin_manager`). `Application.start()` calls `discover()` → `initialize_all()` →
`start_all()`; `Application.stop()` calls `stop_all()` → `shutdown_all()`. The CLI's `ugaf
plugins` command lists discovered `PluginMetadata`; `ugaf health` reports the number of registered
plugins via a dedicated `plugin_manager` health check.

## Writing a `GamePlugin`

```python
from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata

metadata = PluginMetadata(
    name="My Game", id="my_game", author="Me", version="1.0.0",
)

class MyGame(GamePlugin):
    metadata = metadata

    async def initialize(self, context: GameContext) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def shutdown(self) -> None: ...
    # pause()/resume()/health() have sensible no-op/default implementations
    # and only need overriding if the plugin has real work to do there.
```

## Known limitations

- **No hot-reload.** Plugins are discovered once at startup; filesystem changes after that are
  not detected.
- **No dependency ordering between plugins.** `priority` controls start/stop order but there is no
  "plugin A requires plugin B" declaration.
- **No process isolation.** All plugins share the host Python process; a plugin that raises
  outside its lifecycle methods (e.g. in a background task it spawns) can affect the whole
  application.
- **`GameContext.service_container` vision/imaging registration is best-effort.** If OpenCV is
  unavailable, `PluginManager` logs a warning and skips registering `ImagingManager`/
  `VisionManager` rather than failing plugin discovery.
