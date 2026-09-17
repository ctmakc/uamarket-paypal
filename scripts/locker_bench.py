from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict

from edge.drivers import ModbusLockerDriver, SimulatedLockerDriver


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_driver():
    mode = os.getenv("LOCKER_DRIVER", "modbus").strip().lower()
    if mode == "modbus":
        return ModbusLockerDriver.from_env()
    if mode == "simulated":
        return SimulatedLockerDriver()
    raise RuntimeError(f"unsupported LOCKER_DRIVER: {mode}")


async def read_snapshot(driver, bay_id: str | None = None) -> dict:
    bays = [bay_id] if bay_id else driver.list_bays()
    result = {}
    for bay in bays:
        state = await driver.read_state(bay)
        result[bay] = asdict(state)
    return result


async def test_unlock(driver, *, bay_id: str, confirm: str, ttl_seconds: int = 5) -> dict:
    if not _truthy(os.getenv("EDGE_COMMISSIONING_ENABLED")):
        raise RuntimeError("EDGE_COMMISSIONING_ENABLED=true is required")
    if confirm.strip().upper() != "UNLOCK BAY":
        raise RuntimeError('confirmation must be exactly "UNLOCK BAY"')
    before = await driver.read_state(bay_id)
    if not before.inner_gate_closed:
        raise RuntimeError("hardware interlock: inner gate open")
    if not before.outer_door_closed:
        raise RuntimeError("outer door is open")
    if not before.outer_door_locked:
        raise RuntimeError("lock feedback already reports unlocked")
    if before.unlock_output_active:
        raise RuntimeError("unlock output is already active")
    action = await driver.unlock(bay_id, max(1, min(int(ttl_seconds), 10)))
    after = await driver.read_state(bay_id)
    return {
        "bay_id": bay_id,
        "before": asdict(before),
        "action": action,
        "after": asdict(after),
    }


async def _watch(driver, bay_id: str | None, interval: float):
    while True:
        snapshot = await read_snapshot(driver, bay_id)
        print(json.dumps(snapshot, sort_keys=True), flush=True)
        await asyncio.sleep(max(0.2, interval))


async def main_async(args):
    driver = build_driver()
    if args.command == "preflight":
        result = {"driver": type(driver).__name__, "bays": driver.list_bays()}
        if isinstance(driver, ModbusLockerDriver):
            result.update({
                "host": driver.host,
                "port": driver.port,
                "device_id": driver.device_id,
                "map": driver.describe_map(),
                "validation": "OK",
            })
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    if args.command == "status":
        print(json.dumps(await read_snapshot(driver, args.bay), indent=2, sort_keys=True))
        return
    if args.command == "watch":
        await _watch(driver, args.bay, args.interval)
        return
    if args.command == "unlock":
        result = await test_unlock(driver, bay_id=args.bay, confirm=args.confirm, ttl_seconds=args.ttl)
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    raise RuntimeError(f"unknown command: {args.command}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fail-safe locker PLC commissioning bench")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight", help="validate and print locker driver/channel mapping without hardware I/O")

    status = sub.add_parser("status", help="read all locker feedback and unlock coils")
    status.add_argument("--bay")

    watch = sub.add_parser("watch", help="continuously read locker I/O")
    watch.add_argument("--bay")
    watch.add_argument("--interval", type=float, default=1.0)

    unlock = sub.add_parser("unlock", help="pulse one bay using normal driver interlocks")
    unlock.add_argument("--bay", required=True)
    unlock.add_argument("--ttl", type=int, default=5)
    unlock.add_argument("--confirm", required=True)
    return p


def main():
    asyncio.run(main_async(parser().parse_args()))


if __name__ == "__main__":
    main()
