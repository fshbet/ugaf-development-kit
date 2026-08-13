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

---

## ADR-013: `ScreenshotManager` subclasses `ScreenshotProvider`

- **Status**: Accepted
- **Date**: 2026-07-01

### Context

`ugaf.vision.screenshot.ScreenshotProvider` (Milestone 2) is the interface
`VisionManager` depends on. Milestone (Screenshot Capture) needed to add provider
selection, retry, and frame caching on top of whichever concrete provider is chosen —
the same role `InputManager` plays for `InputProvider` and `DeviceManager` plays for
`DeviceProvider`. Unlike those two, `VisionManager`'s constructor already had a
stable, tested `screenshot_provider: ScreenshotProvider | None` parameter predating
this milestone, and changing its type would be a breaking API change for no
architectural gain.

### Decision

`ScreenshotManager` subclasses `ScreenshotProvider` directly rather than being an
unrelated orchestrator class. Its `capture_full`/`capture_region`/
`capture_game_window` methods satisfy the ABC (with `capture_full` widening the
signature with optional `use_cache`/`max_age` keyword arguments — an LSP-compatible
override, verified by `mypy --strict`). This means a `ScreenshotManager` instance can
be passed anywhere a plain `ScreenshotProvider` is expected — in particular,
`VisionManager(screenshot_provider=screenshot_manager)` — with zero changes to
`VisionManager` itself, while transparently adding retry and caching to whichever
concrete provider (`AdbScreenshotProvider`, `MockScreenshotProvider`,
`ImageReplayProvider`, or a future one) it wraps.

### Consequences

- Positive: `VisionManager`'s public API is completely unchanged — verified by the
  existing `test_vision_manager.py` suite passing unmodified.
- Positive: `PluginManager._register_vision_services` constructs and connects a
  `ScreenshotManager` and passes it straight into `VisionManager`'s existing
  `screenshot_provider` parameter — confirmed live end-to-end:
  `VisionManager.screenshot()` now actually returns real image data through the full
  DI chain, closing the exact gap the original repository audit flagged ("the vision
  engine cannot actually see the screen").
- Positive: `ScreenshotManager` is independently resolvable from `GameContext`
  (registered as its own DI singleton) for plugins that want direct access to
  `capture_full_async`/cache control beyond what `VisionManager`'s simpler
  `screenshot()`/`screenshot_region()`/`screenshot_window()` wrappers expose.
- Negative: `ScreenshotManager`'s `capture_full` signature (`use_cache`, `max_age`)
  differs from the plain interface's bare `capture_full()` — a caller holding a
  `ScreenshotProvider`-typed reference can't discover these extra parameters without
  knowing the concrete type is a `ScreenshotManager`. Acceptable: the extra parameters
  are opt-in (default `use_cache=False` preserves plain-provider semantics exactly).

---

## ADR-014: Knowledge/Strategy/Executor split for game automation logic

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

The first `games/shadow_fight_3` plugin (Version 0.1) hardcoded every piece of
game-specific behaviour directly in Python: button/joystick pixel fractions, named
combo sequences (`_COMBOS` dict), and the cycle-rotation combat logic all lived inside
`plugin.py`. This worked, but meant recalibrating a button position, adding a move, or
changing the combat pattern all required editing and redeploying Python — and none of
it was reusable by a second game plugin, which would have had to re-implement the same
joystick-direction math and combo-execution loop from scratch.

### Decision

Split game automation into three reusable, game-agnostic layers under
`ugaf.automation`, with all game-specific content moved to data:

- **Knowledge** (`ugaf.automation.knowledge`): `KnowledgeBase` loads a game's
  `knowledge/moves.yaml` (named moves: ordered generic action steps + metadata —
  cooldown, damage, shadow_cost, range, startup, recovery, priority, tags) and
  `knowledge/buttons.yaml` (named controls: screen positions as fractions of
  width/height, resolved to real pixels from the connected device's detected
  resolution). `MoveDefinition` and `ControlLayout` are the typed result.
- **Strategy** (`ugaf.automation.strategy`): `StrategyEngine` evaluates a
  `strategies/<name>.yaml` file's ordered `when -> do` rules against a per-cycle state
  dict, returning which move names to run this cycle. The condition vocabulary today
  is deliberately small (`"always"`, `{cycle_mod: N}`) — enough to reproduce the
  original hardcoded rotation exactly as data — and is meant to grow (e.g.
  vision-derived facts like enemy distance or health percentage) without changing any
  other layer.
- **Executor** (`ugaf.automation.executor`): `Executor` turns a move's step sequence
  into real `InputManager` calls. It understands exactly four generic verbs (`tap`,
  `move`, `hold`, `wait`) and has zero knowledge of any specific game — the same
  `Executor` class serves every plugin that adopts this architecture.

A plugin (e.g. `ShadowFight3Game`) becomes a thin shell: load knowledge/strategy in
`__init__`/`start()`, drive the executor loop, report status. See
`games/shadow_fight_3/README.md` for the full file layout and how to edit behaviour
without touching Python.

Introduced incrementally: `games/demo_workflow` and `games/example_game` are
untouched and still work exactly as before — nothing about `ugaf.sdk.game.GamePlugin`,
`ugaf.plugins.manager.PluginManager`, or any other existing plugin's structure changed.
A plugin adopts `ugaf.automation` by choice, not by framework requirement.

### Consequences

- Positive: `games/shadow_fight_3/plugin.py` shrank from ~230 lines (with all move/
  coordinate/combo logic inline) to ~185 lines containing zero move names,
  coordinates, or combo sequences — every one of those now lives in YAML and is
  editable without a code change or redeploy.
- Positive: `ugaf.automation.knowledge`/`strategy`/`executor` are immediately reusable
  by any future game or app-automation plugin; none contain a single Shadow-Fight-3-
  specific reference.
- Positive: validated live on real hardware after the refactor — the exact same
  cycle-by-cycle move rotation (shuriken at cycle 4/8/16, shadow ability at cycle 6/12,
  alternating jab/heavy combo otherwise) reproduced identically to the pre-refactor
  version, now driven entirely by `strategies/balanced.yaml`.
- Negative: an extra YAML-parsing/dataclass-construction indirection versus reading
  values directly off a Python dict — judged acceptable; `KnowledgeBase.load()` and
  `Strategy.load()` are each under 40 lines and covered by dedicated unit tests
  (`tests/test_automation_knowledge.py`, `tests/test_automation_strategy.py`).
- Negative: the `StrategyEngine` condition vocabulary (`always`, `cycle_mod`) cannot
  yet express vision-derived conditions ("if enemy is close") from the original
  directive's example — no calibrated template/health-bar data exists for this game
  yet (see `games/shadow_fight_3/knowledge/templates/README.md`). `VisionManager`
  gained `measure_bar_fill`/`wait_until_visible`/`wait_until_hidden` in the same pass
  specifically so this is a small follow-up, not a redesign, once real captures exist.
- Negative (found and fixed in the same pass): this refactor exposed a pre-existing
  bug in `PluginManager.initialize_all()`/`start_all()` — one plugin's failure (e.g. a
  hardware-dependent plugin when no device is connected) aborted every other plugin's
  auto-start, including `demo_workflow`, which needs no hardware at all. Fixed by
  making both methods fault-isolated per plugin (catch, log a warning, continue) —
  see `CHANGELOG.md`.

---

## ADR-015: Reusable `ApplicationManager` for Android app lifecycle, not per-plugin logic

- **Status**: Accepted
- **Date**: 2026-07-02

### Context

`games/shadow_fight_3` assumed the target game was already open before automation
began — the user had to manually launch Shadow Fight 3 before clicking "Run." The V0.2
directive requires the opposite: the user connects a device, picks an automation, and
clicks Run — UGAF opens the target app itself. This is explicitly **not** a
Shadow-Fight-3-specific feature: "every Android automation should reuse the same
system," and a future automation (Calculator, Chrome, a different game) must get the
same install-check/launch/foreground-verify workflow without writing new Python.

### Decision

`ugaf.apps.manager.ApplicationManager` is a new, single reusable class responsible for
Android application lifecycle: `is_installed`, `list_packages`, `get_version`,
`foreground_package`, `launch`, `wait_for_foreground`, `launch_and_wait` (the full
workflow), and `stop`. It has zero game-specific code and talks only to
`DeviceManager.execute_shell()` — never a transport (ADB) directly, mirroring how
`DeviceManager` itself never lets `ugaf.core` touch a transport directly. Per-app
identity and behaviour (package name, launch activity, timeouts/retries, expected
startup templates, shutdown behaviour) is data: `ugaf.apps.types.AppDefinition`,
loaded from an `app.yaml` a plugin ships alongside its `manifest.yaml`/`config.yaml`.
`PluginManager` registers one `ApplicationManager` instance as a DI singleton
(alongside the existing `DeviceManager` singleton) in `_get_or_create_context`, so
every plugin resolves the same instance — no plugin constructs its own.

`ShadowFight3Game.start()` is the first (and reference) consumer: resolve the target
device via `DeviceManager.resolve_device()` -> `ApplicationManager.launch_and_wait()`
-> only on success does it proceed to connect `InputManager`/`ScreenshotManager` and
start the combat loop. A failed launch raises `GameSDKError` with a clear message
("Shadow Fight 3 is not ready: ...") instead of silently automating against whatever
happened to be on screen.

Launching prefers an explicit `launch_activity` (`am start -n pkg/activity`) when
`app.yaml` provides one (more deterministic — confirmed against the real device via
`adb shell cmd package resolve-activity --brief <pkg>`), and falls back to the app's
own launcher intent (`monkey -p <pkg> -c android.intent.category.LAUNCHER 1`) when
none is given — this is what makes "any installed app, not just Shadow Fight 3" true
without per-app Python.

### Consequences

- Positive: adding a second app-backed automation (Calculator, Chrome, a future game)
  requires an `app.yaml` and reusing the same `ApplicationManager`/`DeviceManager`
  singletons — no new Python lifecycle code.
- Positive: validated live on real hardware — `ApplicationManager` detected
  `com.nekki.shadowfight3` installed, launched it via its resolved main activity,
  confirmed foreground in a single attempt (~4-7s), and the combat loop only began
  after that confirmation. Verified visually via a live screenshot showing the game's
  actual title screen before automation started.
- Positive: `DeviceManager.resolve_device()` (new, small, reusable) gives one canonical
  place to answer "which device do I target" — replacing what would otherwise be a
  third independent copy of "configured id, or the sole online device" logic (after
  `AdbInputProvider` and `AdbScreenshotProvider` each already had their own).
- Negative (found and fixed in the same pass): validating this live surfaced a second
  real bug — `AppSession.run_plugin()`'s idempotency check only handled
  `lifecycle is None`, not `GameState.CREATED`. The web UI's automation list now polls
  `/health` to show live status, and `PluginManager.health()` calls `load()` as a side
  effect (creating a `CREATED`-state lifecycle) — so any automation whose health was
  ever checked before its first "Run" click hit `Cannot transition from 'created' to
  'running'`. Fixed by treating `CREATED` the same as "never touched" (initialize then
  start). Covered by a regression test
  (`test_run_succeeds_after_a_prior_health_check`) that reproduces the exact
  poll-then-run sequence.
- Negative: foreground-detection regex (`dumpsys window windows` / `dumpsys activity
  activities` parsing) is inherently a bit fragile across Android/OEM versions — it's
  the same category of risk `AdbDeviceProvider`'s device-state parsing already carries,
  documented rather than solved (mirrors existing project precedent of treating
  device/OS quirks as documented constraints, not framework bugs).

---

## ADR-016: Decouple frame capture from device control via `ScreenshotProvider`

- **Status**: Accepted
- **Date**: 2026-07-03

### Context

`AdbScreenshotProvider`'s `adb exec-out screencap` round trip is slow (measured live:
~2.5s per frame on real hardware — see `PROJECT_STATUS.md`), and is the only frame
source UGAF has. The performance directive requires reducing capture latency and
supporting Windows Android emulators as first-class targets, *without* replacing ADB —
ADB must remain the transport for device discovery, input injection, application
lifecycle, and shell commands.

### Decision

No new abstraction was needed: `ugaf.vision.screenshot.ScreenshotProvider` (present
since Milestone 2) already *is* the capture transport seam — `VisionManager`/
`ScreenshotManager` consume it without knowing which concrete provider is behind it.
This ADR formalizes that seam as the answer to "how do we add faster capture
transports" and adds two new implementations against it:

- `ugaf.vision.window_capture.WindowCaptureProvider` — captures a named window's
  client area directly via `mss`+`pywin32` (optional deps, `ugaf[emulator]`), for
  Android emulators that run as ordinary Windows windows (BlueStacks, NoxPlayer,
  Android Studio's emulator, ...). Bypasses ADB entirely for the frame source; ADB is
  untouched for everything else.
- `ugaf.vision.scrcpy_capture.ScrcpyFrameProvider` — pushes and talks to a scrcpy
  server process over its raw H264 video socket, decoding with PyAV (optional dep,
  `ugaf[scrcpy]`), instead of one ADB round trip per frame.

Neither new module imports its optional dependency at module level — `import
ugaf.vision` never fails even with neither installed; only actually calling
`capture_full()` on an unconfigured provider raises a clear, actionable
`ScreenshotError`.

### Consequences

- Positive: `AdbScreenshotProvider` is completely unchanged and remains the default —
  zero regression risk for existing automations.
- Positive: adding a capture transport is "implement three methods + register a
  string" — no `VisionManager`, `ScreenshotManager`, or plugin code changes, verified
  by both new providers dropping into the same `screenshot_registry.register(...)`
  pattern `AdbScreenshotProvider`/`MockScreenshotProvider` already use.
- Positive: `WindowCaptureProvider` was validated against a real Windows window (a live
  Notepad instance) in this environment, proving the capture mechanism genuinely works;
  full unit coverage mocks `win32gui`/`mss` via `sys.modules` injection for the rest.
- Negative (documented, not solved): neither `scrcpy` nor an Android emulator was
  available in the development environment (no `scrcpy` binary, no BlueStacks/NoxPlayer/
  AVD running, and `pywin32`/`mss`/`av` have no published wheel for the Python 3.14
  interpreter used here — confirmed via `pip install` producing cp310-tagged wheels
  that fail to import). `ScrcpyFrameProvider`'s wire-protocol parsing (device-name
  header, frame-meta framing, PyAV decode call) is covered by unit tests against
  synthetic byte streams built to the documented scrcpy protocol spec, but has **not**
  been validated against a real scrcpy server end-to-end. This is a known, flagged gap
  (see `PROJECT_STATUS.md`), not a silent one — matching the project's standing policy
  of documenting environment constraints rather than pretending they don't exist.

---

## ADR-017: `device_id`-parametrized `PluginManager` for concurrent multi-device automation

- **Status**: Accepted
- **Date**: 2026-07-03

### Context

Every plugin lifecycle method (`start`, `stop`, `health`, ...) took only a `plugin_id`,
and `PluginManager._lifecycles` was keyed by `plugin_id` alone — one instance per
plugin, framework-wide. Running the same automation against two devices concurrently
was impossible: initializing a second time just returned the same `PluginLifecycle`.
The performance/scalability directive requires "multiple automations running
concurrently on different devices," each with independent state, independent logs, and
fault isolation (one device's failure must not stop another's).

### Decision

Every `PluginManager` lifecycle method gained an optional `device_id: str | None =
None` parameter. The internal lifecycle dict key becomes `plugin_id` when `device_id`
is omitted (byte-for-byte the original behaviour — every existing caller, test, and
plugin needed zero changes) or `"{plugin_id}@{device_id}"` when given, which
constructs (or reuses) a **separate** `PluginLifecycle` wrapping a **separate**
`GamePlugin` instance. `GameContext` gained a `device_id: str | None` field;
`PluginManager._get_or_create_context(device_id=...)` returns a cheap
`dataclasses.replace()` copy of the one shared context (same DI container, same
`DeviceManager`/`ApplicationManager` singletons) carrying just that instance's
`device_id`. `games/shadow_fight_3/plugin.py` was updated to prefer
`context.device_id` over its own config/`resolve_device()` fallback when set — the
minimal change needed for the *existing* plugin to become multi-instance-capable, with
no new per-plugin infrastructure.

`initialize_all`/`start_all`/`stop_all`/`pause_all`/`resume_all`/`shutdown_all` iterate
every lifecycle instance regardless of key shape; `stop_all` was additionally made
fault-isolated (catch-log-continue per instance, mirroring `start_all`'s existing
pattern) since a multi-device stop-everything action must not abandon devices whose
stop happens to come after a failing one in iteration order.

This was deliberately *not* built as a new scheduler/orchestrator class — the existing
`PluginLifecycle` dict, `GamePlugin` contract, and `GameState` machine were sufficient
once given a composite key and a per-instance context field.

### Consequences

- Positive: fully backward compatible — the entire pre-existing test suite (all
  `manager.start("id")`-style calls) passed unmodified; only *new* tests needed to add
  `device_id=...`.
- Positive: validated with both a generic dummy plugin
  (`tests/test_plugin_manager_multidevice.py`) and the real `ShadowFight3Game`
  (`tests/test_shadow_fight_3_plugin.py::test_two_concurrent_device_bound_instances_run_independently`)
  running two instances concurrently via `asyncio.gather`, each tapping its own
  mocked device, each reporting independent `cycles_run` in its health dict — and a
  dedicated fault-isolation test proving one instance's `start()`/`stop()` failure
  (`GameState.ERROR`) leaves a sibling instance's state (`GameState.RUNNING`/
  `STOPPED`) untouched.
- Negative: only one physical Android device was available in this environment, so the
  *true* multi-device claim (two distinct physical/emulator devices automated at once)
  is proven by the mocked-device integration tests above, not an end-to-end live demo
  with two real targets. The single-device parts of the workflow (device resolution,
  the startup workflow, capture/input against that one device) were validated live —
  see `PROJECT_STATUS.md`.
- Negative: the web UI surfaces this by scoping the currently-selected device's
  automation card to that device's instance (`?device_id=...` on run/stop/health) —
  a user with two devices connected sees each device's own automation status by
  selecting it, rather than a dedicated "all instances at once" dashboard view. Judged
  sufficient for this milestone; a multi-instance-at-a-glance view is a UI-only
  follow-up, not an architecture gap.

---

## ADR-018: `ugaf.emulator` Emulator Manager Module, as a provider-based subsystem alongside `DeviceManager`

- **Status**: Accepted
- **Date**: 2026-07-04

### Context

Every prior milestone assumed a physical Android device connected over ADB. The
platform directive requires a first-class **Android Emulator** option: the user picks
"Physical Device" or "Android Emulator" in the web UI, and in the emulator case can
browse manufacturer/device profiles (Samsung Galaxy S25 Ultra, Google Pixel 9, ...),
pick a performance preset (Low End/Mid Range/Flagship/Gaming), and create/start/stop/
delete AVDs — all without hand-editing `avdmanager`/`emulator` command lines. The
device/profile library must be data (YAML), not Python, and the design must leave room
for future non-Android-Studio backends (BlueStacks, LDPlayer, Genymotion, ...) without
touching this milestone's code.

This environment happens to have a real, working Android SDK installed
(`sdkmanager`/`avdmanager`/`emulator`, real AVDs, WHPX hardware acceleration usable) —
unlike the scrcpy/emulator gap noted in ADR-016, the bulk of this module could be
live-validated against real tooling, not only mocks.

### Decision

`ugaf.emulator` mirrors the exact pattern already proven twice (`ScreenshotProvider`/
`AdapterRegistry` in ADR-016, `DeviceProvider`/`DeviceManager` from Milestone 3):

- **`EmulatorProvider`** (`ugaf/emulator/provider.py`) — an ABC with the full lifecycle
  contract (`list`/`create`/`delete`/`rename`/`clone`/`update_hardware`/`start`/`stop`/
  `is_running`/`detect_crash`/`wait_until_booted`/`install_apk`/`push`/`pull`),
  registered in an `AdapterRegistry[EmulatorProvider]` under a string name. Only
  `AndroidStudioProvider` (`ugaf/emulator/providers/android_studio.py`) is registered
  today, driving the real `avdmanager`/`emulator`/`adb` binaries via `subprocess`
  exactly like `AdbDeviceProvider` does for device enumeration. A future
  BlueStacks/LDPlayer/Genymotion/Waydroid provider is a new class + one
  `emulator_registry.register(...)` call — no change to `EmulatorManager`, the webapp,
  or any existing provider.
- **`EmulatorManager`** (`ugaf/emulator/manager.py`) — the single facade every caller
  uses (mirrors `ApplicationManager` from ADR-015): resolves the SDK once via
  `AndroidSdkLocator`, wires `DeviceProfileManager`/`PerformanceProfileManager`/
  `AndroidVersionManager`/`HardwareDetector`, and delegates every lifecycle call to
  whichever provider is configured. Nothing above this facade ever imports
  `AndroidStudioProvider` directly.
- **Data-driven device/performance libraries**: `DeviceProfile`
  (`ugaf/emulator/types.py`) loaded from `config/manufacturers.yaml` by
  `DeviceProfileManager`, and `PerformanceProfile` loaded from
  `config/performance_profiles.yaml` by `PerformanceProfileManager` — both follow
  `AppDefinition.load()`'s dataclass-plus-YAML pattern (ADR precedent: apps/types.py).
  Adding a manufacturer/device or a performance preset is a YAML edit; no Python or
  PowerShell hardcodes a device list, matching the directive's explicit requirement.
  `config/android_versions.yaml` is deliberately *not* a device list — it is a static
  API-level-to-marketing-name reference (e.g. `35: "Android 15"`), used only for
  display; the actual set of installed/available system images is always detected live
  via `AndroidVersionManager` parsing real `sdkmanager --list` output, never read from
  a static file.
- **`AndroidSdkLocator`** (`ugaf/emulator/sdk_locator.py`) resolves the SDK root from
  an explicit override, then `ANDROID_HOME`/`ANDROID_SDK_ROOT`, then per-OS default
  install locations — never a hardcoded path. It prefers `adb`/`emulator`/
  `sdkmanager`/`avdmanager` from *within* the resolved SDK root over whatever happens
  to be first on `PATH`: a real audit of this project's development machine found
  *two* installed `adb.exe` copies (one under the SDK, one under
  `C:\Program Files\Adb`), which a PATH-first lookup would have silently preferred,
  potentially the wrong version for the resolved SDK's tooling.
- **`HardwareDetector`** (`ugaf/emulator/hardware.py`) reports CPU count, total RAM, and
  real acceleration status (parses `emulator -accel-check`, e.g. `"WHPX(10.0.26200) is
  installed and usable"`), and recommends a performance preset from detected headroom
  (reserving roughly half of CPU/RAM for the host) — stdlib/subprocess only, no new
  dependency (e.g. `psutil`) for what is a handful of one-shot lookups.
- **Multi-instance launches**: `AndroidStudioProvider.start()` allocates the next free
  console port (starting at `emulator_settings.yaml`'s `first_console_port`, default
  `5554`, stepping by 2 per the emulator's own port-pairing convention), cross-checking
  both its own tracked instances *and* `adb devices` so externally-started emulators
  don't collide with a UGAF-launched one. Each instance gets its own working directory
  and log file under `~/.ugaf/emulator_instances/<name>_<port>/`.
- **Webapp integration**: a new "Connection Type" radio (Physical Device / Android
  Emulator) in the left sidebar toggles between the existing Devices panel and a new
  Android Emulator panel (Android Version / Manufacturer / Device / Performance
  Profile / AVD dropdowns, Create/Start/Stop/Delete/Open Android Studio/Refresh
  buttons) — `AppSession` lazily constructs one `EmulatorManager` on first use
  (`SdkNotFoundError` surfaces as a dismissible banner, not a crash, so the rest of the
  control panel works on a machine with no SDK installed at all), and every new
  `/api/emulator/*` route is a thin delegation, matching every existing route in
  `ugaf/webapp/server.py`.

### Consequences

- Positive: the entire subsystem was live-validated against this machine's real
  Android SDK, not only mocks — real `sdkmanager --list`/`avdmanager list avd`
  parsing, real AVD create/start/is_running/detect_crash/stop/delete cycles, real
  hardware detection (16 CPUs, ~31GB RAM, WHPX usable), and real webapp UI wiring
  (Connection Type toggle to live manufacturer/device/performance/AVD dropdowns,
  populated from this machine's actual catalog) confirmed via the browser preview
  tools. Two bugs were caught specifically *because* real tooling was used instead of
  hand-written fixtures: (1) `sdkmanager --list` repeats every already-installed
  package under "Available Packages" too, which a naive dict-building parser let
  silently overwrite the correct `installed=True` record with a stale `installed=False`
  duplicate; (2) sorting `cmdline-tools` version directories as plain strings ranked
  `"9.0"` above `"12.0"`, silently preferring an older command-line-tools install. Both
  are fixed and covered by regression tests built from the real captured output.
- Positive: this machine's real `avdmanager list avd` surfaced a genuine environment
  edge case worth handling deliberately rather than treating as a framework bug: of 4
  AVDs reported by `emulator -list-avds`, only one (`PixelPlay`) was actually valid —
  two had unparseable `config.ini` files, one referenced a system image tag
  (`google_apis`) that wasn't the one actually installed (`google_apis_playstore`).
  `EmulatorManager.list()`/`AndroidStudioProvider.list()` surface both valid and broken
  AVDs with their error reasons rather than silently hiding or crashing on the broken
  ones — the same "surface the real state" principle `ARCHITECTURE.md` documents for
  physical-device quirks now applies to emulators too.
- Negative (documented, not solved): booting a freshly created AVD to
  `sys.boot_completed=1` did not finish within the default 180s timeout in this
  environment when using software rendering (`gpu_mode=swiftshader_indirect`) on a
  cold boot with no snapshot — the `emulator` process itself stalled at graphics
  backend initialization (`gfxstream`) for several minutes, a real host/driver
  characteristic of this machine's environment, not a bug in `wait_until_booted`'s
  polling logic (which correctly returned `False` at the timeout without raising, and
  correctly reported the process as still alive via `detect_crash`). The full AVD
  lifecycle *up to* boot completion — create, start, `is_running`, `detect_crash`,
  stop, delete — was validated live end-to-end; only the boot-completion wait itself
  needs a longer timeout (or hardware GPU mode) on this specific host to observe a
  `True` result. Users should expect first boots (especially without snapshots or with
  software rendering) to take several minutes and configure
  `emulator_settings.yaml`'s `boot_timeout_seconds` accordingly.
- Negative: "Open Android Studio" only checks a few well-known Windows install paths
  (`%LOCALAPPDATA%\Programs\Android Studio\...`, `Program Files\Android\...`) plus
  `PATH` on other platforms; a non-standard Android Studio install location will report
  "not found" rather than launching. Judged acceptable as a convenience button, not a
  load-bearing part of the emulator lifecycle (every AVD operation works from the web
  UI without ever opening Android Studio itself).

---

## ADR-019: Acceptance Test Driven Development (ATDD) for Emulator Management — two real launch-crash root causes and their fixes

- **Status**: Accepted
- **Date**: 2026-07-05

### Context

A new development directive required treating the emulator lifecycle as a fully
validated end-to-end workflow — Create, Start (through real boot, launcher visibility,
live screen, tap/swipe/type), Stop, Rename, Delete — driven through the actual web UI
exactly as a user would, not just unit tests against mocks. This surfaced two real,
previously-undiagnosed defects that no amount of mocked testing could have found,
plus a genuine per-component dependency-detection gap and two UI state-machine bugs.

### Decision

**Dependency detection (`ugaf.emulator.dependencies.EnvironmentChecker`, new)**: prior
to this directive, `EmulatorManager`'s constructor either fully succeeded or raised on
the *first* missing tool (via `AndroidSdkLocator.locate()`), giving no way to show a
user *which* of Android Studio/SDK/platform-tools/emulator.exe/sdkmanager/avdmanager
is actually missing. `EnvironmentChecker` probes each independently (extending
`AndroidSdkLocator` with public `find_adb`/`find_emulator`/`find_sdkmanager`/
`find_avdmanager`, alongside the existing `find_sdk_root`), producing a
`DependencyReport` the webapp renders as a checklist with real paths or specific,
actionable "missing" reasons. Android Studio is checked and displayed but never
blocking — `avdmanager`/`emulator`/`sdkmanager` are plain command-line tools that work
headlessly without the IDE installed at all; treating Studio as required would break
UGAF's automation-first use case on headless/CI hosts that intentionally only install
the SDK.

**`AndroidStudioLocator` bug (real, found immediately)**: the original "Open Android
Studio" button's candidate paths never found Android Studio on this project's own
development machine, which has it installed at `E:\Android\Android Studio` — a sibling
directory of the Android SDK root (`E:\Android\SDK`), not any of the checked
"well-known" locations. Fixed by checking `ANDROID_STUDIO_HOME`, then the
sibling-of-SDK-root layout, before falling back to the original per-OS defaults and
`PATH`. This is exactly the kind of bug ATDD is meant to catch: every previous "review"
of this code was against assumptions, never the real installed location.

**Emulator launch never reaching boot (real, found via live acceptance testing)**: two
independent, stacked root causes, each confirmed via direct evidence, not guesses:

1. Launched non-interactively, the emulator tried to show a native "send crash reports
   to Google?" consent dialog (crashpad's first-run prompt) — a process with no
   interactive window station to render that dialog on simply exited, silently, before
   ever starting the AVD, with nothing informative in its own log. Fixed by always
   passing `-crash-report-mode disabled`.
2. Even with that fixed, the emulator's shared GPU-capability probe (run regardless of
   the AVD's own `hw.gpu.mode`) crashed with a real access violation inside
   `amdxc64.dll` — confirmed via Windows Event Viewer Application-error records
   (`qemu-system-x86_64.exe` faulting in the AMD graphics driver, exception
   `0xc0000005`) — on this machine's hybrid NVIDIA+AMD GPU configuration.
   `-feature -Vulkan` alone did not reliably avoid it; only additionally forcing
   `-gpu swangle` (ANGLE+SwiftShader for both GLES and Vulkan, overriding the AVD's own
   `hw.gpu.mode`) was confirmed crash-free across repeated real boots. Both fixes are
   gated by `AndroidStudioProvider`'s new `disable_vulkan` flag (default `True`,
   configurable via `emulator_settings.yaml`), so a host that doesn't hit this driver
   bug and wants real hardware-GPU rendering can opt out.

**UI state-machine bugs (found via ATDD's explicit "never show stale status" check)**:

- `AppSession._get_emulator_manager()` used to cache a *failed* SDK-detection attempt
  forever — once "SDK not found" was reported, it stayed cached even after a user fixed
  the underlying problem without restarting the whole webapp. Fixed by only caching
  *successful* construction; `emulator_status()` now always re-probes live via
  `EnvironmentChecker` on every call instead of reusing any prior result.
- The webapp's Connection Type toggle skipped re-checking the Android Emulator panel's
  status after the very first successful load (`if (isEmulator && !emu.devices.length)`),
  so switching away and back could show stale dependency/AVD state. Fixed by always
  re-running the check on every switch to Emulator mode.
- A genuine race condition: rapid manufacturer/device selection changes could let an
  earlier, slower "is the system image installed" response resolve *after* a later,
  faster one and silently overwrite it with stale data for whatever is currently
  selected. Fixed with a monotonic request-token guard (the same pattern applied to
  the manufacturer→device-list fetch, which had the identical race).
- The screen viewer's tap/swipe coordinate math divided by the image element's
  rendered height with no floor, so an unusually short browser viewport (or this
  session's browser-automation tooling reporting a transient zero-height layout) could
  silently compute `y=Infinity`, which JSON serialization turns into `null`, failing
  the tap/swipe request with a confusing 422 instead of just not acting on a bad click.
  Fixed with a CSS `max()` floor on `#screen-img`'s height and an explicit zero-rect
  guard in `imageToDeviceCoords()`.

### Consequences

- Positive: the full Create → Start → boot → launcher-visible → Device-Manager-connected
  → screenshot-captured → live-screen → tap/swipe/type → Stop → clean-shutdown chain was
  validated live, multiple times, through the actual web UI against this machine's real
  Android SDK — not simulated. Every acceptance-checklist item passed with direct
  evidence (real `sys.boot_completed=1`, real `dumpsys` launcher-foreground checks, real
  screenshot bytes at the device profile's exact resolution, real ADB disconnection and
  process exit confirmed via `tasklist`).
- Positive: two genuine, previously-invisible bugs (the crash-consent dialog, the AMD
  driver crash) are now fixed with root-caused, evidence-backed explanations rather than
  trial-and-error flag guessing — both are regression-tested (`start()`'s argument
  construction is asserted directly) even though the underlying host crash itself can't
  be reproduced in a unit test.
- Negative (documented, not solved): the AMD-driver crash fix (`-gpu swangle`) trades
  away hardware-GPU-accelerated rendering by default on *every* host, not just the ones
  that hit this specific bug, since there is no reliable way to detect the bug in
  advance short of trying to boot and watching it crash. A host confirmed not to hit
  this issue can set `emulator_settings.yaml`'s `disable_vulkan: false` to get
  hardware-accelerated rendering back.
- Negative (documented, not solved): "Restart Emulator" is validated as the composition
  of already-independently-proven `stop()` + `start()` (exercised together, repeatedly,
  in this same acceptance pass) rather than via a dedicated `restart()` method — judged
  sufficient since both primitives are independently reliable and a wrapper would add
  no behavior, only a name.

## ADR-020: Single-authoritative `DeviceLifecycle` state machine replacing dual connected/status flags

### Context

The web control panel could show `Status = Online` (from live ADB) and
`Connected = No` (from the session layer) for the same device at the same
time, and `GET /api/devices/{id}/screenshot` could return HTTP 409 even
though the device was perfectly reachable.

Root cause, traced end to end (Launch → ADB discovery → Device Registration
→ Connection State → Screenshot Provider → Web API → UI):

- `ugaf.device.manager.DeviceManager.discover()` is the one real,
  continuously-repolled source of ADB reachability (`DeviceStatus.ONLINE` /
  `OFFLINE` / `UNAUTHORIZED`).
- `ugaf.webapp.session.AppSession` maintained a *second*, entirely
  independent notion of "connected": whether `device_id` was a key in a
  plain `dict` (`self._connections`), set once when `connect_device()` was
  first called and never revisited.
- `GET /api/devices` returned both fields side by side
  (`"status": d.status.value`, `"connected": session.is_connected(d.id)`)
  with no reconciliation between them — so the two could trivially
  disagree (e.g. after a webapp restart, an emulator reboot, or any path
  that left the dict stale while ADB kept reporting the device online).
- `connect_device()` itself never verified readiness — it constructed an
  `InputManager`/`ScreenshotManager` pair and returned immediately, with no
  check that the device had finished booting or could produce a real
  frame. "Connected" and "actually ready to serve a screenshot" were not
  the same thing even when the dict and ADB agreed.
- The screenshot/tap/swipe/text/metrics routes all mapped "not a key in
  `self._connections`" straight to `KeyError` → HTTP 409, with zero
  attempt to revalidate or recover — a transient dict-population gap (e.g.
  right after a restart) was indistinguishable from a genuinely
  unreachable device.

No duplicate state should exist for one device; every subsystem must
consume one authoritative source instead of maintaining independent flags.

### Decision

- Added `ugaf.device.lifecycle.DeviceLifecycle`: the single authoritative
  state machine, one `DeviceState` per `device_id` —
  `DISCOVERED` / `STARTING` / `WAITING_FOR_ADB` / `BOOTING` /
  `INITIALIZING` / `CAPTURING_TEST_FRAME` / `READY` / `DISCONNECTED` /
  `ERROR`. Every transition is logged (`device_lifecycle.transition`, with
  `from_state`/`to_state`/`reason`). Unknown devices report `DISCONNECTED`
  rather than raising, so callers never need a separate existence check.
- `AppSession.is_connected()` now does nothing but read
  `DeviceLifecycle.is_ready()` — the dict-membership flag is gone
  entirely, so "connected" and "state" can never contradict each other by
  construction, not by convention.
- `connect_device()` was rewritten as `_run_boot_sequence()`, implementing
  the documented pipeline: verify ADB reachability (`WAITING_FOR_ADB`) →
  verify `sys.boot_completed == 1` and launcher focus via `dumpsys window`
  (`BOOTING`) → construct the input/screenshot providers
  (`INITIALIZING`) → capture one real test screenshot
  (`CAPTURING_TEST_FRAME`) → only then transition to `READY`. Any stage
  failure transitions to `ERROR` and raises `DeviceRecoveryError(device_id,
  stage, reason)` naming exactly which stage failed.
- Screenshot/tap/swipe/text/metrics no longer 409 on a stale flag: `
  AppSession._ensure_ready()` re-runs the full boot sequence once whenever
  state isn't `READY`, before giving up. Only a genuine pipeline failure
  (device unreachable, still booting, provider init or test-capture
  failure) surfaces as a 409, and its body is a structured diagnostic
  (`{"stage": ..., "reason": ..., "detail": ...}`) naming the failed
  stage — never a bare "not connected".
  `DeviceManager.shell_sync()` was added as the plain synchronous shell
  probe this pipeline needed (existing `execute_shell()` is async with
  retry/recovery semantics that don't fit a single boot-state check).
- `GET /api/devices` now reports `state`/`state_reason` (from
  `DeviceLifecycle`) alongside `connected`, with `connected` derived
  *from* `state` (`state == "ready"`) rather than an independent flag.
  `app.js` renders one status pill sourced from `state` (`STATE_META`
  mapping to label/CSS class) instead of separately rendering `status`
  and a `connected` pill that could disagree.

### Consequences

- Positive: "Status=Online, Connected=No" is now structurally impossible
  — there is only one state to read, and every consumer (API, UI,
  screenshot recovery) reads the same one.
- Positive: a device that looks disconnected purely because of stale
  session state (e.g. right after a webapp restart, while the emulator
  itself never went away) now self-heals on the next request instead of
  requiring the user to manually click Connect.
- Positive: 409 responses are now actionable — they name the exact stage
  that failed (`waiting_for_adb`, `booting`, `initializing`,
  `capturing_test_frame`) instead of a generic "not connected".
- Negative (accepted): `connect_device()`/action calls are slightly slower
  on first use per device, since a real boot-completion check and a test
  screenshot are now mandatory before `READY` — judged acceptable since
  this is exactly the readiness guarantee the control panel previously
  lacked, and a booted device passes the checks in well under a second.
- Negative (documented): `_is_boot_completed()`'s launcher-visible check
  is best-effort (`dumpsys window` parsed for `mCurrentFocus`) — if the
  `dumpsys` call itself fails after `sys.boot_completed == 1` already
  confirmed boot, the device is still treated as booted rather than
  blocking readiness on a secondary, non-critical check.

## ADR-021: `AndroidPlatformManager` — one Android-domain facade over SDK tooling

### Context

Directive: "Android Studio, sdkmanager, avdmanager, emulator.exe and
adb.exe are implementation details. The user should never need to
understand or manually interact with these tools. UGAF should manage
them automatically." Before this pass, the webapp's `AppSession` called
`EmulatorManager`, `EnvironmentChecker`, and `DeviceManager` directly and
independently for every emulator-related action — there was no single
component "the rest of UGAF" talked to, and no lifecycle transitions were
recorded for the emulator-process side of a device's life (only the
webapp's device-*connect* pipeline, ADR-020, had explicit states).

### Decision

- Added `ugaf.android_platform.AndroidPlatformManager`: wraps an
  already-constructed `EmulatorManager`, `DeviceManager`, and
  `EnvironmentChecker` behind Android-domain method names
  (`list_virtual_devices`, `create_virtual_device`,
  `start_virtual_device`, `stop_virtual_device`, `list_physical_devices`,
  `platform_health`) — never builds its own SDK-locating `EmulatorManager`,
  so it adds zero extra SDK-probing cost and stays trivially mockable.
- `start_virtual_device()` now implements the directive's "Create ->
  Validate -> Boot" prefix for real: it runs the full dependency report
  first (`VALIDATING`) and refuses to launch with a specific reason if
  any blocking component is missing, *before* ever invoking
  `emulator.exe` — previously a doomed launch would only fail later,
  opaquely, as a boot timeout. `stop_virtual_device()` brackets the real
  stop with `STOPPING`/`STOPPED` transitions.
- Both methods write to the *same* `DeviceLifecycle` instance
  (ADR-020) the device-connect pipeline uses, keyed first by AVD name
  (`VALIDATING`/`STARTING`) and then — once `start()` returns an
  `adb_serial` — the name-keyed entry is deliberately forgotten, since
  `adb_serial` becomes the canonical key the connect pipeline continues
  from. This is a real, documented seam: the emulator-launch phase and
  the device-connect phase of the *same physical device* are
  necessarily keyed differently (an AVD has a name before it has a
  serial), and no single key spans both phases yet.
- **AVD name sanitization** (`ugaf.emulator.naming.sanitize_avd_name`):
  `EmulatorManager.create()` now sanitizes any user-entered name (e.g.
  `"ROG A15"` -> `"ROG_A15"`) before it ever reaches `avdmanager`, which
  silently rejects/mangles names with spaces or most punctuation. The
  original, human-entered name is preserved on the returned `AvdInfo`'s
  new `display_name` field so the UI can still show what the user typed
  even though the identifier itself was sanitized.
- **Extended SDK validation** (`EnvironmentChecker`): added two new,
  informational (never-blocking) checks — `cmdline_tools_consistency`
  (flags an ambiguous `cmdline-tools` layout: no `latest` symlink/dir
  with more than one versioned dir present) and `hypervisor` (surfaces
  `emulator -accel-check`'s hardware-virtualization-acceleration result,
  reusing the existing `HardwareDetector` rather than re-implementing
  detection).
- **Removed the "Open Android Studio" feature** (button, JS handler,
  `AppSession.open_android_studio()`, and its route) entirely, per the
  directive's explicit "If Android Studio is installed: use it only to
  discover the SDK location. Do not launch Android Studio." UGAF now
  never launches the IDE — `AndroidStudioLocator` is still used, but
  purely to help resolve the SDK root, exactly as it already was inside
  `EnvironmentChecker`.
- **UI terminology**: "AVD" renamed to "Virtual Device" in every
  user-facing label (`New Virtual Device Name`, the `Virtual Device`
  dropdown, status text) — the API/JSON field names (`name`, `avds`,
  etc.) are unchanged, since those are internal contracts, not
  user-facing text.
- **Environment Doctor**: the existing per-dependency checklist UI
  needed no rendering changes at all to pick up the two new checks — it
  already iterated `status.dependencies` generically rather than
  hardcoding component names. Added one new summary line
  (`platform-health-summary`) showing overall health plus live
  physical/virtual device counts, sourced from the exact same
  `DeviceManager.discover()` call `/api/devices` uses (never a second,
  independent count).

### Consequences

- Positive: there is now one real component (`AndroidPlatformManager`)
  that owns Android SDK-tool knowledge for the emulator lifecycle's
  start/stop path, matching the directive's "the rest of UGAF should
  communicate only with AndroidPlatformManager" for that path. The other
  read-only emulator delegation methods (`list_manufacturers`,
  `list_avds`, `check_system_image`, etc.) still call `EmulatorManager`
  directly from `AppSession` — folding them in too was judged unnecessary
  risk for this pass since they're pure reads with no lifecycle
  transitions to own; tracked as a follow-up, not silently dropped.
- Positive: a launch that's doomed to fail (missing `avdmanager`, no
  system image) is now rejected before `emulator.exe` is ever invoked,
  with the exact missing component named — not a multi-minute boot
  timeout with no clear cause.
- Positive: users can now name Virtual Devices anything (`"ROG A15"`,
  `"My Pixel 9!"`) without needing to know `avdmanager`'s naming rules;
  the sanitized identifier is fully transparent unless it had to differ
  from what was typed, in which case the original is preserved for
  display.
- Negative (documented, not solved): the AVD-name-keyed vs.
  adb-serial-keyed lifecycle split described above means there is a
  brief window (between `start_virtual_device()` returning and the
  device-connect pipeline's first `WAITING_FOR_ADB` transition) where
  the device has no tracked lifecycle state at all (`DISCONNECTED` by
  default). Acceptable since nothing reads state during that window
  today, but a future unification (e.g. registering the AVD-name ->
  adb-serial mapping explicitly) would close it.
- Negative (documented, not solved): "Capture Test" and "Input Test"
  buttons and a dedicated `platform_health()`-backed API route were not
  added this pass — `AndroidPlatformManager.platform_health()` exists
  and is unit-tested, but the webapp only consumes its device-count
  logic today (folded directly into `emulator_status()`), not the full
  `PlatformHealth` object via a dedicated route. Tracked as a follow-up.

## ADR-022: One-click "Create Virtual Device" — create/boot/connect collapsed into a single action

### Context

Directive: "The user should not think in terms of SDK / AVD / adb /
emulator.exe. The user should think only in terms of Android Device /
Virtual Device / Automation." Concretely: clicking "Create Virtual
Device" should require zero further manual clicks before the device is
live on screen and ready for automation.

Before this pass, reaching a usable device required three independent
manual actions: click Create (AVD created but not running), click Start
(emulator launches, boots in the background with no visible feedback
loop tying it to readiness), then click Connect (only then does the
ADR-020 boot-sequence pipeline run: ADB reachability, boot completion,
provider init, test screenshot, `READY`). A user unfamiliar with what
each of those three steps actually does has no way to know when it's
safe to click the next one.

### Decision

- Added `AppSession.create_and_ready_avd()`: one method composing four
  already-independently-tested pieces in sequence —
  `AndroidPlatformManager.create_virtual_device()` ->
  `start_virtual_device()` -> `EmulatorManager.wait_until_booted()` ->
  `connect_device()` (the full ADR-020 pipeline). No new duplicate
  logic — this is pure composition, so every failure mode it can hit
  was already independently handled (and tested) by one of those four
  calls.
- New route `POST /api/emulator/avds/one-click` runs the whole thing in
  a worker thread (`asyncio.to_thread`, matching every other
  potentially multi-minute SDK operation this webapp already runs
  off-loop) and returns the final `device_id`/`state` once truly
  `READY` — or a stage-specific diagnostic (via the existing
  `DeviceRecoveryError`/`EmulatorManagerError` exception types) the
  instant something fails.
- The webapp's Create button now calls this route instead of the old
  bare `POST /api/emulator/avds`, and on success immediately selects the
  new device and shows its live screen — matching the directive's "no
  intermediate manual actions" requirement end to end, including making
  the live screen visible without a separate Connect click.
- Extended the ADR-020 boot-sequence pipeline itself with two new
  sub-steps, since they apply to *every* device-connect (not just
  freshly created ones) and the directive lists them as standard
  boot-sequence stages:
  - **Screen unlock** (`_unlock_screen`, inside `BOOTING`): sends
    `KEYCODE_WAKEUP` then `KEYCODE_MENU` over `adb shell input keyevent`
    once boot-completion is confirmed. Best-effort and never fatal — a
    fresh AVD's default swipe-to-unlock screen is dismissed, but a
    PIN/pattern-locked device can't be (and shouldn't be) bypassed this
    way; either way boot-sequence progress continues.
  - **Test tap injection** (new `DeviceState.TESTING_INPUT`, after
    `CAPTURING_TEST_FRAME`): sends one real, harmless tap
    (`InputManager.click(1, 1)`, a corner pixel unlikely to hit any real
    UI element) to verify input injection actually works before
    `READY` — matching the directive's explicit "Tests tap injection"
    acceptance step, previously only implicitly exercised by
    `InputManager.connect()`'s screen-size query.
- A `capture_provider="window"` one-click request defaults `window_title`
  to the (possibly-sanitized) AVD name automatically — the caller can't
  know the final sanitized name in advance for a brand-new AVD, so
  requiring it up front would reintroduce a manual step the directive
  explicitly rules out.

### Consequences

- Positive: "Create Virtual Device -> Ready with a live screen" is now
  provably one action, unit-tested end-to-end (mocked ADB reporting the
  exact serial the mocked `start()` call returns, carrying a request
  through creation, boot-wait, ADB-reachability, boot-completion,
  provider init, test screenshot, and test tap, to a `200`/`state:
  "ready"` response).
- Positive: auto-recovery (ADR-020's `_ensure_ready`) automatically
  covers the new unlock/tap-test sub-steps too, for free — recovery
  re-runs the *entire* pipeline, not a hand-picked subset, so a device
  that lost its unlock state or whose input injection broke transiently
  still gets a real chance to self-heal before surfacing an error.
- Negative (documented, not solved): "Device Profiles" (Gaming
  Phone/Balanced Phone/High Performance/Tablet) were addressed only as
  friendly *display labels* over the existing performance-preset names
  (`gaming`→"Gaming Phone", `mid_range`→"Balanced Phone", etc.) in the
  UI layer — no new "Tablet" form-factor profile or backend renaming was
  added, since the manufacturer/device dropdowns already cover
  brand-name selection (ROG Phone, Samsung Galaxy, Pixel are literal
  existing entries) and renaming the internal preset identifiers would
  touch many existing tests for no functional benefit.
- Negative (documented, not solved): the one-click flow was validated
  end-to-end via the FastAPI TestClient with a mocked ADB device (fast,
  deterministic, exercises every stage including failure paths) and the
  UI wiring was live-verified against the real webapp (confirmed the
  Create button calls the new route with the right payload and restores
  its enabled state on failure) — but not against a real multi-minute
  AVD boot cycle in this pass, to avoid tying up this session for
  several minutes on an already-proven boot path (ADR-019 already
  live-validated that exact boot sequence independently). A full live
  run remains a recommended follow-up before calling this
  production-final.
