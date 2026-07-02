# UGAF Master Prompt

The single entry point for future development sessions. Historical per-sprint prompts
(`00_Project_Bootstrap.md` through `05_PluginLoader.md`, `Refactor.md`, `Release.md`,
`Review.md`) remain as an archival record of what each earlier phase asked for; this
file is what actually governs current work.

## Philosophy

The framework foundation is mature, and Version 0.1's core workflow is validated end
to end on real hardware. Focus has shifted from **framework infrastructure** to
**delivering a real, usable application** — usability, stability, and real-device
validation over new abstractions.

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
  existing manager.
- **`ugaf.automation`** (Knowledge -> Strategy -> Executor) is how a plugin's actual
  behaviour should be expressed once it's more than a one-shot demo: moves and control
  layout as data (`knowledge/*.yaml`), behaviour as data (`strategies/*.yaml`), with
  only the generic execution mechanics in Python (`ugaf.automation.executor.Executor`).
  A new game/app plugin should reach for this instead of hardcoding coordinates, combos,
  or decision logic in `plugin.py` — see `games/shadow_fight_3/` for the pattern and
  `ARCHITECTURE_DECISIONS.md` ADR-014 for why.

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
