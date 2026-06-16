"""iPIXEL Color Bluetooth API client - Refactored version."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .bluetooth.client import BluetoothClient
from .device.commands import make_power_command, make_brightness_command
from .device.clock import make_clock_mode_command, make_time_command
from .device.text import make_text_command
from .device.image import make_image_command
from .device.info import build_device_info_command, parse_device_response
from .display.text_renderer import render_text_to_png
from .display.emoji_renderer import render_emoji_to_png
from .display.widget_renderer import render_page_to_png
from .const import OPT_OVERRIDE_DIMENSIONS, OPT_PANEL_WIDTH, OPT_PANEL_HEIGHT
from .exceptions import iPIXELError, iPIXELConnectionError, iPIXELTimeoutError

_LOGGER = logging.getLogger(__name__)


class iPIXELAPI:

    def __init__(self, hass: HomeAssistant, address: str, entry=None) -> None:
        self._address = address
        self._hass = hass
        self._entry = entry
        self._bluetooth = BluetoothClient(hass, address)
        self._power_state = False
        self._orientation = 0
        self._fun_mode = False
        self._device_info: dict[str, Any] | None = None
        self._device_response: bytes | None = None

    def _apply_dimension_override(self, info: dict[str, Any]) -> dict[str, Any]:
        """Honor user dimension overrides (B.K. Light & co. report wrong sizes)."""
        entry = self._entry
        if entry is None:
            return info
        opts = entry.options or {}
        if not opts.get(OPT_OVERRIDE_DIMENSIONS):
            return info
        w = int(opts.get(OPT_PANEL_WIDTH, 0) or 0)
        h = int(opts.get(OPT_PANEL_HEIGHT, 0) or 0)
        if w > 0:
            info["width"] = w
        if h > 0:
            info["height"] = h
        return info

    async def connect(self) -> bool:
        return await self._bluetooth.connect(self._notification_handler)

    async def disconnect(self) -> None:
        await self._bluetooth.disconnect()

    async def set_power(self, on: bool) -> bool:
        command = make_power_command(on)
        success = await self._bluetooth.send_command(command)
        if success:
            self._power_state = on
            _LOGGER.debug("Power set to %s", "ON" if on else "OFF")
        return success

    async def set_brightness(self, brightness: int) -> bool:
        try:
            command = make_brightness_command(brightness)
            success = await self._bluetooth.send_command(command)
            if success:
                _LOGGER.debug("Brightness set to %d", brightness)
            else:
                _LOGGER.error("Failed to set brightness to %d", brightness)
            return success
        except ValueError as err:
            _LOGGER.error("Invalid brightness value: %s", err)
            return False
        except Exception as err:
            _LOGGER.error("Error setting brightness: %s", err)
            return False

    async def sync_time(self) -> bool:
        try:
            time_command = make_time_command()
            success = await self._bluetooth.send_command(time_command)
            if success:
                _LOGGER.debug("Time synchronized to device")
            else:
                _LOGGER.error("Failed to sync time")
            return success
        except Exception as err:
            _LOGGER.error("Error syncing time: %s", err)
            return False

    async def set_clock_mode(self, style: int = 1, date: str = "", show_date: bool = True, format_24: bool = True) -> bool:
        try:
            command = make_clock_mode_command(style, date, show_date, format_24)
            success = await self._bluetooth.send_command(command)
            if not success:
                _LOGGER.error("Failed to set clock mode")
                return False
            _LOGGER.info("Clock mode set: style=%d, 24h=%s, show_date=%s", style, format_24, show_date)
            time_success = await self.sync_time()
            if not time_success:
                _LOGGER.warning("Clock mode set but time sync failed")
            return success
        except ValueError as err:
            _LOGGER.error("Invalid clock mode parameters: %s", err)
            return False
        except Exception as err:
            _LOGGER.error("Error setting clock mode: %s", err)
            return False

    async def probe_device_info(self) -> dict[str, Any] | None:
        """Best-effort: query the panel over BLE and log what it reports.

        Answers "what does my panel actually say over Bluetooth". Never breaks
        setup: failures are logged and the cached 32x32 default is kept. If the
        panel returns valid dimensions and the user hasn't set a manual
        override, we adopt them (helps non-32x32 models auto-configure).
        """
        try:
            command = build_device_info_command()
        except ImportError:
            return None
        response = await self._bluetooth.query(command)
        if not response:
            _LOGGER.info("Device info: no BLE response (panel may not support the query)")
            return None
        _LOGGER.info("Device info raw BLE response: %s", response.hex())
        try:
            parsed = parse_device_response(response)
        except Exception as err:  # noqa: BLE001
            _LOGGER.info("Device info: could not parse response (%s)", err)
            return None
        _LOGGER.info(
            "Device reports: %sx%s, type=%s, mcu=%s, wifi=%s, has_wifi=%s",
            parsed.get("width"), parsed.get("height"), parsed.get("device_type"),
            parsed.get("mcu_version"), parsed.get("wifi_version"), parsed.get("has_wifi"),
        )
        # Adopt reported dimensions only when sane and not overridden by the user.
        opts = (self._entry.options if self._entry else {}) or {}
        if not opts.get(OPT_OVERRIDE_DIMENSIONS):
            w, h = parsed.get("width"), parsed.get("height")
            if isinstance(w, int) and isinstance(h, int) and 8 <= w <= 256 and 8 <= h <= 256:
                if self._device_info is None:
                    await self.get_device_info()
                self._device_info["width"] = w
                self._device_info["height"] = h
                self._device_info["device_type"] = parsed.get("device_type", 0)
                self._device_info["device_type_str"] = parsed.get("device_type_str", "Unknown")
                self._device_info["mcu_version"] = parsed.get("mcu_version", "Unknown")
                _LOGGER.info("Adopted panel dimensions %dx%d from BLE", w, h)
        return parsed

    async def get_device_info(self) -> dict[str, Any] | None:
        if self._device_info is not None:
            return self._device_info
        _LOGGER.debug("Using default device info (notify already acquired by connect)")
        self._device_info = self._apply_dimension_override({
            "width": 32,
            "height": 32,
            "device_type": 0,
            "device_type_str": "Unknown",
            "led_type": 0,
            "mcu_version": "Unknown",
            "wifi_version": "Unknown",
            "has_wifi": False,
            "password_flag": 255
        })
        return self._device_info

    async def display_text(self, text: str, antialias: bool = True, font_size: float | None = None, font: str | None = None, line_spacing: int = 0, text_color: str = "ffffff", bg_color: str = "000000") -> bool:
        try:
            device_info = await self.get_device_info()
            width = device_info["width"]
            height = device_info["height"]
            png_data = render_text_to_png(text, width, height, antialias, font_size, font, line_spacing, text_color, bg_color)
            commands = make_image_command(image_bytes=png_data, file_extension=".png", resize_method="crop", device_info_dict=device_info)
            for i, command in enumerate(commands):
                success = await self._bluetooth.send_command(command)
                if not success:
                    _LOGGER.error("Failed to send image frame %d/%d", i + 1, len(commands))
                    return False
            return True
        except Exception as err:
            _LOGGER.error("Error displaying text: %s", err)
            return False

    async def display_text_pypixelcolor(self, text: str, color: str = "ffffff", bg_color: str | None = None, font: str = "CUSONG", animation: int = 0, speed: int = 80, rainbow_mode: int = 0) -> bool:
        try:
            device_info = await self.get_device_info()
            device_height = device_info["height"]
            commands = make_text_command(text=text, color=color, bg_color=bg_color, font=font, animation=animation, speed=speed, rainbow_mode=rainbow_mode, save_slot=0, device_height=device_height)
            for i, command in enumerate(commands):
                success = await self._bluetooth.send_command(command)
                if not success:
                    _LOGGER.error("Failed to send text frame %d/%d", i + 1, len(commands))
                    return False
            return True
        except Exception as err:
            _LOGGER.error("Error displaying pypixelcolor text: %s", err)
            return False

    async def _send_image_commands(self, commands: list[bytes], label: str) -> bool:
        """Envoie une liste de commandes image sans reconnexion."""
        total_bytes = sum(len(c) for c in commands)
        _LOGGER.info(
            "Image transfer [%s]: %d window(s), %d bytes total",
            label, len(commands), total_bytes
        )
        for idx, command in enumerate(commands):
            _LOGGER.info("  Window %d/%d: %d bytes", idx + 1, len(commands), len(command))

        if not self.is_connected:
            if not await self._bluetooth.connect(self._notification_handler):
                _LOGGER.error("Connect before image failed")
                return False
            await asyncio.sleep(0.2)

        for idx, command in enumerate(commands):
            success = await self._bluetooth.send_command(command)
            if not success:
                _LOGGER.error("Failed window %d/%d for [%s]", idx + 1, len(commands), label)
                return False
            if idx < len(commands) - 1:
                await asyncio.sleep(0.5)

        _LOGGER.info("Image [%s] displayed — %d bytes OK", label, total_bytes)
        return True

    async def display_widgets(self, page: dict, save_slot: int = 0) -> bool:
        """Render a widget page (the generic engine) and push it to the device.

        save_slot >= 1 also stores the page in the device's memory so it can be
        recalled later with show_slot() without Home Assistant.
        """
        try:
            device_info = await self.get_device_info()
            png_data = await render_page_to_png(
                self._hass, page, device_info["width"], device_info["height"]
            )
            commands = make_image_command(
                image_bytes=png_data, file_extension=".png",
                resize_method="crop", device_info_dict=device_info,
                save_slot=save_slot,
            )
            return await self._send_image_commands(commands, f"page(slot={save_slot})")
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Error displaying widget page: %s", err)
            return False

    async def display_image_file(self, data: bytes, file_extension: str = ".gif", save_slot: int = 0) -> bool:
        """Send a raw image/GIF file as-is. Animated GIFs play natively on the
        panel (pypixelcolor uploads every frame)."""
        try:
            device_info = await self.get_device_info()
            commands = make_image_command(
                image_bytes=data, file_extension=file_extension,
                resize_method="crop", device_info_dict=device_info,
                save_slot=save_slot,
            )
            return await self._send_image_commands(commands, f"file{file_extension}(slot={save_slot})")
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Error sending image file: %s", err)
            return False

    async def set_orientation(self, orientation: int) -> bool:
        """Rotate the display: 0=0°, 1=90°, 2=180°, 3=270°."""
        from .device.commands import make_orientation_command
        try:
            ok = await self._bluetooth.send_command(make_orientation_command(orientation))
            if ok:
                self._orientation = int(orientation)
            return ok
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error setting orientation: %s", err)
            return False

    async def set_fun_mode(self, enable: bool) -> bool:
        """Toggle the panel's built-in 'fun' effect mode.

        Byte sequence is identical to the official app (verified). If nothing
        visible happens, this panel firmware likely ignores it or only animates
        existing content — try enabling it, then sending a page/text.
        """
        from .device.commands import make_fun_mode_command
        try:
            cmd = make_fun_mode_command(enable)
            _LOGGER.info("Fun mode %s -> sending %s", "ON" if enable else "OFF", cmd.hex())
            ok = await self._bluetooth.send_command(cmd)
            if ok:
                self._fun_mode = bool(enable)
            return ok
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error setting fun mode: %s", err)
            return False

    async def set_rhythm_animation(self, style: int, frame: int) -> bool:
        """Play a self-contained rhythm animation (no audio feed needed)."""
        from .device.commands import make_rhythm_animation_command
        try:
            return await self._bluetooth.send_command(make_rhythm_animation_command(style, frame))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error setting rhythm animation: %s", err)
            return False

    async def set_rhythm_levels(self, style: int, levels: list[int]) -> bool:
        """Drive the rhythm bars from externally supplied audio levels (11 x 0-15)."""
        from .device.commands import make_rhythm_levels_command
        try:
            return await self._bluetooth.send_command(make_rhythm_levels_command(style, levels))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error setting rhythm levels: %s", err)
            return False

    async def show_slot(self, number: int) -> bool:
        """Recall a stored program slot on the device."""
        from .device.commands import make_show_slot_command
        try:
            return await self._bluetooth.send_command(make_show_slot_command(number))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error showing slot %s: %s", number, err)
            return False

    async def delete_slot(self, number: int) -> bool:
        """Delete a stored program slot on the device."""
        from .device.commands import make_delete_slot_command
        try:
            return await self._bluetooth.send_command(make_delete_slot_command(number))
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error deleting slot %s: %s", number, err)
            return False

    async def display_emoji(self, emoji: str, bg_color: str = "000000", width_override: int | None = None, height_override: int | None = None) -> bool:
        """Display an emoji using async Twemoji rendering."""
        try:
            base_info = await self.get_device_info()
            width = width_override or base_info["width"]
            height = height_override or base_info["height"]
            device_info = {**base_info, "width": width, "height": height}
            _LOGGER.info("Rendering emoji %r at %dx%d", emoji, width, height)
            png_data = await render_emoji_to_png(self._hass, emoji, width, height, bg_color)
            if png_data is None:
                _LOGGER.error("Could not render emoji %r", emoji)
                return False
            commands = make_image_command(image_bytes=png_data, file_extension=".png", resize_method="crop", device_info_dict=device_info)
            return await self._send_image_commands(commands, f"emoji_{emoji!r}")
        except Exception as err:
            _LOGGER.exception("Error displaying emoji %r: %s", emoji, err)
            return False

    def _notification_handler(self, sender: Any, data: bytearray) -> None:
        _LOGGER.debug("Notification from %s: %s", sender, data.hex())

    @property
    def is_connected(self) -> bool:
        return self._bluetooth.is_connected

    @property
    def power_state(self) -> bool:
        return self._power_state

    @property
    def orientation(self) -> int:
        return self._orientation

    @property
    def fun_mode(self) -> bool:
        return self._fun_mode

    @property
    def address(self) -> str:
        return self._address


__all__ = ["iPIXELAPI", "iPIXELError", "iPIXELConnectionError", "iPIXELTimeoutError"]