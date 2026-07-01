# Game Plugin SDK

The Game SDK (`ugaf.sdk`) defines the contract every UGAF plugin must implement. It is the
**only** plugin system in the framework — see `PLUGIN_ARCHITECTURE.md` for discovery, validation,
and lifecycle orchestration.

## `GamePlugin` (`ugaf.sdk.game.GamePlugin`)

Abstract base class. Subclasses must set a class-level `metadata: PluginMetadata` attribute and
implement the required lifecycle methods:

| Method | Required | Called when |
|---|---|---|
| `initialize(context: GameContext) -> None` | yes | Once, after discovery, before `start()`. |
| `start() -> None` | yes | Transitioning `INITIALIZED` → `RUNNING`. |
| `pause() -> None` | no (no-op default) | Transitioning `RUNNING` → `PAUSED`. |
| `resume() -> None` | no (no-op default) | Transitioning `PAUSED` → `RUNNING`. |
| `stop() -> None` | yes | Transitioning `RUNNING`/`PAUSED` → `STOPPED`. |
| `shutdown() -> None` | yes | Terminal step; releases all resources. |
| `health() -> dict[str, Any]` | no (`{"status": "healthy"}` default) | On demand via `PluginManager.health(plugin_id)`. |

Any exception raised from `initialize`/`start`/`pause`/`resume`/`stop` moves the plugin to
`GameState.ERROR` and publishes a `plugin.failed` event; the exception is re-raised to the caller.
`shutdown()` exceptions are logged but swallowed (shutdown must always be able to complete).

## `PluginMetadata` (`ugaf.sdk.metadata.PluginMetadata`)

Frozen dataclass: `name`, `id`, `author`, `version`, `description`, `supported_platforms`,
`minimum_framework_version`, `capabilities` (list of `Capability`), `priority` (int, default 100).
This is the Python-side mirror of `manifest.yaml` — `PluginValidator.validate_manifest()` produces
one from the parsed YAML at discovery time; the `metadata` object inside `plugin.py` is what the
registry actually uses, so keep it in sync with the manifest by hand (there is currently no
single-source-of-truth enforcement between the two — see `KNOWN_LIMITATIONS.md`).

## `GameContext` (`ugaf.sdk.context.GameContext`)

Passed to `initialize()`. Carries `config: Config`, `logger: Logger`, `event_bus: EventBus`, and
`service_container: DependencyContainer` (pre-populated with `ImagingManager`/`VisionManager`
singletons when OpenCV is available). Plugins resolve their own dependencies from
`service_container` rather than importing framework internals directly.

## `GameState` (`ugaf.sdk.state.GameState`)

`CREATED`, `INITIALIZED`, `RUNNING`, `PAUSED`, `STOPPED`, `SHUTDOWN`, `ERROR`. Transition
validation lives on the enum itself (`GameState.validate_transition`); `PluginLifecycle` delegates
to it rather than re-implementing the state machine.

## `Capability` (`ugaf.sdk.capabilities.Capability`)

`INPUT`, `VISION`, `OCR`, `SCREENSHOT`, `MULTI_DEVICE`, `ADB`, `WINDOWS`. Declared in a plugin's
manifest/metadata so the framework (and future capability-based platform abstraction, see
`ARCHITECTURE.md`) can reason about what a plugin needs without inspecting its code.

## Framework events (`ugaf.sdk.events`)

`PLUGIN_LOADED`, `PLUGIN_INITIALIZED`, `PLUGIN_STARTED`, `PLUGIN_PAUSED`, `PLUGIN_STOPPED`,
`PLUGIN_SHUTDOWN`, `PLUGIN_FAILED` — published on the shared `EventBus` by `PluginManager`/
`PluginLifecycle` as a plugin moves through its lifecycle. Subscribe with wildcard topics (e.g.
`"plugin.**"`) to observe all plugin activity.

## Minimal example

See `games/example_game/` for a complete, runnable reference plugin that exercises the full
lifecycle without performing real automation, and `templates/plugin.py` /
`templates/manifest.yaml` for a copy-paste starting point.
