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

---

## ADR-008: One generic `AdapterRegistry`, not one bespoke registry per platform subsystem

- **Status**: Accepted
- **Date**: 2026-07-01

### Context

Milestone 2 (Platform Abstraction Layer) introduces eight new system-level interfaces
(Display, Clipboard, File System, Network, Accessibility, Notifications, Process
Management, Device). `ugaf.input.registry.InputProviderRegistry` already solved
adapter registration/selection for the Input subsystem with a thread-safe, named,
factory-style registry. Writing eight near-identical copies of that class would
duplicate ~80 lines of correct, tested logic eight times over.

### Decision

Generalize the pattern into `ugaf.platform.registry.AdapterRegistry[T]`, a generic class
parametrized by the subsystem's base interface type, with the exact same
register/unregister/create/list_adapters/is_registered surface as
`InputProviderRegistry`. Each subsystem module exposes one module-level singleton
instance (`display_registry`, `clipboard_registry`, etc.) in `ugaf/platform/__init__.py`
rather than defining its own registry class.

`InputProviderRegistry` itself was **not** refactored to use `AdapterRegistry` in this
pass — it predates this ADR, is stable, well-tested, and touching it would be
unjustified churn for a Milestone whose stated goal is adding new subsystems, not
refactoring a working one. A future cleanup milestone may consolidate it once
`AdapterRegistry` has proven itself across the eight new subsystems.

### Consequences

- Positive: One reviewed, tested implementation instead of eight near-duplicates.
- Positive: New subsystems (future OSes, future capabilities) get registry behavior for
  free by declaring `AdapterRegistry[TheirInterface]`.
- Negative: `mypy --strict` cannot statically verify that `AdapterRegistry(SomeABC)` is
  safe (it assumes `type[T]` implies direct instantiability) — each of the eight
  registry singletons in `ugaf/platform/__init__.py` carries a
  `# type: ignore[type-abstract]` comment. This is a real, understood false positive
  (the registry never calls `self._interface()`), not suppressed carelessly.
- Negative: `ugaf.input.registry.InputProviderRegistry` and
  `ugaf.platform.registry.AdapterRegistry` are now two registries with near-identical
  logic living in the codebase simultaneously — acceptable short-term duplication per
  the "don't refactor working code mid-milestone" reasoning above, tracked as future
  cleanup rather than silently accepted.

---

## ADR-009: Lazy imports in `bootstrap.py`/`context.py` to break a real circular import

- **Status**: Accepted
- **Date**: 2026-07-01

### Context

Building `ugaf.device` for Milestone 3 surfaced a real, pre-existing circular-import
defect introduced in Milestone 1: `ugaf/core/__init__.py` eagerly imports
`ugaf.core.bootstrap.Application`, and `bootstrap.py`/`context.py` import
`ugaf.plugins.manager.PluginManager` (and, as of this milestone,
`ugaf.device.manager.DeviceManager`) at module level. Any package that imports a leaf
`ugaf.core.*` submodule (e.g. `ugaf.core.exceptions`, `ugaf.core.event_bus`) before
`ugaf.core` has been touched elsewhere in the process triggers `ugaf/core/__init__.py`,
which pulls in `bootstrap.py`, which pulls back into the very package that started the
chain (`ugaf.plugins` or `ugaf.device`) while it is still mid-initialization —
`ImportError: cannot import name 'X' from partially initialized module`.

This was already present before Milestone 3 (confirmed:
`python -c "from ugaf.plugins.manager import PluginManager"` fails standalone on the
pre-Milestone-3 tree) but never surfaced in the test suite because pytest collects
test files in an order where some earlier file always imports `ugaf.core` fully first,
masking the defect. `ugaf.device` being a brand-new top-level package made the failure
immediate and impossible to ignore.

### Decision

`ugaf/core/context.py` and `ugaf/core/bootstrap.py` now import `PluginManager` and
`DeviceManager` only under `if TYPE_CHECKING:` for type annotations (safe at runtime
because both modules already use `from __future__ import annotations`, so annotations
are never evaluated). The actual runtime construction in
`Application.initialize()` uses local (function-body) imports instead of module-level
ones. This is a standard, explicit pattern for breaking import cycles without changing
any public API or behavior.

### Consequences

- Positive: `from ugaf.plugins.manager import PluginManager` and
  `from ugaf.device.manager import DeviceManager` (and `AdbDeviceProvider`,
  `ugaf.core.bootstrap.Application`) now all import cleanly standalone, verified
  directly — not just "the test suite happens to pass."
- Positive: No public API changed — `Application.plugin_manager`/`.device_manager`,
  `AppContext.plugin_manager`/`.device_manager`, and every existing import path work
  exactly as before.
- Negative: The import of `PluginManager`/`DeviceManager` (and `AdbDeviceProvider`) now
  happens inside `Application.initialize()` rather than at module load time, which is a
  minor deviation from the codebase's usual all-imports-at-top-of-file convention —
  called out explicitly with a comment at both the `TYPE_CHECKING` block and the local
  import site so it doesn't look like an oversight.
- Negative: This is a targeted fix for the two call sites that actually triggered the
  defect, not an audit of every possible future cycle — if a future package (e.g. the
  Milestone 5 vision pipeline needing `Application`) creates a similar back-reference
  into `ugaf.core`, the same pattern will need to be applied again.

---

## ADR-010: `ugaf.device.manager.DeviceManager` as the sole path to device transports

- **Status**: Accepted
- **Date**: 2026-07-01

### Context

Milestone 3 required a "central orchestrator" the Core Engine talks to instead of ADB
directly. `ugaf.platform.device.DeviceProvider` (Milestone 2) intentionally stayed
narrow — "what devices exist right now" only, no lifecycle/reconnection/health, by
design (see that module's docstring). Something one layer up needs to own polling,
event publication, retry, and recovery across potentially multiple transports.
`ANDROID_TRANSPORT_STRATEGY.md` documents the transport research that preceded this
decision.

### Decision

`ugaf.device.manager.DeviceManager` owns a name-to-`DeviceProvider` registry (not the
shared `AdapterRegistry` from ADR-008, since `DeviceManager` needs richer per-instance
bookkeeping — a device-to-owning-transport map, a last-known-snapshot, an
`asyncio.Task` for polling — that a generic registry doesn't model), and exposes:
`register_provider`/`unregister_provider`, `discover()` (diffing snapshots and
publishing `device.discovered`/`device.online`/`device.offline`/`device.unauthorized`/
`device.lost` events), `start_monitoring()`/`stop_monitoring()` (a background polling
task), and `execute_shell()` (retrying with transport-level recovery via an optional
`restart_server()` capability, informed directly by the research finding that "a stuck
ADB daemon" is the most common cause of a device going `offline`).

Capabilities beyond bare `DeviceProvider` (shell execution, property enrichment,
restart) are modeled as `typing.Protocol` classes (`_ShellCapableTransport`,
`_PropertyCapableTransport`, `_RestartableTransport`) checked via
`isinstance(provider, ...)` at the call site, rather than widening the
`DeviceProvider` ABC itself — this keeps Milestone 2's narrow interface intact while
still letting `DeviceManager` use richer capabilities when the concrete transport
offers them. A transport that can only enumerate devices (no shell, no restart) still
satisfies `DeviceProvider` and works with `discover()`/`list_devices()`; it simply
can't be targeted by `execute_shell()`.

### Consequences

- Positive: `Application` (Core Engine) now owns a `DeviceManager`, not an
  `AdbDeviceProvider` directly — confirmed by grep, no file under `ugaf/core/` imports
  `ugaf.input.adb`, `ugaf.device.adb_provider`, or `subprocess` for device concerns
  outside `ugaf.device` itself.
- Positive: Swapping or adding a transport (UIAutomator2, scrcpy) requires only
  implementing `DeviceProvider` (+ the optional Protocols it wants to support) and
  calling `register_provider()` — no `DeviceManager` code changes needed, verified by
  the test suite's `_NonShellProvider`/`_PropertyProvider` fakes exercising exactly that
  substitutability.
- Positive: Event publication reuses the same tolerant "skip if no running loop"
  pattern already established in `ugaf.plugins.manager.PluginManager.discover()`,
  keeping `discover()` usable both synchronously (e.g. from the `ugaf plugins` CLI
  style call) and from within async application code.
- Negative: `ugaf.input.adb.AdbInputProvider` was not migrated onto
  `DeviceManager`/`AdbDeviceProvider` in this milestone — it still does its own
  independent (and less correct) device-state parsing. Tracked in
  `KNOWN_LIMITATIONS.md`, deliberately deferred rather than expanding this milestone's
  scope into a full input-path migration.

---

## ADR-011: `InputManager` is single-target by design; multi-device means multiple instances

- **Status**: Accepted
- **Date**: 2026-07-01

### Context

The architectural-planning directive requires every milestone to ask "will this still
be correct after several more milestones?" — specifically for multi-device support.
`ugaf.input.manager.InputManager` held exactly one `_provider: InputProvider | None`
and derived its target device solely from a shared `Config` object
(`input.adb.default_device`). Wiring `AdbInputProvider` more tightly into the device
layer (Milestone 4's stated goal) without addressing this first would have meant
redesigning `InputManager` again the moment a second Android device needed driving —
exactly the "implement now, refactor later" pattern this directive says to avoid.

### Decision

Keep `InputManager` single-target, but make the target explicit and independent of a
shared `Config`: add an optional `device_id` constructor parameter (overrides
`input.adb.default_device`) and an optional `device_manager` parameter (used for a
pre-flight online/offline/unauthorized check with a precise error message, sourced from
`AdbDeviceProvider`'s correct parsing rather than `AdbInputProvider`'s own narrower
check). Multi-device support is achieved by holding multiple `InputManager` instances
— one per device — not by making a single instance internally multi-device-aware.
`PluginManager` registers `DeviceManager` as a DI singleton in `GameContext` precisely
so a plugin can enumerate `DeviceManager.list_devices()` and construct one
`InputManager` per device itself.

### Consequences

- Positive: Verified directly — two `InputManager` instances sharing one `Config`
  object but constructed with different `device_id`s independently target different
  devices, and an unauthorized device is rejected with a precise error before any ADB
  connection is attempted.
- Positive: No `InputManager` internals need to change to support N devices — the
  fan-out lives entirely in the caller (a plugin, or a future orchestrator), matching
  how `DeviceManager` already treats devices as an enumerable collection.
- Positive: `ugaf.input` remains usable standalone (Windows desktop automation, or ADB
  without a `DeviceManager`) — `device_id`/`device_manager` are both optional and
  additive; every pre-Milestone-4 call site is unaffected.
- Negative: A caller that wants multi-device orchestration (retry policies across
  devices, aggregate health) must build that itself on top of N `InputManager`
  instances — no such orchestrator exists yet. Acceptable: building one prematurely,
  before a concrete plugin needs it, would be exactly the speculative complexity this
  project's general principles warn against.

---

## ADR-012: `AdbInputProvider` delegates device enumeration to `AdbDeviceProvider`

- **Status**: Accepted
- **Date**: 2026-07-01

### Context

A repository-wide governance audit (mandated after every 2–3 milestones) found a real,
previously-documented-but-deferred duplication: `ugaf.input.adb.AdbInputProvider` and
`ugaf.device.adb_provider.AdbDeviceProvider` each independently shelled out to
`adb devices` and parsed the output — the former with the narrower parser that only
recognizes the literal `"device"` state (the exact defect the original repository audit
flagged), the latter with the correct one built in Milestone 3. `KNOWN_LIMITATIONS.md`
and ADR-010/ADR-011 explicitly deferred unifying these "for future cleanup." The new
continuous-governance directive requires fixing debt like this during the milestone it's
found in, not deferring it a third time.

### Decision

`AdbInputProvider` now composes an `AdbDeviceProvider` instance (injectable via a new
`device_provider` constructor parameter, defaulting to one built against the same
`executable`) and delegates `adb devices` enumeration and `adb shell` execution to it.
`AdbInputProvider._parse_devices()` (the narrower parser) is deleted entirely — there is
now exactly one place in the codebase that parses `adb devices -l` output.
`take_screenshot()` is the one operation intentionally left as a direct `subprocess.run`
call, since ADB's `exec-out screencap` isn't a plain shell command and
`AdbDeviceProvider` doesn't (and shouldn't yet) expose an `exec_out()` method for a
single caller.

### Consequences

- Positive: Connecting to a device that is `offline`/`unauthorized` now produces a
  precise error (e.g. `"Device 'X' is unauthorized (expected online)"`) from
  `AdbInputProvider.connect()` itself, not just from the optional `InputManager`
  pre-flight check added in ADR-011 — the fix applies even when `InputManager` is used
  without a `device_manager`.
- Positive: Exactly one ADB device-state parser exists in the codebase now, rather than
  two with different (and differently correct) behavior.
- Positive: `AdbInputProvider(device_provider=...)` lets a caller reuse the exact
  `AdbDeviceProvider` instance a `DeviceManager` already owns, avoiding redundant `adb`
  subprocess calls when both device orchestration and input injection target the same
  device.
- Negative: 32 tests in `test_input_adb.py` needed their `subprocess.run` patch target
  changed from `ugaf.input.adb.subprocess.run` to `ugaf.device.adb_provider.subprocess.run`
  (the new actual call site) — a one-time migration cost, not ongoing debt.
- Negative: `ugaf.input` now has a real (not just type-checking) runtime dependency on
  `ugaf.device` for the ADB provider specifically. Verified no circular import results
  (`ugaf.device` does not depend on `ugaf.input`); Windows-only usage of `ugaf.input`
  is unaffected since `WindowsInputProvider` doesn't touch this code path.
