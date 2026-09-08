"""Device manager used by the GUI (keeps one live GAIA session open)."""

from __future__ import annotations

import asyncio
import logging

from .gaia import constants as C
from .gaia.features import (
    AudioCurationFeature,
    BasicFeature,
    BatteryFeature,
    OneBringTwoFeature,
)
from .gaia.session import GaiaError, GaiaSession
from .gaia.transport import GaiaTransport, scan

log = logging.getLogger("edge.app")

FEATURE_NAMES = {
    0x00: "BASIC", 0x01: "EARBUD", 0x03: "VOICE_UI", 0x05: "MUSIC_PROCESSING",
    0x06: "UPGRADE", 0x08: "AUDIO_CURATION", 0x0D: "BATTERY", 0x0F: "DAC_GAIN",
    0x10: "CODEC_TYPE", 0x11: "LIGHT_SENSOR", 0x14: "ONEBRINGTWO",
    0x15: "BT_ADDRESS",
}


class EdgeError(Exception):
    pass


class EdgeClient:
    """One persistent GAIA-over-BLE session to a Moondrop EDGE."""

    def __init__(self, address: str, request_timeout: float = 4.0) -> None:
        self.address = address
        self._session: GaiaSession | None = None
        self._timeout = request_timeout

    @property
    def connected(self) -> bool:
        return bool(self._session and self._session.connected)

    async def connect(self) -> None:
        if self.connected:
            return
        tr = GaiaTransport(self.address)
        s = GaiaSession(tr, request_timeout=self._timeout)
        await s.open()
        await s.probe_version()  # best-effort; logs version
        self._session = s
        log.info("EDGE %s connected", self.address)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ---- helpers -----------------------------------------------------------

    def _check(self):
        if not self.connected or self._session is None:
            raise EdgeError("not connected")

    async def _run(self, coro):
        self._check()
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout + 4)
        except (GaiaError, asyncio.TimeoutError) as e:  # noqa: BLE001
            raise EdgeError(f"device error: {e}") from e

    async def read_status(self) -> dict:
        """Gather the overview data shown by the GUI (never raises for a
        single failed read; per-item value becomes None)."""
        self._check()
        s = self._session
        basic, bat = BasicFeature(s), BatteryFeature(s)
        ac, mp = AudioCurationFeature(s), OneBringTwoFeature(s)

        async def safe(label: str, fn):
            try:
                return await asyncio.wait_for(fn(), timeout=self._timeout + 4)
            except Exception as e:  # noqa: BLE001
                log.warning("read %s failed: %s", label, e)
                return None

        ver = await safe("version", basic.get_application_version)
        feats = await safe("features", basic.get_supported_features)
        batt = await safe("battery", bat.read)
        mode_b = await safe("ac-mode", ac.get_mode)
        mp_on = await safe("multipoint", mp.get_state)
        devs = await safe("devices", mp.get_current_devices)

        mode_idx = mode_b[0] if isinstance(mode_b, (bytes, bytearray)) and mode_b else None
        return {
            "address": self.address,
            "version": ver,
            "features": feats,
            "battery": batt,                      # {type: level}
            "anc_index": mode_idx,
            "anc_name": C.AC_STATE_NAMES.get(mode_idx, "?") if mode_idx is not None else None,
            "multipoint": mp_on,
            "devices": devs,
        }

    async def set_anc(self, state) -> dict:
        """state: 'off'|'anc'|'transparent' or index 0..2."""
        if isinstance(state, str):
            idx = {name: i for i, name in C.AC_STATE_NAMES.items()}.get(state)
            if idx is None:
                raise EdgeError(f"unknown ANC state {state!r}")
        else:
            idx = int(state)
        await self._run(AudioCurationFeature(self._session).set_state(idx))
        await asyncio.sleep(0.6)
        st = await self.read_status()
        return {"requested": state, "now": st["anc_name"], "index": st["anc_index"]}

    async def set_multipoint(self, enabled: bool) -> dict:
        await self._run(OneBringTwoFeature(self._session).set_state(bool(enabled)))
        await asyncio.sleep(0.6)
        st = await self.read_status()
        return {"requested": enabled, "now": st["multipoint"]}

    async def disconnect_linked(self, num: int, address: str, name: str) -> None:
        """Ask the EDGE to drop one linked device (OneBringTwo cmd 7)."""
        self._check()
        await self._run(
            OneBringTwoFeature(self._session).disconnect_entry(num, address, name)
        )


async def find_devices(name_substr: str = "EDGE", timeout: float = 4.0) -> list[dict]:
    found = await scan(timeout=timeout, name_substr=name_substr or None)
    seen: dict[str, dict] = {}
    for dev, adv in found:
        key = dev.address
        nm = adv.local_name or dev.name or "<unknown>"
        if key not in seen or (adv.rssi or 0) > (seen[key]["rssi"] or -999):
            seen[key] = {"name": nm, "address": key, "rssi": adv.rssi}
    return sorted(seen.values(), key=lambda d: -(d["rssi"] or 0))
