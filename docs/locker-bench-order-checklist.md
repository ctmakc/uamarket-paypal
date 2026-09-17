# Locker bench order checklist

Use this list for the first physical Modbus locker bench. Do not energize a lock until feedback-only commissioning passes.

## Buy first

- [ ] 1 × Waveshare Modbus POE ETH IO 8CH, SKU 33917
- [ ] 1 × Mean Well HDR-60-24 (24 V / 2.5 A DIN PSU) or equivalent certified 24 VDC supply
- [ ] 1 × SECO-LARM SD-997C-GCQ for the first bay bench
- [ ] 1 × DPDT magnetic/position contact for the shared inner gate (reference: SECO-LARM SM-4201-L6Q)
- [ ] 2 × DIN fuse terminal blocks for the first-bay bench (main + lock branch)
- [ ] 5 × 20 mm fuses: 1 A main, 0.5 A lock branch, plus spares
- [ ] 1 × Hammond 1555YA2GY (300 × 240 × 120 mm) or equivalent deep IP/NEMA enclosure for the one-bay bench
- [ ] DIN rail, terminal blocks, ferrules, glands, labels and wire duct
- [ ] 18 AWG wire for lock power; 22 AWG suitable control cable for feedback contacts
- [ ] Ethernet patch cable
- [ ] 1 × adjustable spring plunger / compression-spring pop-open mechanism for the exterior door

The formerly referenced Hammond RP1450 is superseded for this build because it is too shallow for practical HDR-60 DIN-rail installation and wiring clearance. See `docs/locker-panel-layout-v1.md`.

## After one-bay acceptance

- [ ] 2 × additional SD-997C-GCQ locks
- [ ] 2 × additional lock branch fuse holders
- [ ] matching pop-open hardware for two additional doors
- [ ] additional terminals/glands/wire
- [ ] final 3-bay control enclosure in approximately the 16 × 12 × 6 in class if the bench enclosure is not reused only as a test fixture

## Software values

```dotenv
LOCKER_DRIVER=modbus
LOCKER_MODBUS_PORT=502
LOCKER_MODBUS_DEVICE_ID=1
LOCKER_UNLOCK_PULSE_MS=1500
LOCKER_UNLOCK_VERIFY_TIMEOUT_MS=750
LOCKER_MODBUS_MAP_JSON={"BAY-CP":{"inner_gate_di":0,"outer_door_di":1,"lock_feedback_di":2,"unlock_coil":0},"BAY-OTHER":{"inner_gate_di":0,"outer_door_di":3,"lock_feedback_di":4,"unlock_coil":1},"BAY-OVERFLOW":{"inner_gate_di":0,"outer_door_di":5,"lock_feedback_di":6,"unlock_coil":2}}
```

`LOCKER_UNLOCK_PULSE_MS` is the maximum actuation window, not a fixed dwell. The driver must release the coil earlier as soon as the bolt reports unlocked and the door reports physically open.

## Acceptance before connecting actuator power

- [ ] Modbus TCP reachable on isolated LAN
- [ ] module configured as Modbus TCP / port 502
- [ ] output channels configured in Normal mode
- [ ] `python -m scripts.locker_bench preflight` passes
- [ ] inner gate closed -> DI0 = 1
- [ ] inner gate open -> DI0 = 0
- [ ] outer door closed -> its assigned DI = 1
- [ ] outer door open -> assigned DI = 0
- [ ] lock physically locked -> lock feedback DI = 1
- [ ] lock physically unlocked -> lock feedback DI = 0
- [ ] disconnecting any feedback wire produces unsafe/0 state
- [ ] `locker_bench watch` shows stable states without chatter

## First powered unlock

- [ ] verify hardwired inner-gate pole removes +24 V from the common lock bus when gate opens
- [ ] install only BAY-CP 0.5 A branch fuse
- [ ] enable commissioning on cloud and edge explicitly
- [ ] close BAY-CP normally; verify door-closed + lock-locked inputs
- [ ] run one `locker_bench unlock --bay BAY-CP --confirm "UNLOCK BAY"`
- [ ] verify DO0 turns ON only inside the bounded actuation window
- [ ] verify lock feedback changes to unlocked
- [ ] verify spring/plunger moves door 10–20 mm and door input becomes open without a person pulling it
- [ ] verify DO0 returns OFF immediately after physical open, and always OFF on any error
- [ ] verify normal push-close re-latches and restores door-closed + lock-locked
- [ ] execute `docs/locker-100-cycle-acceptance.md` and log all 100 cycles before adding second and third locks

See `docs/locker-hardware-bom-v1.md`, `docs/locker-terminal-wiring-v1.md`, and `docs/locker-panel-layout-v1.md` for the full build references.
