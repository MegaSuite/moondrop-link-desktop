"""GAIA packet building / parsing (v1/v2 and v3 command words)."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import constants as C

# V3 command word layout (16-bit):
#   bits 15..9 (7 bits): feature id
#   bits 8..7  (2 bits): packet type
#   bits 6..0  (7 bits): command code
# See core/gaia/core/v3/packets/V3Command.java


def v3_command_word(feature: int, ptype: int, command: int) -> int:
    return ((feature & 0x7F) << 9) | ((ptype & 0x3) << 7) | (command & 0x7F)


def v3_decompose(word: int) -> tuple[int, int, int]:
    feature = (word >> 9) & 0x7F
    ptype = (word >> 7) & 0x3
    command = word & 0x7F
    return feature, ptype, command


@dataclass
class GaiaPacket:
    """In-memory GAIA packet. Over BLE it is transmitted unframed:

    [vendor_id: uint16 LE?][command: uint16][payload...]

    (LeGatt GaiaFormatter is identity, i.e. no SOF/checksum/seq bytes.)
    """

    vendor: int
    command: int  # v1v2 raw command, or v3 packed word
    payload: bytes = b""

    # ---- builders ---------------------------------------------------------

    @staticmethod
    def v1v2(vendor: int, command: int, payload: bytes = b"") -> "GaiaPacket":
        return GaiaPacket(vendor, command, payload)

    @staticmethod
    def v3(vendor: int, feature: int, ptype: int, command: int,
           payload: bytes = b"") -> "GaiaPacket":
        return GaiaPacket(vendor, v3_command_word(feature, ptype, command), payload)

    @property
    def is_v3(self) -> bool:
        # Heuristic: a v3 packet carries a type in bits 8..7 that is not an
        # ordinary v1/v2 command echo; explicit session knows which is which.
        feature, ptype, command = v3_decompose(self.command)
        return 0 <= ptype <= 2

    # ---- wire --------------------------------------------------------------

    def to_wire(self) -> bytes:
        """Raw bytes written to the GAIA command characteristic.

        Byte order is BIG-ENDIAN. Verified from the app's native
        `BytesUtils::getHexValueFromByteArray` (libutils-lib.so): a 16-bit
        field is assembled as `byte[0] << 8 | byte[1]`.
        """
        return (
            struct.pack(">H", self.vendor)
            + struct.pack(">H", self.command)
            + bytes(self.payload)
        )

    @staticmethod
    def from_wire(data: bytes) -> "GaiaPacket":
        if len(data) < 4:
            raise ValueError("short GAIA frame")
        vendor, command = struct.unpack_from(">HH", data, 0)
        return GaiaPacket(vendor, command, data[4:])

    # v1v2 command echo helpers
    def response_command(self, is_ack: bool = False) -> int:
        if is_ack:
            return self.command | 0x8000
        return self.command

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"GaiaPacket(vendor=0x{self.vendor:04x}, cmd=0x{self.command:04x}, "
            f"payload={self.payload.hex()})"
        )


def describe(hexstr: str) -> str:
    """pretty-print a hex byte string for logs."""
    return " ".join(f"{b:02x}" for b in bytes.fromhex(hexstr))
