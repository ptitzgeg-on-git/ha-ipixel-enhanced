# Changelog

All notable changes to **iPIXEL Enhanced** are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.7.1] — 2026-06-18

### Added
- **Brand icon** bundled under `brand/` (Brands Proxy API), so the integration
  shows its logo in HACS and the Home Assistant integrations UI.
- **GPL-3.0 `LICENSE`** (this is a derivative of `ha-ipixel-color`, GPL-3.0),
  with copyright attribution, plus an expanded credits section and the project
  logo / product photos in the README.

## [0.7.0] — 2026-06-18

### Added
- **Per-device playlists.** Each panel now runs its own playlist on its own
  self-scheduling loop. Starting a playlist on one panel no longer stops
  another.
- **Multi-panel targeting.** A single playlist can play on several panels at
  once — pick targets in the card (multi-select with live "running" badges) or
  pass a list of `device_id`s to `start_playlist` / `stop_playlist`.
- **Per-panel `Playlist` select entity** (`select.<panel>_playlist`) to drive
  each display straight from automations.
- Responsive, full-height sidebar panel (mobile / narrow aware).
- GPL-3.0 `LICENSE`, project logo, and product photos in the README.

### Changed
- Saving a running playlist now re-applies the edits live to the panels playing
  it, without touching the others.
- `set_playlist` is now a **stop-only legacy shim** — use `start_playlist` with
  a name to start a playlist.

### Internal
- `PageStore` tracks `runs` (`{entry_id: playlist}`) as the source of truth;
  `PlaylistRunner` keeps one loop per panel; added `resolve_targets()` plus
  migration of pre-0.7 saved data.
- Folded in the accumulated Studio work since 0.3.0 (tabbed designer, widget
  renderer, draw grid, device slots) and added an offline `pytest` suite.

## [0.3.0]

- Tabbed **iPIXEL Studio**: Designer / Draw / Playlist / Slots / Device.
- Visual page designer with live 32×32 preview, sidebar panel, native clock and
  entity cleanup.

[0.7.1]: https://github.com/ptitzgeg-on-git/ha-ipixel-enhanced/releases/tag/v0.7.1
[0.7.0]: https://github.com/ptitzgeg-on-git/ha-ipixel-enhanced/releases/tag/v0.7.0
[0.3.0]: https://github.com/ptitzgeg-on-git/ha-ipixel-enhanced/releases/tag/0.3.0
