# Roadmap

Progress is tracked by completed capabilities, not lines of code or milestone counts.
See `PROJECT_STATUS.md` for the authoritative, up-to-date checklist.

## Version 0.1 — reliably automate one Android workflow

- [x] Connect to an Android device (`DeviceManager` + `AdbDeviceProvider`)
- [x] Detect connected devices (online/offline/unauthorized)
- [x] Capture the device screen (`ScreenshotManager` + `AdbScreenshotProvider`)
- [x] Locate an image on the screen (`VisionManager.find_template`)
- [x] Tap the detected location (`InputManager`)
- [x] Swipe
- [x] Enter text
- [x] Execute one sample plugin start to finish (`games/demo_workflow`)
- [x] Desktop application (`ugaf.webapp` — browser-based control panel): detect
      devices, view live screen, click to tap, drag to swipe, send text, run plugins,
      view logs — no coding or ADB commands required
- [x] **Validated on real Android hardware** (not just mocks): device detection,
      connection, screenshot capture, and tap all confirmed live against a physical
      phone — a real 2+2=4 calculation performed via tap coordinates computed from a
      live screenshot, through the actual web app.
- [x] Second sample plugin running as a continuous background loop, not one-shot
      (`games/shadow_fight_3`) — validated live: 14+ real combat cycles against the
      same physical device through the web UI's Run button.

Version 0.1 is complete. Everything also runs against safe mock/replay defaults with
no hardware required for development/testing; switching to a real device is a config
change, not a code change.

## Post-0.1 — data-driven automation platform

- [x] `ugaf.automation` (Knowledge -> Strategy -> Executor): reusable, game-agnostic
      stack so a plugin's moves, control layout, and combat strategy live in YAML, not
      Python. See `ARCHITECTURE_DECISIONS.md` ADR-014.
- [x] `games/shadow_fight_3` migrated onto it — `plugin.py` reduced to a thin shell;
      validated live on real hardware with identical behaviour to the pre-refactor
      version.
- [x] `VisionManager.measure_bar_fill`/`wait_until_visible`/`wait_until_hidden` added
      as reusable primitives.

## Version 0.2 — user-centric automation platform

Goal: connect a device, pick an automation, click Start — UGAF opens the target app
itself. No manual app-launching, no ADB, no Python for normal use.

- [x] `ugaf.apps.ApplicationManager`: reusable Android app lifecycle (install check,
      launch, foreground verification + retry, optional stop) — a platform capability,
      not built for Shadow Fight 3 specifically. See ADR-015.
- [x] `AppDefinition`/`app.yaml`: per-app identity/behaviour as data.
- [x] `DeviceManager.resolve_device()`: canonical target-device resolution.
- [x] Startup workflow (device -> installed -> launch -> verify foreground ->
      automation ready) wired into `games/shadow_fight_3` — **validated live**: real
      package detected, launched, foreground confirmed, game's actual title screen
      visually confirmed before automation began.
- [x] Web UI renamed "Plugins" -> "Automations"; each card shows target app + live
      status; no ADB terminology anywhere.
- [x] Professional UI/UX redesign: real design system, phone-frame viewer, status
      pills/banners, color-coded log console.

## High-performance capture + multi-device architecture

Goal: reduce capture latency and support multiple physical devices/emulators at once,
without replacing ADB (still the transport for device control, input, app lifecycle,
shell commands — only the frame source is now pluggable).

- [x] `ugaf.core.metrics.MetricsTracker`: reusable FPS/latency tracking for capture,
      vision processing, and input — **validated live** (real ~2.5s ADB capture
      latency, ~164ms input latency measured against physical hardware). See ADR-016.
- [x] `WindowCaptureProvider` (Windows emulator window capture, optional
      `ugaf[emulator]`) — validated against a real window; no emulator was available
      to validate emulator-specific capture, but the capture mechanism itself works.
- [x] `ScrcpyFrameProvider` (scrcpy H264 stream decode, optional `ugaf[scrcpy]`) —
      protocol-correct, unit-tested; **not validated against a live scrcpy server**
      (none available in this environment). Documented gap, see ADR-016.
- [x] Multi-device concurrent automation: `PluginManager` lifecycle methods accept an
      optional `device_id`, running the same automation as independent concurrent
      instances. **Validated with integration tests** (two concurrent instances,
      independent state, fault isolation); only one physical device was available for
      a true two-device live demo. See ADR-017.
- [x] Web UI: capture-provider selector, live Performance panel, device-scoped
      automation status.

## Emulator Manager Module

Goal: let a user choose an Android Emulator instance instead of (or alongside) a
physical device, with manufacturer/device profiles and performance presets fully
data-driven, and an architecture open to future emulator backends.

- [x] `ugaf.emulator.sdk_locator.AndroidSdkLocator` — finds the SDK from
      `ANDROID_HOME`/`ANDROID_SDK_ROOT`/default install paths, never a hardcoded path
      — **validated live** against this machine's real SDK, including correctly
      preferring the SDK's own `adb` over a second copy on `PATH`.
- [x] `ugaf.emulator.hardware.HardwareDetector` — CPU/RAM/acceleration detection and
      performance-preset recommendation — **validated live** (16 CPUs, ~31GB RAM, WHPX
      usable, correctly recommended "gaming").
- [x] `ugaf.emulator.profiles.DeviceProfileManager`/`performance.PerformanceProfileManager`
      — full manufacturer/device library and performance presets, entirely
      YAML-driven (`config/manufacturers.yaml`/`config/performance_profiles.yaml`).
- [x] `ugaf.emulator.android_versions.AndroidVersionManager` — live system-image
      detection/install via `sdkmanager` — **validated live**; caught and fixed a real
      parsing bug (duplicate catalog entries) against this machine's actual
      `sdkmanager --list` output.
- [x] `ugaf.emulator.providers.android_studio.AndroidStudioProvider` +
      `ugaf.emulator.manager.EmulatorManager` — full AVD lifecycle (create/start/stop/
      list/delete/clone/rename/update-hardware/is-running/crash-detection/boot-wait/
      install-apk/push/pull) — **validated live**: real create → start → is_running →
      stop → delete cycle against this machine's real SDK; this machine's real broken
      AVDs (bad config, missing system image) are surfaced with error reasons, not
      hidden or crashed on.
- [x] Web UI: "Connection Type" radio (Physical Device / Android Emulator) with a full
      Android Emulator panel — **validated live in the browser preview** against real
      manufacturer/device/version/AVD data.
- [~] Boot-completion wait past the default 180s timeout on this machine when using
      software rendering on a cold boot — a real host/driver characteristic
      (`gfxstream` graphics backend init stalling), not a polling-logic bug; documented
      with a config knob to raise the timeout. See ADR-018.

## After this milestone

Prioritized order (see `PROJECT_STATUS.md` for detail on each):

1. Live-validate `ScrcpyFrameProvider` against a real scrcpy server once one becomes
   available in this environment (the Android SDK/emulator itself is now available —
   see the Emulator Manager Module above — but the separate `scrcpy` binary and the
   `pywin32`/`mss`/`av` optional dependencies still have no compatible wheel for the
   Python 3.14 interpreter used here). The code and unit tests are ready; only
   environment access is missing.
2. Visual automation recorder (design only so far — see `ARCHITECTURE.md`'s "Future:
   automation recorder" section): record tap/swipe/type actions through the web UI
   into an editable `strategies/*.yaml`, so a new automation can be built by
   demonstration instead of writing YAML by hand.
3. Wire vision-derived facts (health/shadow-meter percentage, enemy proximity) into
   `StrategyEngine` conditions for `games/shadow_fight_3` — the primitives exist
   (`measure_bar_fill`), but need calibration screenshots of the game actually running
   to identify real bar regions/colours and template images.
4. A second app-backed automation (e.g. Calculator or Chrome) to prove
   `ApplicationManager`/`app.yaml` generalize beyond Shadow Fight 3 in practice, not
   just in design.
5. A dedicated "all device instances at a glance" dashboard view (today the web UI
   shows one selected device's automation status at a time — functionally complete,
   but a multi-instance overview would be a nicer UX for many concurrent devices).
6. Accessibility Service / UIAutomator2 evaluation for more reliable interaction than
   raw `adb shell input`
7. Wireless ADB
8. Telemetry
9. Packaging (versioned releases, lockfile)
10. A UI for editing `knowledge/`/`strategies/` YAML without a text editor — not
    started; the file format is stable enough now that this is a pure UI exercise
    (would likely build on the recorder's "save as automation" flow above).

Not planned until a concrete need appears: OCR, AI planning/vision/reasoning,
distributed execution, device farms. See the philosophy note in
`prompts/MASTER_PROMPT.md`.
