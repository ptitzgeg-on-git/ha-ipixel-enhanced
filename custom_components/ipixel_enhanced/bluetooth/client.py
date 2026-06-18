"""Bluetooth client management for iPIXEL Color devices."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, TYPE_CHECKING

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from homeassistant.components import bluetooth

from ..const import WRITE_UUID, NOTIFY_UUID
from ..exceptions import iPIXELConnectionError

_LOGGER = logging.getLogger(__name__)

_REQUESTED_MTU = 256
_DEFAULT_CHUNK = 20

# Seuil au-delà duquel on considère une commande comme "grosse" (image)
_LARGE_CMD_THRESHOLD = 200


class BluetoothClient:
    """Manages Bluetooth connection and communication."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self._hass = hass
        self._address = address
        self._client: BleakClientWithServiceCache | None = None
        self._connected = False
        self._notification_handler: Callable | None = None
        self._chunk_size: int = _DEFAULT_CHUNK
        self._capture: asyncio.Future | None = None

    def _on_notify(self, sender: Any, data: bytearray) -> None:
        """Internal notify wrapper: feed any pending capture, then the handler."""
        if self._capture is not None and not self._capture.done():
            try:
                self._capture.set_result(bytes(data))
            except Exception:  # noqa: BLE001
                pass
        if self._notification_handler is not None:
            self._notification_handler(sender, data)

    def _disconnected_callback(self, client: BleakClientWithServiceCache) -> None:
        _LOGGER.warning("iPIXEL device %s disconnected", self._address)
        self._connected = False

    async def connect(self, notification_handler: Callable[[Any, bytearray], None]) -> bool:
        _LOGGER.debug("Connecting to iPIXEL device at %s", self._address)
        try:
            ble_device = bluetooth.async_ble_device_from_address(
                self._hass, self._address, connectable=True
            )
            if not ble_device:
                raise iPIXELConnectionError(
                    f"Device {self._address} not found. "
                    "Ensure the device is powered on and in range."
                )
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                ble_device.name or "iPIXEL Display",
                disconnected_callback=self._disconnected_callback,
                max_attempts=3,
            )
            self._connected = True
            self._notification_handler = notification_handler

            # Lire le MTU négocié (BlueZ le fait automatiquement à la connexion)
            negotiated_mtu = getattr(self._client, "mtu_size", 23)
            if negotiated_mtu > 23:
                self._chunk_size = negotiated_mtu - 3
                _LOGGER.info("MTU auto-négociée : %d → chunk=%d", negotiated_mtu, self._chunk_size)
            else:
                # Tenter une négociation explicite
                try:
                    neg = await self._client.request_mtu(_REQUESTED_MTU)
                    self._chunk_size = max(_DEFAULT_CHUNK, neg - 3)
                    _LOGGER.info("MTU demandée %d → obtenue %d → chunk=%d", _REQUESTED_MTU, neg, self._chunk_size)
                except Exception:
                    self._chunk_size = _DEFAULT_CHUNK
                    _LOGGER.debug("MTU fixée à %d (pas de négociation)", _DEFAULT_CHUNK)

            await self._client.start_notify(NOTIFY_UUID, self._on_notify)
            _LOGGER.info("Connected to iPIXEL — chunk_size=%d", self._chunk_size)
            return True
        except BleakError as err:
            _LOGGER.error("Failed to connect to %s: %s", self._address, err)
            raise iPIXELConnectionError(f"Connection failed: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error connecting to %s: %s", self._address, err)
            raise iPIXELConnectionError(f"Connection failed: {err}") from err

    async def _reconnect_if_needed(self) -> bool:
        """Re-establish the link if the panel dropped it (it disconnects when
        idle). Reuses the notification handler from the first connect, so every
        command path recovers transparently instead of failing silently."""
        if self.is_connected:
            return True
        if self._notification_handler is None:
            return False
        _LOGGER.debug("Link down — reconnecting to %s before sending", self._address)
        try:
            return await self.connect(self._notification_handler)
        except iPIXELConnectionError as err:
            _LOGGER.error("Reconnect to %s failed: %s", self._address, err)
            return False

    async def disconnect(self) -> None:
        if self._client and self._connected:
            try:
                await self._client.stop_notify(NOTIFY_UUID)
                await self._client.disconnect()
                _LOGGER.debug("Disconnected from iPIXEL device")
            except BleakError as err:
                _LOGGER.error("Error during disconnect: %s", err)
            finally:
                self._connected = False
                self._client = None

    async def send_command(self, command: bytes) -> bool:
        """Send command to the device.

        - Petites commandes (texte ≤200 octets) : Write With Response, fiable
        - Grandes commandes (images >200 octets) : Write Without Response, streaming
          Si le device ne supporte pas WwoR → fallback Write With Response
        """
        if not await self._reconnect_if_needed():
            _LOGGER.error("Device not connected")
            return False

        chunk_size = self._chunk_size
        total = len(command)
        is_image = total > _LARGE_CMD_THRESHOLD

        _LOGGER.debug("send_command: %d bytes, %d chunks, image=%s", total, -(-total // chunk_size), is_image)

        try:
            if is_image:
                # Write Without Response : plus rapide, adapté au streaming pixel
                _LOGGER.info("Image transfer: %d bytes via WwoR (chunk=%d)", total, chunk_size)
                for i in range(0, total, chunk_size):
                    await self._client.write_gatt_char(
                        WRITE_UUID,
                        command[i: i + chunk_size],
                        response=False,
                    )
                    await asyncio.sleep(0.01)  # 10 ms — le device stream les données
            else:
                # Write With Response : fiable pour les commandes texte courtes
                for i in range(0, total, chunk_size):
                    await self._client.write_gatt_char(
                        WRITE_UUID,
                        command[i: i + chunk_size],
                        response=True,
                    )
                    await asyncio.sleep(0.04)

            return True

        except BleakError as err:
            if is_image:
                # WwoR non supporté ou erreur → fallback Write With Response
                _LOGGER.warning("WwoR failed (%s), fallback to Write With Response", err)
                try:
                    for i in range(0, total, chunk_size):
                        await self._client.write_gatt_char(
                            WRITE_UUID,
                            command[i: i + chunk_size],
                            response=True,
                        )
                        await asyncio.sleep(0.08)
                    return True
                except BleakError as err2:
                    _LOGGER.error("Image fallback also failed: %s", err2)
                    return False
            _LOGGER.error("Failed to send command: %s", err)
            return False

    async def query(self, command: bytes, timeout: float = 2.0) -> bytes | None:
        """Send a small command and return the next notification (or None)."""
        if not self._connected or not self._client:
            return None
        loop = asyncio.get_running_loop()
        self._capture = loop.create_future()
        try:
            for i in range(0, len(command), self._chunk_size):
                await self._client.write_gatt_char(
                    WRITE_UUID, command[i: i + self._chunk_size], response=True
                )
            return await asyncio.wait_for(self._capture, timeout)
        except (asyncio.TimeoutError, BleakError) as err:
            _LOGGER.debug("query: no response (%s)", err)
            return None
        finally:
            self._capture = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client and self._client.is_connected

    @property
    def address(self) -> str:
        return self._address
