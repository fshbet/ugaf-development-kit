# Changelog

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
