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

## After Version 0.2

Prioritized order (see `PROJECT_STATUS.md` for detail on each):

1. Visual automation recorder (design only so far — see `ARCHITECTURE.md`'s "Future:
   automation recorder" section): record tap/swipe/type actions through the web UI
   into an editable `strategies/*.yaml`, so a new automation can be built by
   demonstration instead of writing YAML by hand.
2. Wire vision-derived facts (health/shadow-meter percentage, enemy proximity) into
   `StrategyEngine` conditions for `games/shadow_fight_3` — the primitives exist
   (`measure_bar_fill`), but need calibration screenshots of the game actually running
   to identify real bar regions/colours and template images.
3. A second app-backed automation (e.g. Calculator or Chrome) to prove
   `ApplicationManager`/`app.yaml` generalize beyond Shadow Fight 3 in practice, not
   just in design.
4. Accessibility Service / UIAutomator2 evaluation for more reliable interaction than
   raw `adb shell input`
5. Advanced transports (scrcpy for continuous capture, wireless ADB)
6. Telemetry
7. Packaging (versioned releases, lockfile)
8. A UI for editing `knowledge/`/`strategies/` YAML without a text editor — not
   started; the file format is stable enough now that this is a pure UI exercise
   (would likely build on the recorder's "save as automation" flow above).

Not planned until a concrete need appears: OCR, AI planning/vision/reasoning,
distributed execution, device farms. See the philosophy note in
`prompts/MASTER_PROMPT.md`.
