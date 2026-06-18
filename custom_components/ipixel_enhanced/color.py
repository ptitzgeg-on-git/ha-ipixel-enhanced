"""Colour conversion helpers for the iPIXEL Color integration."""
from __future__ import annotations

from .common import rgb_to_hex  # re-exported for convenience

__all__ = ["hex_to_rgb", "hex_to_rgb_normalized", "rgb_to_hex"]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert a hex colour string (e.g. 'ffffff' or '#ffffff') to an RGB tuple.

    Raises:
        ValueError: if the string is not 6 hex digits.
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color length: {hex_color} (expected 6 characters)")
    try:
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
    except ValueError as e:
        raise ValueError(f"Invalid hex color format: {hex_color}") from e


def hex_to_rgb_normalized(hex_color: str) -> tuple[float, float, float]:
    """Convert a hex colour string to a normalized (0.0-1.0) RGB tuple."""
    r, g, b = hex_to_rgb(hex_color)
    return (r / 255.0, g / 255.0, b / 255.0)
