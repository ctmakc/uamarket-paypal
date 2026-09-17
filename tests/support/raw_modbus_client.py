from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass


@dataclass
class BitResult:
    bits: list[bool]
    error: bool = False

    def isError(self):
        return self.error


class WriteResult:
    def __init__(self, error: bool = False):
        self.error = error

    def isError(self):
        return self.error


class RawAsyncModbusTcpClient:
    """Tiny test client matching the subset of PyModbus used by the driver."""

    _transaction = 0

    def __init__(self, host: str, *, port: int = 502, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self):
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self.timeout
        )
        return True

    def close(self):
        if self.writer is not None:
            self.writer.close()

    @classmethod
    def _next_transaction(cls) -> int:
        cls._transaction = (cls._transaction + 1) & 0xFFFF
        return cls._transaction

    async def _request(self, unit_id: int, pdu: bytes) -> bytes:
        assert self.reader is not None and self.writer is not None
        tx = self._next_transaction()
        frame = struct.pack(">HHHB", tx, 0, len(pdu) + 1, unit_id) + pdu
        self.writer.write(frame)
        await self.writer.drain()
        header = await asyncio.wait_for(self.reader.readexactly(7), timeout=self.timeout)
        rx_tx, protocol, length, rx_unit = struct.unpack(">HHHB", header)
        if rx_tx != tx or protocol != 0 or rx_unit != unit_id:
            raise RuntimeError("invalid Modbus response header")
        response = await asyncio.wait_for(self.reader.readexactly(length - 1), timeout=self.timeout)
        if response and response[0] & 0x80:
            raise RuntimeError(f"Modbus exception {response[1] if len(response) > 1 else 'unknown'}")
        return response

    @staticmethod
    def _unpack_bits(payload: bytes, count: int) -> list[bool]:
        if len(payload) < 2:
            return []
        byte_count = payload[1]
        data = payload[2:2 + byte_count]
        return [bool(data[i // 8] & (1 << (i % 8))) for i in range(count)]

    async def read_discrete_inputs(self, address, *, count=1, device_id=1):
        pdu = bytes([2]) + struct.pack(">HH", int(address), int(count))
        return BitResult(self._unpack_bits(await self._request(device_id, pdu), count))

    async def read_coils(self, address, *, count=1, device_id=1):
        pdu = bytes([1]) + struct.pack(">HH", int(address), int(count))
        return BitResult(self._unpack_bits(await self._request(device_id, pdu), count))

    async def write_coil(self, address, value, *, device_id=1):
        raw = 0xFF00 if value else 0x0000
        pdu = bytes([5]) + struct.pack(">HH", int(address), raw)
        response = await self._request(device_id, pdu)
        return WriteResult(error=response != pdu)
