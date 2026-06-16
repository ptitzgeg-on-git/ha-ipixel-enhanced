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
from .display.layout_renderer import render_layout_to_png
from .display.widget_renderer import render_page_to_png
from .exceptions import iPIXELError, iPIXELConnectionError, iPIXELTimeoutError

_LOGGER = logging.getLogger(__name__)


class iPIXELAPI:

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._address = address
        self._hass = hass
        self._bluetooth = BluetoothClient(hass, address)
        self._power_state = False
        self._device_info: dict[str, Any] | None = None
        self._device_response: bytes | None = None

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

    async def get_device_info(self) -> dict[str, Any] | None:
        if self._device_info is not None:
            return self._device_info
        _LOGGER.debug("Using default device info (notify already acquired by connect)")
        self._device_info = {
            "width": 32,
            "height": 32,
            "device_type": 0,
            "device_type_str": "Unknown",
            "led_type": 0,
            "mcu_version": "Unknown",
            "wifi_version": "Unknown",
            "has_wifi": False,
            "password_flag": 255
        }
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

    async def display_layout(
        self,
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
    ) -> bool:
        """Display a full layout page using PIL rendering."""
        try:
            device_info = await self.get_device_info()
            _LOGGER.info("Rendering layout page %d", page)
            png_data = await render_layout_to_png(
                self._hass, time_str, temp_str, rain_str, travel_str,
                emoji_png, bg_color, text_color, accent_color, page,
                metro_ok, metro_a_ok, metro_b_ok, metro_emoji_png, advice_str,
                condition_str=condition_str,
                morning_str=morning_str,
                evening_str=evening_str,
                morning_emoji_png=morning_emoji_png,
                evening_emoji_png=evening_emoji_png,
            )
            commands = make_image_command(image_bytes=png_data, file_extension=".png", resize_method="crop", device_info_dict=device_info)
            return await self._send_image_commands(commands, f"layout_p{page}")
        except Exception as err:
            _LOGGER.exception("Error displaying layout page %d: %s", page, err)
            return False

    async def display_widgets(self, page: dict) -> bool:
        """Render a widget page (the generic engine) and push it to the device."""
        try:
            device_info = await self.get_device_info()
            png_data = await render_page_to_png(
                self._hass, page, device_info["width"], device_info["height"]
            )
            commands = make_image_command(
                image_bytes=png_data, file_extension=".png",
                resize_method="crop", device_info_dict=device_info,
            )
            return await self._send_image_commands(commands, "page")
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Error displaying widget page: %s", err)
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
    def address(self) -> str:
        return self._address


__all__ = ["iPIXELAPI", "iPIXELError", "iPIXELConnectionError", "iPIXELTimeoutError"]