from __future__ import annotations

import argparse
import asyncio
import json
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class BayMap:
    inner_gate_di: int
    outer_door_di: int
    lock_feedback_di: int
    unlock_coil: int


class ModbusLockerSimulator:
    """Small Modbus/TCP locker simulator for pre-hardware HIL testing.

    Implements only the function codes used by ModbusLockerDriver:
    FC01 Read Coils, FC02 Read Discrete Inputs and FC05 Write Single Coil.

    The simulated bay models the selected spring/plunger mechanism: energizing
    unlock retracts the bolt and immediately moves the exterior door out of its
    closed-sensor zone. That lets network-HIL exercise the production physical
    success condition rather than treating a coil pulse as success by itself.
    """

    def __init__(self, bays: dict[str, BayMap]):
        if not bays:
            raise ValueError("at least one bay mapping is required")
        self.bays = bays
        self.discrete_inputs: dict[int, bool] = {}
        self.coils: dict[int, bool] = {}
        self._coil_to_lock_feedback: dict[int, int] = {}
        self._coil_to_outer_door: dict[int, int] = {}
        self.server: asyncio.AbstractServer | None = None
        for cfg in bays.values():
            self.discrete_inputs[cfg.inner_gate_di] = True
            self.discrete_inputs[cfg.outer_door_di] = True
            self.discrete_inputs[cfg.lock_feedback_di] = True
            self.coils[cfg.unlock_coil] = False
            self._coil_to_lock_feedback[cfg.unlock_coil] = cfg.lock_feedback_di
            self._coil_to_outer_door[cfg.unlock_coil] = cfg.outer_door_di

    def set_discrete_input(self, address: int, value: bool) -> None:
        self.discrete_inputs[int(address)] = bool(value)

    def close_door(self, bay_id: str) -> None:
        cfg = self.bays[bay_id]
        self.discrete_inputs[cfg.outer_door_di] = True
        self.discrete_inputs[cfg.lock_feedback_di] = True
        self.coils[cfg.unlock_coil] = False

    def relock(self, bay_id: str) -> None:
        self.close_door(bay_id)

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        self.server = await asyncio.start_server(self._handle_client, host, port)
        socket = self.server.sockets[0]
        return int(socket.getsockname()[1])

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

    @staticmethod
    def _pack_bits(values: list[bool]) -> bytes:
        out = bytearray((len(values) + 7) // 8)
        for index, value in enumerate(values):
            if value:
                out[index // 8] |= 1 << (index % 8)
        return bytes(out)

    def _read_bits(self, store: dict[int, bool], address: int, quantity: int) -> bytes:
        values = [bool(store.get(address + offset, False)) for offset in range(quantity)]
        packed = self._pack_bits(values)
        return bytes([len(packed)]) + packed

    def _process_pdu(self, pdu: bytes) -> bytes:
        if not pdu:
            return bytes([0x80, 0x03])
        function = pdu[0]
        if function in (1, 2):
            if len(pdu) != 5:
                return bytes([function | 0x80, 0x03])
            address, quantity = struct.unpack(">HH", pdu[1:5])
            if not 1 <= quantity <= 2000:
                return bytes([function | 0x80, 0x03])
            store = self.coils if function == 1 else self.discrete_inputs
            return bytes([function]) + self._read_bits(store, address, quantity)
        if function == 5:
            if len(pdu) != 5:
                return bytes([function | 0x80, 0x03])
            address, raw_value = struct.unpack(">HH", pdu[1:5])
            if raw_value not in (0x0000, 0xFF00):
                return bytes([function | 0x80, 0x03])
            value = raw_value == 0xFF00
            self.coils[address] = value
            if value:
                feedback = self._coil_to_lock_feedback.get(address)
                outer = self._coil_to_outer_door.get(address)
                if feedback is not None:
                    self.discrete_inputs[feedback] = False
                if outer is not None:
                    self.discrete_inputs[outer] = False
            return pdu[:5]
        return bytes([function | 0x80, 0x01])

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                try:
                    header = await reader.readexactly(7)
                except asyncio.IncompleteReadError:
                    break
                transaction_id, protocol_id, length, unit_id = struct.unpack(">HHHB", header)
                if protocol_id != 0 or length < 2:
                    break
                pdu = await reader.readexactly(length - 1)
                response_pdu = self._process_pdu(pdu)
                response_header = struct.pack(">HHHB", transaction_id, 0, len(response_pdu) + 1, unit_id)
                writer.write(response_header + response_pdu)
                await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


def parse_map(raw: str) -> dict[str, BayMap]:
    parsed = json.loads(raw)
    return {name: BayMap(**cfg) for name, cfg in parsed.items()}


async def _serve(args) -> None:
    sim = ModbusLockerSimulator(parse_map(args.map_json))
    port = await sim.start(args.host, args.port)
    print(f"Modbus locker simulator listening on {args.host}:{port}", flush=True)
    assert sim.server is not None
    async with sim.server:
        await sim.server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Modbus/TCP locker simulator")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15020)
    parser.add_argument(
        "--map-json",
        default='{"BAY-CP":{"inner_gate_di":0,"outer_door_di":1,"lock_feedback_di":2,"unlock_coil":0}}',
    )
    args = parser.parse_args()
    asyncio.run(_serve(args))


if __name__ == "__main__":
    main()
