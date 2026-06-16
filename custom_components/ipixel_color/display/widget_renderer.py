"""Generic widget renderer for iPIXEL Enhanced.

A *page* is a dict::

    {
        "background": "000000",
        "widgets": [
            {"type": "text", "text": "{{ states('sensor.temp') }}C",
             "anchor": "top_left", "color": "ffaa00", "font": "5x5"},
            {"type": "emoji", "emoji": "☀️", "anchor": "top_right", "size": 12},
            {"type": "clock", "format": "%H:%M", "anchor": "bottom_center"},
        ],
    }

The engine resolves Jinja2 templates against Home Assistant state, fetches any
emoji / remote images asynchronously, then draws everything onto a single
canvas at the device resolution and returns PNG bytes.

Positioning: every widget may use absolute ``x``/``y`` OR a named ``anchor``
(``top_left``, ``top_center``, ``top_right``, ``center_left``, ``center``,
``center_right``, ``bottom_left``, ``bottom_center``, ``bottom_right``) plus
optional ``dx``/``dy`` pixel offsets. Anchors make it trivial to say
"sensor in the bottom-left, emoji top-right" without doing pixel math.
"""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.template import Template

from ..fonts import get_font_path
from .emoji_renderer import fetch_emoji_png

_LOGGER = logging.getLogger(__name__)

DEFAULT_FONT = "WP7xn"
DEFAULT_FONT_SIZE = 7
EMOJI_DOWNLOAD_TIMEOUT = 10

ANCHORS = {
    "top_left", "top_center", "top_right",
    "center_left", "center", "center_right",
    "bottom_left", "bottom_center", "bottom_right",
}

# Named colours so users don't have to remember hex codes.
NAMED_COLORS = {
    "black": "000000", "white": "ffffff", "red": "ff0000", "green": "00cc33",
    "blue": "2266ff", "yellow": "ffcc00", "orange": "ff8800", "purple": "aa44ff",
    "pink": "ff66cc", "cyan": "00ccdd", "gray": "888888", "grey": "888888",
    "lime": "88ff00", "teal": "00ccaa", "gold": "ffd700", "silver": "c0c0c0",
}


def parse_color(value, default=(0, 0, 0)) -> tuple[int, int, int]:
    """Accept '#rrggbb', 'rrggbb', a CSS-ish name or an [r,g,b] list."""
    if value is None:
        return default
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(max(0, min(255, c))) for c in value)
    if isinstance(value, str):
        v = value.strip().lower()
        v = NAMED_COLORS.get(v, v)
        v = v.lstrip("#")
        if len(v) == 3:  # shorthand #abc
            v = "".join(c * 2 for c in v)
        if len(v) == 6:
            try:
                return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
            except ValueError:
                pass
    return default


# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------
def _looks_templated(value) -> bool:
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _resolve_templates(hass: HomeAssistant, node):
    """Deep-render any Jinja2 string in the page definition."""
    if isinstance(node, dict):
        return {k: _resolve_templates(hass, v) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_templates(hass, v) for v in node]
    if _looks_templated(node):
        try:
            return Template(node, hass).async_render(parse_result=False)
        except Exception as err:  # noqa: BLE001 - never let one bad template kill the page
            _LOGGER.warning("Template error in %r: %s", node, err)
            return ""
    return node


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off", "none", "unavailable", "unknown")
    return bool(value)


# ---------------------------------------------------------------------------
# Fonts (cached). We reuse the pixel TTFs bundled with the integration.
# ---------------------------------------------------------------------------
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _get_font(name: str | None, size: int) -> ImageFont.FreeTypeFont:
    name = name or DEFAULT_FONT
    size = max(1, int(size))
    key = (name, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = None
    path = get_font_path(name)
    if path:
        try:
            font = ImageFont.truetype(str(path), size)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Font %s@%d failed: %s", name, size, err)
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# ---------------------------------------------------------------------------
# Async asset prefetch (emoji + remote images)
# ---------------------------------------------------------------------------
async def _fetch_remote_image(hass: HomeAssistant, url: str) -> bytes | None:
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(EMOJI_DOWNLOAD_TIMEOUT):
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Image %s -> HTTP %s", url, resp.status)
                    return None
                return await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.warning("Image fetch failed %s: %s", url, err)
        return None


def _read_local_image(hass: HomeAssistant, src: str) -> bytes | None:
    candidates: list[Path] = []
    if src.startswith("/local/"):
        candidates.append(Path(hass.config.path("www", src[len("/local/"):])))
    elif src.startswith("/"):
        candidates.append(Path(src))
    else:
        candidates.append(Path(hass.config.path("www", src)))
        candidates.append(Path(hass.config.path(src)))
    for path in candidates:
        try:
            if path.is_file():
                return path.read_bytes()
        except OSError as err:
            _LOGGER.warning("Cannot read image %s: %s", path, err)
    _LOGGER.warning("Local image not found: %s", src)
    return None


async def _prefetch_assets(hass: HomeAssistant, widgets: list[dict]) -> dict[int, bytes]:
    """Fetch every emoji/image asset, keyed by the widget's index."""
    assets: dict[int, bytes] = {}
    tasks = []
    indices = []
    for i, w in enumerate(widgets):
        wtype = w.get("type")
        if wtype == "emoji":
            emoji = (w.get("emoji") or "").strip()
            if emoji:
                indices.append(i)
                tasks.append(fetch_emoji_png(hass, _emoji_codepoint(emoji)))
        elif wtype == "image":
            src = (w.get("src") or "").strip()
            if src.startswith(("http://", "https://")):
                indices.append(i)
                tasks.append(_fetch_remote_image(hass, src))
            elif src:
                indices.append(i)
                tasks.append(hass.async_add_executor_job(_read_local_image, hass, src))
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for idx, res in zip(indices, results):
            if isinstance(res, (bytes, bytearray)):
                assets[idx] = bytes(res)
    return assets


def _emoji_codepoint(emoji: str) -> str:
    # Twemoji filenames keep the ZWJ (200d) joiner but omit the FE0F selector,
    # e.g. 👨‍💻 -> "1f468-200d-1f4bb". Only strip FE0F.
    return "-".join(f"{ord(c):x}" for c in emoji if c != "️")


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def _place(anchor: str, box_w: int, box_h: int, cw: int, ch: int) -> tuple[int, int]:
    vert, _, horiz = anchor.partition("_")
    if horiz == "left":
        x = 0
    elif horiz == "right":
        x = cw - box_w
    else:  # center
        x = (cw - box_w) // 2
    if vert == "top":
        y = 0
    elif vert == "bottom":
        y = ch - box_h
    else:  # center
        y = (ch - box_h) // 2
    return x, y


def _resolve_position(w: dict, box_w: int, box_h: int, cw: int, ch: int) -> tuple[int, int]:
    dx = int(w.get("dx", 0) or 0)
    dy = int(w.get("dy", 0) or 0)
    if "x" in w or "y" in w:
        return int(w.get("x", 0) or 0) + dx, int(w.get("y", 0) or 0) + dy
    anchor = str(w.get("anchor", "top_left")).strip().lower()
    if anchor not in ANCHORS:
        anchor = "top_left"
    x, y = _place(anchor, box_w, box_h, cw, ch)
    return x + dx, y + dy


# ---------------------------------------------------------------------------
# Per-widget drawing (runs in executor — pure PIL, no awaits)
# ---------------------------------------------------------------------------
def _text_size(font: ImageFont.FreeTypeFont, text: str, spacing: int) -> tuple[int, int, int, int]:
    """Return (width, height, x_offset, y_offset) of the rendered text bbox."""
    tmp = Image.new("L", (1, 1))
    d = ImageDraw.Draw(tmp)
    bbox = d.multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    return bbox[2] - bbox[0], bbox[3] - bbox[1], bbox[0], bbox[1]


def _draw_text(canvas, draw, w, cw, ch):
    text = str(w.get("text", ""))
    if not text:
        return
    font = _get_font(w.get("font"), w.get("size", DEFAULT_FONT_SIZE))
    spacing = int(w.get("spacing", 1) or 0)
    align = str(w.get("align", "left")).lower()
    color = parse_color(w.get("color", "ffffff"), (255, 255, 255))
    # Crisp 1-bit glyphs by default (LED matrices can't show anti-aliased grays);
    # set "antialias": true for smooth edges on larger text.
    prev_mode = draw.fontmode
    draw.fontmode = "L" if _truthy(w.get("antialias", False)) else "1"
    try:
        tw, th, ox, oy = _text_size(font, text, spacing)
        px, py = _resolve_position(w, tw, th, cw, ch)
        draw.multiline_text((px - ox, py - oy), text, font=font, fill=color,
                            spacing=spacing, align=align)
    finally:
        draw.fontmode = prev_mode


def _draw_emoji(canvas, draw, w, asset, cw, ch):
    if not asset:
        return
    size = int(w.get("size", 12) or 12)
    try:
        img = Image.open(io.BytesIO(asset)).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Emoji decode failed: %s", err)
        return
    px, py = _resolve_position(w, size, size, cw, ch)
    canvas.paste(img, (px, py), img)


def _draw_image(canvas, draw, w, asset, cw, ch):
    if not asset:
        return
    try:
        img = Image.open(io.BytesIO(asset)).convert("RGBA")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Image decode failed: %s", err)
        return
    iw = int(w.get("width", img.width) or img.width)
    ih = int(w.get("height", img.height) or img.height)
    fit = str(w.get("fit", "contain")).lower()
    if fit == "cover":
        scale = max(iw / img.width, ih / img.height)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        left = (img.width - iw) // 2
        top = (img.height - ih) // 2
        img = img.crop((left, top, left + iw, top + ih))
    elif fit == "stretch":
        img = img.resize((iw, ih), Image.LANCZOS)
    else:  # contain
        img.thumbnail((iw, ih), Image.LANCZOS)
    px, py = _resolve_position(w, img.width, img.height, cw, ch)
    canvas.paste(img, (px, py), img)


def _draw_line(canvas, draw, w, cw, ch):
    color = parse_color(w.get("color", "888888"), (136, 136, 136))
    width = int(w.get("width", 1) or 1)
    x1 = int(w.get("x", 0) or 0)
    y1 = int(w.get("y", 0) or 0)
    x2 = int(w.get("x2", cw - 1) if w.get("x2") is not None else cw - 1)
    y2 = int(w.get("y2", y1) if w.get("y2") is not None else y1)
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)


def _draw_rect(canvas, draw, w, cw, ch):
    color = parse_color(w.get("color", "ffffff"), (255, 255, 255))
    rw = int(w.get("width", 4) or 4)
    rh = int(w.get("height", 4) or 4)
    px, py = _resolve_position(w, rw, rh, cw, ch)
    fill = w.get("fill", True)
    radius = int(w.get("radius", 0) or 0)
    box = [px, py, px + rw - 1, py + rh - 1]
    if radius > 0:
        draw.rounded_rectangle(box, radius=radius,
                               fill=color if _truthy(fill) else None,
                               outline=color if not _truthy(fill) else None)
    else:
        draw.rectangle(box, fill=color if _truthy(fill) else None,
                       outline=color if not _truthy(fill) else None)


def _draw_progress(canvas, draw, w, cw, ch):
    try:
        value = float(w.get("value", 0) or 0)
    except (TypeError, ValueError):
        value = 0.0
    value = max(0.0, min(100.0, value))
    rw = int(w.get("width", cw) or cw)
    rh = int(w.get("height", 4) or 4)
    px, py = _resolve_position(w, rw, rh, cw, ch)
    bg = parse_color(w.get("bg", "303030"), (48, 48, 48))
    fg = parse_color(w.get("color", "00cc33"), (0, 204, 51))
    draw.rectangle([px, py, px + rw - 1, py + rh - 1], fill=bg)
    fill_w = int((rw - 0) * value / 100.0)
    if fill_w > 0:
        draw.rectangle([px, py, px + fill_w - 1, py + rh - 1], fill=fg)


def _draw_clock(canvas, draw, w, cw, ch):
    fmt = str(w.get("format", "%H:%M"))
    try:
        text = datetime.now().strftime(fmt)
    except ValueError:
        text = datetime.now().strftime("%H:%M")
    cw_widget = dict(w)
    cw_widget["text"] = text
    _draw_text(canvas, draw, cw_widget, cw, ch)


_DRAWERS_NEEDING_ASSET = {"emoji", "image"}


def _render_canvas(page: dict, assets: dict[int, bytes], width: int, height: int) -> bytes:
    bg = parse_color(page.get("background", page.get("bg", "000000")), (0, 0, 0))
    canvas = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(canvas)
    for i, w in enumerate(page.get("widgets", []) or []):
        if not isinstance(w, dict):
            continue
        if "if" in w and not _truthy(w.get("if")):
            continue
        wtype = str(w.get("type", "text")).lower()
        try:
            if wtype == "text":
                _draw_text(canvas, draw, w, width, height)
            elif wtype == "emoji":
                _draw_emoji(canvas, draw, w, assets.get(i), width, height)
            elif wtype == "image":
                _draw_image(canvas, draw, w, assets.get(i), width, height)
            elif wtype == "line":
                _draw_line(canvas, draw, w, width, height)
            elif wtype in ("rect", "rectangle", "box"):
                _draw_rect(canvas, draw, w, width, height)
            elif wtype in ("progress", "bar"):
                _draw_progress(canvas, draw, w, width, height)
            elif wtype == "clock":
                _draw_clock(canvas, draw, w, width, height)
            else:
                _LOGGER.warning("Unknown widget type: %s", wtype)
        except Exception as err:  # noqa: BLE001 - one bad widget shouldn't blank the page
            _LOGGER.warning("Widget %d (%s) failed: %s", i, wtype, err)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


async def render_page_to_png(
    hass: HomeAssistant, page: dict, width: int = 32, height: int = 32
) -> bytes:
    """Resolve templates, fetch assets and render a page to PNG bytes."""
    resolved = _resolve_templates(hass, page or {})
    widgets = resolved.get("widgets", []) or []
    assets = await _prefetch_assets(hass, widgets)
    return await hass.async_add_executor_job(
        _render_canvas, resolved, assets, width, height
    )
