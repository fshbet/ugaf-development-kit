# Architecture Decision Records

## ADR-001: YAML-driven configuration with environment variable overrides

- **Status**: Accepted
- **Date**: 2026-06-27

### Context

Game automation plugins need configuration that can vary per deployment
(API keys, file paths, log levels). Using only YAML files requires file
modification for each environment, which is error-prone in CI/CD.

### Decision

Use YAML for the base configuration, then overlay environment variables
using a dotted-to-uppercase-underscore naming convention
(`UGAF_LOGGING_LEVEL` → `logging.level`). Environment overrides take
precedence over YAML values. The config is parsed once at startup and
remains immutable afterward.

### Consequences

- Positive: Simple, stateless configuration that works equally well in
  containers and local development.
- Positive: Environment variables can override any nested key without
  touching YAML files.
- Negative: No runtime config reload. A restart is required for changes.
- Negative: Only scalar overrides are supported (no way to set entire
  sub-trees via a single variable).

---

## ADR-002: Structured logging with structlog

- **Status**: Accepted
- **Date**: 2026-06-27

### Context

The framework needs logging that is machine-parseable (for CI and log
aggregators) while remaining human-readable during development.

### Decision

Use `structlog` as the logging layer with:
- Pretty-printed console output for local development.
- JSON output for file logging (configurable).
- A uniform event-name convention (`app.started`, `plugin_loader.loaded`)
  for structured log consumers.

### Consequences

- Positive: Structured key=value pairs make log analysis and filtering
  straightforward.
- Positive: Same API works for both human and machine consumers.
- Negative: Additional dependency (`structlog`).
- Negative: The standard library `logging` module is still used under
  the hood for output destination management.

---

## ADR-003: In-process plugin model with async event bus

- **Status**: Accepted
- **Date**: 2026-06-27

### Context

Game plugins (bots, vision modules, strategy engines) need to communicate
without hard coupling. A fully microservice architecture would be
premature given the alpha stage.

### Decision

Keep plugins as Python modules loaded in-process via
`importlib.util.spec_from_file_location`. Use an async publish/subscribe
event bus (`EventBus`) as the sole communication channel between plugins
and the framework. Wildcard topic patterns (`bot.*`, `app.**`) allow
flexible subscription without tight coupling.

### Consequences

- Positive: No serialization overhead. Plugins share Python objects
  directly through event data.
- Positive: Simple deployment — a single `uvicorn` or similar process.
- Negative: No isolation. A plugin crash or memory leak affects the
  entire application.
- Negative: No horizontal scaling for individual plugins (all run
  in one process).

---

## ADR-004: Base exception hierarchy with UGAFError

- **Status**: Accepted
- **Date**: 2026-06-27

### Context

Module-specific exceptions (`ConfigError`, `EventBusError`) make it
hard for callers to catch all framework-related errors without knowing
every module. Tests and framework integrations need a single base type.

### Decision

Introduce `UGAFError(Exception)` as the common base for all framework
exceptions. Each module still has its own typed exception:
- `ConfigError(UGAFError)`
- `EventBusError(UGAFError)`
- `ApplicationError(UGAFError, RuntimeError)` — double inheritance ensures
  existing `except RuntimeError` handlers still work while also
  appearing as `UGAFError`.

### Consequences

- Positive: Callers can catch `UGAFError` for framework-level error
  handling, or catch specific types for granular control.
- Positive: Backward compatible — `isinstance(ApplicationError(),
  RuntimeError)` is `True`.
- Negative: `ApplicationError` with multiple inheritance may confuse
  some tooling (though mypy and ruff accept it).

---

## ADR-005: No plugin dependency manager (alpha deferral)

- **Status**: Accepted
- **Date**: 2026-06-27

### Context

Plugins may depend on each other (e.g., a strategy plugin depends on a
vision plugin). Managing start/stop order and version compatibility
adds significant complexity.

### Decision

Defer plugin dependency management to a future sprint. The current
`PluginLoader` loads plugins in filesystem order (alphabetical), and
there is no dependency graph resolution. Plugin authors are expected
to ensure their plugins can start independently.

### Consequences

- Positive: Simpler initial implementation — 338 lines including
  discovery, loading, and lifecycle.
- Negative: Plugins that depend on other plugins may fail at startup
  if ordering is wrong.
- Negative: No version compatibility checking between plugins.

---

## ADR-006: `__all__` for public API surfaces

- **Status**: Accepted
- **Date**: 2026-06-27

### Context

With mypy's strict mode, implicit re-exports through `__init__.py` are
flagged as errors. The project needs a clear delineation of public vs.
private API.

### Decision

Every public module defines an explicit `__all__` listing its public
names. The `ugaf.core.__init__.py` re-exports these as the top-level
public API. Names not in `__all__` are considered internal
(prefixed with `_` where appropriate, but `__all__` is the enforcement
mechanism).

### Consequences

- Positive: Clear public API contract for consumers.
- Positive: mypy strict mode compliance without `type: ignore` noise.
- Negative: Requires maintenance — adding a new public function must
  also update `__all__`.

---

## ADR-007: Retire the legacy plugin loader in favor of the SDK exclusively

- **Status**: Accepted
- **Date**: 2026-07-01
- **Supersedes**: The plugin-loading half of ADR-003 and ADR-005 (their `EventBus`/no-dependency-manager
  conclusions still stand; only "which loader" changes).

### Context

A source-verified repository audit (see `PROJECT_STATUS.md`) found the project had accumulated
two independent, incompatible plugin systems: `ugaf/core/plugin_loader.py` + `ugaf/core/plugin.py`
(discovered `manifest.yaml` + optional `bot.py`/`vision.py`/`strategy.py`, but never actually
invoked any function inside them — plugins were "loaded" but not run), and `ugaf.plugins.*` +
`ugaf.sdk.game.GamePlugin` (fully implemented, unit-tested, correctly drives the real plugin
lifecycle). Only the legacy, non-functional loader was wired into `Application`/`cli.py`. The
project's own untracked sprint-validation reports had already flagged this as a critical defect
before this ADR was written.

### Decision

Delete `ugaf/core/plugin_loader.py` and `ugaf/core/plugin.py` entirely (including their exports
from `ugaf/core/__init__.py` and the now-unused `PluginLoaderError`/`PluginLifecycleError`
exceptions). Rewire `ugaf.core.bootstrap.Application`, `ugaf.core.context.AppContext`, and
`ugaf.core.cli` to construct and drive `ugaf.plugins.manager.PluginManager` instead. Replace the
legacy `templates/bot.py`/`strategy.py`/`vision.py`/`manifest.yaml` with a single
`templates/plugin.py` + SDK-style `templates/manifest.yaml` matching `games/example_game/`.

### Consequences

- Positive: `ugaf start` now actually executes plugin lifecycle code — verified manually by
  observing `example_game.initialized`/`.started`/`.stopped`/`.shutdown` log events fire during a
  live `Application.start()`/`stop()` run, which never happened before this change.
- Positive: One plugin system means one place to fix bugs, one manifest schema, one set of docs.
- Positive: `ugaf/core/` no longer needs to know about game/plugin concerns at all beyond owning a
  `PluginManager` instance — plugin-domain logic stays in `ugaf.plugins`/`ugaf.sdk`.
- Negative: Breaking change for anyone who had authored a plugin against the legacy
  `bot.py`/`vision.py`/`strategy.py` layout — there was no deprecation window because the legacy
  loader never worked in the first place (nothing could have depended on its runtime behavior).
- Negative: `manifest.yaml` and the in-code `metadata` object in `plugin.py` can still drift apart
  silently (tracked in `KNOWN_LIMITATIONS.md`) — not addressed by this ADR.
