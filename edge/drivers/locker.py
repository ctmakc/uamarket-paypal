from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Callable, Protocol


class LockerCoilLatchedError(RuntimeError):
    """The unlock output could not be proven de-energized.

    Raised when the de-energize write is rejected, the PLC stops answering, or
    the coil read-back still reports the output active. It is a distinct type
    because it is a physical safety incident: the latch may be held open with
    nothing left to switch it off, so the bay must be taken out of service
    instead of being reported as a successful unlock.
    """


# A fault sink receives (event_type, payload) and forwards it to the cloud.
LockerFaultHandler = Callable[[str, dict], None]


class LockerFaultReporter:
    """Lets a driver hand a hardware fault to whoever owns the uplink."""

    fault_handler: LockerFaultHandler | None = None

    def emit_fault(self, event_type: str, payload: dict) -> None:
        handler = self.fault_handler
        if handler is None:
            return
        try:
            handler(event_type, dict(payload))
        except Exception:
            # The uplink is best effort here; the caller still raises so the
            # command fails loudly and the bay is not reported as unlocked.
            pass


@dataclass(frozen=True)
class BayIOState:
    inner_gate_closed: bool = True
    outer_door_locked: bool = True
    outer_door_closed: bool = True
    unlock_output_active: bool = False

    def as_payload(self, bay_id: str) -> dict:
        return {"bay_id": bay_id, **asdict(self)}


class LockerDriver(Protocol):
    def list_bays(self) -> list[str]: ...
    async def read_state(self, bay_id: str) -> BayIOState: ...
    async def unlock(self, bay_id: str, ttl_seconds: int) -> dict: ...


class SimulatedLockerDriver(LockerFaultReporter):
    """Fail-secure software stand-in for the future PLC/relay driver."""

    def __init__(self, bay_ids: list[str] | None = None):
        self.bays: dict[str, BayIOState] = {
            bay_id: BayIOState() for bay_id in (bay_ids or ["BAY-CP", "BAY-OTHER", "BAY-OVERFLOW"])
        }

    def list_bays(self) -> list[str]:
        return sorted(self.bays)

    def state(self, bay_id: str) -> BayIOState:
        return self.bays.setdefault(bay_id, BayIOState())

    def _replace(self, bay_id: str, **changes):
        current = self.state(bay_id)
        values = asdict(current)
        values.update(changes)
        self.bays[bay_id] = BayIOState(**values)

    def set_inner_gate(self, bay_id: str, closed: bool):
        self._replace(bay_id, inner_gate_closed=closed)

    def set_outer_door(self, bay_id: str, closed: bool):
        self._replace(bay_id, outer_door_closed=closed)

    def set_lock(self, bay_id: str, locked: bool):
        self._replace(bay_id, outer_door_locked=locked)

    async def read_state(self, bay_id: str) -> BayIOState:
        await asyncio.sleep(0)
        return self.state(bay_id)

    async def unlock(self, bay_id: str, ttl_seconds: int) -> dict:
        state = self.state(bay_id)
        if not state.inner_gate_closed:
            raise RuntimeError("hardware interlock: inner gate open")
        if not state.outer_door_closed:
            raise RuntimeError("outer door is already open")
        self.set_lock(bay_id, False)
        await asyncio.sleep(0)
        return {**(await self.read_state(bay_id)).as_payload(bay_id), "ttl_seconds": ttl_seconds}
