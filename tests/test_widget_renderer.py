"""Widget rendering engine (display/widget_renderer.py).

Pure PIL path, exercised against the real bundled fonts. No HA, no BLE.
"""
import io

import pytest
from PIL import Image


# --- parse_color ----------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        ("ff0000", (255, 0, 0)),
        ("#00ff00", (0, 255, 0)),
        ("#0f0", (0, 255, 0)),          # shorthand
        ("red", (255, 0, 0)),           # named
        ("orange", (255, 136, 0)),      # named -> ff8800
        ([1, 2, 3], (1, 2, 3)),         # rgb list
        ((10, 20, 30), (10, 20, 30)),   # rgb tuple
        ("bogus", (0, 0, 0)),           # invalid -> default
        (None, (0, 0, 0)),              # none -> default
    ],
)
def test_parse_color(widget_renderer, value, expected):
    assert widget_renderer.parse_color(value) == expected


def test_parse_color_custom_default(widget_renderer):
    assert widget_renderer.parse_color("nope", (9, 9, 9)) == (9, 9, 9)


def test_parse_color_clamps_list(widget_renderer):
    assert widget_renderer.parse_color([300, -5, 128]) == (255, 0, 128)


# --- _truthy --------------------------------------------------------------
@pytest.mark.parametrize("value", ["1", "true", "on", "yes", "anything", 1, True])
def test_truthy_true(widget_renderer, value):
    assert widget_renderer._truthy(value) is True


@pytest.mark.parametrize(
    "value", ["", "0", "false", "no", "off", "none", "unavailable", "unknown", 0, False]
)
def test_truthy_false(widget_renderer, value):
    assert widget_renderer._truthy(value) is False


# --- emoji codepoints (Twemoji filename rule) -----------------------------
def test_emoji_codepoint_strips_only_fe0f(widget_renderer):
    # ☀️ = 2600 FE0F -> "2600" (FE0F dropped)
    assert widget_renderer._emoji_codepoint("☀️") == "2600"
    # 👨‍💻 keeps the ZWJ joiner (200d)
    assert widget_renderer._emoji_codepoint("\U0001f468‍\U0001f4bb") == "1f468-200d-1f4bb"


# --- geometry -------------------------------------------------------------
def test_place_anchors_on_32x32(widget_renderer):
    place = widget_renderer._place
    assert place("top_left", 10, 10, 32, 32) == (0, 0)
    assert place("bottom_right", 10, 10, 32, 32) == (22, 22)
    assert place("center", 10, 10, 32, 32) == (11, 11)
    assert place("top_right", 10, 10, 32, 32) == (22, 0)
    assert place("bottom_center", 10, 10, 32, 32) == (11, 22)


def test_resolve_position_absolute_with_offset(widget_renderer):
    w = {"x": 5, "y": 6, "dx": 2, "dy": -1}
    assert widget_renderer._resolve_position(w, 4, 4, 32, 32) == (7, 5)


def test_resolve_position_bad_anchor_falls_back_top_left(widget_renderer):
    w = {"anchor": "nonsense"}
    assert widget_renderer._resolve_position(w, 4, 4, 32, 32) == (0, 0)


# --- template resolution --------------------------------------------------
def test_resolve_templates_renders_states(widget_renderer):
    page = {"widgets": [{"type": "text", "text": "{{ states('sensor.temperature') }}C"}]}
    out = widget_renderer._resolve_templates(None, page)
    assert out["widgets"][0]["text"] == "21C"


def test_resolve_templates_bad_template_becomes_empty(widget_renderer):
    page = {"widgets": [{"type": "text", "text": "x{{ broken"}]}
    out = widget_renderer._resolve_templates(None, page)
    # "{{" still present -> our stub renderer returns "" (engine swallows errors)
    assert out["widgets"][0]["text"] == ""


# --- full render ----------------------------------------------------------
def _render(widget_renderer, page):
    return Image.open(io.BytesIO(widget_renderer._render_canvas(page, {}, 32, 32))).convert("RGB")


def test_render_blank_page_is_all_background(widget_renderer):
    img = _render(widget_renderer, {"background": "0000ff", "widgets": []})
    assert img.size == (32, 32)
    assert set(img.getdata()) == {(0, 0, 255)}


def test_render_text_lights_pixels(widget_renderer):
    page = {"background": "000000", "widgets": [
        {"type": "text", "text": "HI", "anchor": "center", "color": "ffffff", "font": "5x5", "size": 8},
    ]}
    img = _render(widget_renderer, page)
    lit = [px for px in img.getdata() if px != (0, 0, 0)]
    assert lit, "text widget drew nothing"
    # crisp 1-bit default -> only the text colour, no anti-aliased greys
    assert all(px == (255, 255, 255) for px in lit)


def test_render_shapes(widget_renderer):
    page = {"background": "000000", "widgets": [
        {"type": "rect", "anchor": "top_left", "width": 10, "height": 10, "color": "2266ff", "fill": True},
        {"type": "progress", "value": 50, "anchor": "bottom_center", "width": 28, "height": 5, "color": "00cc33"},
        {"type": "line", "x": 0, "y": 17, "x2": 31, "y2": 17, "color": "ff0000"},
    ]}
    img = _render(widget_renderer, page)
    colors = set(img.getdata())
    assert (0x22, 0x66, 0xff) in colors   # rect
    assert (0x00, 0xcc, 0x33) in colors   # progress fill
    assert (0xff, 0x00, 0x00) in colors   # line


def test_render_conditional_if(widget_renderer):
    page = {"background": "000000", "widgets": [
        {"type": "rect", "anchor": "center", "width": 32, "height": 32, "color": "00ff00", "if": "1"},
        {"type": "rect", "anchor": "center", "width": 32, "height": 32, "color": "ff0000", "if": "0"},
    ]}
    colors = set(_render(widget_renderer, page).getdata())
    assert (0, 255, 0) in colors        # shown
    assert (255, 0, 0) not in colors    # hidden


def test_render_unknown_widget_does_not_crash(widget_renderer):
    page = {"background": "000000", "widgets": [{"type": "wormhole"}]}
    img = _render(widget_renderer, page)
    assert img.size == (32, 32)


def test_native_text_preview_draws_text(widget_renderer):
    # native_text scrolls on the panel; the preview must still show it statically.
    page = {"background": "000000", "widgets": [
        {"type": "native_text", "text": "HI", "color": "ffffff", "animation": 1},
    ]}
    img = _render(widget_renderer, page)
    lit = [px for px in img.getdata() if px != (0, 0, 0)]
    assert lit, "native_text preview drew nothing"
    assert all(px == (255, 255, 255) for px in lit)


def test_progress_clamps(widget_renderer):
    # over 100 must not paint past the bar width (no exception, full bar)
    page = {"background": "000000", "widgets": [
        {"type": "progress", "value": 999, "x": 0, "y": 0, "width": 32, "height": 4, "color": "00cc33"},
    ]}
    img = _render(widget_renderer, page)
    row = [img.getpixel((x, 0)) for x in range(32)]
    assert all(px == (0, 0xcc, 0x33) for px in row)
