"""GAIA session: one negotiated link with request/response routing."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from . import constants as C
from .packet import GaiaPacket, v3_decompose
from .transport import GaiaTransport

log = logging.getLogger("gaia.session")

# callback(data, feature, command)
NotifyCb = Callable[[bytes, int, int], Awaitable[None]]


class GaiaError(Exception):
    def __init__(self, kind: str, code: int | None = None, raw: bytes = b""):
        self.kind = kind
        self.code = code
        self.raw = raw
        super().__init__(f"{kind}({code})")

    @classmethod
    def from_v3(cls, payload: bytes) -> "GaiaError":
        code = payload[0] if payload else None
        return cls("v3_error", code, payload)

    @classmethod
    def timeout(cls) -> "GaiaError":
        return cls("timeout")


class GaiaSession:
    def __init__(
        self,
        transport: GaiaTransport,
        request_timeout: float = 5.0,
        on_notification: NotifyCb | None = None,
        print_rx: bool = False,
    ) -> None:
        self._t = transport
        self._timeout = request_timeout
        self.on_notification = on_notification
        self.print_rx = print_rx
        self._pend: dict[tuple, asyncio.Future] = {}
        self.gaia_version: int | None = None  # 1/2/3 after probe
        self.connected = False

    # ---- lifecycle --------------------------------------------------------

    async def open(self) -> None:
        await self._t.connect()
        await self._t.start(self._on_frame)
        self.connected = True

    async def close(self) -> None:
        self.connected = False
        await self._t.disconnect()

    # ---- version probe -----------------------------------------------------

    async def probe_version(self) -> dict:
        """Send GAIA Get API Version (V1/V2, vendor 0x000A) and parse.

        Response: command 0x8300 (0x0300 | ACK), payload [status][protocol][gaiaMajor][minor]
        Returns raw parsed info; caller decides which envelope to use.
        """
        fut = asyncio.get_event_loop().create_future()
        key = (C.VENDOR_CSR_V1V2, 0x0300)
        self._pend[key] = fut
        pkt = GaiaPacket.v1v2(C.VENDOR_CSR_V1V2, C.CMD_GET_API_VERSION)
        log.info("probe GAIA version TX %s", pkt.to_wire().hex())
        await self._t.send_packet(pkt)
        try:
            data = await self._wait_fut(fut)
        except asyncio.TimeoutError:
            self._pend.pop(key, None)
            log.warning("probe GAIA version: no response")
            return {}
        info = {}
        if data:
            info["status"] = data[0]
            info["protocol"] = data[1] if len(data) > 1 else None
            info["gaia_major"] = data[2] if len(data) > 2 else None
            info["minor"] = data[3] if len(data) > 3 else None
        self.gaia_version = info.get("gaia_major")
        log.info("GAIA version probe: %s (bytes %s)", info, data.hex())
        return info

    # ---- request / response -----------------------------------------------

    async def request(self, pkt: GaiaPacket, wait: bool = True) -> bytes:
        """Send a v3 command packet and await its response payload.

        Matching: keyed by (vendor, feature, command); any RESPONSE completes
        the future; an ERROR frame raises GaiaError. When ``wait=False`` the
        packet is fire-and-forget (some set commands on EDGE never reply but
        are still applied).
        """
        feat, typ, cmd = v3_decompose(pkt.command)
        key = (pkt.vendor, feat, cmd)
        fut = asyncio.get_event_loop().create_future()
        self._pend[key] = fut
        log.debug("TX %s", pkt.to_wire().hex())
        await self._t.send_packet(pkt)
        if not wait:
            self._pend.pop(key, None)
            return b""
        try:
            data = await self._wait_fut(fut)
        except asyncio.TimeoutError:
            self._pend.pop(key, None)
            raise GaiaError.timeout() from None
        return data

    async def _wait_fut(self, fut) -> bytes:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(asyncio.shield(fut), timeout=self._timeout)

    def _complete(self, key, data: bytes, error: GaiaError | None = None) -> None:
        fut = self._pend.pop(key, None)
        if fut and not fut.done():
            if error:
                fut.set_exception(error)
            else:
                fut.set_result(data)

    # ---- inbound -----------------------------------------------------------

    async def _on_frame(self, raw: bytes) -> None:
        log.debug("RX %s", raw.hex())
        try:
            pkt = GaiaPacket.from_wire(raw)
        except ValueError:
            log.warning("RX unparseable %s", raw.hex())
            return
        feat, typ, cmd = v3_decompose(pkt.command)
        if self.print_rx:
            print(f"RX {raw.hex()}  vendor=0x{pkt.vendor:04x} "
                  f"cmd=0x{pkt.command:04x} (feat=0x{feat:02x} type={typ} cmd={cmd})")

        # version probe responses: vendor 0x000A + ack bit
        if pkt.vendor == C.VENDOR_CSR_V1V2 and (pkt.command & 0x8000):
            self._complete((pkt.vendor, pkt.command & 0x7FFF), pkt.payload)
            return

        key = (pkt.vendor, feat, cmd)
        if typ == C.T_RESPONSE:
            self._complete(key, pkt.payload)
        elif typ == C.T_ERROR:
            self._complete(key, b"", GaiaError.from_v3(pkt.payload))
        elif typ == C.T_NOTIFICATION:
            if self.on_notification:
                try:
                    await self.on_notification(pkt.payload, feat, cmd)
                except Exception:  # noqa: BLE001
                    log.exception("notification callback failed")
        else:  # T_COMMAND (unexpected inbound command)
            log.info("RX command type frame %s", raw.hex())
