# Known Limitations

## Configuration

- **No config schema**. `Config.load()` does not validate the shape or
  types of configuration values beyond requiring the top-level YAML node
  to be a mapping. Invalid keys or wrong types are silently accepted.
- **No config file watching**. Changes to YAML files after `Config()`
  construction are not picked up at runtime.
- **Environment variable override only supports dotted-flat keys**. Nested
  keys like `database.pool.size` require the env var `UGAF_DATABASE_POOL_SIZE`;
  there is no way to override a sub-tree with a single variable.
- **`Config.get()` returns `None` for missing dotted paths deeper than one
  level** — partial mid-level lookups may silently return `None` without
  warning.

## Plugin System

As of Milestone 1 of the architecture hardening pass, `ugaf.plugins`/`ugaf.sdk` (the Game SDK) is
the framework's only plugin system — the previously-coexisting legacy loader
(`ugaf/core/plugin_loader.py`, `ugaf/core/plugin.py`) has been removed. See
`PLUGIN_ARCHITECTURE.md` for the current design.

- **No hot-reload**. Plugins must be discovered at startup; adding,
  removing, or modifying plugin directories at runtime is not detected.
- **No dependency ordering between plugins**. `priority` controls start/stop order but there is no
  mechanism to declare "plugin A requires plugin B".
- **No process isolation**. Plugins share the same Python process and global
  interpreter state. A crashing plugin task running outside its lifecycle methods
  (e.g. a background `asyncio.Task` it spawns itself) can affect the whole
  application; lifecycle-method exceptions are caught and converted to `plugin.failed`
  events, but that only covers `initialize`/`start`/`pause`/`resume`/`stop`.
- **Manifest and in-code metadata are not kept in sync automatically**. `manifest.yaml` and the
  `metadata` object inside `plugin.py` are independent — nothing currently detects if they drift
  apart (this project's own `games/example_game/` shipped with a `capabilities` mismatch between
  the two before it was caught and fixed manually during Milestone 1).
- **Plugin discovery failures (bad manifest, missing `GamePlugin` subclass, import error) are
  logged and the plugin is skipped** rather than raising — this means a broken plugin does not
  prevent other plugins from loading, but also means a typo in a manifest can silently produce
  "0 plugins discovered" with no obvious error unless log output is inspected.

## Event Bus

- **No subscriber timeout**. A slow or hanging handler blocks all
  subsequent handlers for the same event topic.
- **No handler ordering**. When multiple handlers subscribe to the same
  topic, their execution order is undefined.
- **No event history/replay**. Past events cannot be replayed to
  late-joining subscribers.
- **No backpressure or rate limiting**. High-frequency publishers can
  overwhelm subscribers.

## Logging

- **No structured log shipping**. Structlog output goes to console and/or
  file; there is no built-in integration with log aggregators (ELK,
  Datadog, Grafana Loki).
- **No log sampling**. High-volume events cannot be sampled or throttled.
- **Logger configuration is read-once**. `configure_logger()` is designed
  to be called once at startup. Calling it again has undefined behavior.

## Platform

- **Windows signal handling is limited**. `loop.add_signal_handler` is
  partially supported on Windows. The `SIGINT`/`SIGTERM` fallback may not
  work in all Windows environments.
- **Python >= 3.13 only**. The project targets Python 3.13+ (using
  `X | Y` type union syntax and `Path.read_text`/`write_text` patterns).
  It will not install on older Python versions.
- **Alpha maturity**. This is an alpha release. APIs may change without
  notice. Not recommended for production workloads.
