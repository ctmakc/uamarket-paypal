import asyncio

import pytest

from edge.drivers import SimulatedLockerDriver
from scripts.locker_bench import read_snapshot, test_unlock as bench_unlock


def test_bench_status_reads_all_feedback_and_output_state():
    driver = SimulatedLockerDriver(["BAY-CP"])
    result = asyncio.run(read_snapshot(driver))
    assert result["BAY-CP"] == {
        "inner_gate_closed": True,
        "outer_door_locked": True,
        "outer_door_closed": True,
        "unlock_output_active": False,
    }


def test_bench_unlock_is_double_armed(monkeypatch):
    driver = SimulatedLockerDriver(["BAY-CP"])
    monkeypatch.setenv("EDGE_COMMISSIONING_ENABLED", "false")
    with pytest.raises(RuntimeError, match="EDGE_COMMISSIONING_ENABLED"):
        asyncio.run(bench_unlock(driver, bay_id="BAY-CP", confirm="UNLOCK BAY"))

    monkeypatch.setenv("EDGE_COMMISSIONING_ENABLED", "true")
    with pytest.raises(RuntimeError, match="confirmation"):
        asyncio.run(bench_unlock(driver, bay_id="BAY-CP", confirm="unlock"))


def test_bench_unlock_uses_same_interlocks(monkeypatch):
    monkeypatch.setenv("EDGE_COMMISSIONING_ENABLED", "true")
    driver = SimulatedLockerDriver(["BAY-CP"])
    driver.set_inner_gate("BAY-CP", False)
    with pytest.raises(RuntimeError, match="inner gate"):
        asyncio.run(bench_unlock(driver, bay_id="BAY-CP", confirm="UNLOCK BAY"))


def test_bench_unlock_executes_when_safe(monkeypatch):
    monkeypatch.setenv("EDGE_COMMISSIONING_ENABLED", "true")
    driver = SimulatedLockerDriver(["BAY-CP"])
    result = asyncio.run(bench_unlock(driver, bay_id="BAY-CP", confirm="UNLOCK BAY"))
    assert result["before"]["outer_door_locked"] is True
    assert result["action"]["outer_door_locked"] is False
    assert result["after"]["outer_door_locked"] is False
