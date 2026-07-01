# 05_PluginLoader

Implement plugin discovery, validation, and lifecycle orchestration for the Game SDK
(`ugaf.plugins.loader.PluginLoader`, `ugaf.plugins.validator.PluginValidator`,
`ugaf.plugins.registry.PluginRegistry`, `ugaf.plugins.lifecycle.PluginLifecycle`,
`ugaf.plugins.manager.PluginManager`). Plugins are discovered from a games directory
(default `games/`) as `<id>/manifest.yaml` + `<id>/plugin.py`, where `plugin.py` exposes a
module-level `metadata: PluginMetadata` and a `ugaf.sdk.game.GamePlugin` subclass. There is no
alternative plugin layout — see `PLUGIN_ARCHITECTURE.md`.

Acceptance Criteria:
- Production ready
- Type hints
- Tests
- Documentation
- No placeholder code
- Discovered plugins are actually driven through the full `GamePlugin` lifecycle
  (`initialize`/`start`/`pause`/`resume`/`stop`/`shutdown`) by `Application`, not merely
  discovered and left inert.
