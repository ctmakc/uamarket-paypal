import asyncio

import pytest

from edge.drivers import ModbusBayMap, ModbusLockerDriver
from tests.support.raw_modbus_client import RawAsyncModbusTcpClient
from tools.modbus_locker_sim import BayMap, ModbusLockerSimulator


async def scenario_safe_unlock_over_real_tcp():
    sim = ModbusLockerSimulator({
        "BAY-CP": BayMap(inner_gate_di=0, outer_door_di=1, lock_feedback_di=2, unlock_coil=5)
    })
    port = await sim.start()
    try:
        driver = ModbusLockerDriver(
            host="127.0.0.1",
            port=port,
            device_id=1,
            pulse_ms=100,
            verify_timeout_ms=50,
            bays={"BAY-CP": ModbusBayMap(inner_gate_di=0, outer_door_di=1, lock_feedback_di=2, unlock_coil=5)},
            client_factory=RawAsyncModbusTcpClient,
        )
        before = await driver.read_state("BAY-CP")
        assert before.inner_gate_closed is True
        assert before.outer_door_closed is True
        assert before.outer_door_locked is True
        assert before.unlock_output_active is False

        result = await driver.unlock("BAY-CP", 5)
        assert result["outer_door_locked"] is False
        assert result["outer_door_closed"] is False
        assert result["door_opened"] is True
        assert isinstance(result["t_lock_feedback_ms"], int)
        assert isinstance(result["t_door_open_ms"], int)
        assert isinstance(result["coil_on_ms"], int)
        assert result["coil_on_ms"] >= result["t_door_open_ms"] >= result["t_lock_feedback_ms"]
        assert sim.coils[5] is False, "unlock coil must always be de-energized after physical opening"
        assert sim.discrete_inputs[2] is False, "simulated lock feedback should report unlocked"
        assert sim.discrete_inputs[1] is False, "pop-open simulator should report the door physically open"
    finally:
        await sim.stop()


async def scenario_open_inner_gate_blocks_network_write():
    sim = ModbusLockerSimulator({
        "BAY-CP": BayMap(inner_gate_di=0, outer_door_di=1, lock_feedback_di=2, unlock_coil=5)
    })
    sim.set_discrete_input(0, False)
    port = await sim.start()
    try:
        driver = ModbusLockerDriver(
            host="127.0.0.1",
            port=port,
            device_id=1,
            pulse_ms=100,
            verify_timeout_ms=50,
            bays={"BAY-CP": ModbusBayMap(inner_gate_di=0, outer_door_di=1, lock_feedback_di=2, unlock_coil=5)},
            client_factory=RawAsyncModbusTcpClient,
        )
        with pytest.raises(RuntimeError, match="inner gate open"):
            await driver.unlock("BAY-CP", 5)
        assert sim.coils[5] is False
        assert sim.discrete_inputs[2] is True
        assert sim.discrete_inputs[1] is True
    finally:
        await sim.stop()


def test_modbus_driver_safe_unlock_over_real_tcp_protocol():
    asyncio.run(scenario_safe_unlock_over_real_tcp())


def test_modbus_driver_interlock_blocks_actuation_over_real_tcp_protocol():
    asyncio.run(scenario_open_inner_gate_blocks_network_write())
