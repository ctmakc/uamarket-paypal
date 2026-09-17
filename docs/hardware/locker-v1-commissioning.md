# Locker v1 — bench commissioning

This document is for the first freestanding courier-locker prototype. It does not replace the final hardwired interlock/safety design.

## Logical I/O per bay

- `inner_gate_di`: TRUE only when the internal loading gate is physically closed.
- `outer_door_di`: TRUE only when the courier door is physically closed.
- `lock_feedback_di`: TRUE only when the fail-secure lock reports locked.
- `unlock_coil`: momentary output used to release the outer lock.

The external-lock power path must be physically conditioned on `inner_gate_closed`; software checks are defense in depth, not the only interlock.

## First bench sequence

1. Power the PLC/I/O module and sensors with the unlock actuator disconnected.
2. Configure `LOCKER_MODBUS_*` and `LOCKER_MODBUS_MAP_JSON`.
3. Run `python scripts/locker_bench.py status` and verify every input manually by opening/closing each switch.
4. Run `python scripts/locker_bench.py watch --interval 0.5` and confirm no bouncing/inverted signals.
5. Connect the lock output through the physical inner-gate interlock.
6. Keep `EDGE_COMMISSIONING_ENABLED=false` and confirm `unlock` is refused.
7. Set `EDGE_COMMISSIONING_ENABLED=true` only for the bench session.
8. With both doors/gates closed and lock feedback TRUE, run:

   `python scripts/locker_bench.py unlock --bay BAY-CP --confirm "UNLOCK BAY"`

9. Verify the output pulse de-energizes and feedback changes as expected.
10. Repeat failure tests: inner gate open, outer door open, already-unlocked feedback, disconnected lock feedback. None may energize the unlock output except the intended feedback-failure test after the preconditions have passed; in that case the output must still return OFF.
11. Return `EDGE_COMMISSIONING_ENABLED=false` after the session.

## Production rule

Do not use the bench CLI as the courier access path. Production access remains cloud authorization → device-scoped edge command → local durable journal → physical driver → sensor event/ACK.
