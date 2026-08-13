# UGAF Project Status

## Version 0.1 Capability Checklist (authoritative — updated 2026-07-02)

Progress is tracked by completed capabilities, not lines of code, test count, or
number of abstractions.

- [x] Connect to an Android device — **validated on real hardware**
- [x] Detect connected devices (online/offline/unauthorized) — **validated on real hardware**
- [x] Capture the device screen — **validated on real hardware**
- [x] Locate an image on the screen (real-image reliability tests; mock/replay demo)
- [x] Tap the detected location — **validated on real hardware** (see below)
- [x] Swipe — command executes on real hardware without error; visual UI-response
      confirmation still pending a swipe-reactive app
- [x] Enter text — implemented and unit-tested; not yet visually confirmed on real
      hardware in this pass
- [x] Execute one sample plugin from start to finish
- [x] Desktop application (`ugaf.webapp`) — browser-based control panel; users detect
      devices, view the live screen, tap/swipe/type, run plugins, and view logs with
      no code or ADB commands; screen refreshes live after every action
- [x] Second sample plugin, running continuously (not one-shot): `games/shadow_fight_3`
      — **validated on real hardware**, 14+ real ADB-driven combat cycles

**Version 0.1 is complete, including real-hardware validation.** A physical Android
device (Xiaomi/HyperOS, codename `peridot`) was connected via ADB and used to validate
device detection, connection, and screenshot capture live. Tap was validated
end-to-end through the actual web application: a real screenshot was captured, button
coordinates were computed from it, `2 + 2 = 4` was executed on the device's real
Calculator app via tap, and confirmed by a second real screenshot showing the result —
not a simulation. The Shadow Fight 3 plugin was then run against the same device
through the web UI's Run button, executing real combo taps for 14+ combat cycles with
clean start/stop and double-click idempotency. See `CHANGELOG.md` for the full
sequence and the real bugs this uncovered and fixed (below).

### Real-hardware findings (this pass)

- **Real bug found and fixed**: the web UI's "Run" button returned
  `400 Cannot transition from 'running' to 'initialized'` on first use, because
  `Application.start()` unconditionally auto-started every discovered plugin at boot
  (correct for the CLI, wrong for the web UI's explicit per-plugin Run button). Fixed
  with an `auto_start_plugins` flag and an idempotent `AppSession.run_plugin()`/
  `stop_plugin()` that check the plugin's actual `GameState` before acting.
- **Real bug found and fixed**: the live screen did not refresh after tap/swipe/text
  actions unless the "Auto-refresh" checkbox (unchecked by default) was on. Checkbox
  now defaults checked, and action feedback always triggers an immediate re-capture
  regardless of its state.

### Earlier real-hardware findings

- **Device-specific ADB restriction, not a UGAF defect**: this test device's OS (MIUI/
  HyperOS) rejected raw `adb shell input tap` with
  `SecurityException: Injecting input events requires... INJECT_EVENTS permission`
  until an additional Developer Options toggle ("USB debugging (Security settings)")
  was enabled. Documented in `README.md`.
- **Real bug found and fixed**: `AdbInputProvider._adb_shell()` silently swallowed
  this exact failure (by design, for fire-and-forget tap/swipe semantics) with zero
  logging — the SecurityException was completely invisible until raw `adb` was tested
  directly, outside the framework. Now logged at warning level with the device,
  command, and error.
- **Real bug found and fixed**: `AppSession.list_plugins()` called
  `PluginManager.discover()`, which only returns *newly* discovered plugins —
  since `Application.start()` already discovers plugins once at startup, the web UI's
  plugin panel was always empty after the first load. Fixed to read
  `PluginManager.registry.list()` instead.
- **Real bug found and fixed**: connecting a device from the web UI reused the shared
  framework config's `input.provider: windows` default instead of forcing `adb` for an
  Android device connection, causing every real-device connect attempt to fail. Fixed
  by adding `Config.from_dict()` (a small, justified new public API — needed by two
  independent call sites) and using it to force `provider: adb` for web-UI device
  connections specifically.

See `ROADMAP.md` for what's next.

## Post-0.1: Data-Driven Automation Architecture (2026-07-02)

Version 0.1's second sample plugin (`games/shadow_fight_3`) originally hardcoded every
move, coordinate, and combo directly in Python. Per direction to make UGAF a reusable
automation *platform* rather than accumulate game-specific Python, that logic was
extracted into a new reusable stack:

- [x] `ugaf.automation.knowledge.KnowledgeBase` — loads a game's moves
      (`knowledge/moves.yaml`) and control layout (`knowledge/buttons.yaml`) from YAML
- [x] `ugaf.automation.strategy.StrategyEngine` — picks moves per cycle from a
      `strategies/<name>.yaml` file's ordered rules; three strategies shipped
      (`balanced`, `aggressive`, `defensive`)
- [x] `ugaf.automation.executor.Executor` — generic `tap`/`move`/`hold`/`wait` verbs,
      zero game-specific knowledge, reusable by any future plugin
- [x] `games/shadow_fight_3/plugin.py` reduced to a thin shell (connect, load, run
      loop, report status) — no move names, coordinates, or combos remain in Python
- [x] `VisionManager` gained `measure_bar_fill`/`wait_until_visible`/
      `wait_until_hidden` — reusable primitives, ready for vision-driven strategy
      conditions once real game captures exist
- [x] **Validated on real hardware**: identical cycle-by-cycle move rotation to the
      pre-refactor version, now driven entirely by `strategies/balanced.yaml`
- [x] **Real bug found and fixed**: `PluginManager.initialize_all()`/`start_all()`
      let one plugin's failure (e.g. no device connected) abort every other plugin's
      auto-start — this refactor's real-hardware round-trip (device unplugged between
      sessions) is what surfaced it. Now fault-isolated per plugin.
- [x] Existing plugins (`demo_workflow`, `example_game`) untouched and still pass
      unmodified — introduced incrementally, not a rewrite

See ADR-014 in `ARCHITECTURE_DECISIONS.md` and `games/shadow_fight_3/README.md` for
the full design and how to edit behaviour without touching Python.

## Version 0.2: Application Manager + professional UI (2026-07-02)

Goal: the user connects a device, picks an automation, clicks Start — UGAF opens the
target app itself. No manual app-launching, no ADB commands, no editing Python for
normal use.

- [x] `ugaf.apps.ApplicationManager` — reusable Android app lifecycle (install check,
      launch, foreground verification with retry, optional stop). Not Shadow-Fight-3-
      specific: registered as a DI singleton, resolvable by any plugin.
- [x] `AppDefinition`/`app.yaml` — per-app identity and launch/shutdown behaviour as
      data, never hardcoded package names or activities in Python.
- [x] `DeviceManager.resolve_device()` — canonical target-device resolution, reused by
      `ApplicationManager` and available to any future consumer.
- [x] Startup workflow wired into `games/shadow_fight_3`: device -> installed -> launch
      -> verify foreground -> automation ready -> execute strategy -> report status.
      **Validated on real hardware**: `com.nekki.shadowfight3` detected installed,
      launched via its resolved main activity, foreground confirmed in a single
      attempt (~4-8s), and the combat loop began only after that confirmation — the
      game's actual title screen was visually confirmed via a live screenshot before
      automation started.
- [x] Web UI renamed "Plugins" -> "Automations" throughout; each automation card shows
      its target application and live status (idle/running/paused/error) with a busy
      indicator during launch. No ADB terminology exposed anywhere.
- [x] Full professional UI/UX redesign: real design system (typography, spacing,
      elevation, light/dark tokens), phone-frame device viewer with a proper empty
      state, status-pill/banner components, color-coded activity log.
- [x] **Real bug found and fixed**: `AppSession.run_plugin()` 400'd with "Cannot
      transition from 'created' to 'running'" the first time a never-before-run
      automation's health was polled (a side effect of the new live-status UI) before
      the user clicked Start. Fixed and covered by a regression test.

See ADR-015 in `ARCHITECTURE_DECISIONS.md` for the full Application Manager design,
and `ARCHITECTURE.md`'s "Startup workflow" section for the execution sequence.

## High-performance capture + multi-device architecture (2026-07-03)

Goal: reduce capture latency and support automating multiple physical devices and
Windows emulators at once, without replacing ADB (still the transport for device
control, input, app lifecycle, and shell commands — only the *frame source* is now
pluggable).

- [x] `ugaf.core.metrics.MetricsTracker` — reusable FPS/latency primitive, wired into
      capture (`ScreenshotManager.metrics`), vision processing
      (`VisionManager.processing_metrics`), and input (`InputManager.metrics`).
      **Validated on real hardware**: `/api/devices/{id}/metrics` and the web UI's
      Performance panel showed real live numbers — ~2.5s ADB capture latency, ~0.2
      FPS, ~164ms input latency — not placeholders.
- [x] `ugaf.vision.window_capture.WindowCaptureProvider` — captures a Windows
      emulator's window directly (`mss`+`pywin32`, optional `ugaf[emulator]`).
      **Validated against a real window** (Notepad) once the optional deps were
      installed in a compatible environment; full unit coverage otherwise.
- [x] `ugaf.vision.scrcpy_capture.ScrcpyFrameProvider` — decodes a scrcpy server's raw
      H264 stream via PyAV (optional `ugaf[scrcpy]`) instead of one ADB round trip per
      frame. Protocol-correct implementation, unit-tested against synthetic byte
      streams. **Not validated against a live scrcpy server** — neither `scrcpy` nor
      an Android emulator was available in this environment, and `pywin32`/`mss`/`av`
      currently have no published wheel for the Python 3.14 interpreter used here
      (confirmed via `pip install` resolving incompatible cp310 wheels). Documented,
      flagged gap — see ADR-016.
- [x] Multi-device concurrent automation — `PluginManager`'s lifecycle methods accept
      an optional `device_id`, letting the same automation run as independent
      concurrent instances (one per device), each with its own state/logs, fault
      isolated. Fully backward compatible. **Validated with real integration tests**:
      two concurrent `ShadowFight3Game` instances via `asyncio.gather`, independent
      `cycles_run`, and a dedicated test proving one instance's failure leaves the
      other's `GameState` untouched. Only one physical device was available in this
      environment, so the *true* two-physical-device claim rests on these
      mocked-device tests rather than a live two-device demo — see ADR-017.
- [x] Web UI: capture-provider selector (ADB/window) on connect, live Performance
      panel, and device-scoped automation Start/Stop/status.

See ADR-016 and ADR-017 in `ARCHITECTURE_DECISIONS.md` for the full designs, including
honest validation-gap writeups for the two hardware/tooling-gated capabilities.

## Emulator Manager Module (2026-07-04)

Goal: let a user target an Android Emulator instance instead of (or alongside) a
physical device, with manufacturer/device profiles and performance presets fully
data-driven (no hardcoded devices in Python or PowerShell), and an architecture that
leaves room for future non-Android-Studio emulator backends.

- [x] `ugaf.emulator.sdk_locator.AndroidSdkLocator` — finds the Android SDK from an
      explicit override, `ANDROID_HOME`/`ANDROID_SDK_ROOT`, or default per-OS install
      paths; resolves `adb`/`emulator`/`sdkmanager`/`avdmanager` from *within* that SDK
      root rather than trusting `PATH` first. **Validated on real hardware**: this
      development machine has a real SDK at `E:\Android\SDK` with *two* installed
      `adb.exe` copies — the locator correctly prefers the SDK's own copy.
- [x] `ugaf.emulator.hardware.HardwareDetector` — CPU/RAM/virtualization-acceleration
      detection and a performance-preset recommendation. **Validated on real
      hardware**: correctly detected 16 CPUs, ~31GB RAM, and WHPX acceleration
      ("usable") on this machine, recommending the "gaming" preset.
- [x] `ugaf.emulator.profiles.DeviceProfileManager` /
      `ugaf.emulator.performance.PerformanceProfileManager` — full manufacturer/device
      library (Google, Samsung, OnePlus, Nothing, Xiaomi, OPPO, vivo, Motorola, Sony,
      ASUS, HONOR) and performance presets (Low End/Mid Range/Flagship/Gaming/Custom),
      loaded entirely from `config/manufacturers.yaml`/`config/performance_profiles.yaml`.
- [x] `ugaf.emulator.android_versions.AndroidVersionManager` — detects installed system
      images and installs missing ones via `sdkmanager`, always live-queried (never a
      static list). **Validated on real hardware**: correctly parsed this machine's
      real `sdkmanager --list` output (239 catalog images, exactly 1 correctly
      identified as installed) — a real parsing bug (duplicate catalog entries
      overwriting the installed record) was caught and fixed this way, not by a
      hand-written fixture.
- [x] `ugaf.emulator.providers.android_studio.AndroidStudioProvider` +
      `ugaf.emulator.manager.EmulatorManager` — the full AVD lifecycle (create, start,
      stop, list, delete, clone, rename, update hardware, is-running, crash detection,
      boot-wait, install APK, push, pull). **Validated on real hardware**: a real AVD
      was created, started, confirmed running, stopped, and deleted end-to-end against
      this machine's real SDK; this machine's real `avdmanager list avd` also surfaced
      a genuine edge case (3 of 4 pre-existing AVDs were broken — bad `config.ini` or a
      missing system image) that `list()` now surfaces with error reasons instead of
      hiding or crashing.
- [x] Web UI: "Connection Type" radio (Physical Device / Android Emulator) toggles a
      new Android Emulator panel (Android Version / Manufacturer / Device /
      Performance Profile / AVD dropdowns, Create/Start/Stop/Delete/Open Android
      Studio/Refresh) — **validated live in the browser preview**: manufacturer
      selection correctly re-populates the device dropdown, the Android Version
      dropdown correctly pre-selects this machine's one installed image, and the AVD
      dropdown correctly lists real (and broken) AVDs from this machine.
- [x] Boot-completion wait: the ADR-018 boot stall was **root-caused and fixed** during
      the ATDD acceptance pass below — see the "ATDD acceptance validation" entry.

See ADR-018 in `ARCHITECTURE_DECISIONS.md` for the full design, including both bugs
this real-environment validation caught (sdkmanager catalog-duplicate parsing,
cmdline-tools version-string sorting).

## Emulator Manager: ATDD acceptance validation (2026-07-05)

Directive: treat every emulator feature as a complete, user-facing workflow and
validate it exactly as a user would, through the real web UI, with evidence — not
"unit tests pass" as a stand-in for "the feature works."

- [x] **Dependency checklist**: `ugaf.emulator.dependencies.EnvironmentChecker` probes
      Android Studio/SDK/platform-tools/emulator.exe/sdkmanager/avdmanager
      independently; the webapp renders real per-item status and gates
      Create/Start/Stop/Rename/Delete with a specific reason when a blocking
      dependency is missing. **Validated live**: all 6 show green on this machine's
      real SDK; simulated-missing-dependency scenario correctly disables every button
      and shows the exact missing component.
- [x] **Root-caused and fixed the ADR-018 boot stall**: two independent real bugs,
      each confirmed with direct evidence (not guessed) — (1) the emulator's own
      first-run crash-reporting consent dialog silently killed non-interactive
      launches (fixed: always pass `-crash-report-mode disabled`); (2) a real access
      violation inside this machine's AMD graphics driver (`amdxc64.dll`, confirmed via
      Windows Event Viewer) during the emulator's GPU-capability probe, regardless of
      the AVD's own GPU mode (fixed: force `-feature -Vulkan -gpu swangle` by default,
      configurable via `emulator_settings.yaml`'s `disable_vulkan`). See ADR-019.
- [x] **Full Create → Start → boot → live-screen → Stop chain validated live,
      repeatedly**, through the actual web UI: AVD created → listed → exists on disk →
      config valid; emulator process starts → ADB detects it (`emulator-5554`,
      `offline` → `device`) → real `sys.boot_completed=1` → launcher confirmed
      foreground via `dumpsys` → connected through the webapp's Device Manager → real
      screenshot captured at the device profile's exact resolution (1080×2424 for
      Pixel 9) → tap/swipe/type all executed successfully against the live device →
      Stop → ADB disconnects → both `emulator.exe` and `qemu-system-x86_64.exe`
      processes exit (confirmed via `tasklist`) → UI updates correctly. Rename and
      Delete also validated via the real API (a Rename route/button did not exist
      before this pass — added, since `EmulatorManager.rename()` already existed at
      the Python level but was never exposed through the webapp).
- [x] **Fixed three real UI state-machine bugs** found by this pass: emulator status
      being cached forever after a failed SDK-detection attempt instead of
      re-probing live; the Connection Type toggle skipping re-checks after the first
      load; and a genuine out-of-order-response race where rapid manufacturer/device
      switching could let a stale "system image installed?" answer overwrite a fresher
      one (fixed with a monotonic request-token guard).
- [x] **Fixed a real coordinate-overlay bug**: the tap/swipe coordinate math divided by
      the screen image's rendered height with no floor, so an unusually short
      viewport could compute `y=Infinity` (silently becoming `null` over JSON and
      failing the request with a confusing 422). Fixed with a CSS floor and an
      explicit zero-rect guard.

801 tests passing (26 new regression tests added this pass), ruff and mypy clean. See
ADR-019 in `ARCHITECTURE_DECISIONS.md` for full root-cause writeups and the one
documented, unsolved trade-off (the AMD-driver fix disables hardware-GPU rendering by
default on every host, not just ones that hit the bug, since there's no way to detect
it in advance short of booting and watching it crash).

## Device state machine and lifecycle bug investigation (2026-07-05)

Directive: the web UI could show `Status = Online` (real ADB) and `Connected = No`
(session-local flag) simultaneously, with screenshot requests 409ing on a fully
reachable device — find the root cause, not a workaround, and replace duplicate state
with one authoritative source.

- [x] **Traced the full lifecycle** (Launch → ADB discovery → Device Registration →
      Connection State → Screenshot Provider → Web API → UI) and confirmed the exact
      mechanism: `AppSession._connections` (pure dict-membership) and
      `DeviceManager.discover()` (live ADB status) were two independent, unreconciled
      state sources exposed side by side by `GET /api/devices`, with `connect_device()`
      never verifying actual boot/readiness before declaring "connected". See ADR-020
      for the full trace.
- [x] **Added `ugaf.device.lifecycle.DeviceLifecycle`**: one authoritative state per
      device (`DISCOVERED`/`STARTING`/`WAITING_FOR_ADB`/`BOOTING`/`INITIALIZING`/
      `CAPTURING_TEST_FRAME`/`READY`/`DISCONNECTED`/`ERROR`), every transition logged.
      `AppSession.is_connected()` now reads only this state — the dict-membership flag
      is gone, so the two can never disagree again.
- [x] **Implemented the full boot-sequence pipeline** in `AppSession._run_boot_sequence()`:
      verify ADB reachability → `sys.boot_completed == 1` + launcher focus via
      `dumpsys window` → initialize input/screenshot providers → capture a real test
      screenshot → only then `READY`. Any stage failure raises `DeviceRecoveryError`
      naming the exact stage.
- [x] **Screenshot/tap/swipe/text/metrics never hard-409 on a stale flag anymore**:
      `AppSession._ensure_ready()` re-runs the boot sequence once before giving up, so a
      device that's actually online and booted self-heals instead of requiring a manual
      reconnect. A genuine failure now returns a structured diagnostic
      (`{"stage": ..., "reason": ..., "detail": ...}`) naming which stage failed.
- [x] **UI reflects one authoritative state**: `GET /api/devices` now reports
      `state`/`state_reason` from `DeviceLifecycle`, with `connected` derived from it
      (never independent); `app.js` renders a single status pill from `state`
      (`STATE_META`) instead of separately rendering ADB status and a connected pill
      that could disagree.
- [x] **Regression tests**: `tests/test_device_lifecycle.py` (7 tests for the state
      machine itself) plus `tests/test_webapp_server.py` updated/extended to cover the
      full pipeline (boot-completion gating, stage-specific 409 diagnostics, and
      auto-recovery on a stale-but-reachable device via the real FastAPI TestClient with
      mocked ADB).

809 tests passing, ruff and mypy clean. See ADR-020 in `ARCHITECTURE_DECISIONS.md` for
the complete root-cause writeup.

**Not yet done**: live end-to-end acceptance validation against a real booted AVD,
including the directive's explicit "repeat every test after restarting the web
server" requirement — this pass validated the pipeline via the FastAPI TestClient with
mocked ADB (fast, deterministic, covers every stage/failure path) rather than a live
emulator boot cycle, which the next pass should still perform for full confidence.

## Android Platform Reliability sprint (2026-07-05)

Directive: Android Studio/sdkmanager/avdmanager/emulator.exe/adb.exe are
implementation details the user should never need to know about — refactor the
Android Platform layer into a real platform manager, not just add features.

- [x] **`ugaf.android_platform.AndroidPlatformManager`** built as the Android-domain
      facade: `list_virtual_devices`/`create_virtual_device`/`start_virtual_device`/
      `stop_virtual_device`/`list_physical_devices`/`platform_health`. Wraps
      already-constructed managers (never builds its own SDK-locating
      `EmulatorManager`) so it adds no extra SDK-probing cost and stays trivially
      mockable. `AppSession.start_avd`/`stop_avd`/`delete_avd` now route through it.
- [x] **Validate-before-boot**: `start_virtual_device()` runs the full dependency
      report and refuses to launch (naming the exact missing component) *before*
      ever invoking `emulator.exe` — previously a doomed launch only failed later as
      an opaque boot timeout. `DeviceLifecycle` (ADR-020) gained
      `VALIDATING`/`STOPPING`/`STOPPED`, driven by this same facade, on the same
      authoritative state store the device-connect pipeline uses.
- [x] **Automatic AVD name sanitization**: `EmulatorManager.create()` now sanitizes
      any user-entered name (`"ROG A15"` → `"ROG_A15"`) before it reaches
      `avdmanager`, preserving the original on `AvdInfo.display_name` for the UI.
- [x] **Two new non-blocking SDK checks**: `cmdline_tools_consistency` (ambiguous
      `cmdline-tools` layout with no `latest` dir) and `hypervisor` (surfaces
      `emulator -accel-check`'s hardware-acceleration result). The existing
      dependency-checklist UI needed zero rendering changes to pick these up — it
      already iterated the list generically.
- [x] **Environment Doctor summary** added to the emulator panel: overall platform
      health plus live physical/virtual device counts, from the same `DeviceManager`
      source `/api/devices` uses — live-validated against this machine's real SDK
      (`Overall Platform Health: Healthy`, real Hypervisor=WHPX, real cmdline-tools
      path, 8 dependency rows all correctly rendered).
- [x] **Removed "Open Android Studio"** (button, JS handler, session method, route)
      entirely per the directive — UGAF now only ever uses Android Studio's install
      location to help find the SDK, never launches the IDE.
- [x] **UI terminology**: "AVD" → "Virtual Device" throughout every user-facing label.
- [x] **Regression tests**: `tests/test_android_platform_manager.py` (7),
      `tests/test_emulator_naming.py` (8), 3 new cmdline-tools/hypervisor tests in
      `tests/test_emulator_dependencies.py`, plus updated fixtures across
      `test_webapp_emulator_routes.py`/`test_emulator_manager.py`.

831 tests passing, ruff and mypy clean. See ADR-021 in `ARCHITECTURE_DECISIONS.md` for
the full design rationale and documented follow-ups (the AVD-name-vs-adb-serial
lifecycle-key seam, and the read-only emulator listing methods that still call
`EmulatorManager` directly rather than through the new facade).

**Not yet done** (scoped out of this pass, tracked as follow-ups): "Capture Test"/
"Input Test" buttons and a dedicated `platform_health()` API route (the facade method
exists and is unit-tested, but the webapp only consumes its device-count logic today);
folding the remaining read-only `AppSession` emulator methods through
`AndroidPlatformManager` too; live acceptance validation of the validate-before-boot
path against a real AVD start (validated live only against this machine's already
fully-healthy environment, not against a deliberately-broken one).

## Android Platform Experience sprint: one-click Create Virtual Device (2026-07-05)

Directive: eliminate manual setup — clicking "Create Virtual Device" should be the
*only* user action needed to reach a live, automation-ready device. No SDK/AVD/adb
terminology should be user-facing.

- [x] **One-click flow**: `AppSession.create_and_ready_avd()` composes
      create → validate → start → wait-for-boot → connect (the full ADR-020
      pipeline) into a single call; `POST /api/emulator/avds/one-click` runs it
      off-loop. The webapp's Create button now calls this route and, on success,
      immediately shows the new device's live screen — zero intermediate
      Start/Connect clicks.
- [x] **Boot sequence extended** with two new real stages, applied to every
      device-connect (not just fresh creates): screen unlock (`adb shell input
      keyevent` wake + menu, best-effort) inside `BOOTING`, and a genuine test tap
      (new `DeviceState.TESTING_INPUT`) after the test screenshot, before `READY`.
      Auto-recovery (ADR-020) covers both automatically since it re-runs the whole
      pipeline.
- [x] **Friendly profile labels**: performance presets now show as "Gaming
      Phone"/"Balanced Phone"/"High Performance"/"Budget Phone" in the UI; backend
      identifiers (`gaming`/`mid_range`/etc.) unchanged.
- [x] **Regression tests**: `tests/test_webapp_one_click_avd.py` (4 tests, including
      a full success path with a mocked ADB device carrying the exact serial the
      mocked `start()` returns through every pipeline stage to `state: "ready"`).
- [x] **Live-verified UI wiring**: confirmed via the real browser preview that the
      Create button calls `/api/emulator/avds/one-click` with the correct payload
      and correctly re-enables its buttons and shows a diagnostic on failure.

835 tests passing, ruff and mypy clean. See ADR-022 in `ARCHITECTURE_DECISIONS.md`.

**Not yet done**: a full live run against a real multi-minute AVD boot cycle (this
pass validated the pipeline via TestClient + mocked ADB, and live-verified only the
UI-to-route wiring, deliberately avoiding a several-minute real boot already proven
independently in ADR-019); a "Tablet" form-factor device profile (only
brand/performance profiles exist today, no dedicated tablet hardware profile);
`AndroidPlatformManager.platform_health()` still isn't exposed via its own route.

---

# Source-Verified Audit (historical)

**Generated:** 2026-07-01
**Method:** Every claim below was verified by reading actual source code, running the test suite, running static analysis, and checking import/wiring paths — not by reading existing markdown docs. Markdown docs (ROADMAP.md, sprint reports, etc.) were treated as claims to be checked, not facts. Where a doc's claim was checked and found accurate, that is noted explicitly.

**2026-07-01 update — Milestones 1–3 landed since this audit was written.** This
document is preserved as a historical point-in-time snapshot (do not edit the findings
below to match current reality — that defeats the purpose of an audit trail). Current
status:

- **Critical Finding #1 (dual plugin systems): resolved.** See `ARCHITECTURE_DECISIONS.md`
  ADR-007. The legacy loader is deleted; `PluginManager`/`GamePlugin` is the only
  plugin system, and `Application.start()` now actually executes plugin lifecycle code.
- **Critical Finding #2 (no robust ADB reconnection): partially addressed.**
  `ugaf.device.manager.DeviceManager` + `ugaf.device.adb_provider.AdbDeviceProvider`
  (Milestone 3) now provide real device discovery with correct `online`/`offline`/
  `unauthorized` state parsing, lifecycle events, polling, and retry-with-restart
  recovery — see `ANDROID_TRANSPORT_STRATEGY.md` and `ARCHITECTURE_DECISIONS.md`
  ADR-010. **Not yet done:** `ugaf.input.adb.AdbInputProvider` (the input-injection
  path) was not migrated onto this new device layer and still has the narrower device
  parsing described in Finding #2 below — tracked in `KNOWN_LIMITATIONS.md`.
  **Update:** this ADB-parsing duplication was resolved in a subsequent governance
  audit fix — see `ARCHITECTURE_DECISIONS.md` ADR-012. `AdbInputProvider` now delegates
  to `AdbDeviceProvider` for device enumeration.
- **Screenshot capture gap (line ~119 below): resolved.** `ugaf.vision.adb_screenshot.
  AdbScreenshotProvider` (real, `adb exec-out screencap`), `MockScreenshotProvider`,
  and `ImageReplayProvider` now exist, orchestrated by
  `ugaf.vision.screenshot_manager.ScreenshotManager` and wired into `VisionManager` via
  `PluginManager` — verified live that `VisionManager.screenshot()` returns real image
  data end-to-end. See `SCREENSHOT_CAPTURE_STRATEGY.md` and ADR-013.
- A Platform Abstraction Layer (`ugaf.platform`, Milestone 2) now exists for Display,
  Clipboard, File System, Network, Notifications, Process Management — see
  `PLATFORM_ABSTRACTION.md`.
- The per-module completion table and remaining findings below reflect the tree
  **before** these three milestones and are not reflective of current line numbers or
  coverage percentages for the files they discuss (`ugaf/core/bootstrap.py`,
  `ugaf/core/context.py`, `ugaf/core/__init__.py`, `ugaf/core/exceptions.py` in
  particular have all changed since). For current numbers, see `BUILD_STATUS.md`'s
  latest run and the CHANGELOG's Milestone entries.

## Executive Summary

The codebase is higher-quality *per module* than typical alpha software — clean typing, structlog logging, real DI, real event bus, genuinely working OpenCV-backed vision. But the project has **one critical architectural defect that undermines the whole "framework"**: there are two independent, incompatible plugin systems, and the one that is actually wired into the application entry point (`ugaf/core/cli.py` → `ugaf/core/bootstrap.py`) is the **dead-end legacy one that never executes plugin code**. The real, tested, capability-checked SDK plugin system (`ugaf/plugins/*` driving `ugaf/sdk/game.GamePlugin`) is fully built and unit-tested but is never instantiated by the application. Running `ugaf start` today would discover plugins via the legacy loader, flip a `started` boolean, and fire generic events — it would never call `initialize()`/`start()` on any actual game plugin.

This is not a fabricated-progress problem — the project's own untracked sprint reports (`SPRINT_VALIDATION_REPORT.md`, `SPRINT_05_RELEASE_REPORT.md`) already flag this as a known critical defect and rate the release "BETA-READY (not production-ready)". The problem is that `KNOWN_LIMITATIONS.md`, `GAME_PLUGIN_SDK.md`, and `PLUGIN_ARCHITECTURE.md` were never updated to reflect it, so a reader of just those three docs would not know two systems exist.

Secondary finding: the ADB input subsystem described in the project directive ("robust ADB connection manager: reconnect automatically, monitor authorization, recover from disconnects/server restarts, expose device events") **does not exist**. What exists is a single one-shot `adb devices` shell-out plus a generic bounded retry loop around the *initial* connection attempt. There is no persistent monitoring, no offline/unauthorized state discrimination, no ADB-server-restart recovery, and no multi-device support.

## Build / Quality Snapshot (verified by running tools, not reading docs)

| Check | Result |
|---|---|
| `pytest` | **415 / 415 passed** (3.0s) |
| `ruff check .` | **All checks passed**, 0 warnings |
| `ruff format --check .` | **97 files already formatted**, 0 diffs |
| `mypy ugaf` (strict mode) | **Success: no issues found in 58 source files** |
| Overall statement coverage | **79%** (2563 stmts, 531 missed) — see gaps below; this number is misleading in isolation |
| CI/CD pipeline | **Does not exist.** No `.github/workflows/`, no `.gitlab-ci.yml`, no other CI config found anywhere in the repo |
| Python target | 3.13+ declared, tested here on 3.14.6 |
| Dependencies installed in this environment | `pyyaml`, `structlog`, `cv2` 4.13.0, `numpy` 2.3.5 present; `pytesseract` **absent** (OCR has no backend to bind to even if implemented) |

Full detail in [BUILD_STATUS.md](BUILD_STATUS.md).

## Critical Finding #1 — Dual, Incompatible Plugin Systems (confirmed, not speculative)

**System A — Legacy (wired into the app, does nothing functional):**
- `ugaf/core/plugin_loader.py` (`PluginLoader`) — scans `games/*/manifest.yaml` (expects flat `name`/`version` fields), optionally imports raw `bot.py`/`vision.py`/`strategy.py` modules but **never calls any function inside them**. `start_all()`/`stop_all()` just flip a `started: bool` and publish generic `plugin.started`/`plugin.stopped` events (plugin_loader.py:158–202).
- `ugaf/core/plugin.py` (`PluginInstance`, `PluginState`) — a full state-machine implementation (6 states, transition table, event publishing) that is **entirely dead code**. Confirmed via repo-wide grep: nothing outside `ugaf/core/plugin.py` itself imports `PluginInstance` or `PluginState`. 0% test coverage, 61 statements, unreachable.
- Wired via `ugaf/core/bootstrap.py:18,89,122-123` (`Application.__init__`/`.start()`) and surfaced through `ugaf/core/cli.py`'s `start`/`plugins` commands.

**System B — SDK-based (fully built, tested, correct — and orphaned):**
- `ugaf/sdk/game.py` (`GamePlugin` ABC: `initialize/start/pause/resume/stop/shutdown/health`), `ugaf/sdk/metadata.py`, `ugaf/sdk/state.py` (`GameState` with a real transition-validation state machine), `ugaf/sdk/events.py`, `ugaf/sdk/context.py`.
- `ugaf/plugins/loader.py` (`PluginLoader`) discovers `games/*/manifest.yaml` + `plugin.py`, validates the manifest via `ugaf/plugins/validator.py` (`PluginValidator` — real semver checks, capability enum validation, framework-version compatibility check, priority range check), and imports the module to find a concrete `GamePlugin` subclass.
- `ugaf/plugins/lifecycle.py` (`PluginLifecycle`) correctly drives the real lifecycle methods on the plugin instance, converts exceptions to `plugin.failed` events, and maps state → event topic.
- `ugaf/plugins/manager.py` (`PluginManager`) orchestrates discovery → registry → lifecycle for all plugins, including priority-ordered `start_all`/`pause_all`/`stop_all`/`shutdown_all`, and — notably — is the piece of code that actually wires up `ImagingManager`/`VisionManager` into the DI container (`_register_vision_services`, lines 311–334).
- **`PluginManager` is never imported or instantiated anywhere under `ugaf/core/`.** Confirmed by grep: zero references to `ugaf.plugins.manager` or `PluginManager` outside `ugaf/plugins/` itself and its tests.
- The only real example plugin, `games/example_game/plugin.py`, targets System B exclusively (`from ugaf.sdk.game import GamePlugin`), and its `manifest.yaml` uses System-B-style fields (`id`, `capabilities`, `priority`). It would be silently skipped or mishandled by System A's loader expectations, and System A's `Application` never runs System B's loader at all — so **the one working example plugin in the repo cannot actually be started by `ugaf start` today.**
- Bonus inconsistency found: `games/example_game/plugin.py:19` declares `capabilities=[]` while its own `manifest.yaml:10-12` declares `capabilities: [input]` — a real, minor authoring bug in the one example that exists.

**Doc consistency check:** `GAME_PLUGIN_SDK.md` (1 line) describes System B's lifecycle; `PLUGIN_ARCHITECTURE.md` (1 line) describes System A's file layout (`bot.py`/`vision.py`/`strategy.py`). They contradict each other and neither flags that the other system exists. `KNOWN_LIMITATIONS.md` documents only System A's behavior as if it were the sole plugin system. The untracked `SPRINT_VALIDATION_REPORT.md` (line 29) and `SPRINT_05_RELEASE_REPORT.md` (lines 69, 131) already correctly flag this exact defect as "Critical" / unresolved technical debt — those two reports are the most trustworthy documents in the repo; the rest of the docs have not caught up to them.

**Required fix (not yet made, flagging for planning):** `ugaf/core/bootstrap.py` needs to be repointed at `ugaf.plugins.manager.PluginManager` instead of `ugaf.core.plugin_loader.PluginLoader`, `ugaf/core/plugin.py` and `ugaf/core/plugin_loader.py` should be deleted as dead code (after confirming no external consumer depends on them), and `PLUGIN_ARCHITECTURE.md`/`KNOWN_LIMITATIONS.md` need rewriting to describe System B only.

## Critical Finding #2 — ADB "Robust Reconnection Subsystem" Does Not Exist

Per-file reality (`ugaf/input/adb.py`, `~55%` functionally complete):
- `connect()` issues **one** `subprocess.run(["adb", "devices"])` call, parses tab-delimited output, and picks/validates a device. No loop, no polling.
- Devices in `unauthorized` or `offline` ADB state are **silently indistinguishable from "no device"** — the parser only matches lines ending in `"device"`, so a real user plugging in a phone that needs USB-debugging authorization gets a generic `DeviceNotFoundError` with no diagnostic hint.
- `disconnect()` just clears local state — issues no actual ADB command.
- The ADB binary being entirely absent from PATH raises an **uncaught `FileNotFoundError`** rather than the framework's own `ConnectionFailedError` — only non-zero exit codes are handled.
- `key_up()` is `pass`-only (documented, deliberate — ADB has no key-up concept).
- No `adb kill-server`/`start-server` recovery, no continuous device-state monitor, no device-event stream, no concurrent multi-device orchestration.

What *does* exist: `ugaf/input/manager.py` has a real, generic, bounded retry loop (`for attempt in range(1, retry_count+1)` with `time.sleep`) around the **initial** `provider.connect()` call — this is reconnect-on-startup-failure, not the mid-session monitoring/recovery the project directive calls for.

`ugaf/core/platform.py` has genuine OS/WSL detection logic but is **never consulted** for input-provider selection — the ADB-vs-Windows choice is 100% manual config (`input.provider` key), not platform-detected, despite `platform.py` existing seemingly for that purpose.

**Test coverage note:** `test_input_adb.py` genuinely mocks `subprocess.run` and asserts real argv construction (not vacuous), but a test named `test_connect_retries_after_transport_error` does not actually test retry-on-transport-error — it feeds three consecutive successful calls, so the name overstates what's verified.

## Per-Module Completion Assessment

Estimates are based on working-logic coverage, not line count, and factor in the audits above.

| Module | Completion | Notes |
|---|---|---|
| `ugaf/core/config.py` | **95%** | Real YAML load, deep-merge, env-var override with type coercion, dotted-key access. Only gap: no schema validation (structural dict-check only), no secrets masking (`__repr__` dumps everything). Well tested (96% line coverage, 14 tests). |
| `ugaf/core/event_bus.py` | **95%** | Real async pub/sub, correct recursive `*`/`**` wildcard matching, asyncio.Lock-guarded. Well tested (99% coverage, 12 tests covering edge cases). |
| `ugaf/core/logger.py` | **90%** | Structlog fully wired: console + rotating file handlers, JSON/console render modes, level control. Gap: no correlation/request-ID context propagation. Well tested (99% coverage). |
| `ugaf/core/di.py` | **70% implemented, ~10% verified** | Genuinely sophisticated: singleton/transient lifetimes, thread-safe registry (`threading.Lock`), real constructor auto-wiring via type hints, real circular-dependency detection via a visiting-set. **Zero dedicated tests exist (`test_di.py` does not exist)** — 35% line coverage, and the *entire* auto-wiring/circular-detection/singleton-caching engine (lines 246–309) is unexercised. One real bug: the lock is held during dict mutation but **not** during the recursive dependency-graph walk, so the "thread-safe for concurrent resolution" docstring claim is not fully accurate. No scoped (request) lifetime, only singleton/transient. |
| `ugaf/core/health.py` | **90% implemented, ~30% verified** | Real registry with per-check exception isolation. **No `test_health.py` exists.** Docstring claims checks run "concurrently"; implementation is a sequential `for` loop — a real doc/code mismatch. |
| `ugaf/core/platform.py` | **90% implemented, 0% verified** | Real OS/WSL detection. **No `test_platform.py` exists at all** — not even a smoke test. Output is not consumed anywhere for provider selection (see Finding #2). |
| `ugaf/core/bootstrap.py` | **65%** | `Application` lifecycle (init/start/stop/run_forever, signal handling, health checks) is real and reasonably tested (63% coverage via `test_bootstrap.py`), but it orchestrates the **wrong plugin system** (Finding #1). |
| `ugaf/core/cli.py` | **60% implemented, 0% verified** | Real argparse-based CLI with `start`/`stop`/`health`/`plugins`/`version` subcommands, all delegating correctly to `Application`. **0% test coverage — no CLI tests exist at all.** Also inherits Finding #1 (the `plugins`/`start` commands operate on the dead plugin system). |
| `ugaf/core/plugin.py` | **0% (dead code)** | Fully implemented state machine, but unreachable — nothing imports it. Should be deleted. |
| `ugaf/core/plugin_loader.py` | **N/A (functional but architecturally wrong)** | Works as designed, but is the legacy system that should be retired per Finding #1. |
| `ugaf/plugins/*` (loader, validator, registry, lifecycle, manager) | **95% implemented, well tested** | This is the actual production-quality plugin system. Real semver/capability/priority validation, real lifecycle-state-machine enforcement (delegated to `ugaf/sdk/state.GameState`), real DI wiring of vision services. **Its only defect is that nothing outside its own package instantiates it** (Finding #1). |
| `ugaf/sdk/*` (game, metadata, state, events, context, capabilities, exceptions) | **95%** | Clean, well-typed, well-tested ABC + supporting types. This is solid foundation work. |
| `ugaf/input/adb.py` | **~55%** | Tap/swipe/text/screenshot mechanics work against a real `adb` shell-out. Connection robustness (the framework's stated top priority) is thin — see Finding #2. |
| `ugaf/input/manager.py` | **85%** | Real coordinate validation, dry-run mode, generic startup-retry loop, context-manager lifecycle. Solid. |
| `ugaf/input/windows.py` | **90%** | Genuine `pyautogui`/`keyboard`/`mouse` delegation, correctly gated on library availability. |
| `ugaf/input/registry.py`, `provider.py`, `types.py`, `exceptions.py` | **95–100%** | Clean, thread-safe (verified by real concurrency tests for the registry), fully tested. |
| `ugaf/imaging/opencv_backend.py` | **90%** | Real, working `cv2`-backed implementation — resize/rotate/blur/sharpen/threshold/grayscale/draw/template-match/encode-decode all call actual OpenCV functions, no stub branches. |
| `ugaf/imaging/image.py`, `manager.py`, `backend.py`, `types.py` | **95–100%** | Real, well-tested. |
| `ugaf/imaging/filters.py`, `formats.py`, `operations.py`, `transforms.py` | **0% functional (pure decoration)** | Each file is a single `X = str` type alias with a docstring listing "supported values." **Nothing in the codebase imports, validates, or dispatches on these names** — confirmed by repo-wide grep. The actual enum-like dispatch is hardcoded separately and redundantly inside `opencv_backend.py`'s internal maps. These four files should either be deleted or actually wired up as the single source of truth. |
| `ugaf/vision/detector.py`, `matcher.py` | **90%** | Real algorithms: Canny/contour/blob/Hough detection via cv2, hand-rolled IoU-based non-maximum suppression in `matcher.py`. Not placeholders. |
| `ugaf/vision/manager.py`, `color.py`, `pixel.py`, `region.py`, `screenshot.py`, `provider.py` | **90–100%** | Real composition and pixel/color/region math. Minor cosmetic bug: `vision/provider.py:104-105` has a duplicated `@abstractmethod` decorator (harmless but sloppy). |
| `ugaf/vision/ocr.py` | **0% functional, honestly labeled** | Both public methods unconditionally raise `OCRError("OCR is not implemented in this release")`. This is the one place where the code is honest about being a stub — docstring and tests both say so plainly. `pytesseract` isn't even installed. `VisionManager.ocr_text()` will always raise in production. |
| Screenshot capture (`ScreenshotProvider`) | **0% (no concrete implementation exists anywhere)** | `VisionManager` is wired up in production with `screenshot_provider=None` — grep found zero concrete `ScreenshotProvider` subclasses outside a throwaway test class. This means `vision.screenshot()`/`screenshot_region()`/`screenshot_window()` will always raise `ScreenshotError` end-to-end today, even though the manager itself is correctly wired. This is a meaningful, previously-undocumented gap — the vision engine cannot actually see the screen yet. |

## Blockers to Production Readiness (ranked)

1. **Dual plugin system** (Finding #1) — the app cannot currently run any game plugin end-to-end. This blocks everything downstream.
2. **No screenshot capture implementation** — the vision engine, once reachable, still can't see the screen. Blocks Android automation entirely.
3. **ADB connection management is not robust** (Finding #2) — directly contradicts the stated top priority ("never assume ADB remains connected").
4. **No CI/CD** — nothing prevents regressions from merging; all verification here was manual.
5. **`di.py`, `health.py`, `platform.py` have little-to-no dedicated test coverage** despite `di.py` containing the most architecturally load-bearing logic in `ugaf/core/` (auto-wiring, circular-dependency detection).
6. **OCR is unimplemented** and has no bound library even installed.

## What Is Genuinely Solid

- Config, logging, event bus, SDK plugin system, imaging backend, vision detector/matcher, input registry/windows-provider are all real, tested, reasonably production-quality code — not scaffolding.
- Static analysis is completely clean: ruff, ruff-format, and strict mypy all pass with zero issues across 58 source files.
- The project's own untracked sprint-validation documents are honest self-assessments (rating the release "BETA-READY, not production-ready" and explicitly flagging the dual-plugin-system defect) — this is a good sign for the team's calibration, even though the published-facing docs (ROADMAP, KNOWN_LIMITATIONS, architecture docs) haven't caught up.
