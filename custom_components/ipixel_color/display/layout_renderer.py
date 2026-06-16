"""Layout renderer for iPIXEL Color — full 32×32 pixel layout."""
from __future__ import annotations
import io
import re
import logging
from PIL import Image, ImageDraw

from .pixel_font import draw_pixel_text, pixel_text_width, CHAR_H

_LOGGER = logging.getLogger(__name__)


def _hex(color: str) -> tuple[int, int, int]:
    try:
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
    except Exception:
        return 0, 0, 0


def _paste_emoji(canvas: Image.Image, png_bytes: bytes | None, x: int, y: int, size: int) -> None:
    if not png_bytes:
        return
    try:
        from PIL import Image as _Img
        img = _Img.open(io.BytesIO(png_bytes)).convert("RGBA")
        img = img.resize((size, size), _Img.LANCZOS)
        canvas.paste(img, (x, y), img)
    except Exception as err:
        _LOGGER.warning("Emoji paste error: %s", err)


def _parse_forecast(s: str) -> tuple[str, str, str]:
    parts = s.split()
    return (
        parts[0] if len(parts) > 0 else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )


# ---------------------------------------------------------------------------
# Page 1 : météo actuelle + heure
#
#   y=1  : [emoji 14×14]  temp orange     (row 1–7)
#   y=9  :                rain% bleu       (row 9–15)
#   y=17 : ────────── séparateur
#   y=20 : heure centrée gris clair        (row 20–26)
# ---------------------------------------------------------------------------
def _render_page1(
    time_str: str,
    temp_str: str,
    rain_str: str,
    emoji_png: bytes | None,
    bg_color: str = "000000",
) -> bytes:
    canvas = Image.new("RGB", (32, 32), _hex(bg_color))
    draw = ImageDraw.Draw(canvas)

    _paste_emoji(canvas, emoji_png, 0, 1, 14)
    draw_pixel_text(canvas, 15, 1, temp_str, (255, 170, 0))
    draw_pixel_text(canvas, 15, 9, rain_str, (90, 150, 255))

    draw.line([(0, 17), (31, 17)], fill=(45, 45, 45))

    tw = pixel_text_width(time_str)
    x = max(0, (32 - tw) // 2)
    draw_pixel_text(canvas, x, 20, time_str, (190, 190, 190))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Page 2 : prévision soirée 17h
#
#   y=0  : [emoji 12×12]  "17H" gris      (row 0–6)
#   y=8  :                temp blanc       (row 8–14)
#   y=16 : ────────── séparateur
#   y=19 : pluie% centré bleu             (row 19–25)
#
#   Zéro collision possible : "17H" et temp sur lignes séparées,
#   pluie seule sous le séparateur.
# ---------------------------------------------------------------------------
def _render_page2(
    evening_str: str,
    evening_emoji_png: bytes | None,
    bg_color: str = "000000",
) -> bytes:
    canvas = Image.new("RGB", (32, 32), _hex(bg_color))
    draw = ImageDraw.Draw(canvas)

    _icon, e_temp, e_rain = _parse_forecast(evening_str)

    # Emoji météo 12×12 haut-gauche + "17H" et temp à droite
    _paste_emoji(canvas, evening_emoji_png, 0, 0, 12)
    draw_pixel_text(canvas, 14, 0, "17H", (80, 80, 80))
    draw_pixel_text(canvas, 14, 8, e_temp, (240, 240, 240))

    draw.line([(0, 16), (31, 16)], fill=(45, 45, 45))

    # Bas : emoji 7×7 + pluie% côte à côte
    if e_rain:
        _paste_emoji(canvas, evening_emoji_png, 1, 19, 7)
        draw_pixel_text(canvas, 10, 19, e_rain, (90, 150, 255))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Page 3 : statut métro A + B + temps vélo
#
#   y=2  : A: OK/KO  (gris + vert/rouge)   (row 2–8)
#   y=11 : B: OK/KO  (gris + vert/rouge)   (row 11–17)
#   y=19 : ────────── séparateur
#   y=21 : [vélo 11×11]  chiffre + "m"     (row 22–28)
# ---------------------------------------------------------------------------
def _render_page3(
    metro_a_ok: bool,
    metro_b_ok: bool,
    travel_str: str,
    bike_emoji_png: bytes | None,
    metro_emoji_png: bytes | None,
    bg_color: str = "000000",
) -> bytes:
    canvas = Image.new("RGB", (32, 32), _hex(bg_color))
    draw = ImageDraw.Draw(canvas)

    # Ligne A : Ⓜ️ (9×9) + "A" + OK/KO
    _paste_emoji(canvas, metro_emoji_png, 0, 1, 9)
    x = draw_pixel_text(canvas, 10, 2, "A", (200, 200, 200))
    draw_pixel_text(canvas, x + 1, 2,
                    "OK" if metro_a_ok else "KO",
                    (0, 210, 75) if metro_a_ok else (255, 55, 55))

    # Ligne B : Ⓜ️ (9×9) + "B" + OK/KO
    _paste_emoji(canvas, metro_emoji_png, 0, 10, 9)
    x = draw_pixel_text(canvas, 10, 11, "B", (200, 200, 200))
    draw_pixel_text(canvas, x + 1, 11,
                    "OK" if metro_b_ok else "KO",
                    (0, 210, 75) if metro_b_ok else (255, 55, 55))

    draw.line([(0, 19), (31, 19)], fill=(45, 45, 45))

    _paste_emoji(canvas, bike_emoji_png, 0, 21, 11)

    if travel_str.strip():
        m = re.match(r"(\d+)", travel_str.strip())
        num = m.group(1) if m else travel_str.strip()
        x = draw_pixel_text(canvas, 13, 22, num, (0, 200, 230))
        draw_pixel_text(canvas, x, 22, "m", (0, 145, 175))

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------
async def render_layout_to_png(
    hass,
    time_str: str = "",
    temp_str: str = "",
    rain_str: str = "",
    travel_str: str = "",
    emoji_png: bytes | None = None,
    bg_color: str = "000000",
    text_color: str = "ffffff",
    accent_color: str = "00bfff",
    page: int = 1,
    metro_ok: bool = True,
    metro_a_ok: bool = True,
    metro_b_ok: bool = True,
    metro_emoji_png: bytes | None = None,
    advice_str: str = "",
    condition_str: str = "",
    morning_str: str = "",
    evening_str: str = "",
    morning_emoji_png: bytes | None = None,
    evening_emoji_png: bytes | None = None,
) -> bytes:
    if page == 1:
        return await hass.async_add_executor_job(
            _render_page1,
            time_str, temp_str, rain_str, emoji_png, bg_color,
        )
    elif page == 2:
        return await hass.async_add_executor_job(
            _render_page2,
            evening_str, evening_emoji_png, bg_color,
        )
    else:
        return await hass.async_add_executor_job(
            _render_page3,
            metro_a_ok, metro_b_ok, travel_str, emoji_png, metro_emoji_png, bg_color,
        )
