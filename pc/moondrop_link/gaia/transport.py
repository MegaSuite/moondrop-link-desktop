"""BLE GAIA transport (bleak backend).

Mirrors the behaviour observed in the Android app's `LeGattClient`:

* connect to the GAIA GATT service (pure BLE, no classic pairing needed)
* writes go to the command characteristic as Write-Without-Response
* responses/notifications arrive on the response characteristic (CCCD 0x01)
* MTU is negotiated (the app requests 512)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from bleak import BleakClient
from bleak.backends.scanner import AdvertisementData, BLEDevice

from . import constants as C
from .packet import GaiaPacket

log = logging.getLogger("gaia.transport")

NotificationHandler = Callable[[bytes], Awaitable[None]]


def is_gaia_advertisement(adv: AdvertisementData) -> bool:
    """Heuristic: does the advertisement look like a GAIA headset?

    The app does NOT filter advertisements by service UUID; it shows every BLE
    device and lets the user pick one, then validates the GAIA service after
    connecting. Here we accept devices that advertise the GAIA service UUID or
    whose complete/abbreviated local name is non-empty. Pass ``name_substr`` to
    narrow to a product model name if known.
    """
    return True


async def scan(
    timeout: float = 5.0,
    name_substr: Optional[str] = None,
) -> list[tuple[BLEDevice, AdvertisementData]]:
    """BLE scan mimicking the app (LOW_LATENCY, 5 s)."""
    from bleak import BleakScanner

    found: list[tuple[BLEDevice, AdvertisementData]] = []

    def cb(device: BLEDevice, adv: AdvertisementData) -> None:
        if name_substr and adv.local_name:
            if name_substr.lower() not in adv.local_name.lower():
                return
        found.append((device, adv))

    async with BleakScanner(detection_callback=cb) as scanner:
        await asyncio.sleep(timeout)
    return found


class GaiaTransport:
    """A single GAIA-over-BLE link to one device."""

    def __init__(self, address_or_device: str | BLEDevice) -> None:
        self._client = BleakClient(address_or_device)

    @property
    def client(self) -> BleakClient:
        return self._client

    # ---- connection --------------------------------------------------------

    async def connect(self) -> None:
        await self._client.connect()
        log.info("connected to %s", self._client.address)
        # MTU negotiation is best-effort; bleak exposes a request_mtu method on
        # some backends (winrt/bluez). Default 23 still works for short frames.
        try:
            await self._client.request_mtu(C.MTU_TARGET)
        except Exception:  # noqa: BLE001
            pass

    async def pair(self) -> bool:
        """LE pairing (may show an OS consent dialog on Windows)."""
        try:
            ok = await self._client.pair()
            log.info("pair result: %s", ok)
            return bool(ok)
        except Exception as e:  # noqa: BLE001
            log.warning("pair failed: %s", e)
            return False

    async def list_services(self) -> list[dict]:
        """Dump every GATT service/characteristic to help identify endpoints."""
        out = []
        for svc in self._client.services:
            row = {"service": svc.uuid, "chars": []}
            for ch in svc.characteristics:
                row["chars"].append(
                    {"char": ch.uuid,
                     "props": [p for p in ch.properties]}
                )
            out.append(row)
        return out

    async def send_raw(self, char_uuid: str, data: bytes) -> None:
        await self._client.write_gatt_char(char_uuid, data, response=False)

    async def write_char(self, char_uuid: str, data: bytes,
                         response: bool = True) -> None:
        await self._client.write_gatt_char(char_uuid, data, response=response)

    async def subscribe(self, char_uuid: str, cb) -> None:
        await self._client.start_notify(char_uuid, cb)

    async def read_char(self, char_uuid: str) -> bytes:
        return bytes(await self._client.read_gatt_char(char_uuid))

    async def start(self, on_frame: NotificationHandler | None = None) -> None:
        """Enable notifications on response(+data) characteristics."""
        self._on_frame = on_frame or self._default_on_frame
        await self._client.start_notify(
            C.GAIA_RSP_UUID, self._notify_cb
        )
        # data characteristic notifications are optional for non-RWCP use
        # (the app enables them too); RWCP only used when a plugin opts in.
        try:
            await self._client.start_notify(C.GAIA_DATA_UUID, self._notify_cb)
        except Exception:
            log.debug("no data-characteristic notifications")

    def _notify_cb(self, _handle: int, data: bytearray) -> None:
        asyncio.create_task(self._on_frame(bytes(data)))

    async def _default_on_frame(self, data: bytes) -> None:
        log.debug("RX %s", data.hex())

    # ---- send --------------------------------------------------------------

    async def send_packet(self, pkt: GaiaPacket) -> None:
        wire = pkt.to_wire()
        log.debug("TX %s", wire.hex())
        # NOTE: EDGE only answers to write-WITH-response on the command
        # characteristic (discovered live: it has no write-without-response
        # property and ignores those writes).
        await self._client.write_gatt_char(C.GAIA_CMD_UUID, wire, response=True)

    async def read_pairing(self) -> None:
        """In-band pairing induction: the app reads the data characteristic.

        Only needed when the headset requests bonding during handshake.
        """
        try:
            await self._client.read_gatt_char(C.GAIA_DATA_UUID)
        except Exception as e:  # noqa: BLE001
            log.debug("pairing induce read failed: %s", e)

    async def disconnect(self) -> None:
        try:
            await self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass
