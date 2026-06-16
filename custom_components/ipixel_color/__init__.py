"""The iPIXEL Color integration."""
from __future__ import annotations
import asyncio
import logging
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from .api import iPIXELAPI, iPIXELConnectionError, iPIXELTimeoutError
from .const import DOMAIN, CONF_ADDRESS, CONF_NAME

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH, Platform.TEXT, Platform.SENSOR,
    Platform.SELECT, Platform.NUMBER, Platform.BUTTON, Platform.LIGHT
]

SERVICE_RENDER_PREVIEW = "render_preview"

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

SERVICE_SHOW_LAYOUT = "show_layout"
SHOW_LAYOUT_SCHEMA = vol.Schema({
    vol.Optional("time_str", default=""): str,
    vol.Optional("temp_str", default=""): str,
    vol.Optional("rain_str", default=""): str,
    vol.Optional("travel_str", default=""): str,
    vol.Optional("emoji_codepoint", default=""): str,
    vol.Optional("bg_color", default="000000"): str,
    vol.Optional("text_color", default="ffffff"): str,
    vol.Optional("accent_color", default="00bfff"): str,
    vol.Optional("page", default=1): vol.All(int, vol.Range(min=1, max=3)),
    vol.Optional("metro_ok", default=True): vol.Boolean(),
    vol.Optional("metro_a_ok", default=True): vol.Boolean(),
    vol.Optional("metro_b_ok", default=True): vol.Boolean(),
    vol.Optional("advice_str", default=""): str,
    vol.Optional("condition_str", default=""): str,
    vol.Optional("morning_str", default=""): str,
    vol.Optional("evening_str", default=""): str,
    vol.Optional("emoji_codepoint_morning", default=""): str,
    vol.Optional("emoji_codepoint_evening", default=""): str,
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


async def _handle_show_layout(hass: HomeAssistant, call: ServiceCall) -> None:
    import asyncio
    from .display.emoji_renderer import fetch_emoji_png
    api = _resolve_api(hass, call)
    page = call.data.get("page", 1)

    async def _fetch(cp: str):
        return await fetch_emoji_png(hass, cp) if cp.strip() else None

    # Ⓜ️ (24c2) fetché automatiquement pour page 3 — mis en cache après 1er appel
    metro_cp = "24c2" if page == 3 else ""

    emoji_png, morning_emoji_png, evening_emoji_png, metro_emoji_png = await asyncio.gather(
        _fetch(call.data.get("emoji_codepoint", "")),
        _fetch(call.data.get("emoji_codepoint_morning", "")),
        _fetch(call.data.get("emoji_codepoint_evening", "")),
        _fetch(metro_cp),
    )

    await api.display_layout(
        time_str=call.data.get("time_str", ""),
        temp_str=call.data.get("temp_str", ""),
        rain_str=call.data.get("rain_str", ""),
        travel_str=call.data.get("travel_str", ""),
        emoji_png=emoji_png,
        bg_color=call.data.get("bg_color", "000000"),
        text_color=call.data.get("text_color", "ffffff"),
        accent_color=call.data.get("accent_color", "00bfff"),
        page=page,
        metro_ok=call.data.get("metro_ok", True),
        metro_a_ok=call.data.get("metro_a_ok", True),
        metro_b_ok=call.data.get("metro_b_ok", True),
        metro_emoji_png=metro_emoji_png,
        advice_str=call.data.get("advice_str", ""),
        condition_str=call.data.get("condition_str", ""),
        morning_str=call.data.get("morning_str", ""),
        evening_str=call.data.get("evening_str", ""),
        morning_emoji_png=morning_emoji_png,
        evening_emoji_png=evening_emoji_png,
    )


async def _handle_render_preview(hass: HomeAssistant, call: ServiceCall) -> None:
    """Render all pages with test data and save PNGs to /homeassistant/www/ipixel_preview/."""
    from pathlib import Path
    from .display.emoji_renderer import fetch_emoji_png
    from .display.layout_renderer import render_layout_to_png

    out_dir = Path("/homeassistant/www/ipixel_preview")
    out_dir.mkdir(parents=True, exist_ok=True)

    sunny_png, rainy_png, cloudy_png, bike_png, metro_png = await asyncio.gather(
        fetch_emoji_png(hass, "1f31e"),  # ☀
        fetch_emoji_png(hass, "1f327"),  # 🌧
        fetch_emoji_png(hass, "26c5"),   # ⛅
        fetch_emoji_png(hass, "1f6b4"),  # 🚴
        fetch_emoji_png(hass, "24c2"),   # Ⓜ
    )

    scenarios = [
        ("page1_sunny",  {"page": 1, "time_str": "14:35", "temp_str": "22C", "rain_str": "5%",  "emoji_png": sunny_png}),
        ("page1_rain",   {"page": 1, "time_str": "08:10", "temp_str": "14C", "rain_str": "70%", "emoji_png": rainy_png}),
        ("page2_sun17",  {"page": 2, "evening_str": "SUN 9C 5%",   "evening_emoji_png": sunny_png}),
        ("page2_rain17", {"page": 2, "evening_str": "PLU 16C 75%", "evening_emoji_png": rainy_png}),
        ("page3_all_ok", {"page": 3, "metro_a_ok": True,  "metro_b_ok": True,  "travel_str": "8min",  "emoji_png": bike_png, "metro_emoji_png": metro_png}),
        ("page3_a_ko",   {"page": 3, "metro_a_ok": False, "metro_b_ok": True,  "travel_str": "14min", "emoji_png": bike_png, "metro_emoji_png": metro_png}),
        ("page3_b_ko",   {"page": 3, "metro_a_ok": True,  "metro_b_ok": False, "travel_str": "22min", "emoji_png": bike_png, "metro_emoji_png": metro_png}),
        ("page3_all_ko", {"page": 3, "metro_a_ok": False, "metro_b_ok": False, "travel_str": "22min", "emoji_png": bike_png, "metro_emoji_png": metro_png}),
    ]

    for name, kwargs in scenarios:
        try:
            from PIL import Image
            import io as _io
            png = await render_layout_to_png(hass, **kwargs)
            # Upscale 4× so it's visible in a browser (32→128px)
            img = Image.open(_io.BytesIO(png)).convert("RGB")
            img = img.resize((img.width * 4, img.height * 4), Image.NEAREST)
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            (out_dir / f"{name}.png").write_bytes(buf.getvalue())
            _LOGGER.info("Preview saved: /local/ipixel_preview/%s.png", name)
        except Exception as err:
            _LOGGER.error("Preview %s failed: %s", name, err)

    _LOGGER.info(
        "All previews available at http://your-ha:8123/local/ipixel_preview/ — "
        "page1_sunny, page1_rain, page2_sun17, page2_rain17, page3_ok, page3_ko"
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    name = entry.data[CONF_NAME]
    _LOGGER.debug("Setting up iPIXEL Color for %s (%s)", name, address)
    api = iPIXELAPI(hass, address)
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
    if not hass.services.has_service(DOMAIN, SERVICE_SHOW_LAYOUT):
        async def _show_layout_service(call: ServiceCall) -> None:
            await _handle_show_layout(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_SHOW_LAYOUT, _show_layout_service, schema=SHOW_LAYOUT_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_RENDER_PREVIEW):
        async def _render_preview_service(call: ServiceCall) -> None:
            await _handle_render_preview(hass, call)
        hass.services.async_register(DOMAIN, SERVICE_RENDER_PREVIEW, _render_preview_service, schema=vol.Schema({}))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading iPIXEL Color integration")
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        api: iPIXELAPI = hass.data[DOMAIN].pop(entry.entry_id)
        try:
            await api.disconnect()
        except Exception as err:
            _LOGGER.error("Error disconnecting: %s", err)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)