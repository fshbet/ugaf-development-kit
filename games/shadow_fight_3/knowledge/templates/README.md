# Templates

Visual templates for this game belong here (e.g. `fight_button.png`,
`victory.png`, `defeat.png`, `enemy_health.png`, `shadow_bar.png`,
`health_bar.png`, `menu.png`) — never referenced by path from inside
Python; a knowledge/strategy file names the template and the
`VisionManager` loads it.

Empty for now: this plugin was built from a screenshot description and
a control-scheme reference, not a captured device session, so there
are no real template images to calibrate against yet. Add real
captures here (and wire `VisionManager.find_template` /
`wait_until_visible` calls into the plugin) once the game has actually
been run and screenshotted on a connected device — see `ROADMAP.md`.
