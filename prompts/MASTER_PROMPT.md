# UGAF Master Prompt

The single entry point for future development sessions. Historical per-sprint prompts
(`00_Project_Bootstrap.md` through `05_PluginLoader.md`, `Refactor.md`, `Release.md`,
`Review.md`) remain as an archival record of what each earlier phase asked for; this
file is what actually governs current work.

## Philosophy

The framework foundation is mature, and Version 0.1's core workflow is validated end
to end on real hardware. Version 0.2 shifted focus again: from **framework
infrastructure** to **a polished, user-centric automation platform** — the user
connects a device, picks an automation, and clicks Start; UGAF opens the target app
itself. Usability, reliability, and reusable automation (not per-game Python) are the
priority over new framework complexity.

- The user should never need to: open the target app manually, remember ADB commands,
  hand-tune coordinates, or edit Python for normal automation use. UGAF prepares the
  environment (`ugaf.apps.ApplicationManager`'s startup workflow — see ADR-015).
- A new automation capability (a new game, a new target app) must be reusable
  platform capability, not something built specifically for one game. If you find
  yourself writing Shadow-Fight-3-specific (or any-single-app-specific) logic outside
  `games/<that_app>/`, it probably belongs in `ugaf.apps`/`ugaf.automation` instead.
- Keep the implementation simple. Do not build for hypothetical future features.
- When two solutions are valid, choose the simpler one unless there is clear technical
  evidence the extra complexity is required.
- Do not create additional managers, factories, coordinators, dispatchers, registries,
  or abstraction layers unless the current milestone actually requires one. Prefer
  extending an existing component.
- Every milestone must produce something demonstrable. At the end, answer: **"What can
  the user do today that they could not do yesterday?"**
- Research mature existing solutions before writing custom code. Only implement custom
  code where UGAF provides unique value.
- **Validate on real hardware whenever a real device is available, not only mocks.**
  Real hardware surfaces real bugs mocks cannot — three were found and fixed this way
  already (see `CHANGELOG.md`): a plugin list that only ever showed newly-discovered
  plugins, a device connection that ignored the intended transport, and a silently
  swallowed ADB `SecurityException` on a device with input-injection restricted by its
  OS. Devices may have OS-specific quirks (e.g. some Android builds require an extra
  Developer Options toggle for ADB input injection) — these are real constraints to
  document, not framework bugs to chase.

## Architecture, in one page

- **Core Engine** (`ugaf.core`) never depends on a specific transport or plugin
  implementation. It talks only to `DeviceManager` (never ADB directly) and
  `PluginManager` (only `GamePlugin`/the SDK, never a legacy loader).
- **`DeviceManager`** (`ugaf.device`) owns one or more `DeviceProvider` transports.
  ADB (`AdbDeviceProvider`) is the first and, for Version 0.1, the only one. Adding a
  future transport (Accessibility Service, UIAutomator2, MediaProjection, scrcpy,
  emulator, remote/cloud device) must not require Core Engine or plugin-API changes —
  it's a new `DeviceProvider`/`InputProvider`/`ScreenshotProvider` registered under a
  name, nothing more.
- **Interaction preference order** (highest-level capability first): Accessibility →
  UIAutomator2 → Vision+ADB → ADB shell input → low-level fallback. For Version 0.1,
  plain ADB is sufficient — do not delay on Accessibility/UIAutomator2 integration.
- **Vision** treats screenshots as image frames (`ScreenshotProvider`). Do not
  redesign into a `FrameProvider`/streaming abstraction until a real need appears.
- **One `InputManager`/`ScreenshotManager` per target** (one device, or one desktop) —
  multi-device means holding multiple instances, not making one instance multi-device
  aware. See `ARCHITECTURE_DECISIONS.md` ADR-011.
- **`ugaf.webapp`** is the user-facing application (browser-based control panel) —
  it's a thin FastAPI/HTML layer over the existing framework, not a new automation
  path. It must never contain automation logic itself; every route delegates to an
  existing manager. User-facing terminology is application-oriented ("Automations",
  target app names/status), never ADB/developer jargon. The frontend follows the
  design-token system in `ugaf/webapp/static/style.css` — extend it, don't bypass it
  with one-off inline styles.
- **`ugaf.automation`** (Knowledge -> Strategy -> Executor) is how a plugin's actual
  behaviour should be expressed once it's more than a one-shot demo: moves and control
  layout as data (`knowledge/*.yaml`), behaviour as data (`strategies/*.yaml`), with
  only the generic execution mechanics in Python (`ugaf.automation.executor.Executor`).
  A new game/app plugin should reach for this instead of hardcoding coordinates, combos,
  or decision logic in `plugin.py` — see `games/shadow_fight_3/` for the pattern and
  `ARCHITECTURE_DECISIONS.md` ADR-014 for why.
- **`ugaf.apps.ApplicationManager`** is how a plugin gets its target Android app ready
  before automating: installed check, launch, foreground verification with retry,
  optional stop — all driven by an `app.yaml` (package, activity, timeouts, shutdown
  behaviour), never hardcoded. Registered as a DI singleton in `PluginManager`
  alongside `DeviceManager`; a plugin resolves it, it does not construct its own. See
  ADR-015 for why this must stay reusable across every app-backed automation, not
  become Shadow-Fight-3-specific.

## Documentation

Only maintain: `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `PROJECT_STATUS.md`,
`CHANGELOG.md`, and this file. Do not create additional standalone documents unless
they become genuinely useful. When implementation changes, update only the
documentation directly affected — do not let docs drift, but do not pad them either.

## Testing

Every new capability needs unit tests, integration tests where appropriate, and an
end-to-end demonstration — the demonstration is part of the milestone, not optional
polish.

## Progress tracking

Track progress by completed capabilities (see `PROJECT_STATUS.md`'s checklist), never
by lines of code, test count, or number of abstractions.
