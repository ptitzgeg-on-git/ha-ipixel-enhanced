"""BLE frame encoding for the device-native commands (device/commands.py).

Only the builders that don't depend on the optional `pypixelcolor` package are
tested here; the thin pypixelcolor wrappers are exercised on real hardware.
"""
import pytest


def test_power_command(commands_mod):
    assert commands_mod.make_power_command(True) == bytes([5, 0, 7, 1, 1])
    assert commands_mod.make_power_command(False) == bytes([5, 0, 7, 1, 0])


def test_command_payload_header(commands_mod):
    # length (LE 2 bytes) + opcode (LE 2 bytes) + payload
    frame = commands_mod.make_command_payload(0x8004, bytes([42]))
    assert frame == bytes([5, 0, 0x04, 0x80, 42])
    # length field counts payload + 4
    assert frame[0] + (frame[1] << 8) == len(bytes([42])) + 4


def test_brightness_command_range(commands_mod):
    assert commands_mod.make_brightness_command(50) == bytes([5, 0, 0x04, 0x80, 50])
    assert commands_mod.make_brightness_command(1)[-1] == 1
    assert commands_mod.make_brightness_command(100)[-1] == 100


@pytest.mark.parametrize("bad", [0, -1, 101, 255])
def test_brightness_command_rejects_out_of_range(commands_mod, bad):
    with pytest.raises(ValueError):
        commands_mod.make_brightness_command(bad)


def test_program_command_encoding(commands_mod):
    frame = commands_mod.make_program_command([1, 2, 3])
    n = 3
    total = 6 + n
    assert frame == bytes([total & 0xFF, total >> 8, 0x08, 0x80, n, 0, 1, 2, 3])


def test_program_command_empty_falls_back_to_zero(commands_mod):
    # An empty slot list must not produce a zero-length payload.
    frame = commands_mod.make_program_command([])
    assert frame[4] == 1  # count == 1
    assert frame[-1] == 0  # slot 0


def test_program_command_masks_to_byte(commands_mod):
    frame = commands_mod.make_program_command([256 + 7])
    assert frame[-1] == 7
