"""Persistent page library + playlist runner for iPIXEL Enhanced.

A *page library* is a named collection of page definitions the user builds in
the Lovelace card. A *playlist* rotates through chosen pages on a timer and
pushes each one to a device, so a non-technical user can say "show weather for
10s, then the clock for 5s" entirely from the UI.

Playlists are *per device*: each panel runs its own active playlist on its own
loop, so two panels never fight over a single timer. The mapping of which
playlist plays on which panel lives in ``PageStore.runs`` (``{entry_id: name}``),
and a single playlist can be started on several panels at once.
"""
from __future__ import annotations

import logging
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}_pages"
MIN_DURATION = 2

# Fired whenever the page/playlist library changes, so the Page / Playlist
# select entities can refresh their options live.
SIGNAL_LIBRARY_UPDATED = f"{DOMAIN}_library_updated"


def device_api_entry_ids(hass: HomeAssistant) -> list[str]:
    """Config-entry ids that have a connected iPIXEL API (i.e. real panels)."""
    return [
        k for k, v in hass.data.get(DOMAIN, {}).items()
        if hasattr(v, "display_widgets")
    ]


def resolve_targets(hass: HomeAssistant, raw: Any) -> list[str]:
    """Normalise a raw target spec to a list of config-entry ids.

    ``raw`` may be ``None``, an entry_id, a device_id, or a list mixing the two
    (the card and services hand us device_ids; the select entity hands us
    entry_ids). Anything that can't be mapped to a live panel is dropped.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    valid = set(device_api_entry_ids(hass))
    out: list[str] = []
    reg = None
    for target in raw:
        if not target:
            continue
        if target in valid:
            if target not in out:
                out.append(target)
            continue
        if reg is None:
            from homeassistant.helpers import device_registry as dr
            reg = dr.async_get(hass)
        device = reg.async_get(target)
        if device:
            for entry_id in device.config_entries:
                if entry_id in valid and entry_id not in out:
                    out.append(entry_id)
    return out


class PageStore:
    """Loads/saves the page library and per-device playlist state from disk."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store = Store(hass, STORE_VERSION, STORE_KEY)
        self.pages: dict[str, dict] = {}
        # Named playlist library: {name: {"items": [...], "targets": [id,...]}}.
        # "targets" are the *default* panels offered when starting from the UI.
        self.playlists: dict[str, dict] = {}
        # What is playing where: {entry_id: playlist_name}. Source of truth for
        # the runner and the per-device select entity.
        self.runs: dict[str, str] = {}
        # Which device-memory slot each library page is stored in: {name: int}.
        # The panel can't be queried for its slot contents, so we track the
        # mapping here (persisted) — that's the source of truth for the UI.
        self.slots: dict[str, int] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self.pages = data.get("pages", {}) or {}
            self.playlists = data.get("playlists", {}) or {}
            self.runs = {str(k): str(v) for k, v in (data.get("runs", {}) or {}).items()}
            self.slots = {k: int(v) for k, v in (data.get("slots", {}) or {}).items()}

        # Normalise every named playlist to the {items, targets} shape, folding
        # in the legacy single "target" string.
        for name, pl in self.playlists.items():
            pl.setdefault("items", [])
            if "targets" not in pl:
                legacy = pl.pop("target", None)
                pl["targets"] = [legacy] if legacy else []

        # Migration from the old single-playlist model.
        legacy_pl = (data or {}).get("playlist") if data else None
        if not self.playlists and legacy_pl and legacy_pl.get("items"):
            self.playlists = {"Default": {
                "items": list(legacy_pl["items"]),
                "targets": [legacy_pl["target"]] if legacy_pl.get("target") else [],
            }}
        if not self.runs and legacy_pl and legacy_pl.get("enabled"):
            active = (data or {}).get("active") or "Default"
            target = legacy_pl.get("target")
            if active in self.playlists and target:
                # Best-effort: a device_id is resolved here; an entry_id passes
                # through. If the old target was None we can't know the panel,
                # so the user simply re-starts the playlist once.
                for entry_id in resolve_targets(self._hass, target):
                    self.runs[entry_id] = active

    async def async_save(self) -> None:
        await self._store.async_save({
            "pages": self.pages,
            "playlists": self.playlists,
            "runs": self.runs,
            "slots": self.slots,
        })
        # Let the Page / Playlist select entities pick up the new contents.
        async_dispatcher_send(self._hass, SIGNAL_LIBRARY_UPDATED)

    async def save_page(self, name: str, page: dict) -> None:
        self.pages[name] = page
        await self.async_save()

    async def delete_page(self, name: str) -> None:
        self.pages.pop(name, None)
        self.slots.pop(name, None)
        # drop it from every named playlist
        for pl in self.playlists.values():
            pl["items"] = [it for it in pl.get("items", []) if it.get("name") != name]
        await self.async_save()

    async def set_slot(self, name: str, slot: int | None) -> None:
        """Assign a library page to a device slot (or clear it with slot=None)."""
        if slot is None:
            self.slots.pop(name, None)
        else:
            self.slots[name] = int(slot)
        await self.async_save()

    # --- named playlists -------------------------------------------------
    async def save_named_playlist(self, name: str, items: list, targets=None) -> None:
        """Create or update a named playlist and its default target panels."""
        self.playlists[name] = {
            "items": list(items or []),
            "targets": list(targets or []),
        }
        await self.async_save()

    async def delete_named_playlist(self, name: str) -> None:
        self.playlists.pop(name, None)
        # stop it everywhere it was playing
        self.runs = {e: n for e, n in self.runs.items() if n != name}
        await self.async_save()

    async def start_named_playlist(self, name: str, targets: list[str]) -> bool:
        """Play a named playlist on each of ``targets`` (config-entry ids).

        Other panels keep whatever they were already playing.
        """
        if name not in self.playlists or not targets:
            return False
        for entry_id in targets:
            self.runs[entry_id] = name
        await self.async_save()
        return True

    async def stop_playlist(self, target: str | None = None) -> None:
        """Stop the playlist on ``target`` (entry_id), or on every panel."""
        if target is None:
            self.runs.clear()
        else:
            self.runs.pop(target, None)
        await self.async_save()

    def running_on(self, entry_id: str) -> str | None:
        """Name of the playlist currently playing on a panel, or None."""
        return self.runs.get(entry_id)

    def as_dict(self) -> dict:
        return {
            "pages": self.pages,
            "playlists": self.playlists,
            "runs": self.runs,
            "slots": self.slots,
        }


class PlaylistRunner:
    """Self-scheduling loops that push playlist pages to each panel.

    One independent loop per config entry, so two panels rotate their own
    playlists without interfering.
    """

    def __init__(self, hass: HomeAssistant, store: PageStore) -> None:
        self._hass = hass
        self._store = store
        # entry_id -> {"index": int, "cancel": callable | None}
        self._loops: dict[str, dict] = {}

    @callback
    def restart(self) -> None:
        """Reconcile running loops with the store: stop the gone, (re)start the rest."""
        for entry_id in list(self._loops):
            if entry_id not in self._store.runs:
                self._stop_one(entry_id)
        for entry_id in self._store.runs:
            self.restart_one(entry_id)

    @callback
    def restart_one(self, entry_id: str) -> None:
        self._stop_one(entry_id)
        name = self._store.runs.get(entry_id)
        pl = self._store.playlists.get(name) if name else None
        if pl and pl.get("items"):
            self._loops[entry_id] = {"index": 0, "cancel": None}
            self._schedule(entry_id, 0)

    @callback
    def stop(self, entry_id: str | None = None) -> None:
        if entry_id is None:
            for existing in list(self._loops):
                self._stop_one(existing)
        else:
            self._stop_one(entry_id)

    @callback
    def _stop_one(self, entry_id: str) -> None:
        loop = self._loops.pop(entry_id, None)
        if loop and loop.get("cancel"):
            loop["cancel"]()

    @callback
    def _schedule(self, entry_id: str, delay: float) -> None:
        loop = self._loops.get(entry_id)
        if loop is None:
            return
        loop["cancel"] = async_call_later(self._hass, delay, partial(self._tick, entry_id))

    async def _tick(self, entry_id: str, _now=None) -> None:
        loop = self._loops.get(entry_id)
        if loop is None:
            return
        loop["cancel"] = None
        name = self._store.runs.get(entry_id)
        pl = self._store.playlists.get(name) if name else None
        items = pl.get("items", []) if pl else []
        if not items:
            self._stop_one(entry_id)
            return
        if loop["index"] >= len(items):
            loop["index"] = 0
        item = items[loop["index"]]
        page = self._store.pages.get(item.get("name", ""))
        duration = max(MIN_DURATION, int(item.get("duration", 10) or 10))
        if page is not None:
            api = self._resolve_api(entry_id)
            if api is not None:
                try:
                    await api.display_widgets(page)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Playlist render of %s failed: %s", item.get("name"), err)
        loop["index"] += 1
        self._schedule(entry_id, duration)

    def _resolve_api(self, entry_id: str):
        api = self._hass.data.get(DOMAIN, {}).get(entry_id)
        return api if hasattr(api, "display_widgets") else None
