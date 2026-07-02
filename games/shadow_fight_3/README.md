# Shadow Fight 3 — knowledge-driven combat plugin

`plugin.py` is deliberately small. It only: connects to the device,
loads this folder's knowledge and strategy, drives the
`ugaf.automation.executor.Executor` loop, and reports status. Every
piece of game-specific behaviour lives in data below, editable without
touching Python:

```
games/shadow_fight_3/
  manifest.yaml          # plugin identity (id, version, capabilities)
  config.yaml             # device connection + which strategy to run
  plugin.py                # thin wiring: connect -> load -> run -> stop
  knowledge/
    moves.yaml             # named move -> action-step sequence + metadata
    buttons.yaml            # named control -> screen position (fractions)
    templates/              # visual templates (button/health-bar images)
  strategies/
    balanced.yaml            # default: mirrors the original hardcoded loop
    aggressive.yaml
    defensive.yaml
  assets/                    # calibration screenshots, non-template assets
```

## Changing behaviour without touching code

- **Add or edit a move**: edit `knowledge/moves.yaml`. A move is an
  ordered list of steps using the executor's generic verbs — `tap:
  <button>`, `move: <direction>`, `hold: {button, duration}`, `wait:
  <seconds>` — plus metadata (`cooldown`, `damage`, `shadow_cost`,
  `range`, `startup`, `recovery`, `priority`, `tags`). No Python
  change needed; `ShadowFight3Game` picks up new moves automatically.
- **Recalibrate a button/joystick position**: edit `knowledge/buttons.yaml`.
  Positions are fractions of screen width/height (0.0-1.0), resolved
  to real pixels from the connected device's detected resolution at
  runtime — the same file works across devices.
- **Change the combat strategy**: edit an existing file under
  `strategies/`, or add a new one and point `config.yaml`'s `strategy:`
  key at it. A strategy is an ordered list of `when -> do` rules
  (`when: always`, or `when: {cycle_mod: N}` — true every Nth cycle);
  the first matching rule's move names run that cycle. See
  `ugaf/automation/strategy.py` for the condition vocabulary and how
  to extend it (e.g. once vision-derived facts like enemy distance or
  health percentage are available).
- **Switch strategies at runtime**: set `strategy: aggressive` (or
  `defensive`, or a custom name) in `config.yaml`, or override via
  `UGAF_STRATEGY=aggressive` (environment variables override any
  dotted config key — see `ugaf.core.config`).

## What's still Python

Only the reusable, game-agnostic pieces: `ugaf.automation.knowledge`
(loads the YAML into typed objects), `ugaf.automation.strategy`
(evaluates rules), and `ugaf.automation.executor` (turns a move's
steps into real `InputManager` calls). None of these three modules
know anything about Shadow Fight 3 specifically — they are shared
infrastructure any future plugin (a different game, a different app)
can reuse by supplying its own `knowledge/`/`strategies/` files.

## Known limitation

Strategy conditions today are cycle-count-based (`cycle_mod`), not
vision-based (e.g. "if enemy is close, do X") — there's no calibrated
template/health-bar data for this game yet (see
`knowledge/templates/README.md`). `VisionManager.measure_bar_fill`,
`wait_until_visible`, and `wait_until_hidden` exist and are ready to
use once real captures are available; wiring vision-derived facts into
strategy `when` conditions is the natural next step (see `ROADMAP.md`).
