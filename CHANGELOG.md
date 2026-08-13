# Changelog

## Unreleased

### Android Platform Experience: one-click Create Virtual Device

#### Added

- **One-click "Create Virtual Device"** (`AppSession.create_and_ready_avd`,
  `POST /api/emulator/avds/one-click`): a single click now takes a device from
  "does not exist" all the way to a live screen and `READY` — create, validate
  dependencies, boot, wait for ADB, unlock the screen, capture a test
  screenshot, test a real tap, and connect — no intermediate Start/Connect
  clicks. The webapp's Create button now calls this route directly.
- **Screen unlock** and **test tap injection** (`DeviceState.TESTING_INPUT`)
  added as standard stages of the device-connect boot sequence (ADR-020) —
  every connect, not just freshly created devices, now unlocks the screen and
  verifies input injection with a real tap before declaring `READY`.
- Friendly performance-profile labels in the UI (`mid_range` → "Balanced
  Phone", `gaming` → "Gaming Phone", `flagship` → "High Performance",
  `low_end` → "Budget Phone") — the underlying identifiers are unchanged.

### Android Platform Reliability: AndroidPlatformManager facade, SDK validation, name sanitization, Environment Doctor

#### Added

- **`ugaf.android_platform.AndroidPlatformManager`**: the single Android-domain facade
  the webapp now routes AVD start/stop through — exposes `list_virtual_devices`,
  `create_virtual_device`, `start_virtual_device`, `stop_virtual_device`,
  `list_physical_devices`, `platform_health()` instead of raw SDK-tool operations.
  `start_virtual_device()` validates every blocking SDK dependency *before* launching
  the emulator process (the directive's "Create -> Validate -> Boot" sequence),
  refusing with a specific reason instead of a doomed multi-minute boot timeout.
- **`ugaf.emulator.naming.sanitize_avd_name()`**: user-entered Virtual Device names
  (e.g. `"ROG A15"`) are automatically sanitized into valid `avdmanager` identifiers
  (`"ROG_A15"`) — the original is preserved on `AvdInfo.display_name` for the UI.
- **Two new, non-blocking `EnvironmentChecker` checks**: `cmdline_tools_consistency`
  (flags an ambiguous `cmdline-tools` layout with no `latest` dir) and `hypervisor`
  (surfaces `emulator -accel-check`'s hardware-acceleration result).
- **Environment Doctor summary**: the emulator panel now shows overall platform
  health plus live physical/virtual device counts, from the same `DeviceManager`
  source `/api/devices` uses.
- **`DeviceLifecycle`** (ADR-020) gained `VALIDATING`/`STOPPING`/`STOPPED` states,
  now driven by `AndroidPlatformManager`'s start/stop pipeline.

#### Changed

- **UI terminology**: "AVD" renamed to "Virtual Device" in every user-facing label.
- **Removed** the "Open Android Studio" button/route/session method entirely — per
  the directive, UGAF now only ever uses Android Studio's install location to help
  locate the SDK, and never launches the IDE itself.

### Device lifecycle: single-authoritative state machine, real boot-sequence validation, auto-recovering screenshots

#### Added

- **`ugaf.device.lifecycle.DeviceLifecycle`**: the one authoritative state machine per
  device, replacing the dual `DeviceManager` status / `AppSession._connections`
  dict-membership flags that could disagree. States:
  `DISCOVERED`/`STARTING`/`WAITING_FOR_ADB`/`BOOTING`/`INITIALIZING`/
  `CAPTURING_TEST_FRAME`/`READY`/`DISCONNECTED`/`ERROR`, every transition logged.
- **`DeviceManager.shell_sync()`**: a plain synchronous ADB shell probe for the
  boot-sequence pipeline's `sys.boot_completed`/launcher check.
- **`DeviceRecoveryError`**: raised with the exact pipeline stage and reason when a
  device can't be brought to `READY`; surfaced as a structured 409 diagnostic
  (`{"stage": ..., "reason": ..., "detail": ...}`), never a bare "not connected".

#### Fixed

- **Real bug**: the web UI could show `Status = Online` (from live ADB, via
  `DeviceManager.discover()`) and `Connected = No` (from `AppSession._connections`
  dict membership) simultaneously, and screenshot requests could 409 even though the
  device was fully reachable — two independent, unreconciled state sources for one
  device. `is_connected()` is now backed entirely by `DeviceLifecycle`, so the two can
  never disagree. See ADR-020 for the full lifecycle trace and root cause.
- **Real bug**: `connect_device()` declared a device "connected" the instant its
  `InputManager`/`ScreenshotManager` objects were constructed, with no check that the
  device had actually finished booting or could produce a real frame. Replaced with a
  boot-sequence pipeline: verify ADB reachability → `sys.boot_completed == 1` +
  launcher focus → initialize providers → capture a real test screenshot → only then
  `READY`.
- **Real bug**: screenshot/tap/swipe/text/metrics returned HTTP 409 purely because an
  internal "connected" flag was stale (e.g. right after a webapp restart), even when
  the device was online and ready. These routes now auto-recover by re-running the
  boot-sequence pipeline once before reporting a (now stage-specific) failure.

### Emulator Manager: ATDD acceptance validation, dependency checklist, real boot-crash fixes

#### Added

- **`ugaf.emulator.dependencies.EnvironmentChecker`**: probes Android Studio, the SDK
  root, platform-tools, `emulator.exe`, `sdkmanager`, and `avdmanager` independently
  (never one all-or-nothing failure), producing a `DependencyReport` the webapp renders
  as a real checklist with paths or specific "missing" reasons. Android Studio is
  checked/displayed but never blocking (the SDK command-line tools work headlessly).
  `AndroidSdkLocator` gained public `find_adb`/`find_emulator`/`find_sdkmanager`/
  `find_avdmanager` to support this.
- **Webapp**: the Android Emulator panel now shows a live per-dependency checklist and
  a "Required system image installed" indicator for the selected device, and disables
  Create/Start/Stop/Rename/Delete with a specific reason when a blocking dependency is
  missing. Added a Rename button/route (`EmulatorManager.rename()` already existed at
  the Python API level but was never exposed through the webapp).

#### Fixed

- **Real bug**: `AndroidStudioLocator` (the "Open Android Studio" button) never found
  Android Studio on this project's own development machine — it's installed as a
  sibling of the SDK root (`E:\Android\Android Studio` next to `E:\Android\SDK`), not
  any of the "well-known" default locations previously checked. Now checks
  `ANDROID_STUDIO_HOME`, then the sibling-of-SDK-root layout, before falling back to
  the original defaults and `PATH`.
- **Real bug**: launched non-interactively, the emulator never reached boot — it tried
  to show a native crash-reporting consent dialog with no window station to render it
  on, and exited silently before starting the AVD. Fixed by always passing
  `-crash-report-mode disabled`.
- **Real bug**: on this machine's hybrid NVIDIA+AMD GPU configuration, the emulator
  crashed with a real access violation inside the AMD graphics driver (`amdxc64.dll`,
  confirmed via Windows Event Viewer) during its GPU-capability probe, regardless of
  the AVD's own GPU mode. Fixed by forcing `-feature -Vulkan -gpu swangle` by default
  (configurable via `emulator_settings.yaml`'s new `disable_vulkan` setting).
- **Real bug**: `AppSession._get_emulator_manager()` cached a *failed* SDK-detection
  attempt forever, so "SDK not found" could keep showing even after a user fixed the
  underlying problem without restarting the webapp. `emulator_status()` now always
  re-probes live instead of reusing a cached result.
- **Real bug**: switching Connection Type away from and back to "Android Emulator"
  skipped re-checking dependency/AVD status after the first successful load, risking
  stale status. Now always re-checks on every switch.
- **Real bug**: rapid manufacturer/device selection changes could let an earlier,
  slower "system image installed?" response resolve after a later, faster one and
  silently overwrite it with stale data — a genuine out-of-order response race. Fixed
  with a monotonic request-token guard (applied to both the system-image check and the
  manufacturer→device-list fetch, which had the identical race).
- **Real bug**: the screen viewer's tap/swipe coordinate math divided by the image
  element's rendered height with no floor; an unusually short browser viewport could
  compute `y=Infinity`, which JSON serializes to `null`, failing the request with a
  confusing 422 instead of just ignoring the click. Fixed with a CSS floor on the
  image's max-height and an explicit zero-rect guard in the coordinate calculation.

#### Validation

Full Create → Start → real boot (`sys.boot_completed=1`) → launcher-visible (verified
via `dumpsys`) → Device-Manager-connected → real screenshot captured (device profile's
exact resolution) → live screen → tap/swipe/type → Stop → clean shutdown (ADB
disconnect + process exit confirmed via `tasklist`) → Rename → Delete chain validated
live, repeatedly, through the actual web UI against this machine's real Android SDK —
see ADR-019 for the full root-cause writeups. 801 tests passing (26 new regression
tests for the dependency checker, Android Studio locator, and `-crash-report-mode`/
`disable_vulkan` argument threading), ruff and mypy clean.

### Emulator Manager Module

#### Added

- **`ugaf.emulator`**: a new subsystem letting a user target an Android Emulator
  instance instead of (or alongside) a physical device — an emulator becomes an
  ordinary `adb` serial once running, so no other layer needs emulator-specific code.
  - **`EmulatorProvider`** (`ugaf.emulator.provider`): an ABC + `AdapterRegistry`, the
    same seam pattern as `ScreenshotProvider`/`DeviceProvider`. Only
    `AndroidStudioProvider` is registered today; a future BlueStacks/LDPlayer/
    Genymotion/Waydroid backend is a new class + one registration call.
  - **`AndroidStudioProvider`** (`ugaf.emulator.providers.android_studio`): drives real
    `avdmanager`/`emulator`/`adb` binaries for the full AVD lifecycle — create, start,
    stop, list, delete, clone, rename, update hardware, is-running, crash detection,
    boot-wait, install APK, push, pull. Allocates a fresh console/ADB port pair per
    launched instance for concurrent multi-instance support.
  - **`EmulatorManager`** (`ugaf.emulator.manager`): the single facade every caller
    uses, wiring the SDK locator, device/performance profile managers, the Android
    version manager, and hardware detector to whichever provider is configured.
  - **`AndroidSdkLocator`** (`ugaf.emulator.sdk_locator`): finds the Android SDK from
    `ANDROID_HOME`/`ANDROID_SDK_ROOT`/default install paths, never a hardcoded path;
    prefers the SDK's own `platform-tools/adb` over whatever is first on `PATH`.
  - **`DeviceProfileManager`/`PerformanceProfileManager`** (`ugaf.emulator.profiles`/
    `performance`): the full manufacturer/device library (Google, Samsung, OnePlus,
    Nothing, Xiaomi, OPPO, vivo, Motorola, Sony, ASUS, HONOR) and performance presets
    (Low End/Mid Range/Flagship/Gaming/Custom), entirely YAML-driven
    (`config/manufacturers.yaml`/`config/performance_profiles.yaml`) — no device or
    preset is hardcoded in Python.
  - **`AndroidVersionManager`** (`ugaf.emulator.android_versions`): detects installed
    Android system images and installs missing ones via `sdkmanager`, always
    live-queried against the real SDK, never a static list.
  - **`HardwareDetector`** (`ugaf.emulator.hardware`): CPU/RAM/virtualization-
    acceleration detection (WHPX/Hyper-V/HAXM/KVM via `emulator -accel-check`) and a
    performance-preset recommendation based on detected headroom.
  - **Web UI**: a new "Connection Type" radio (Physical Device / Android Emulator)
    toggles a new Android Emulator panel — Android Version/Manufacturer/Device/
    Performance Profile/AVD dropdowns, Create/Start/Stop/Delete/Open Android
    Studio/Refresh buttons — wired to new `/api/emulator/*` routes, all thin
    delegations to `EmulatorManager` via `AppSession`.

#### Fixed

- Two real bugs were caught specifically by validating against this machine's actual
  Android SDK rather than only hand-written test fixtures:
  - `sdkmanager --list` re-lists every already-installed package under "Available
    Packages" too; a naive dict-building parser let that not-installed duplicate
    silently overwrite the correct `installed=True` record, making
    `AndroidVersionManager.ensure_installed()` think an already-installed system image
    needed downloading. Fixed by preferring the "Installed packages" record when both
    exist for the same package path.
  - `AndroidSdkLocator`'s `cmdline-tools` version-directory fallback sorted directory
    names as plain strings, ranking `"9.0"` above `"12.0"` (lexicographic comparison of
    the leading digit) and silently preferring an older command-line-tools install.
    Fixed with numeric-tuple version comparison.

#### Known gaps (documented, not hidden)

- A freshly created AVD did not finish booting to `sys.boot_completed=1` within the
  default 180s timeout on this development machine when using software rendering on a
  cold boot — the `emulator` process itself stalled at `gfxstream` graphics backend
  initialization for several minutes, a real host/driver characteristic of this
  machine, not a bug in `wait_until_booted()`'s polling logic (which correctly returned
  `False` at the timeout without raising, and correctly reported the process as still
  alive). The full AVD lifecycle up to boot completion — create, start, is-running,
  crash detection, stop, delete — was validated live end-to-end. See ADR-018.
- "Open Android Studio" only checks a handful of well-known Windows install paths (plus
  `PATH` on other platforms); a non-standard install location reports "not found"
  rather than launching. Not load-bearing — every AVD operation works from the web UI
  without it.

#### Validation

54 new unit/integration tests (`tests/test_emulator_*.py`), all passing, alongside the
full existing suite (775 tests total), ruff, and mypy strict. Live-validated against
this machine's real Android SDK installation: real `sdkmanager --list`/`avdmanager list
avd` parsing (catching the two bugs above), a real create → start → is_running → stop →
delete AVD cycle, real hardware detection (16 CPUs, ~31GB RAM, WHPX acceleration
usable), and the web UI's Connection Type toggle and Android Emulator panel confirmed
live in the browser preview against this machine's actual manufacturer/device/version/
AVD data — including this machine's 3 genuinely broken pre-existing AVDs (bad
`config.ini`, missing system image), which `list()` now surfaces with error reasons
instead of hiding or crashing on. See ADR-018 in `ARCHITECTURE_DECISIONS.md`.

### High-performance capture + multi-device architecture

#### Added

- **`ugaf.core.metrics.MetricsTracker`**: a single reusable rolling-window
  FPS/latency/processing-time primitive, wired into `ScreenshotManager.metrics`
  (capture), `VisionManager.processing_metrics` (template-matching time), and
  `InputManager.metrics` (input round-trip latency). Exposed live via the web UI's new
  "Performance" panel and `GET /api/devices/{id}/metrics`.
- **`ugaf.vision.window_capture.WindowCaptureProvider`**: a new capture transport that
  captures a named Windows window's client area directly (`mss`+`pywin32`, optional
  `pip install ugaf[emulator]`) — for Android emulators (BlueStacks, NoxPlayer, the
  Android Studio emulator, ...) running as ordinary windows. Bypasses ADB entirely for
  the frame source; ADB stays the transport for everything else.
- **`ugaf.vision.scrcpy_capture.ScrcpyFrameProvider`**: a new capture transport that
  decodes a scrcpy server's raw H264 video stream via PyAV (optional
  `pip install ugaf[scrcpy]`) instead of one `adb screencap` round trip per frame.
  Protocol-correct implementation (push server, forward socket, parse frame-meta
  framing, decode) — not validated against a live scrcpy server in this environment
  (none available); see "known gaps" below.
- **Multi-device concurrent automation**: every `PluginManager` lifecycle method
  (`initialize`/`start`/`pause`/`resume`/`stop`/`shutdown`/`health`) now accepts an
  optional `device_id`, letting the *same* automation run as independent, concurrent
  instances — one per target device — each with its own `GameState`, task, and logs.
  Fully backward compatible (omitting `device_id` is byte-identical to the old
  behaviour). `games/shadow_fight_3` now honors a per-instance `context.device_id`.
  The web UI scopes each automation card's Start/Stop/status to the currently selected
  device via `?device_id=...`. See ADR-017 in `ARCHITECTURE_DECISIONS.md`.
- **Web UI**: capture-provider selector (ADB / window capture, with a window-title
  field) on device connect, and a live "Performance" panel (capture FPS, capture
  latency, input latency).

#### Known gaps (documented, not hidden)

- Neither `scrcpy` nor an Android emulator was available in this development
  environment, and `pywin32`/`mss`/`av` have no published wheel yet for the Python 3.14
  interpreter used here (confirmed: `pip install` resolves cp310-tagged wheels that
  fail to import). `ScrcpyFrameProvider` and `WindowCaptureProvider`'s Win32-API logic
  are covered by full unit-test suites (synthetic byte streams / injected fake
  `win32gui`/`mss`/`av` modules) but not live end-to-end. `WindowCaptureProvider`'s
  actual capture mechanism *was* validated against a real window (Notepad) once the
  optional deps were installed in a compatible environment.
- The "multiple devices at once" claim is proven by mocked-device integration tests
  (two concurrent `ShadowFight3Game` instances via `asyncio.gather`, independent state,
  fault isolation) rather than a live two-physical-device demo — only one real Android
  device was available. See ADR-016/ADR-017 for the full validation breakdown.

#### Validation

Full test suite (721 tests), ruff, and mypy pass. Live-validated on the physical
Xiaomi/HyperOS device: real capture/input metrics captured through the new
`/api/devices/{id}/metrics` endpoint and the web UI's Performance panel (measured:
~2.5s ADB capture latency, ~0.2 FPS, ~164ms input latency — real numbers, not
placeholders), confirming the metrics pipeline works end-to-end against real hardware.

### Version 0.2: Application Manager + professional UI redesign

#### Added

- **`ugaf.apps`**: a new, reusable Application Manager (`ApplicationManager`) for
  Android application lifecycle — install detection, launch (explicit activity or the
  app's own launcher intent), foreground verification with retry, and optional
  force-stop. Per-app identity/behaviour is data (`AppDefinition`, loaded from an
  `app.yaml`), never hardcoded Python. Registered as a DI singleton in `PluginManager`
  alongside `DeviceManager`, so every plugin gets the same instance for free — not
  built specifically for Shadow Fight 3. See ADR-015 in `ARCHITECTURE_DECISIONS.md`.
- **`DeviceManager.resolve_device()`**: canonical "which device do I target" helper
  (configured id, or the sole online device) — replacing what would have been a third
  independent copy of that logic.
- **`games/shadow_fight_3/app.yaml`**: declares the real package
  (`com.nekki.shadowfight3`) and main activity
  (`com.nekki.unityplugins.NekkiNativeActivity`), both confirmed against the real
  connected device via `adb shell pm list packages` /
  `adb shell cmd package resolve-activity --brief`. The plugin's `start()` now runs the
  full startup workflow (resolve device -> confirm installed -> launch -> verify
  foreground) before the combat loop begins — validated live: the game's real title
  screen was visually confirmed on screen before automation started.
- **Web UI professional redesign**: `ugaf/webapp/static/{index.html,style.css,app.js}`
  rebuilt with a real design system (typography, spacing, elevation, light/dark color
  tokens), a phone-frame device viewer with a proper empty state, status-pill
  automations list showing each automation's target application and live
  running/idle/error state with a busy spinner during launch, a status-banner "Current
  Action" indicator, and a color-coded activity log console. "Plugins" renamed
  "Automations" throughout — no ADB terminology exposed anywhere in the UI.

#### Fixed

- **Real bug found via this pass**: `AppSession.run_plugin()`'s idempotency check
  didn't account for `GameState.CREATED` — the new automation list's live-status
  polling calls `/health`, which calls `PluginManager.load()` as a side effect
  (creating a `CREATED` lifecycle) before the user ever clicks "Run." Clicking Run from
  that state hit `400 Cannot transition from 'created' to 'running'`. Fixed by treating
  `CREATED` the same as "never touched" (initialize then start); covered by a
  regression test that reproduces the exact poll-then-run sequence.

#### Validation

Full test suite (683 tests), ruff, and mypy pass. Validated live end-to-end on the same
physical Xiaomi/HyperOS device: detected `com.nekki.shadowfight3` installed, launched
it via the resolved main activity, confirmed foreground in a single attempt, the
combat loop began only after that confirmation, and the redesigned UI correctly
reflected device connection, live screen (showing the game's actual title/combat
screens), and automation status throughout — including a spinner-labeled busy state
during the ~4-8s launch window.

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
