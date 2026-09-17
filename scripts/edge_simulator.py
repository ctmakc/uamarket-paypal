"""Tiny edge agent simulator: polls cloud commands and acknowledges them.

Usage against a running API:
  API_URL=http://127.0.0.1:8000 EDGE_SHARED_TOKEN=dev-edge-token python scripts/edge_simulator.py
"""
from __future__ import annotations

import os
import time
import httpx

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("EDGE_SHARED_TOKEN", "dev-edge-token")


def main():
    headers = {"x-edge-token": TOKEN}
    seen = set()
    while True:
        r = httpx.get(f"{API_URL}/edge/commands", headers=headers, timeout=10)
        r.raise_for_status()
        for cmd in r.json()["commands"]:
            if cmd["id"] in seen:
                continue
            print("EXEC", cmd["event_type"], cmd["aggregate_id"], cmd["payload"])
            ack = httpx.post(
                f"{API_URL}/edge/commands/{cmd['id']}/ack",
                headers=headers,
                json={"ok": True, "details": {"simulator": True}},
                timeout=10,
            )
            ack.raise_for_status()
            seen.add(cmd["id"])
        time.sleep(1)


if __name__ == "__main__":
    main()
