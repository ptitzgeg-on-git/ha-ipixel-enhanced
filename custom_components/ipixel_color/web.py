"""HTTP preview view + websocket page-library API for iPIXEL Enhanced."""
from __future__ import annotations

import base64
import io
import logging

import voluptuous as vol
from aiohttp import web

from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .display.widget_renderer import render_page

_LOGGER = logging.getLogger(__name__)

PREVIEW_URL = "/api/ipixel_color/preview"


class PreviewView(HomeAssistantView):
    """Render a page server-side and return a base64 PNG for the live preview."""

    url = PREVIEW_URL
    name = "api:ipixel_color:preview"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        try:
            body = await request.json()
        except ValueError:
            return self.json_message("Invalid JSON", status_code=400)

        page = body.get("page", {})
        width = int(body.get("width", 32) or 32)
        height = int(body.get("height", 32) or 32)
        scale = max(1, min(16, int(body.get("scale", 1) or 1)))

        try:
            data, fmt = await render_page(hass, page, width, height)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Preview render failed: %s", err)
            return self.json_message(f"Render error: {err}", status_code=500)

        if scale > 1:
            from PIL import Image

            def _upscale(raw: bytes, is_gif: bool) -> bytes:
                src = Image.open(io.BytesIO(raw))
                if not is_gif:
                    img = src.convert("RGB").resize(
                        (src.width * scale, src.height * scale), Image.NEAREST)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return buf.getvalue()
                # Animated GIF: upscale every frame, keep per-frame durations.
                frames, durations = [], []
                try:
                    n = int(getattr(src, "n_frames", 1) or 1)
                except Exception:  # noqa: BLE001
                    n = 1
                for i in range(n):
                    src.seek(i)
                    frames.append(src.convert("RGB").resize(
                        (src.width * scale, src.height * scale), Image.NEAREST))
                    durations.append(src.info.get("duration", 100))
                buf = io.BytesIO()
                frames[0].save(buf, format="GIF", save_all=True,
                               append_images=frames[1:], duration=durations,
                               loop=0, disposal=2)
                return buf.getvalue()

            data = await hass.async_add_executor_job(_upscale, data, fmt == "gif")

        mime = "image/gif" if fmt == "gif" else "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return self.json({"image": f"data:{mime};base64,{b64}", "width": width, "height": height})


# ---------------------------------------------------------------------------
# Websocket: page library CRUD + playlist
# ---------------------------------------------------------------------------
def _store(hass: HomeAssistant):
    return hass.data.get(f"{DOMAIN}_store")


def _runner(hass: HomeAssistant):
    return hass.data.get(f"{DOMAIN}_runner")


def _api_for_device(hass: HomeAssistant, device_id: str | None):
    """Resolve a device_id (or first device) to its iPIXEL API instance."""
    apis = {
        k: v for k, v in hass.data.get(DOMAIN, {}).items()
        if hasattr(v, "display_widgets")
    }
    if not apis:
        return None
    if device_id:
        if device_id in apis:
            return apis[device_id]
        from homeassistant.helpers import device_registry as dr
        device = dr.async_get(hass).async_get(device_id)
        if device:
            for entry_id in device.config_entries:
                if entry_id in apis:
                    return apis[entry_id]
    return next(iter(apis.values()))


@websocket_api.websocket_command({vol.Required("type"): "ipixel_color/pages/list"})
@callback
def ws_list(hass, connection, msg):
    store = _store(hass)
    devices = []
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    for entry_id, api in hass.data.get(DOMAIN, {}).items():
        if not hasattr(api, "display_widgets"):
            continue
        info = getattr(api, "cached_info", None) or {}
        for device in dr.async_entries_for_config_entry(dev_reg, entry_id):
            name = device.name_by_user or device.name or entry_id
            devices.append({
                "id": device.id,
                "entry_id": entry_id,
                "name": name,
                "width": int(info.get("width", 32) or 32),
                "height": int(info.get("height", 32) or 32),
            })
            break
    connection.send_result(
        msg["id"],
        {"pages": store.pages if store else {},
         "playlists": store.playlists if store else {},
         "runs": store.runs if store else {},
         "slots": store.slots if store else {},
         "devices": devices},
    )


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/pages/save",
    vol.Required("name"): str,
    vol.Required("page"): dict,
})
@websocket_api.async_response
async def ws_save(hass, connection, msg):
    store = _store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    await store.save_page(msg["name"], msg["page"])
    connection.send_result(msg["id"], {"saved": msg["name"]})


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/pages/delete",
    vol.Required("name"): str,
})
@websocket_api.async_response
async def ws_delete(hass, connection, msg):
    store = _store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    await store.delete_page(msg["name"])
    connection.send_result(msg["id"], {"deleted": msg["name"]})


def _playlist_state(store):
    return {"playlists": store.playlists, "runs": store.runs}


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/playlists/save",
    vol.Required("name"): str,
    vol.Required("items"): list,
    vol.Optional("targets"): vol.Any(None, [str]),
})
@websocket_api.async_response
async def ws_pl_save(hass, connection, msg):
    store = _store(hass)
    runner = _runner(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    await store.save_named_playlist(msg["name"], msg["items"], msg.get("targets"))
    # Refresh any panel currently playing this playlist so edits take effect.
    if runner:
        for entry_id, name in store.runs.items():
            if name == msg["name"]:
                runner.restart_one(entry_id)
    connection.send_result(msg["id"], _playlist_state(store))


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/playlists/delete",
    vol.Required("name"): str,
})
@websocket_api.async_response
async def ws_pl_delete(hass, connection, msg):
    store = _store(hass)
    runner = _runner(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    await store.delete_named_playlist(msg["name"])
    if runner:
        runner.restart()
    connection.send_result(msg["id"], _playlist_state(store))


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/playlists/start",
    vol.Required("name"): str,
    vol.Optional("targets"): vol.Any(None, [str]),
})
@websocket_api.async_response
async def ws_pl_start(hass, connection, msg):
    from .pages import device_api_entry_ids, resolve_targets

    store = _store(hass)
    runner = _runner(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    if msg["name"] not in store.playlists:
        connection.send_error(msg["id"], "unknown", f"Unknown playlist '{msg['name']}'")
        return
    targets = resolve_targets(hass, msg.get("targets"))
    if not targets:
        pl = store.playlists.get(msg["name"]) or {}
        targets = resolve_targets(hass, pl.get("targets")) or device_api_entry_ids(hass)
    if not await store.start_named_playlist(msg["name"], targets):
        connection.send_error(msg["id"], "no_device", "No panel available to play on")
        return
    if runner:
        for entry_id in targets:
            runner.restart_one(entry_id)
    connection.send_result(msg["id"], _playlist_state(store))


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/playlists/stop",
    vol.Optional("targets"): vol.Any(None, [str]),
})
@websocket_api.async_response
async def ws_pl_stop(hass, connection, msg):
    from .pages import resolve_targets

    store = _store(hass)
    runner = _runner(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    targets = resolve_targets(hass, msg.get("targets"))
    if targets:
        for entry_id in targets:
            await store.stop_playlist(entry_id)
            if runner:
                runner.stop(entry_id)
    else:
        await store.stop_playlist()
        if runner:
            runner.stop()
    connection.send_result(msg["id"], _playlist_state(store))


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/slots/set",
    vol.Required("name"): str,
    vol.Required("slot"): vol.Any(None, vol.All(int, vol.Range(min=1, max=255))),
})
@websocket_api.async_response
async def ws_slot_set(hass, connection, msg):
    store = _store(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    await store.set_slot(msg["name"], msg["slot"])
    connection.send_result(msg["id"], {"slots": store.slots})


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/draw_grid",
    vol.Optional("target"): vol.Any(None, str),
    vol.Required("width"): int,
    vol.Required("height"): int,
    vol.Required("pixels"): list,
    vol.Optional("background", default="000000"): str,
})
@websocket_api.async_response
async def ws_draw_grid(hass, connection, msg):
    api = _api_for_device(hass, msg.get("target"))
    if api is None:
        connection.send_error(msg["id"], "no_device", "No iPIXEL device available")
        return
    ok = await api.display_grid(
        msg["pixels"], msg["width"], msg["height"], msg.get("background", "000000")
    )
    connection.send_result(msg["id"], {"sent": ok})


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the HTTP view and websocket commands (idempotent)."""
    if hass.data.get(f"{DOMAIN}_web_registered"):
        return
    hass.http.register_view(PreviewView())
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_save)
    websocket_api.async_register_command(hass, ws_delete)
    websocket_api.async_register_command(hass, ws_pl_save)
    websocket_api.async_register_command(hass, ws_pl_delete)
    websocket_api.async_register_command(hass, ws_pl_start)
    websocket_api.async_register_command(hass, ws_pl_stop)
    websocket_api.async_register_command(hass, ws_slot_set)
    websocket_api.async_register_command(hass, ws_draw_grid)
    hass.data[f"{DOMAIN}_web_registered"] = True
