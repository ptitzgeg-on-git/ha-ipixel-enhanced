"""Select entity for iPIXEL Color font selection."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .api import iPIXELAPI
from .const import DOMAIN, CONF_ADDRESS, CONF_NAME, AVAILABLE_MODES, DEFAULT_MODE
from .common import trigger_auto_update, build_device_info
from .fonts import get_available_fonts
from .pages import SIGNAL_LIBRARY_UPDATED

# Shown in the Playlist / Show Page selects to mean "nothing selected / stop".
NONE_OPTION = "(none)"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iPIXEL Color select entities."""
    address = entry.data[CONF_ADDRESS]
    name = entry.data[CONF_NAME]
    
    api = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        iPIXELFontSelect(hass, api, entry, address, name),
        iPIXELModeSelect(hass, api, entry, address, name),
        iPIXELClockStyleSelect(hass, api, entry, address, name),
        iPIXELOrientationSelect(api, entry, address, name),
        iPIXELPlaylistSelect(hass, api, entry, address, name),
        iPIXELPageSelect(hass, api, entry, address, name),
    ])


class iPIXELPlaylistSelect(SelectEntity):
    """Pick which saved playlist runs on this panel ((none) = stop).

    Options are the playlists you build in the iPIXEL Studio and refresh live.
    Usable from automations (select.select_option) with a real name dropdown,
    instead of typing the name into the start_playlist service.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:playlist-play"

    def __init__(self, hass: HomeAssistant, api: iPIXELAPI, entry: ConfigEntry, address: str, name: str) -> None:
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Playlist"
        self._attr_unique_id = f"{address}_playlist_select"
        self._attr_options = [NONE_OPTION]
        self._attr_current_option = NONE_OPTION
        self._attr_device_info = build_device_info(api, address, name)

    def _store(self):
        return self.hass.data.get(f"{DOMAIN}_store")

    def _runner(self):
        return self.hass.data.get(f"{DOMAIN}_runner")

    @callback
    def _refresh(self) -> None:
        store = self._store()
        if not store:
            return
        self._attr_options = [NONE_OPTION] + sorted(store.playlists)
        active = store.running_on(self._entry.entry_id)
        self._attr_current_option = active if active in store.playlists else NONE_OPTION
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_LIBRARY_UPDATED, self._refresh)
        )
        self._refresh()

    async def async_select_option(self, option: str) -> None:
        store, runner = self._store(), self._runner()
        if not store:
            return
        entry_id = self._entry.entry_id
        if option == NONE_OPTION:
            await store.stop_playlist(entry_id)
            if runner:
                runner.stop(entry_id)
        else:
            if not await store.start_named_playlist(option, [entry_id]):
                _LOGGER.error("Unknown playlist: %s", option)
                return
            if runner:
                runner.restart_one(entry_id)
        self._attr_current_option = option
        self.async_write_ha_state()


class iPIXELPageSelect(SelectEntity):
    """Show a saved page on the panel by picking its name ((none) = no-op).

    Options are the pages saved in the iPIXEL Studio and refresh live, so you
    can recall a saved page from an automation without retyping its name.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:image-multiple"

    def __init__(self, hass: HomeAssistant, api: iPIXELAPI, entry: ConfigEntry, address: str, name: str) -> None:
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Show Page"
        self._attr_unique_id = f"{address}_page_select"
        self._attr_options = [NONE_OPTION]
        self._attr_current_option = NONE_OPTION
        self._attr_device_info = build_device_info(api, address, name)

    def _store(self):
        return self.hass.data.get(f"{DOMAIN}_store")

    @callback
    def _refresh(self) -> None:
        store = self._store()
        if not store:
            return
        options = [NONE_OPTION] + sorted(store.pages)
        self._attr_options = options
        if self._attr_current_option not in options:
            self._attr_current_option = NONE_OPTION
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_LIBRARY_UPDATED, self._refresh)
        )
        self._refresh()

    async def async_select_option(self, option: str) -> None:
        store = self._store()
        if not store or option == NONE_OPTION:
            self._attr_current_option = NONE_OPTION
            self.async_write_ha_state()
            return
        page = store.pages.get(option)
        if page is None:
            _LOGGER.error("Unknown page: %s", option)
            return
        await self._api.display_widgets(page)
        self._attr_current_option = option
        self.async_write_ha_state()


ORIENTATION_OPTIONS = {"0°": 0, "90°": 1, "180°": 2, "270°": 3}


class iPIXELOrientationSelect(SelectEntity, RestoreEntity):
    """Rotate the display (hardware orientation, affects all modes)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:screen-rotation"

    def __init__(self, api: iPIXELAPI, entry: ConfigEntry, address: str, name: str) -> None:
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Orientation"
        self._attr_unique_id = f"{address}_orientation"
        self._attr_options = list(ORIENTATION_OPTIONS.keys())
        self._attr_current_option = "0°"
        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ORIENTATION_OPTIONS:
            self._attr_current_option = last_state.state

    async def async_select_option(self, option: str) -> None:
        if option not in ORIENTATION_OPTIONS:
            return
        if not self._api.is_connected:
            await self._api.connect()
        if await self._api.set_orientation(ORIENTATION_OPTIONS[option]):
            self._attr_current_option = option
            self.async_write_ha_state()


class iPIXELFontSelect(SelectEntity, RestoreEntity):
    """Representation of an iPIXEL Color font selection."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, 
        hass: HomeAssistant,
        api: iPIXELAPI, 
        entry: ConfigEntry, 
        address: str, 
        name: str
    ) -> None:
        """Initialize the font select."""
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Font"
        self._attr_unique_id = f"{address}_font_select"

        # Get available fonts from all locations
        self._attr_options = get_available_fonts()
        self._attr_current_option = "OpenSans-Light.ttf" if "OpenSans-Light.ttf" in self._attr_options else self._attr_options[0]
        
        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            _LOGGER.debug("Restored font selection: %s", self._attr_current_option)

    @property
    def current_option(self) -> str | None:
        """Return the current selected font."""
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Select a font option."""
        if option in self._attr_options:
            self._attr_current_option = option
            _LOGGER.debug("Font changed to: %s", option)
            await trigger_auto_update(self.hass, self._address, self._name, self._api)
        else:
            _LOGGER.error("Invalid font option: %s", option)


class iPIXELModeSelect(SelectEntity, RestoreEntity):
    """Representation of an iPIXEL Color mode selection."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        api: iPIXELAPI,
        entry: ConfigEntry,
        address: str,
        name: str
    ) -> None:
        """Initialize the mode select."""
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Mode"
        self._attr_unique_id = f"{address}_mode_select"

        # Set available mode options
        self._attr_options = AVAILABLE_MODES
        self._attr_current_option = DEFAULT_MODE

        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            _LOGGER.debug("Restored mode selection: %s", self._attr_current_option)

    @property
    def current_option(self) -> str | None:
        """Return the current selected mode."""
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Select a mode option."""
        if option in self._attr_options:
            self._attr_current_option = option
            _LOGGER.info("Mode changed to: %s", option)
            await trigger_auto_update(self.hass, self._address, self._name, self._api)
        else:
            _LOGGER.error("Invalid mode option: %s", option)


class iPIXELClockStyleSelect(SelectEntity, RestoreEntity):
    """Representation of an iPIXEL Color clock style selection."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        hass: HomeAssistant,
        api: iPIXELAPI,
        entry: ConfigEntry,
        address: str,
        name: str
    ) -> None:
        """Initialize the clock style select."""
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Clock Style"
        self._attr_unique_id = f"{address}_clock_style_select"

        # Clock styles 0-8
        self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]
        self._attr_current_option = "1"  # Default style

        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            _LOGGER.debug("Restored clock style selection: %s", self._attr_current_option)

    @property
    def current_option(self) -> str | None:
        """Return the current selected clock style."""
        return self._attr_current_option

    async def async_select_option(self, option: str) -> None:
        """Select a clock style option."""
        if option in self._attr_options:
            self._attr_current_option = option
            _LOGGER.info("Clock style changed to: %s", option)
            await trigger_auto_update(
                self.hass, self._address, self._name, self._api, only_modes=("clock",)
            )
        else:
            _LOGGER.error("Invalid clock style option: %s", option)