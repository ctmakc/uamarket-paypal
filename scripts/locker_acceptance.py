from __future__ import annotations

import argparse
import asyncio
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.locker_bench import build_driver


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


FIELDS = [
    "cycle", "timestamp", "ambient_c", "supply_v_before",
    "inner_gate_closed_before", "outer_door_closed_before", "lock_feedback_locked_before",
    "unlock_accepted", "t_lock_feedback_ms", "t_door_open_ms", "coil_off_ms",
    "door_pop_mm", "relocked_after_close", "result", "fault_code", "notes",
]


async def _wait_ready(driver, bay: str, timeout: float, label: str):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last = None
    while loop.time() < deadline:
        last = await driver.read_state(bay)
        if (
            last.inner_gate_closed
            and last.outer_door_closed
            and last.outer_door_locked
            and not last.unlock_output_active
        ):
            return last
        await asyncio.sleep(0.1)
    raise RuntimeError(f"timeout waiting for {label}; last_state={last}")


def _append(path: Path, row: dict):
    exists = path.exists() and path.stat().st_size > 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
        f.flush()


async def run(args):
    if not _truthy(os.getenv("EDGE_COMMISSIONING_ENABLED")):
        raise RuntimeError("EDGE_COMMISSIONING_ENABLED=true is required")
    if args.confirm.strip().upper() != "RUN ACCEPTANCE":
        raise RuntimeError('confirmation must be exactly "RUN ACCEPTANCE"')

    driver = build_driver()
    if args.bay not in driver.list_bays():
        raise RuntimeError(f"unknown bay: {args.bay}")

    output = Path(args.output)
    for cycle in range(args.start_cycle, args.start_cycle + args.cycles):
        before = await _wait_ready(driver, args.bay, args.ready_timeout, "closed + locked bay")
        row = {
            "cycle": cycle,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ambient_c": args.ambient_c if args.ambient_c is not None else "",
            "supply_v_before": args.supply_v if args.supply_v is not None else "",
            "inner_gate_closed_before": before.inner_gate_closed,
            "outer_door_closed_before": before.outer_door_closed,
            "lock_feedback_locked_before": before.outer_door_locked,
        }
        try:
            result = await driver.unlock(args.bay, 5)
            row.update({
                "unlock_accepted": True,
                "t_lock_feedback_ms": result.get("t_lock_feedback_ms", ""),
                "t_door_open_ms": result.get("t_door_open_ms", ""),
                "coil_off_ms": result.get("coil_on_ms", result.get("unlock_pulse_ms_actual", "")),
            })
            print(
                f"cycle {cycle}: OPENED; lock={row['t_lock_feedback_ms']}ms "
                f"door={row['t_door_open_ms']}ms coil_off={row['coil_off_ms']}ms. "
                "Close/re-latch the door to continue.",
                flush=True,
            )
            await _wait_ready(driver, args.bay, args.reclose_timeout, "operator re-close/re-lock")
            row.update({"relocked_after_close": True, "result": "PASS"})
            _append(output, row)
        except Exception as exc:
            row.update({
                "unlock_accepted": False,
                "relocked_after_close": False,
                "result": "FAIL",
                "fault_code": type(exc).__name__,
                "notes": str(exc),
            })
            _append(output, row)
            raise RuntimeError(f"cycle {cycle} failed; consecutive acceptance run stops: {exc}") from exc

    print(f"PASS: {args.cycles} consecutive cycles logged to {output}")


def parser():
    p = argparse.ArgumentParser(description="Interactive physical locker acceptance runner")
    p.add_argument("--bay", default="BAY-CP")
    p.add_argument("--cycles", type=int, default=100)
    p.add_argument("--start-cycle", type=int, default=1)
    p.add_argument("--output", default="locker-acceptance-run.csv")
    p.add_argument("--ready-timeout", type=float, default=60)
    p.add_argument("--reclose-timeout", type=float, default=60)
    p.add_argument("--ambient-c", type=float)
    p.add_argument("--supply-v", type=float)
    p.add_argument("--confirm", required=True)
    return p


def main():
    asyncio.run(run(parser().parse_args()))


if __name__ == "__main__":
    main()
