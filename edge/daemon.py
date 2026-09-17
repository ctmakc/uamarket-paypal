from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from websockets.asyncio.client import connect

from .drivers import BayIOState, ModbusLockerDriver, SimulatedLockerDriver
from .store import ACTUATING, COMPLETED, EdgeStore

# Commands that move a physical latch. They get an ACTUATING journal entry, so a
# daemon that dies mid-pulse never repeats the pulse on redelivery.
ACTUATING_COMMANDS = {"UNLOCK_BAY", "COMMISSIONING_UNLOCK_BAY"}

# Hardware faults wait here while the uplink is down. Older ones are dropped
# rather than grown without bound during a long outage.
MAX_QUEUED_FAULTS = 50


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


class EdgeDaemon:
    def __init__(self):
        self.url = os.getenv("EDGE_WS_URL", "ws://127.0.0.1:8000/edge/ws")
        self.token = os.getenv("EDGE_DEVICE_TOKEN") or os.getenv("EDGE_SHARED_TOKEN", "dev-edge-token")
        self.site = os.getenv("EDGE_SITE", "default")
        self.device_id = os.getenv("EDGE_DEVICE_ID", "LOCKER-PLC-01")
        self.store = EdgeStore(os.getenv("EDGE_STATE_DB", "edge-state.db"))
        self.locker = self._make_locker_driver()
        self._last_states: dict[str, BayIOState] = {}
        self._sensor_faulted: set[str] = set()
        self._last_snapshot_monotonic: dict[str, float] = {}
        self._faults: list[tuple[str, dict]] = []
        if hasattr(self.locker, "fault_handler"):
            self.locker.fault_handler = self._record_fault

    @staticmethod
    def _make_locker_driver():
        driver = os.getenv("LOCKER_DRIVER", "simulated").strip().lower()
        if driver == "modbus":
            return ModbusLockerDriver.from_env()
        if driver == "simulated":
            return SimulatedLockerDriver()
        raise RuntimeError(f"unsupported LOCKER_DRIVER: {driver}")

    def _url(self) -> str:
        parts = urlparse(self.url)
        q = dict(parse_qsl(parts.query))
        q.update({"site": self.site, "device_id": self.device_id})
        return urlunparse(parts._replace(query=urlencode(q)))

    @staticmethod
    def _ensure_command_fresh(payload: dict) -> None:
        expires_at = payload.get("expires_at")
        if not expires_at:
            return
        try:
            expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError("invalid command expires_at") from exc
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise RuntimeError("command expired before edge execution")

    async def _execute(self, command: dict) -> dict:
        event_type = command.get("event_type")
        payload = command.get("payload") or {}
        if event_type in {"UNLOCK_BAY", "COMMISSIONING_UNLOCK_BAY"}:
            self._ensure_command_fresh(payload)
        if event_type == "READ_LOCKER_STATE":
            state = await self.locker.read_state(payload["bay_id"])
            return state.as_payload(payload["bay_id"])
        if event_type == "UNLOCK_BAY":
            return await self.locker.unlock(payload["bay_id"], int(payload.get("ttl_seconds", 60)))
        if event_type == "COMMISSIONING_UNLOCK_BAY":
            if not _truthy(os.getenv("EDGE_COMMISSIONING_ENABLED")):
                raise RuntimeError("edge commissioning mode is not enabled")
            result = await self.locker.unlock(payload["bay_id"], int(payload.get("ttl_seconds", 5)))
            return {**result, "commissioning": True}
        raise RuntimeError(f"unsupported command: {event_type}")

    @staticmethod
    def _result_event_type(command: dict) -> str:
        event_type = command.get("event_type")
        if event_type == "READ_LOCKER_STATE":
            return "LOCKER_STATE"
        if event_type in {"UNLOCK_BAY", "COMMISSIONING_UNLOCK_BAY"}:
            return "LOCKER_UNLOCKED"
        return "COMMAND_COMPLETED"

    def _record_fault(self, event_type: str, payload: dict) -> None:
        """Driver-side hardware fault, queued until the uplink can carry it."""
        self._faults.append((event_type, dict(payload)))
        # A long outage must not turn the queue into a memory leak; the newest
        # faults describe the current state of the panel.
        del self._faults[:-MAX_QUEUED_FAULTS]

    async def _drain_faults(self, ws) -> None:
        while self._faults:
            event_type, payload = self._faults.pop(0)
            await ws.send(json.dumps({
                "type": "EVENT", "device_id": self.device_id,
                "event_type": event_type, "payload": payload,
            }))

    async def _send_event(self, ws, event_type: str, payload: dict, command_id: str | None = None) -> None:
        message = {"type": "EVENT", "device_id": self.device_id, "event_type": event_type, "payload": payload}
        if command_id:
            message["command_id"] = command_id
        await ws.send(json.dumps(message))

    async def _handle(self, ws, command: dict):
        command_id = command["id"]
        local = self.store.remember(command_id, command)
        if local.state == COMPLETED:
            # The physical action already happened. Answer from the journal and
            # never touch the hardware again: the courier has closed the door.
            if local.result is not None:
                await self._send_event(
                    ws, self._result_event_type(command), {**local.result, "replayed": True}, command_id
                )
            await ws.send(json.dumps({"type": "ACK", "command_id": command_id, "ok": True, "duplicate": True}))
            return
        if local.state == ACTUATING:
            # The daemon stopped in the middle of a pulse. The outcome is
            # unknown, so the safe answer is to report it, not to repeat it.
            error = "a previous actuation of this command never reported back; refusing to repeat it"
            await self._send_event(ws, "EDGE_COMMAND_INDETERMINATE", {
                "bay_id": (command.get("payload") or {}).get("bay_id"),
                "error": error,
            }, command_id)
            await ws.send(json.dumps({
                "type": "ACK", "command_id": command_id, "ok": False,
                "details": {"error": error, "indeterminate": True},
            }))
            return

        if command.get("event_type") in ACTUATING_COMMANDS:
            self.store.mark_actuating(command_id)
        try:
            result = await self._execute(command)
        except Exception as exc:
            self.store.mark_failed(command_id, str(exc))
            await self._drain_faults(ws)
            await ws.send(json.dumps({
                "type": "ACK", "command_id": command_id, "ok": False, "details": {"error": str(exc)},
            }))
            return
        # The physical action finished. The journal is written before any
        # transport work, and mark_failed can no longer demote it, so a socket
        # that dies from here on costs one redelivery, not a second unlock.
        self.store.mark_completed(command_id, result)
        await self._drain_faults(ws)
        await self._send_event(ws, self._result_event_type(command), result, command_id)
        await ws.send(json.dumps({"type": "ACK", "command_id": command_id, "ok": True}))

    async def _emit_sensor_events(self, ws):
        for bay_id in self.locker.list_bays():
            try:
                state = await self.locker.read_state(bay_id)
            except Exception as exc:
                self._sensor_faulted.add(bay_id)
                await ws.send(json.dumps({
                    "type": "EVENT", "device_id": self.device_id,
                    "event_type": "LOCKER_SENSOR_ERROR", "payload": {"bay_id": bay_id, "error": str(exc)},
                }))
                continue
            previous = self._last_states.get(bay_id)
            recovered = bay_id in self._sensor_faulted
            if recovered:
                self._sensor_faulted.discard(bay_id)
            now_mono = asyncio.get_running_loop().time()
            snapshot_interval = max(1.0, float(os.getenv("LOCKER_SNAPSHOT_INTERVAL_SECONDS", "15")))
            snapshot_due = (
                previous is None
                or recovered
                or now_mono - self._last_snapshot_monotonic.get(bay_id, 0.0) >= snapshot_interval
            )
            if snapshot_due:
                await ws.send(json.dumps({
                    "type": "EVENT", "device_id": self.device_id,
                    "event_type": "LOCKER_STATE", "payload": state.as_payload(bay_id),
                }))
                self._last_snapshot_monotonic[bay_id] = now_mono
            else:
                changes = []
                if state.inner_gate_closed != previous.inner_gate_closed:
                    changes.append("INNER_GATE_CLOSED" if state.inner_gate_closed else "INNER_GATE_OPENED")
                if state.outer_door_closed != previous.outer_door_closed:
                    changes.append("OUTER_DOOR_CLOSED" if state.outer_door_closed else "OUTER_DOOR_OPENED")
                if state.outer_door_locked != previous.outer_door_locked:
                    changes.append("LOCKER_LOCKED" if state.outer_door_locked else "LOCKER_UNLOCKED")
                for event_type in changes:
                    await ws.send(json.dumps({
                        "type": "EVENT", "device_id": self.device_id,
                        "event_type": event_type, "payload": state.as_payload(bay_id),
                    }))
            self._last_states[bay_id] = state

    async def run_forever(self):
        backoff = 1.0
        while True:
            try:
                async with connect(
                    self._url(), additional_headers={"X-Edge-Token": self.token},
                    ping_interval=20, ping_timeout=20, max_size=1_000_000,
                ) as ws:
                    backoff = 1.0
                    await ws.send(json.dumps({"type": "HELLO", "device_id": self.device_id, "site": self.site}))
                    # A hardware fault raised while the uplink was down still has
                    # to reach the cloud; it is queued, not dropped.
                    await self._drain_faults(ws)
                    await self._emit_sensor_events(ws)
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "COMMAND":
                            await self._handle(ws, msg["command"])
                        elif msg.get("type") == "PING":
                            await ws.send(json.dumps({"type": "PONG", "device_id": self.device_id}))
                            await self._emit_sensor_events(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"edge disconnected: {exc}")
                await asyncio.sleep(backoff + random.random() * 0.25)
                backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    asyncio.run(EdgeDaemon().run_forever())
