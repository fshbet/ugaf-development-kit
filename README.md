# Universal Game Automation Framework (UGAF)

A plugin-based automation framework for Android games and apps, controlled from a
Windows/Linux/macOS desktop. Android is the primary automation target; ADB is the
current transport (see `ARCHITECTURE.md`).

## Quickstart

```bash
pip install -e ".[dev,input,imaging,vision,webapp]"
pytest                    # run the test suite
ruff check . && mypy ugaf # lint + type check
```

### Web control panel (no coding required)

```bash
python -m ugaf.webapp --port 8420
```

Open `http://127.0.0.1:8420` in a browser to detect connected Android devices, view
the live screen, click to tap, drag to swipe, send text, and run automations — all
without touching ADB or writing code. For an automation with a target app (see
`games/shadow_fight_3/app.yaml`), clicking **Start** launches the app itself and waits
for it to reach the foreground before automation begins — no manual app-launching
required. See `ugaf/webapp/` for the FastAPI backend and static frontend.

The toolbar's capture-provider selector switches the screen's frame source between ADB
(`adb exec-out screencap` — the default) and direct window capture for Android
emulators running as Windows windows (`pip install ugaf[emulator]`). The sidebar's
"Performance" panel shows live capture FPS/latency and input latency, whichever
transport is active. Multiple connected devices can each run the same automation
concurrently — selecting a device scopes that automation card's Start/Stop/status to
that device's own instance. See ADR-016/ADR-017 in `ARCHITECTURE_DECISIONS.md`.

The sidebar's "Connection Type" toggle switches between a physical device (the above)
and an **Android Emulator**: pick a manufacturer/device profile (e.g. Samsung Galaxy
S25 Ultra) and a performance preset (Low End/Mid Range/Flagship/Gaming), then
Create/Start/Stop/Delete an AVD directly from the browser — no `avdmanager`/`emulator`
command lines required. Requires a local Android SDK (`ANDROID_HOME`/`ANDROID_SDK_ROOT`
set, or installed at the default Android Studio location); the panel shows a clear
banner instead of failing if no SDK is found. See `ugaf.emulator` and ADR-018 in
`ARCHITECTURE_DECISIONS.md`.

### Command-line

Run the bundled demonstration plugin (capture → find template → tap → swipe → type
text, against safe mock/replay defaults, no real device required):

```bash
python -m ugaf.core.cli --games-dir games plugins   # list discovered plugins
python -m ugaf.core.cli --games-dir games health    # health check, incl. plugin count
```

See `games/demo_workflow/` for the demo plugin itself, `games/example_game/` for a
minimal reference plugin exercising just the `GamePlugin` lifecycle, and
`games/shadow_fight_3/` for a continuously-running plugin built on the data-driven
automation stack described below.

## Writing a plugin

A plugin lives under `games/<your_id>/` with a `manifest.yaml` and a `plugin.py`
exposing a `metadata` object and a `GamePlugin` subclass. See
`templates/manifest.yaml` / `templates/plugin.py` for a starting point, and
`ARCHITECTURE.md` for how the plugin, device, input, and vision layers fit together.

For a plugin whose behaviour should be editable without touching Python (moves,
button positions, combat/workflow strategy), build on `ugaf.automation`
(`KnowledgeBase` + `StrategyEngine` + `Executor`) instead of hardcoding logic in
`plugin.py` — see `games/shadow_fight_3/README.md` for a worked example and
`ARCHITECTURE_DECISIONS.md` ADR-014 for the design rationale.

If a plugin targets a specific installed Android app, add an `app.yaml` (name,
package, launch activity, timeouts, shutdown behaviour) and call
`ugaf.apps.ApplicationManager.launch_and_wait()` at the start of `start()` — see
`games/shadow_fight_3/app.yaml`/`plugin.py` and ADR-015. This gets the app launched
and foreground-verified for free, reusing the same platform capability every
app-backed automation shares.

## Known device-specific quirk: ADB input injection blocked

Some Android builds (MIUI/HyperOS confirmed; possibly others) reject ADB input
injection (tap/swipe/text) with `SecurityException: Injecting input events requires...
INJECT_EVENTS permission` unless an additional Developer Options toggle — **"USB
debugging (Security settings)"**, separate from plain "USB debugging" — is enabled
(may require signing into a device account). If taps/swipes silently have no effect,
check this setting first; the framework now logs this failure (previously silent).

## Status

See `PROJECT_STATUS.md` for the current capability checklist and known limitations,
and `CHANGELOG.md` for what changed recently.
