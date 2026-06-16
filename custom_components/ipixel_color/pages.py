"""Persistent page library + playlist runner for iPIXEL Enhanced.

A *page library* is a named collection of page definitions the user builds in
the Lovelace card. A *playlist* rotates through chosen pages on a timer and
pushes each one to a device, so a non-technical user can say "show weather for
10s, then the clock for 5s" entirely from the UI.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}_pages"
MIN_DURATION = 2


class PageStore:
    """Loads/saves the page library and playlist config from disk."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store = Store(hass, STORE_VERSION, STORE_KEY)
        self.pages: dict[str, dict] = {}
        self.playlist: dict[str, Any] = {"enabled": False, "items": [], "target": None}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self.pages = data.get("pages", {}) or {}
            self.playlist = data.get("playlist", self.playlist) or self.playlist
            self.playlist.setdefault("enabled", False)
            self.playlist.setdefault("items", [])
            self.playlist.setdefault("target", None)

    async def async_save(self) -> None:
        await self._store.async_save({"pages": self.pages, "playlist": self.playlist})

    async def save_page(self, name: str, page: dict) -> None:
        self.pages[name] = page
        await self.async_save()

    async def delete_page(self, name: str) -> None:
        self.pages.pop(name, None)
        # drop it from the playlist too
        self.playlist["items"] = [
            it for it in self.playlist.get("items", []) if it.get("name") != name
        ]
        await self.async_save()

    async def set_playlist(self, playlist: dict) -> None:
        self.playlist = {
            "enabled": bool(playlist.get("enabled", False)),
            "items": list(playlist.get("items", []) or []),
            "target": playlist.get("target"),
        }
        await self.async_save()

    def as_dict(self) -> dict:
        return {"pages": self.pages, "playlist": self.playlist}


class PlaylistRunner:
    """Self-scheduling loop that pushes playlist pages to a device."""

    def __init__(self, hass: HomeAssistant, store: PageStore) -> None:
        self._hass = hass
        self._store = store
        self._cancel = None
        self._index = 0

    @callback
    def restart(self) -> None:
        self.stop()
        if self._store.playlist.get("enabled") and self._store.playlist.get("items"):
            self._index = 0
            self._schedule(0)

    @callback
    def stop(self) -> None:
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

    @callback
    def _schedule(self, delay: float) -> None:
        self._cancel = async_call_later(self._hass, delay, self._tick)

    async def _tick(self, _now=None) -> None:
        self._cancel = None
        items = self._store.playlist.get("items", [])
        if not self._store.playlist.get("enabled") or not items:
            return
        if self._index >= len(items):
            self._index = 0
        item = items[self._index]
        page = self._store.pages.get(item.get("name", ""))
        duration = max(MIN_DURATION, int(item.get("duration", 10) or 10))
        if page is not None:
            api = self._resolve_target()
            if api is not None:
                try:
                    await api.display_widgets(page)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Playlist render of %s failed: %s", item.get("name"), err)
        self._index += 1
        self._schedule(duration)

    def _resolve_target(self):
        apis = {
            k: v for k, v in self._hass.data.get(DOMAIN, {}).items()
            if hasattr(v, "display_widgets")
        }
        if not apis:
            return None
        target = self._store.playlist.get("target")
        if target:
            if target in apis:  # entry_id
                return apis[target]
            # maybe a device_id -> map to its config entry
            from homeassistant.helpers import device_registry as dr
            device = dr.async_get(self._hass).async_get(target)
            if device:
                for entry_id in device.config_entries:
                    if entry_id in apis:
                        return apis[entry_id]
        return next(iter(apis.values()))
