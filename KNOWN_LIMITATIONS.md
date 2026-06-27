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

- **No hot-reload**. Plugins must be discovered at startup; adding,
  removing, or modifying plugin directories at runtime is not detected.
- **No dependency ordering**. If plugin A depends on plugin B, there is no
  mechanism to guarantee start/stop ordering.
- **No isolation**. Plugins share the same Python process and global
  interpreter state. A crashing plugin can bring down the entire
  application.
- **No plugin lifecycle hooks beyond start/stop**. There is no
  `before_start`, `after_stop`, or `on_error` callback.
- **Plugin config parsing failures are silently swallowed**. When a
  plugin's `config.yaml` is invalid YAML, `_load_config` logs a warning
  and returns an empty dict. The error is not propagated.
- **Module import errors are silently swallowed**. When a plugin's
  `bot.py` (or similar) fails to import, `_import_module` logs an error
  and returns `None` without raising. The plugin is still "loaded" with
  missing modules.

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
