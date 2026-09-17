from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .locker import BayIOState, LockerCoilLatchedError, LockerFaultReporter

try:
    from pymodbus.client import AsyncModbusTcpClient
except ImportError:  # Tests can inject a client factory without importing pymodbus.
    AsyncModbusTcpClient = None


@dataclass(frozen=True)
class ModbusBayMap:
    inner_gate_di: int
    outer_door_di: int
    lock_feedback_di: int
    unlock_coil: int


class ModbusLockerDriver(LockerFaultReporter):
    """Modbus/TCP locker driver.

    The software interlock is defense-in-depth only. The unlock output must also
    be physically hardwired through an inner-gate-closed safety/interlock path.

    Production unlock semantics assume a spring/plunger causes the exterior door
    to pop open as soon as the fail-secure solenoid retracts. An unlock is not
    considered successful until both lock feedback reports unlocked and the
    outer-door contact reports open.

    The unlock coil is de-energized in finally, and the de-energize is proven by
    reading the coil back. A rejected OFF write or a PLC that stops answering
    leaves the latch held open, so that case raises LockerCoilLatchedError and
    emits a LOCKER_COIL_LATCHED fault instead of returning a successful unlock.
    """

    def __init__(
        self,
        *,
        host: str,
        bays: dict[str, ModbusBayMap],
        port: int = 502,
        device_id: int = 1,
        pulse_ms: int = 1500,
        verify_timeout_ms: int = 750,
        timeout: float = 3.0,
        release_attempts: int = 3,
        release_retry_ms: int = 100,
        client_factory: Callable[..., Any] | None = None,
    ):
        if not bays:
            raise ValueError("at least one Modbus bay mapping is required")
        if not host:
            raise ValueError("Modbus host is required")
        self._validate_bays(bays)
        self.host = host
        self.port = port
        self.device_id = device_id
        self.pulse_ms = max(100, min(int(pulse_ms), 5000))
        self.verify_timeout_ms = max(50, min(int(verify_timeout_ms), self.pulse_ms))
        self.timeout = timeout
        # How hard the driver tries to prove the unlock output is off again.
        # Defaults: 3 attempts, 100 ms apart (LOCKER_UNLOCK_RELEASE_ATTEMPTS /
        # LOCKER_UNLOCK_RELEASE_RETRY_MS).
        self.release_attempts = max(1, min(int(release_attempts), 10))
        self.release_retry_ms = max(0, min(int(release_retry_ms), 2000))
        self.bays = bays
        self.client_factory = client_factory or AsyncModbusTcpClient
        if self.client_factory is None:
            raise RuntimeError("pymodbus is required for the Modbus locker driver")

    @staticmethod
    def _duplicates(values: list[int]) -> list[int]:
        return sorted({value for value in values if values.count(value) > 1})

    @classmethod
    def _validate_bays(cls, bays: dict[str, ModbusBayMap]) -> None:
        """Fail fast on wiring-map mistakes before any network or hardware I/O."""
        for bay_id, mapping in bays.items():
            for field in ("inner_gate_di", "outer_door_di", "lock_feedback_di", "unlock_coil"):
                value = getattr(mapping, field)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7:
                    raise ValueError(f"{bay_id}.{field} must be an integer Modbus channel in range 0..7")

        coils = [mapping.unlock_coil for mapping in bays.values()]
        dup_coils = cls._duplicates(coils)
        if dup_coils:
            raise ValueError(f"duplicate unlock_coil address(es): {dup_coils}")

        doors = [mapping.outer_door_di for mapping in bays.values()]
        dup_doors = cls._duplicates(doors)
        if dup_doors:
            raise ValueError(f"duplicate outer_door_di address(es): {dup_doors}")

        locks = [mapping.lock_feedback_di for mapping in bays.values()]
        dup_locks = cls._duplicates(locks)
        if dup_locks:
            raise ValueError(f"duplicate lock_feedback_di address(es): {dup_locks}")

        overlap = sorted(set(doors) & set(locks))
        if overlap:
            raise ValueError(f"door and lock feedback DI addresses overlap: {overlap}")

        inner = {mapping.inner_gate_di for mapping in bays.values()}
        sensor_overlap = sorted(inner & (set(doors) | set(locks)))
        if sensor_overlap:
            raise ValueError(f"inner_gate_di overlaps door/lock feedback DI address(es): {sensor_overlap}")

    @classmethod
    def from_env(cls) -> "ModbusLockerDriver":
        raw = os.getenv("LOCKER_MODBUS_MAP_JSON", "")
        if not raw:
            raise RuntimeError("LOCKER_MODBUS_MAP_JSON is required when LOCKER_DRIVER=modbus")
        try:
            parsed = json.loads(raw)
            bays = {name: ModbusBayMap(**cfg) for name, cfg in parsed.items()}
        except Exception as exc:
            raise RuntimeError(f"invalid LOCKER_MODBUS_MAP_JSON: {exc}") from exc
        return cls(
            host=os.getenv("LOCKER_MODBUS_HOST", ""),
            port=int(os.getenv("LOCKER_MODBUS_PORT", "502")),
            device_id=int(os.getenv("LOCKER_MODBUS_DEVICE_ID", "1")),
            pulse_ms=int(os.getenv("LOCKER_UNLOCK_PULSE_MS", "1500")),
            verify_timeout_ms=int(os.getenv("LOCKER_UNLOCK_VERIFY_TIMEOUT_MS", "750")),
            timeout=float(os.getenv("LOCKER_MODBUS_TIMEOUT", "3")),
            release_attempts=int(os.getenv("LOCKER_UNLOCK_RELEASE_ATTEMPTS", "3")),
            release_retry_ms=int(os.getenv("LOCKER_UNLOCK_RELEASE_RETRY_MS", "100")),
            bays=bays,
        )

    def list_bays(self) -> list[str]:
        return sorted(self.bays)

    def describe_map(self) -> dict[str, dict[str, int]]:
        return {bay_id: asdict(self.bays[bay_id]) for bay_id in self.list_bays()}

    async def _client(self):
        client = self.client_factory(self.host, port=self.port, timeout=self.timeout)
        connected = await client.connect()
        if connected is False:
            client.close()
            raise RuntimeError("Modbus PLC connection failed")
        return client

    @staticmethod
    def _bit(result, what: str) -> bool:
        if result is None or (hasattr(result, "isError") and result.isError()):
            raise RuntimeError(f"Modbus read failed: {what}")
        bits = getattr(result, "bits", None)
        if not bits:
            raise RuntimeError(f"Modbus read returned no bits: {what}")
        return bool(bits[0])

    async def _release_unlock_coil(self, client, mapping: ModbusBayMap, bay_id: str) -> float:
        """De-energize the unlock output and prove it with a read-back.

        Returns the monotonic time at which the output was proven off. Raises
        LockerCoilLatchedError when it cannot be proven, after emitting a
        LOCKER_COIL_LATCHED fault event.
        """
        loop = asyncio.get_running_loop()
        last_error = "no de-energize attempt completed"
        known_active = False
        attempts_made = 0
        for attempt in range(1, self.release_attempts + 1):
            attempts_made = attempt
            written = False
            try:
                result = await client.write_coil(mapping.unlock_coil, False, device_id=self.device_id)
                if result is None or (hasattr(result, "isError") and result.isError()):
                    # The PLC answered and refused: the last command it accepted
                    # for this coil is still the ON one.
                    known_active = True
                    last_error = "PLC rejected the unlock coil de-energize write"
                else:
                    written = True
            except Exception as exc:
                last_error = f"unlock coil de-energize write failed: {exc}"
            if written:
                try:
                    read_back = await client.read_coils(mapping.unlock_coil, count=1, device_id=self.device_id)
                    if self._bit(read_back, "unlock_output_after_release"):
                        known_active = True
                        last_error = "unlock coil read-back still reports the output energized"
                    else:
                        return loop.time()
                except Exception as exc:
                    last_error = f"unlock coil read-back failed: {exc}"
            if attempt < self.release_attempts and self.release_retry_ms:
                await asyncio.sleep(self.release_retry_ms / 1000)
        fault = {
            "bay_id": bay_id,
            "unlock_coil": mapping.unlock_coil,
            "device_id": self.device_id,
            "attempts": attempts_made,
            "error": last_error,
            # Claim the output is active only on something the PLC said: a
            # read-back that still reads on, or a refused de-energize write. If
            # it stopped answering the state is unknown, and the caller treats
            # unknown as unsafe.
            "unlock_output_active": True if known_active else None,
            "unlock_output_verified": False,
        }
        self.emit_fault("LOCKER_COIL_LATCHED", fault)
        raise LockerCoilLatchedError(
            f"unlock coil {mapping.unlock_coil} for {bay_id} could not be proven de-energized "
            f"after {attempts_made} attempt(s): {last_error}"
        )

    async def read_state(self, bay_id: str) -> BayIOState:
        mapping = self.bays.get(bay_id)
        if not mapping:
            raise RuntimeError(f"unknown locker bay: {bay_id}")
        client = await self._client()
        try:
            inner = await client.read_discrete_inputs(mapping.inner_gate_di, count=1, device_id=self.device_id)
            outer = await client.read_discrete_inputs(mapping.outer_door_di, count=1, device_id=self.device_id)
            lock = await client.read_discrete_inputs(mapping.lock_feedback_di, count=1, device_id=self.device_id)
            output = await client.read_coils(mapping.unlock_coil, count=1, device_id=self.device_id)
            return BayIOState(
                inner_gate_closed=self._bit(inner, "inner_gate_closed"),
                outer_door_closed=self._bit(outer, "outer_door_closed"),
                outer_door_locked=self._bit(lock, "lock_feedback"),
                unlock_output_active=self._bit(output, "unlock_output"),
            )
        finally:
            client.close()

    async def unlock(self, bay_id: str, ttl_seconds: int) -> dict:
        mapping = self.bays.get(bay_id)
        if not mapping:
            raise RuntimeError(f"unknown locker bay: {bay_id}")
        state = await self.read_state(bay_id)
        if not state.inner_gate_closed:
            raise RuntimeError("hardware interlock: inner gate open")
        if not state.outer_door_closed:
            raise RuntimeError("outer door is already open")
        if not state.outer_door_locked:
            raise RuntimeError("outer lock feedback already reports unlocked")

        client = await self._client()
        loop = asyncio.get_running_loop()
        started = loop.time()
        pulse_deadline = started + self.pulse_ms / 1000
        verify_deadline = started + self.verify_timeout_ms / 1000
        unlocked_seen = False
        door_open_seen = False
        lock_feedback_ms = None
        door_open_ms = None
        coil_on_ms = None
        try:
            result = await client.write_coil(mapping.unlock_coil, True, device_id=self.device_id)
            if result is None or (hasattr(result, "isError") and result.isError()):
                raise RuntimeError("Modbus unlock output failed")
            try:
                while loop.time() < verify_deadline:
                    feedback = await client.read_discrete_inputs(
                        mapping.lock_feedback_di, count=1, device_id=self.device_id
                    )
                    if not self._bit(feedback, "lock_feedback_after_unlock"):
                        unlocked_seen = True
                        lock_feedback_ms = max(0, int(round((loop.time() - started) * 1000)))
                        break
                    await asyncio.sleep(min(0.05, max(0.0, verify_deadline - loop.time())))
                if not unlocked_seen:
                    raise RuntimeError("unlock feedback did not change to unlocked before verification timeout")

                while loop.time() < pulse_deadline:
                    outer = await client.read_discrete_inputs(
                        mapping.outer_door_di, count=1, device_id=self.device_id
                    )
                    if not self._bit(outer, "outer_door_after_unlock"):
                        door_open_seen = True
                        door_open_ms = max(0, int(round((loop.time() - started) * 1000)))
                        break
                    await asyncio.sleep(min(0.05, max(0.0, pulse_deadline - loop.time())))
                if not door_open_seen:
                    raise RuntimeError("outer door did not open before unlock pulse timeout")
            finally:
                released_at = await self._release_unlock_coil(client, mapping, bay_id)
                coil_on_ms = max(0, int(round((released_at - started) * 1000)))
        finally:
            client.close()

        actual_ms = coil_on_ms if coil_on_ms is not None else max(0, int(round((loop.time() - started) * 1000)))
        # Every field below was read back from the PLC: lock feedback and door
        # contact during the pulse, the unlock output after the de-energize.
        verified = BayIOState(
            inner_gate_closed=state.inner_gate_closed,
            outer_door_closed=False,
            outer_door_locked=False,
            unlock_output_active=False,
        )
        return {
            **verified.as_payload(bay_id),
            "unlock_output_verified": True,
            "door_opened": True,
            "unlock_pulse_ms_max": self.pulse_ms,
            "unlock_pulse_ms_actual": actual_ms,
            "t_lock_feedback_ms": lock_feedback_ms,
            "t_door_open_ms": door_open_ms,
            "coil_on_ms": actual_ms,
            "unlock_verify_timeout_ms": self.verify_timeout_ms,
            "ttl_seconds": ttl_seconds,
        }
