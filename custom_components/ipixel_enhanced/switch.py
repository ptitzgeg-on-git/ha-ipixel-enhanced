"""Switch platform for iPIXEL Color."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .api import iPIXELAPI, iPIXELConnectionError
from .const import DOMAIN, CONF_ADDRESS, CONF_NAME
from .common import trigger_auto_update, build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the iPIXEL Color switch."""
    address = entry.data[CONF_ADDRESS]
    name = entry.data[CONF_NAME]
    
    api = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        iPIXELSwitch(api, entry, address, name),
        iPIXELAntialiasingSwitch(api, entry, address, name),
        iPIXELAutoUpdateSwitch(api, entry, address, name),
        iPIXELClock24HSwitch(hass, api, entry, address, name),
        iPIXELClockShowDateSwitch(hass, api, entry, address, name),
        iPIXELFunModeSwitch(api, entry, address, name),
    ])


class iPIXELSwitch(SwitchEntity):
    """Representation of an iPIXEL Color switch (panel power)."""

    _attr_has_entity_name = True

    def __init__(
        self, 
        api: iPIXELAPI, 
        entry: ConfigEntry, 
        address: str, 
        name: str
    ) -> None:
        """Initialize the switch."""
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Power"
        self._attr_unique_id = f"{address}_power"
        self._is_on = False

        self._attr_device_info = build_device_info(api, address, name)

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        try:
            if not self._api.is_connected:
                _LOGGER.debug("Reconnecting to device before turning on")
                await self._api.connect()
            
            success = await self._api.set_power(True)
            if success:
                self._is_on = True
                _LOGGER.debug("Successfully turned on iPIXEL display")
            else:
                _LOGGER.error("Failed to turn on iPIXEL display")
                
        except iPIXELConnectionError as err:
            _LOGGER.error("Connection error while turning on: %s", err)
            # Don't set unavailable to allow retry
        except Exception as err:
            _LOGGER.error("Unexpected error while turning on: %s", err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        try:
            if not self._api.is_connected:
                _LOGGER.debug("Reconnecting to device before turning off")
                await self._api.connect()
            
            success = await self._api.set_power(False)
            if success:
                self._is_on = False
                _LOGGER.debug("Successfully turned off iPIXEL display")
            else:
                _LOGGER.error("Failed to turn off iPIXEL display")
                
        except iPIXELConnectionError as err:
            _LOGGER.error("Connection error while turning off: %s", err)
            # Don't set unavailable to allow retry
        except Exception as err:
            _LOGGER.error("Unexpected error while turning off: %s", err)

    async def async_update(self) -> None:
        """Sync the cached power state from the API when connected."""
        if self._api.is_connected:
            self._is_on = self._api.power_state


class iPIXELAntialiasingSwitch(SwitchEntity, RestoreEntity):
    """Representation of an iPIXEL Color antialiasing setting."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:vector-selection"

    def __init__(
        self, 
        api: iPIXELAPI, 
        entry: ConfigEntry, 
        address: str, 
        name: str
    ) -> None:
        """Initialize the antialiasing switch."""
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Antialiasing"
        self._attr_unique_id = f"{address}_antialiasing"
        self._is_on = True  # Default to antialiasing enabled

        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
            _LOGGER.debug("Restored antialiasing state: %s", self._is_on)

    @property
    def is_on(self) -> bool:
        """Return True if antialiasing is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable antialiasing."""
        self._is_on = True
        _LOGGER.debug("Antialiasing enabled")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable antialiasing."""
        self._is_on = False
        _LOGGER.debug("Antialiasing disabled")


class iPIXELAutoUpdateSwitch(SwitchEntity, RestoreEntity):
    """Representation of an iPIXEL Color auto-update setting."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:auto-fix"

    def __init__(
        self, 
        api: iPIXELAPI, 
        entry: ConfigEntry, 
        address: str, 
        name: str
    ) -> None:
        """Initialize the auto-update switch."""
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Auto Update"
        self._attr_unique_id = f"{address}_auto_update"
        self._is_on = False  # Default to manual updates only

        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
            _LOGGER.debug("Restored auto-update state: %s", self._is_on)

    @property
    def is_on(self) -> bool:
        """Return True if auto-update is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable auto-update."""
        self._is_on = True
        _LOGGER.debug("Auto-update enabled - display will update automatically on changes")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable auto-update."""
        self._is_on = False
        _LOGGER.debug("Auto-update disabled - use update button for manual updates")


class iPIXELFunModeSwitch(SwitchEntity):
    """Enable the panel's DIY/draw mode.

    Turning this on clears the screen to a blank canvas; you then light pixels
    with the ipixel_enhanced.set_pixel service. (This is the device's 'fun'/DIY
    drawing mode — a black screen when enabled is expected.)
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:draw"

    def __init__(self, api: iPIXELAPI, entry: ConfigEntry, address: str, name: str) -> None:
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "DIY Draw Mode"
        self._attr_unique_id = f"{address}_fun_mode"
        self._attr_device_info = build_device_info(api, address, name)

    @property
    def is_on(self) -> bool:
        return self._api.fun_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._api.is_connected:
            await self._api.connect()
        await self._api.set_fun_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self._api.is_connected:
            await self._api.connect()
        await self._api.set_fun_mode(False)


class iPIXELClock24HSwitch(SwitchEntity, RestoreEntity):
    """Representation of an iPIXEL Color clock 24h format setting."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(
        self,
        hass: HomeAssistant,
        api: iPIXELAPI,
        entry: ConfigEntry,
        address: str,
        name: str
    ) -> None:
        """Initialize the clock 24h switch."""
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Clock 24h"
        self._attr_unique_id = f"{address}_clock_24h"
        self._is_on = True  # Default to 24h format

        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
            _LOGGER.debug("Restored clock 24h state: %s", self._is_on)

    @property
    def is_on(self) -> bool:
        """Return True if 24h format is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable 24h format."""
        self._is_on = True
        _LOGGER.debug("Clock 24h format enabled")
        await trigger_auto_update(self.hass, self._address, self._name, self._api, only_modes=("clock",))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable 24h format (use 12h)."""
        self._is_on = False
        _LOGGER.debug("Clock 12h format enabled")
        await trigger_auto_update(self.hass, self._address, self._name, self._api, only_modes=("clock",))


class iPIXELClockShowDateSwitch(SwitchEntity, RestoreEntity):
    """Representation of an iPIXEL Color clock show date setting."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        hass: HomeAssistant,
        api: iPIXELAPI,
        entry: ConfigEntry,
        address: str,
        name: str
    ) -> None:
        """Initialize the clock show date switch."""
        self.hass = hass
        self._api = api
        self._entry = entry
        self._address = address
        self._name = name
        self._attr_name = "Clock Show Date"
        self._attr_unique_id = f"{address}_clock_show_date"
        self._is_on = True  # Default to showing date

        self._attr_device_info = build_device_info(api, address, name)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore last state if available
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
            _LOGGER.debug("Restored clock show date state: %s", self._is_on)

    @property
    def is_on(self) -> bool:
        """Return True if show date is enabled."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable showing date."""
        self._is_on = True
        _LOGGER.debug("Clock show date enabled")
        await trigger_auto_update(self.hass, self._address, self._name, self._api, only_modes=("clock",))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable showing date."""
        self._is_on = False
        _LOGGER.debug("Clock show date disabled")
        await trigger_auto_update(self.hass, self._address, self._name, self._api, only_modes=("clock",))