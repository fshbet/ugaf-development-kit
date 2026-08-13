# UGAF — Universal Game Automation Framework

> A plugin-based automation framework for Android games and apps, driven from your desktop.

**Status:** Alpha (`v1.0.0a5`) · 11 commits · CI configured · 81 test files · 34 design docs
**Stack:** Python 3.13 · FastAPI web console · ADB transport · OpenCV vision · structlog

---

## What it does

UGAF automates Android games and apps from a Windows/Linux/macOS desktop. Android is the
primary target and ADB is the current transport. Automations are written as **plugins**,
and behaviour lives in data files rather than hardcoded Python, so a plugin's moves, button
positions, and strategy can be edited without touching code.

The layered pipeline: **device → capture → vision → strategy → input**, with a plugin
lifecycle and event bus tying it together.

## Two ways to drive it

**Web control panel** — no coding required:

```bash
pip install -e ".[dev,input,imaging,vision,webapp]"
python -m ugaf.webapp --port 8420
```

Open <http://127.0.0.1:8420> to detect connected devices, watch the live screen, click to
tap, drag to swipe, send text, and run automations. Notable capabilities:

- **Capture providers** — switch the frame source between ADB `screencap` (default) and
  direct window capture for emulators running as Windows windows.
- **Multi-device** — several connected devices can run the same automation concurrently,
  each with its own scoped Start/Stop/status.
- **Emulator management** — pick a manufacturer/device profile and a performance preset,
  then create, start, stop, or delete an AVD from the browser. Requires a local Android SDK.
- **Performance panel** — live capture FPS/latency and input latency for either transport.

**Command line:**

```bash
python -m ugaf.core.cli --games-dir games plugins   # list discovered plugins
python -m ugaf.core.cli --games-dir games health    # health check
```

The bundled demo plugin runs against safe mock/replay defaults — no real device needed.

## Writing a plugin

A plugin lives in `games/<your_id>/` with a `manifest.yaml` and a `plugin.py` exposing a
`metadata` object and a `GamePlugin` subclass. Start from `templates/`.

| Example | Shows |
|---|---|
| `games/example_game/` | Minimal reference — just the `GamePlugin` lifecycle |
| `games/demo_workflow/` | Capture → find template → tap → swipe → type |
| `games/shadow_fight_3/` | Full data-driven automation via `KnowledgeBase` + `StrategyEngine` + `Executor` |

For behaviour that should be editable without touching Python, build on `ugaf.automation`
rather than hardcoding logic in `plugin.py`.

## Layout

```
ugaf/         Framework — core, input, vision, sdk, webapp, automation, emulator, plugins
games/        Automation plugins (demo, example, shadow_fight_3)
templates/    Starting points for new plugins
tests/        81 test files
docs/         Additional documentation
config/       Configuration files
examples/     Usage examples
prompts/      LLM prompt templates
```

Design documentation is unusually thorough — 34 top-level markdown files including
`ARCHITECTURE.md`, `ARCHITECTURE_DECISIONS.md` (ADRs), `PLUGIN_ARCHITECTURE.md`,
`VISION_ENGINE.md`, `INPUT_ENGINE.md`, `GAME_PLUGIN_SDK.md`, and `TESTING_GUIDE.md`.

## Codebase

| Metric | Value |
|---|---|
| Total tokens | **317,541** |
| Source code | 237,344 (Python 217,289 · JavaScript 9,291 · CSS 5,856 · HTML 2,985 · PowerShell 1,923) |
| Tests | 94,783 tokens across 81 files |
| Documentation | 74,116 tokens across 51 files |
| Files / lines | 272 files · 36,724 lines |

Documentation is 23% of the codebase by tokens — the highest ratio in this collection.
Measured with `cl100k_base`, excluding dependencies and build output.

## Development

```bash
pytest                    # test suite
ruff check . && mypy ugaf # lint and type check
```

Requires Python 3.13+. Optional extras: `input`, `imaging`, `vision`, `webapp`, `emulator`.
