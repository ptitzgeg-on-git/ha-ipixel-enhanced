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
from .pages import (
    PageStore,
    PlaylistRunner,
    device_api_entry_ids,
    resolve_targets,
)
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
    vol.Optional("save_slot", default=0): vol.All(int, vol.Range(min=0, max=255)),
})

SERVICE_SET_ORIENTATION = "set_orientation"
SET_ORIENTATION_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("orientation"): vol.All(int, vol.Range(min=0, max=3)),
})

SERVICE_SET_FUN_MODE = "set_fun_mode"
SET_FUN_MODE_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("enable"): vol.Boolean(),
})

SERVICE_SHOW_IMAGE = "show_image"
SHOW_IMAGE_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("source"): str,
    vol.Optional("save_slot", default=0): vol.All(int, vol.Range(min=0, max=255)),
})

SERVICE_SHOW_SLOT = "show_slot"
SHOW_SLOT_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("slot"): vol.All(int, vol.Range(min=0, max=255)),
})

SERVICE_DELETE_SLOT = "delete_slot"
DELETE_SLOT_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("slot"): vol.All(int, vol.Range(min=0, max=255)),
})

SERVICE_RHYTHM_ANIMATION = "set_rhythm_animation"
RHYTHM_ANIMATION_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("style", default=0): vol.All(int, vol.Range(min=0, max=1)),
    vol.Optional("frame", default=0): vol.All(int, vol.Range(min=0, max=7)),
})

SERVICE_RHYTHM_LEVELS = "set_rhythm_levels"
RHYTHM_LEVELS_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("style", default=0): vol.All(int, vol.Range(min=0, max=4)),
    vol.Required("levels"): vol.All(
        [vol.All(int, vol.Range(min=0, max=15))], vol.Length(min=1, max=11)
    ),
})

SERVICE_SET_PLAYLIST = "set_playlist"
SET_PLAYLIST_SCHEMA = vol.Schema({
    vol.Required("enable"): vol.Boolean(),
    vol.Optional("device_id"): vol.Any(None, str, [str]),
})

SERVICE_START_PLAYLIST = "start_playlist"
START_PLAYLIST_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Optional("device_id"): vol.Any(None, str, [str]),
})

SERVICE_STOP_PLAYLIST = "stop_playlist"
STOP_PLAYLIST_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
})

SERVICE_SET_PROGRAM = "set_program"
SET_PROGRAM_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("slots"): vol.All(
        [vol.All(int, vol.Range(min=0, max=255))], vol.Length(min=1, max=64)
    ),
})

SERVICE_SHOW_CLOCK = "show_clock"
SHOW_CLOCK_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("style", default=1): vol.All(int, vol.Range(min=0, max=8)),
    vol.Optional("format_24", default=True): vol.Boolean(),
    vol.Optional("show_date", default=True): vol.Boolean(),
})

SERVICE_SET_PIXEL = "set_pixel"
SET_PIXEL_SCHEMA = vol.Schema({
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Required("x"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Required("y"): vol.All(int, vol.Range(min=0, max=255)),
    vol.Optional("color", default="ffffff"): str,
})

SERVICE_SHOW_TEXT = "show_text"
SHOW_TEXT_SCHEMA = vol.Schema({
    vol.Required("text"): str,
    vol.Optional("device_id"): vol.Any(None, str, [str]),
    vol.Optional("color", default="ffffff"): str,
    vol.Optional("bg_color", default="000000"): vol.Any(None, str),
    vol.Optional("animation", default=1): vol.All(int, vol.Range(min=0, max=7)),
    vol.Optional("speed", default=60): vol.All(int, vol.Range(min=0, max=100)),
    vol.Optional("rainbow", default=0): vol.All(int, vol.Range(min=0, max=9)),
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
    await api.display_widgets(page, save_slot=call.data.get("save_slot", 0))


async def _handle_set_orientation(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).set_orientation(call.data["orientation"])


async def _handle_set_fun_mode(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).set_fun_mode(call.data["enable"])


async def _handle_show_slot(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).show_slot(call.data["slot"])


async def _handle_delete_slot(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).delete_slot(call.data["slot"])


async def _handle_rhythm_animation(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).set_rhythm_animation(
        call.data.get("style", 0), call.data.get("frame", 0)
    )


async def _handle_rhythm_levels(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).set_rhythm_levels(
        call.data.get("style", 0), call.data["levels"]
    )


def _resolve_playlist_targets(hass: HomeAssistant, store: PageStore, name: str, raw):
    """Pick the panels a start_playlist call should play on.

    Priority: the call's device_id, then the playlist's saved targets, then all
    connected panels (so single-panel setups "just work").
    """
    targets = resolve_targets(hass, raw)
    if not targets:
        pl = store.playlists.get(name) or {}
        targets = resolve_targets(hass, pl.get("targets"))
    if not targets:
        targets = device_api_entry_ids(hass)
    return targets


async def _handle_set_playlist(hass: HomeAssistant, call: ServiceCall) -> None:
    """Legacy enable/disable shim mapped onto the per-device model."""
    store: PageStore | None = hass.data.get(STORE_DATA)
    runner: PlaylistRunner | None = hass.data.get(RUNNER_DATA)
    if not store:
        raise HomeAssistantError("Page store not ready")
    raw = call.data.get("device_id")
    if not call.data["enable"]:
        for entry_id in (resolve_targets(hass, raw) or device_api_entry_ids(hass)):
            await store.stop_playlist(entry_id)
        if runner:
            runner.restart()
        return
    # enable=True needs a playlist name; with the named model use start_playlist.
    raise HomeAssistantError(
        "set_playlist only stops playback now — use start_playlist with a name to start one."
    )


async def _handle_start_playlist(hass: HomeAssistant, call: ServiceCall) -> None:
    store: PageStore | None = hass.data.get(STORE_DATA)
    runner: PlaylistRunner | None = hass.data.get(RUNNER_DATA)
    if not store:
        raise HomeAssistantError("Page store not ready")
    name = call.data["name"]
    if name not in store.playlists:
        known = ", ".join(sorted(store.playlists)) or "(none)"
        raise HomeAssistantError(f"Unknown playlist '{name}'. Saved playlists: {known}")
    targets = _resolve_playlist_targets(hass, store, name, call.data.get("device_id"))
    if not await store.start_named_playlist(name, targets):
        raise HomeAssistantError(f"No panel available to play '{name}' on.")
    if runner:
        runner.restart()


async def _handle_stop_playlist(hass: HomeAssistant, call: ServiceCall) -> None:
    store: PageStore | None = hass.data.get(STORE_DATA)
    runner: PlaylistRunner | None = hass.data.get(RUNNER_DATA)
    if not store:
        raise HomeAssistantError("Page store not ready")
    targets = resolve_targets(hass, call.data.get("device_id"))
    if targets:
        for entry_id in targets:
            await store.stop_playlist(entry_id)
    else:
        await store.stop_playlist()
    if runner:
        runner.restart()


async def _handle_set_program(hass: HomeAssistant, call: ServiceCall) -> None:
    await _resolve_api(hass, call).set_program(call.data["slots"])


async def _handle_show_clock(hass: HomeAssistant, call: ServiceCall) -> None:
    api = _resolve_api(hass, call)
    if not api.is_connected:
        await api.connect()
    await api.set_clock_mode(
        style=call.data.get("style", 1),
        show_date=call.data.get("show_date", True),
        format_24=call.data.get("format_24", True),
    )


async def _handle_set_pixel(hass: HomeAssistant, call: ServiceCall) -> None:
    api = _resolve_api(hass, call)
    color = call.data.get("color", "ffffff").lstrip("#")
    await api.set_pixel(call.data["x"], call.data["y"], color)


async def _handle_show_image(hass: HomeAssistant, call: ServiceCall) -> None:
    from .display.widget_renderer import _read_local_image, _fetch_remote_image
    api = _resolve_api(hass, call)
    source = call.data["source"].strip()
    if source.startswith(("http://", "https://")):
        data = await _fetch_remote_image(hass, source)
    else:
        data = await hass.async_add_executor_job(_read_local_image, hass, source)
    if not data:
        raise HomeAssistantError(f"Could not read image source: {source}")
    ext = "." + source.rsplit(".", 1)[-1].lower() if "." in source.rsplit("/", 1)[-1] else ".gif"
    await api.display_image_file(data, file_extension=ext, save_slot=call.data.get("save_slot", 0))


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

    # Frontend assets are served with a long cache, so append the integration
    # version as a cache-buster — otherwise browsers keep stale JS after an
    # upgrade. The sidebar panel propagates the same query to the card it loads.
    version = "0"
    try:
        from homeassistant.loader import async_get_integration

        version = str((await async_get_integration(hass, DOMAIN)).version)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not read integration version: %s", err)
    card_url = f"{CARD_URL}?v={version}"
    panel_url = f"{PANEL_URL}?v={version}"

    # Serve the whole www/ dir, auto-load the card, and register a sidebar panel
    # so the designer is discoverable without manually adding a Lovelace card.
    # Each step is independent: a failure in one (e.g. a static path already
    # registered after a reload) must not stop the sidebar panel registering.
    www_dir = Path(__file__).parent / "www"

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(www_dir), True)]
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("iPIXEL static path already registered or failed: %s", err)

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, card_url)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not add the iPIXEL card JS url: %s", err)

    if not hass.data.get(PANEL_DATA):
        try:
            from homeassistant.components import panel_custom

            await panel_custom.async_register_panel(
                hass,
                webcomponent_name="ipixel-panel",
                frontend_url_path="ipixel",
                module_url=panel_url,
                sidebar_title="iPIXEL",
                sidebar_icon="mdi:dots-grid",
                require_admin=False,
                embed_iframe=False,
            )
            hass.data[PANEL_DATA] = True
            _LOGGER.info("iPIXEL sidebar panel registered at /ipixel")
        except ValueError as err:
            # Raised when the frontend_url_path is already registered (reloads).
            _LOGGER.debug("iPIXEL sidebar panel already registered: %s", err)
            hass.data[PANEL_DATA] = True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not register the iPIXEL sidebar panel: %s", err)


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
        # Best-effort: ask the panel what it actually is (logged; never fatal).
        try:
            await api.probe_device_info()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Device info probe failed: %s", err)
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

    for _svc, _handler, _schema in (
        (SERVICE_SET_ORIENTATION, _handle_set_orientation, SET_ORIENTATION_SCHEMA),
        (SERVICE_SET_FUN_MODE, _handle_set_fun_mode, SET_FUN_MODE_SCHEMA),
        (SERVICE_SHOW_IMAGE, _handle_show_image, SHOW_IMAGE_SCHEMA),
        (SERVICE_SHOW_SLOT, _handle_show_slot, SHOW_SLOT_SCHEMA),
        (SERVICE_DELETE_SLOT, _handle_delete_slot, DELETE_SLOT_SCHEMA),
        (SERVICE_RHYTHM_ANIMATION, _handle_rhythm_animation, RHYTHM_ANIMATION_SCHEMA),
        (SERVICE_RHYTHM_LEVELS, _handle_rhythm_levels, RHYTHM_LEVELS_SCHEMA),
        (SERVICE_SET_PLAYLIST, _handle_set_playlist, SET_PLAYLIST_SCHEMA),
        (SERVICE_START_PLAYLIST, _handle_start_playlist, START_PLAYLIST_SCHEMA),
        (SERVICE_STOP_PLAYLIST, _handle_stop_playlist, STOP_PLAYLIST_SCHEMA),
        (SERVICE_SET_PROGRAM, _handle_set_program, SET_PROGRAM_SCHEMA),
        (SERVICE_SET_PIXEL, _handle_set_pixel, SET_PIXEL_SCHEMA),
        (SERVICE_SHOW_CLOCK, _handle_show_clock, SHOW_CLOCK_SCHEMA),
    ):
        if not hass.services.has_service(DOMAIN, _svc):
            def _make(handler):
                async def _svc_fn(call: ServiceCall) -> None:
                    await handler(hass, call)
                return _svc_fn
            hass.services.async_register(DOMAIN, _svc, _make(_handler), schema=_schema)

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
        # Stop just this panel's playlist loop (others keep running).
        runner: PlaylistRunner | None = hass.data.get(RUNNER_DATA)
        if runner:
            runner.stop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)