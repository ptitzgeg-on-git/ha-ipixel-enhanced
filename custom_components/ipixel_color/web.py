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
from .display.widget_renderer import render_page_to_png

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
            png = await render_page_to_png(hass, page, width, height)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Preview render failed: %s", err)
            return self.json_message(f"Render error: {err}", status_code=500)

        if scale > 1:
            from PIL import Image

            def _upscale(data: bytes) -> bytes:
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()

            png = await hass.async_add_executor_job(_upscale, png)

        b64 = base64.b64encode(png).decode("ascii")
        return self.json({"image": f"data:image/png;base64,{b64}", "width": width, "height": height})


# ---------------------------------------------------------------------------
# Websocket: page library CRUD + playlist
# ---------------------------------------------------------------------------
def _store(hass: HomeAssistant):
    return hass.data.get(f"{DOMAIN}_store")


def _runner(hass: HomeAssistant):
    return hass.data.get(f"{DOMAIN}_runner")


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
        for device in dr.async_entries_for_config_entry(dev_reg, entry_id):
            name = device.name_by_user or device.name or entry_id
            devices.append({"id": device.id, "name": name})
            break
    connection.send_result(
        msg["id"],
        {"pages": store.pages if store else {},
         "playlist": store.playlist if store else {},
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


@websocket_api.websocket_command({
    vol.Required("type"): "ipixel_color/playlist/set",
    vol.Required("playlist"): dict,
})
@websocket_api.async_response
async def ws_set_playlist(hass, connection, msg):
    store = _store(hass)
    runner = _runner(hass)
    if not store:
        connection.send_error(msg["id"], "not_ready", "Store not initialised")
        return
    await store.set_playlist(msg["playlist"])
    if runner:
        runner.restart()
    connection.send_result(msg["id"], {"playlist": store.playlist})


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the HTTP view and websocket commands (idempotent)."""
    if hass.data.get(f"{DOMAIN}_web_registered"):
        return
    hass.http.register_view(PreviewView())
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_save)
    websocket_api.async_register_command(hass, ws_delete)
    websocket_api.async_register_command(hass, ws_set_playlist)
    hass.data[f"{DOMAIN}_web_registered"] = True
