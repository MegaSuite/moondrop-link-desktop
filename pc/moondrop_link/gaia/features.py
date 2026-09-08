"""GAIA v3 feature command client.

High-level helpers that talk to the QTIL v3 plugin command set
(see out/notes/v3-codec.md). All functions assume the session already
negotiated GAIA v3 and enable their own notifications where needed.

These encode/parse bytes as reconstructed from the app:
  - V3AncV2Plugin (feature 0x20), V3BatteryPlugin (0x0D),
    V3BasicPlugin (0x00), V3OnebringtwoPlugin (0x14), V3AudioCurationPlugin (0x08)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import constants as C
from .packet import GaiaPacket

log = logging.getLogger("gaia.features")


# ---------------------------------------------------------------------------
# value objects
# ---------------------------------------------------------------------------

@dataclass
class DeviceStatus:
    app_version: str | None = None
    batteries: dict[int, int] = field(default_factory=dict)  # type -> level(0..100,255)
    anc_mode: int | None = None
    anc_switch_conf: bytes | None = None
    onebringtwo_on: bool | None = None
    current_devices: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Basic feature (0x00): version, serial, notification registration, features
# ---------------------------------------------------------------------------

class BasicFeature:
    def __init__(self, s) -> None:  # s: GaiaSession
        self.s = s

    async def get_application_version(self) -> str:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_BASIC, C.T_COMMAND, 5)
        rsp = await self.s.request(pkt)
        return bytes(rsp).decode("utf-8", "replace")

    async def get_supported_features(self) -> list[tuple[int, int]]:
        """feature-list pages; returns [(featureId, version), ...]."""
        out: list[tuple[int, int]] = []
        more = True
        cmd = 1  # V1_GET_SUPPORTED_FEATURES ; then 2 (NEXT) for further pages
        while more:
            pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_BASIC, C.T_COMMAND, cmd)
            data = await self.s.request(pkt)
            if not data:
                break
            more = bool(data[0] & 0x01)
            i = 1
            while i + 1 < len(data):
                out.append((data[i], data[i + 1]))
                i += 2
            cmd = 2
        return out

    async def register_notification(self, feature: int) -> None:
        pkt = GaiaPacket.v3(
            C.VENDOR_QTI_V3, C.FEATURE_BASIC, C.T_COMMAND, 7, bytes([feature])
        )
        await self.s.request(pkt)

    async def cancel_notification(self, feature: int) -> None:
        pkt = GaiaPacket.v3(
            C.VENDOR_QTI_V3, C.FEATURE_BASIC, C.T_COMMAND, 8, bytes([feature])
        )
        await self.s.request(pkt)


# ---------------------------------------------------------------------------
# Battery feature (0x0D)
# ---------------------------------------------------------------------------

class BatteryFeature:
    def __init__(self, s) -> None:
        self.s = s

    async def get_supported(self) -> list[int]:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_BATTERY, C.T_COMMAND, 0)
        data = await self.s.request(pkt)
        return [b for b in data if b in (0, 1, 2, 3)]

    async def get_levels(self, batteries: list[int]) -> dict[int, int]:
        pkt = GaiaPacket.v3(
            C.VENDOR_QTI_V3, C.FEATURE_BATTERY, C.T_COMMAND, 1, bytes(batteries)
        )
        data = await self.s.request(pkt)
        out: dict[int, int] = {}
        for i in range(0, len(data) - 1, 2):
            out[data[i]] = data[i + 1]
        return out

    async def read(self) -> dict[int, int]:
        bats = await self.get_supported()
        if not bats:  # device may return all four; fall back to common set
            bats = [C.BAT_SINGLE_DEVICE, C.BAT_LEFT_DEVICE,
                    C.BAT_RIGHT_DEVICE, C.BAT_CHARGER_CASE]
        return await self.get_levels(bats)


# ---------------------------------------------------------------------------
# ANC_V2 feature (0x20)
# ---------------------------------------------------------------------------

class AncV2Feature:
    def __init__(self, s) -> None:
        self.s = s

    async def get_mode(self) -> int | None:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ANC_V2, C.T_COMMAND, 3)
        data = await self.s.request(pkt)
        return data[0] if data else None

    async def set_mode(self, mode: int) -> None:
        pkt = GaiaPacket.v3(
            C.VENDOR_QTI_V3, C.FEATURE_ANC_V2, C.T_COMMAND, 4, bytes([mode & 0xFF])
        )
        await self.s.request(pkt)

    async def get_switch_conf(self) -> bytes | None:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ANC_V2, C.T_COMMAND, 41)
        data = await self.s.request(pkt)
        return bytes(data) if data is not None else None

    async def set_switch_conf(self, conf: bytes) -> None:
        """conf: 5 bytes [STATE][ANC_ON][ANC_OFF][TRANSPARENT][ORDER]."""
        pkt = GaiaPacket.v3(
            C.VENDOR_QTI_V3, C.FEATURE_ANC_V2, C.T_COMMAND, 42, bytes(conf)
        )
        await self.s.request(pkt)


# ---------------------------------------------------------------------------
# Audio curation feature (0x08) — older devices using feature 8 instead of 32
# ---------------------------------------------------------------------------

class AudioCurationFeature:
    """Audio curation (feature 0x08) — EDGE's ANC control.

    Commands (V3AudioCurationPlugin):
      GET_AC_STATE=0, SET_AC_STATE=1, GET_MODES_COUNT=2,
      GET_CURRENT_MODE=3, SET_MODE=4, GET_TOGGLE_CONFIGURATION_COUNT=7,
      GET_TOGGLE_CONFIGURATION=8, SET_TOGGLE_CONFIGURATION=9,
      GET_CURRENT_ANC_SWITCH_CONF=41, SET_ANC_SWITCH_CONF=42
    Notifications: V1_AC_STATE_CHANGE=0, V1_MODE_CHANGE=1, ...
    """

    def __init__(self, s) -> None:
        self.s = s

    async def _raw(self, cmd: int, payload: bytes = b"", wait: bool = True) -> bytes:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_AUDIO_CURATION,
                            C.T_COMMAND, cmd, payload)
        return await self.s.request(pkt, wait=wait)

    async def get_ac_state(self) -> bytes | None:
        data = await self._raw(0)
        return bytes(data) if data else None

    async def get_modes_count(self) -> int | None:
        data = await self._raw(2)
        return data[0] if data else None

    async def get_toggle_conf_count(self) -> int | None:
        data = await self._raw(7)
        return data[0] if data else None

    async def get_toggle_conf(self, index: int = 0) -> bytes | None:
        data = await self._raw(8, bytes([index]))
        return bytes(data) if data is not None else None

    async def get_mode(self) -> bytes | None:
        data = await self._raw(3)
        return bytes(data) if data else None

    async def set_mode(self, mode: int) -> None:
        # fire-and-forget: EDGE does not ack AC set commands but applies them
        await self._raw(4, bytes([mode & 0xFF]), wait=False)

    async def set_state(self, state_idx: int) -> None:
        """Select an AC mode by state index.

        EDGE firmware expects a bit mask (1 << state_idx) as the SET_MODE
        payload: 1 -> off, 2 -> ANC, 4 -> transparent (live-verified).
        """
        if state_idx not in C.AC_SET_PAYLOAD:
            raise ValueError(f"unknown AC state index {state_idx}")
        await self.set_mode(C.AC_SET_PAYLOAD[state_idx])

    async def get_anc_switch_conf(self) -> bytes | None:
        data = await self._raw(41)
        return bytes(data) if data is not None else None

    async def set_anc_switch_conf(self, conf: bytes) -> None:
        await self._raw(42, bytes(conf), wait=False)


# ---------------------------------------------------------------------------
# OneBringTwo / multipoint feature (0x14)  — "device dual connection"
# ---------------------------------------------------------------------------

class OneBringTwoFeature:
    def __init__(self, s) -> None:
        self.s = s

    async def get_state(self) -> bool | None:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ONEBRINGTWO, C.T_COMMAND, 1)
        data = await self.s.request(pkt)
        return bool(data[0]) if data else None

    async def set_state(self, enabled: bool) -> None:
        await self.s.request(
            GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ONEBRINGTWO, C.T_COMMAND, 2,
                          bytes([1 if enabled else 0])),
            wait=False,
        )

    async def get_timeout(self) -> int | None:
        pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ONEBRINGTWO, C.T_COMMAND, 3)
        data = await self.s.request(pkt)
        return data[0] if data else None

    async def set_timeout(self, seconds: int) -> None:
        await self.s.request(
            GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ONEBRINGTWO, C.T_COMMAND, 4,
                          bytes([seconds & 0xFF])),
            wait=False,
        )

    async def get_current_devices(self) -> list[dict]:
        """List current linked devices.

        Each GAIA response carries exactly one DeviceInfo:
          [deviceNum:1][addr:6][name utf8...]
        When there are no more devices the firmware repeats the last entry, so
        we stop as soon as a response duplicates an already-collected device.
        """
        devices: list[dict] = []
        seen: set[str] = set()
        # first page via cmd 5, then follow-ups via cmd 6 (guard against loops)
        for cmd in [5] + [6] * 3:
            pkt = GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ONEBRINGTWO,
                                C.T_COMMAND, cmd)
            try:
                data = await self.s.request(pkt)
            except GaiaError:
                break
            if len(data) < 7:
                break
            num = data[0]
            addr = ":".join(f"{b:02X}" for b in data[1:7])
            name = bytes(data[7:]).decode("utf-8", "replace")
            key = addr + "|" + name
            if key in seen:  # repeated entry = end of list
                break
            seen.add(key)
            devices.append({"num": num, "address": addr, "name": name})
        return devices

    async def disconnect_device(self, address: str, name: str = "") -> None:
        """addr like AA:BB:CC:DD:EE:FF; payload num=0? + 6-byte addr + name."""
        addr_bytes = bytes(int(x, 16) for x in address.split(":"))
        if len(addr_bytes) != 6:
            raise ValueError("address must be 6 bytes")
        await self.disconnect_entry(0, address, name)

    async def disconnect_entry(self, num: int, address: str, name: str) -> None:
        """Disconnect one linked device; payload mirrors DeviceInfo entries
        returned by get_current_devices(): [num:1][addr:6][name utf8].
        """
        addr_bytes = bytes(int(x, 16) for x in address.split(":"))
        if len(addr_bytes) != 6:
            raise ValueError("address must be 6 bytes")
        payload = bytes([num & 0xFF]) + addr_bytes + name.encode("utf-8")
        await self.s.request(
            GaiaPacket.v3(C.VENDOR_QTI_V3, C.FEATURE_ONEBRINGTWO, C.T_COMMAND, 7,
                          payload),
            wait=False,
        )


def build_anc_switch_conf(
    state: int, anc_on: int, anc_off: int, transparent: int, order: int
) -> bytes:
    return bytes([state, anc_on, anc_off, transparent, order])
