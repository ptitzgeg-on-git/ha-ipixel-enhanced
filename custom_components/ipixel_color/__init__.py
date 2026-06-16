"""The iPIXEL Color integration."""
from __future__ import annotations
import logging
from pathlib import Path
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from .api import iPIXELAPI, iPIXELConnectionError, iPIXELTimeoutError
from .const import DOMAIN, CONF_ADDRESS, CONF_NAME
from .pages import PageStore, PlaylistRunner
from . import web as ipixel_web

STORE_DATA = f"{DOMAIN}_store"
RUNNER_DATA = f"{DOMAIN}_runner"
GLOBAL_DATA = f"{DOMAIN}_global_setup"
PANEL_DATA = f"{DOMAIN}_panel"
STATIC_URL = "/ipixel_color_static"
CARD_URL = f"{STATIC_URL}/ipixel-card.js"
PANEL_URL = f"{STATIC_URL}/ipixel-panel.js"

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH, Platform.TEXT, Platform.SENSOR,
    Platform.SELECT, Platform.NUMBER, Platform.BUTTON, Platform.LIGHT
]

SERVICE_SHOW_PAGE = "show_page"
SHOW_PAGE_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("name"): str,
    vol.Optional("page"): dict,
})

SERVICE_SHOW_TEXT = "show_text"
SHOW_TEXT_SCHEMA = vol.Schema({
    vol.Required("text"): str,
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("color", default="ffffff"): str,
    vol.Optional("bg_color", default="000000"): vol.Any(None, str),
    vol.Optional("animation", default=1): vol.All(int, vol.Range(min=0, max=10)),
    vol.Optional("speed", default=60): vol.All(int, vol.Range(min=0, max=100)),
    vol.Optional("rainbow", default=0): vol.All(int, vol.Range(min=0, max=3)),
})

SERVICE_SHOW_EMOJI = "show_emoji"
SHOW_EMOJI_SCHEMA = vol.Schema({
    vol.Required("emoji"): vol.All(str, vol.Length(min=1)),
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("bg_color"): vol.All([vol.All(int, vol.Range(min=0, max=255))], vol.Length(min=3, max=3)),
    vol.Optional("width"): vol.All(int, vol.Range(min=1, max=512)),
    vol.Optional("height"): vol.All(int, vol.Range(min=1, max=512)),
})


def _resolve_api(hass: HomeAssistant, call: ServiceCall) -> iPIXELAPI:
    apis: dict[str, iPIXELAPI] = hass.data.get(DOMAIN, {})
    if not apis:
        raise HomeAssistantError("No iPIXEL devices are configured")
    raw = call.data.get("device_id")
    if not raw:
        target = getattr(call, "target", None) or {}
        raw = target.get("device_id") if isinstance(target, dict) else None
    target_device_ids = [raw] if isinstance(raw, str) else (raw or [])
    if not target_device_ids:
        if len(apis) == 1:
            return next(iter(apis.values()))
        raise HomeAssistantError("Multiple iPIXEL devices configured — specify a device_id")
    device_reg = dr.async_get(hass)
    for device_id in target_device_ids:
        device = device_reg.async_get(device_id)
        if not device:
            continue
        for entry_id in device.config_entries:
            if entry_id in apis:
                return apis[entry_id]
    raise HomeAssistantError(f"No iPIXEL device matched {target_device_ids}")


async def _handle_show_text(hass: HomeAssistant, call: ServiceCall) -> None:
    api = _resolve_api(hass, call)
    bg = call.data.get("bg_color", "000000") or "000000"
    await api.display_text_pypixelcolor(
        text=call.data["text"],
        color=call.data.get("color", "ffffff"),
        bg_color=bg if bg != "000000" else None,
        animation=call.data.get("animation", 1),
        speed=call.data.get("speed", 60),
        rainbow_mode=call.data.get("rainbow", 0),
    )


async def _handle_show_emoji(hass: HomeAssistant, call: ServiceCall) -> None:
    api = _resolve_api(hass, call)
    emoji = call.data["emoji"]
    bg_rgb = call.data.get("bg_color")
    bg_color = "{:02x}{:02x}{:02x}".format(*bg_rgb) if bg_rgb else "000000"
    await api.display_emoji(
        emoji,
        bg_color=bg_color,
        width_override=call.data.get("width"),
        height_override=call.data.get("height")
    )


async def _handle_show_page(hass: HomeAssistant, call: ServiceCall) -> None:
    api = _resolve_api(hass, call)
    page = call.data.get("page")
    if page is None:
        store: PageStore | None = hass.data.get(STORE_DATA)
        name = call.data.get("name")
        if not store or not name or name not in store.pages:
            raise HomeAssistantError(f"Unknown page '{name}' — save it in the iPIXEL card first")
        page = store.pages[name]
    await api.display_widgets(page)


async def _async_global_setup(hass: HomeAssistant) -> None:
    """One-time setup shared by all config entries: store, runner, web, card."""
    if hass.data.get(GLOBAL_DATA):
        return
    hass.data[GLOBAL_DATA] = True

    store = PageStore(hass)
    await store.async_load()
    hass.data[STORE_DATA] = store
    hass.data[RUNNER_DATA] = PlaylistRunner(hass, store)

    ipixel_web.async_register(hass)

    # Serve the whole www/ dir, auto-load the card, and register a sidebar panel
    # so the designer is discoverable without manually adding a Lovelace card.
    try:
        from homeassistant.components.http import StaticPathConfig
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components import panel_custom

        www_dir = Path(__file__).parent / "www"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(www_dir), True)]
        )
        add_extra_js_url(hass, CARD_URL)

        if not hass.data.get(PANEL_DATA):
            await panel_custom.async_register_panel(
                hass,
                webcomponent_name="ipixel-panel",
                frontend_url_path="ipixel",
                module_url=PANEL_URL,
                sidebar_title="iPIXEL",
                sidebar_icon="mdi:dots-grid",
                require_admin=False,
                embed_iframe=False,
            )
            hass.data[PANEL_DATA] = True
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not auto-register the iPIXEL UI: %s", err)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Component-level setup: register the designer card, preview view and
    page store once — independent of whether any display is reachable."""
    await _async_global_setup(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    name = entry.data[CONF_NAME]
    _LOGGER.debug("Setting up iPIXEL Color for %s (%s)", name, address)
    api = iPIXELAPI(hass, address, entry)
    try:
        if not await api.connect():
            raise ConfigEntryNotReady(f"Failed to connect to iPIXEL device at {address}")
        _LOGGER.info("Successfully connected to iPIXEL device %s", address)
        await api.get_device_info()
    except iPIXELTimeoutError as err:
        raise ConfigEntryNotReady(f"Connection timeout: {err}") from err
    except iPIXELConnectionError as err:
        raise ConfigEntryNotReady(f"Connection failed: {err}") from err
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = api
    entry.runtime_data = api
    await _async_global_setup(hass)  # idempotent; ensures setup if async_setup was skipped
    # Warm the font cache in an executor so the font select entity doesn't
    # scan the fonts directory (blocking glob/rglob) inside the event loop.
    from .fonts import get_available_fonts
    await hass.async_add_executor_job(get_available_fonts)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_TEXT):
        async def _show_text_service(call: ServiceCall) -> None:
            await _handle_show_text(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_SHOW_TEXT, _show_text_service, schema=SHOW_TEXT_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_EMOJI):
        async def _show_emoji_service(call: ServiceCall) -> None:
            await _handle_show_emoji(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_SHOW_EMOJI, _show_emoji_service, schema=SHOW_EMOJI_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_PAGE):
        async def _show_page_service(call: ServiceCall) -> None:
            await _handle_show_page(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_SHOW_PAGE, _show_page_service, schema=SHOW_PAGE_SCHEMA)

    # Reload the entry when its options (e.g. panel dimensions) change.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Start the playlist loop now that an API is available.
    runner: PlaylistRunner | None = hass.data.get(RUNNER_DATA)
    if runner:
        runner.restart()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading iPIXEL Color integration")
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        api: iPIXELAPI = hass.data[DOMAIN].pop(entry.entry_id)
        try:
            await api.disconnect()
        except Exception as err:
            _LOGGER.error("Error disconnecting: %s", err)
        # No devices left -> stop the playlist loop.
        remaining = [v for v in hass.data.get(DOMAIN, {}).values() if hasattr(v, "display_widgets")]
        runner: PlaylistRunner | None = hass.data.get(RUNNER_DATA)
        if runner and not remaining:
            runner.stop()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)