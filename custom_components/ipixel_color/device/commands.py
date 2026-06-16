"""Command building for iPIXEL Color devices."""
from __future__ import annotations


def make_power_command(on: bool) -> bytes:
    """Build power control command.
    
    Command format from protocol documentation:
    [5, 0, 7, 1, on_byte] where on_byte = 1 for on, 0 for off
    """
    on_byte = 1 if on else 0
    return bytes([5, 0, 7, 1, on_byte])


def make_brightness_command(brightness: int) -> bytes:
    """Build brightness control command.

    Command 0x8004 from ipixel-ctrl set_brightness.py

    Args:
        brightness: Brightness level from 1 to 100

    Returns:
        Command bytes for brightness control

    Raises:
        ValueError: If brightness is not in valid range (1-100)
    """
    if brightness < 1 or brightness > 100:
        raise ValueError("Brightness must be between 1 and 100")

    return make_command_payload(0x8004, bytes([brightness]))


def make_command_payload(opcode: int, payload: bytes) -> bytes:
    """Create command with header (following ipixel-ctrl/common.py format)."""
    total_length = len(payload) + 4  # +4 for length and opcode

    command = bytearray()
    command.extend(total_length.to_bytes(2, 'little'))  # Length (little-endian)
    command.extend(opcode.to_bytes(2, 'little'))        # Opcode (little-endian)
    command.extend(payload)                             # Payload data

    return bytes(command)


# --- Thin wrappers over pypixelcolor command builders ---------------------
# Each builder returns a SendPlan; we take the single window's raw bytes.
def make_orientation_command(orientation: int) -> bytes:
    """0=0°, 1=90°, 2=180°, 3=270°."""
    from pypixelcolor.commands.set_orientation import set_orientation
    return set_orientation(int(orientation)).windows[0].data


def make_fun_mode_command(enable: bool) -> bytes:
    from pypixelcolor.commands.set_fun_mode import set_fun_mode
    return set_fun_mode(bool(enable)).windows[0].data


def make_show_slot_command(number: int) -> bytes:
    from pypixelcolor.commands.show_slot import show_slot
    return show_slot(int(number)).windows[0].data


def make_delete_slot_command(number: int) -> bytes:
    from pypixelcolor.commands.delete import delete
    return delete(int(number)).windows[0].data


def make_rhythm_animation_command(style: int, frame: int) -> bytes:
    """Self-contained rhythm animation (no audio feed needed). style 0-1, frame 0-7."""
    from pypixelcolor.commands.set_rhythm_mode import set_rhythm_mode_2
    return set_rhythm_mode_2(int(style), int(frame)).windows[0].data


def make_rhythm_levels_command(style: int, levels: list[int]) -> bytes:
    """Audio-reactive bars from externally supplied levels. style 0-4, 11 levels 0-15."""
    from pypixelcolor.commands.set_rhythm_mode import set_rhythm_mode
    lv = (list(levels) + [0] * 11)[:11]
    return set_rhythm_mode(int(style), *[int(x) for x in lv]).windows[0].data


def make_set_pixel_command(x: int, y: int, color: str) -> bytes:
    """Light one pixel (requires DIY/fun mode enabled first). color = 'RRGGBB'."""
    from pypixelcolor.commands.set_fun_mode import set_pixel
    return set_pixel(int(x), int(y), color).windows[0].data


def make_program_command(slots: list[int]) -> bytes:
    """Native animation: tell the device to auto-cycle these stored slots
    (command 0x8008). The panel rotates them by itself, no Home Assistant."""
    s = [int(n) & 0xFF for n in slots] or [0]
    n = len(s)
    total = 6 + n
    return bytes([total & 0xFF, total >> 8, 0x08, 0x80, n & 0xFF, n >> 8] + s)