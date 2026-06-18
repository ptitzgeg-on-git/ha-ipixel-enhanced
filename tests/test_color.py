"""Colour conversion helpers (color.py)."""
import pytest


def test_hex_to_rgb_plain(color_mod):
    assert color_mod.hex_to_rgb("ff0000") == (255, 0, 0)
    assert color_mod.hex_to_rgb("00ff00") == (0, 255, 0)
    assert color_mod.hex_to_rgb("0000ff") == (0, 0, 255)


def test_hex_to_rgb_with_hash(color_mod):
    assert color_mod.hex_to_rgb("#ffffff") == (255, 255, 255)
    assert color_mod.hex_to_rgb("#000000") == (0, 0, 0)


@pytest.mark.parametrize("bad", ["fff", "12345", "1234567", "", "gggggg"])
def test_hex_to_rgb_rejects_bad_input(color_mod, bad):
    with pytest.raises(ValueError):
        color_mod.hex_to_rgb(bad)


def test_hex_to_rgb_normalized(color_mod):
    assert color_mod.hex_to_rgb_normalized("ffffff") == (1.0, 1.0, 1.0)
    r, g, b = color_mod.hex_to_rgb_normalized("ff8000")
    assert r == 1.0 and 0.49 < g < 0.51 and b == 0.0


def test_rgb_to_hex_roundtrip(color_mod):
    for hexval in ("ffaa00", "123456", "000000", "ffffff"):
        assert color_mod.rgb_to_hex(*color_mod.hex_to_rgb(hexval)) == hexval
