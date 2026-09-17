# Locker terminal wiring v1 — 3 carrier bays

Status: assembly reference for the 24 VDC locker control panel
Date: 2026-08-31

This document freezes the **24 VDC secondary/control wiring** for the first three-bay locker panel. It intentionally does not prescribe the 120 VAC branch-circuit wiring upstream of the certified DIN power supply. The mains side, enclosure entry, disconnect/overcurrent protection, grounding/bonding and inspection requirements must be handled to the applicable electrical code by a qualified person.

The design uses one shared internal loading gate and three external carrier doors: `BAY-CP`, `BAY-OTHER`, and `BAY-OVERFLOW`.

This document supersedes the passive/floating DI wording in the earlier BOM. Inputs are frozen here as 24 V PNP/wet-contact inputs: `DICOM -> 0V`, and a safe-state field contact applies `CONTROL_24V` to its DI channel.

## Device tags

| Tag | Device |
|---|---|
| PS1 | Mean Well HDR-60-24, 24 VDC PSU |
| IO1 | Waveshare Modbus POE ETH IO 8CH |
| S1 | Shared inner-gate DPDT position contact |
| L1 | BAY-CP SECO-LARM SD-997C-GCQ |
| L2 | BAY-OTHER SECO-LARM SD-997C-GCQ |
| L3 | BAY-OVERFLOW SECO-LARM SD-997C-GCQ |
| F0 | 0.5 A control/I-O fuse |
| F1 | 1.0 A main lock-bus fuse |
| F2 | 0.5 A BAY-CP lock branch fuse |
| F3 | 0.5 A BAY-OTHER lock branch fuse |
| F4 | 0.5 A BAY-OVERFLOW lock branch fuse |
| X1 | 24 VDC source/distribution terminals |
| X2 | input/sense terminals |
| X3 | lock/output field terminals |

## Design rules

1. `CONTROL_24V` and `LOCK_24V` are separate branches from `+24V_RAW`.
2. Opening the inner loading gate removes `LOCK_24V` electrically through pole B of S1, while IO1 remains powered and can still report the unsafe state.
3. Inputs use Waveshare's 24 V PNP/wet-contact mode: `DICOM -> 0V`; a safe/normal closed contact applies `CONTROL_24V` to its DI channel.
4. Therefore a broken field conductor tends to produce DI=0 / unsafe.
5. External lock outputs are NPN open-drain sinks. `DOCOM` is tied to `LOCK_24V` as required for the module's flyback-diode common.
6. Lock power is fail-secure: loss of power leaves the exterior lock mechanically secured.
7. Do not rely on SECO-LARM wire colours as the acceptance criterion. Identify each status contact by COM/NO/NC function and verify with a continuity meter before termination.
8. No software commissioning mode may bypass S1 pole B.

## Power topology

```text
PS1 +24V
  |
  +---- X1.01  +24V_RAW
          |
          +---- F0 0.5A ---- CONTROL_24V ----------------------+
          |                                                      |
          |                                                      +--> IO1 +7..36V
          |                                                      +--> S1 pole A common
          |                                                      +--> L1 door/lock status contact commons
          |                                                      +--> L2 door/lock status contact commons
          |                                                      +--> L3 door/lock status contact commons
          |
          +---- F1 1.0A ---- S1 pole B CLOSED-WHEN-GATE-CLOSED ---- LOCK_24V
                                                                   |
                                                                   +--> IO1 DOCOM
                                                                   +--> F2 0.5A --> L1 lock +
                                                                   +--> F3 0.5A --> L2 lock +
                                                                   +--> F4 0.5A --> L3 lock +

PS1 0V
  |
  +---- X1.02  0V ------------------------------------------------+--> IO1 GND
                                                                   +--> IO1 DICOM

L1 lock - --------------------------------------------------------------> IO1 DO1
L2 lock - --------------------------------------------------------------> IO1 DO2
L3 lock - --------------------------------------------------------------> IO1 DO3
```

## Input topology

All status inputs are wired so the **safe state is logical 1**.

```text
CONTROL_24V --> S1 pole A safe contact --------------------------> IO1 DI1
CONTROL_24V --> L1 door-status contact CLOSED when door closed --> IO1 DI2
CONTROL_24V --> L1 lock-status contact CLOSED when locked ------> IO1 DI3
CONTROL_24V --> L2 door-status contact CLOSED when door closed --> IO1 DI4
CONTROL_24V --> L2 lock-status contact CLOSED when locked ------> IO1 DI5
CONTROL_24V --> L3 door-status contact CLOSED when door closed --> IO1 DI6
CONTROL_24V --> L3 lock-status contact CLOSED when locked ------> IO1 DI7
CONTROL_24V --> spare/tamper contact if used --------------------> IO1 DI8

IO1 DICOM -------------------------------------------------------> 0V
```

This is the Waveshare documented high-level / PNP input mode: DICOM is connected to supply negative and the field contact presents positive voltage to the DI channel.

## Exact Modbus map

| IO1 terminal | Zero-based address | Signal |
|---|---:|---|
| DI1 | 0 | shared `inner_gate_closed` |
| DI2 | 1 | `BAY-CP outer_door_closed` |
| DI3 | 2 | `BAY-CP lock_feedback_locked` |
| DI4 | 3 | `BAY-OTHER outer_door_closed` |
| DI5 | 4 | `BAY-OTHER lock_feedback_locked` |
| DI6 | 5 | `BAY-OVERFLOW outer_door_closed` |
| DI7 | 6 | `BAY-OVERFLOW lock_feedback_locked` |
| DI8 | 7 | spare / tamper |
| DO1 | 0 | `BAY-CP unlock` |
| DO2 | 1 | `BAY-OTHER unlock` |
| DO3 | 2 | `BAY-OVERFLOW unlock` |
| DO4–DO8 | 3–7 | spare |

## Terminal schedule

### X1 — DC source and internal buses

| Terminal | Net | Connected to |
|---|---|---|
| X1.01 | `+24V_RAW` | PS1 +24V; F0 input; F1 input |
| X1.02 | `0V` | PS1 0V; IO1 GND; IO1 DICOM |
| X1.03 | `CONTROL_24V` | F0 output; IO1 power +; status-contact supply |
| X1.04 | `LOCK_PRE_INTERLOCK` | F1 output; S1 pole B COM |
| X1.05 | `LOCK_24V` | S1 pole B safe-state output; IO1 DOCOM; F2/F3/F4 inputs |

### X2 — field status contacts

| Terminal | Field wire | IO1 destination | Required closed condition |
|---|---|---|---|
| X2.01 | S1 pole A return | DI1 | inner gate fully closed |
| X2.02 | L1 door-status return | DI2 | BAY-CP outer door fully closed |
| X2.03 | L1 lock-status return | DI3 | BAY-CP bolt/lock secured |
| X2.04 | L2 door-status return | DI4 | BAY-OTHER outer door fully closed |
| X2.05 | L2 lock-status return | DI5 | BAY-OTHER bolt/lock secured |
| X2.06 | L3 door-status return | DI6 | BAY-OVERFLOW outer door fully closed |
| X2.07 | L3 lock-status return | DI7 | BAY-OVERFLOW bolt/lock secured |
| X2.08 | spare/tamper return | DI8 | application-specific |
| X2.09 | `CONTROL_24V` field supply | contact commons | common +24 V sense feed |

### X3 — lock actuators

| Terminal | Net | Connected to |
|---|---|---|
| X3.01 | `L1_LOCK_PLUS` | F2 output -> L1 lock + |
| X3.02 | `L1_LOCK_MINUS` | L1 lock - -> IO1 DO1 |
| X3.03 | `L2_LOCK_PLUS` | F3 output -> L2 lock + |
| X3.04 | `L2_LOCK_MINUS` | L2 lock - -> IO1 DO2 |
| X3.05 | `L3_LOCK_PLUS` | F4 output -> L3 lock + |
| X3.06 | `L3_LOCK_MINUS` | L3 lock - -> IO1 DO3 |
| X3.07 | `LOCK_24V` service test | protected test point only |
| X3.08 | `0V` service test | protected test point only |

## Inner-gate DPDT contact S1

Use both poles of the same mechanically actuated device where practicable.

- **Pole A — telemetry:** `CONTROL_24V -> S1A COM -> S1A safe-state contact -> X2.01 -> DI1`.
- **Pole B — hard interlock:** `F1 output -> S1B COM -> S1B safe-state contact -> LOCK_24V`.

The two poles must change state from the same physical gate motion. During commissioning, verify that there is no gate position where software reports closed while pole B still permits lock power with the gate materially open.

## Fuse schedule

| Fuse | Rating | Protects |
|---|---:|---|
| F0 | 0.5 A | IO1 + input-sense/control branch |
| F1 | 1.0 A | total three-lock actuator bus |
| F2 | 0.5 A | BAY-CP actuator branch |
| F3 | 0.5 A | BAY-OTHER actuator branch |
| F4 | 0.5 A | BAY-OVERFLOW actuator branch |

Use suitably rated DC fuses/fuse terminals. Final ratings should be confirmed against actual inrush, conductor gauge and the selected installation method after the first physical measurements.

## Wire identification convention

- Every conductor gets a permanent wire ID at both ends.
- Recommended internal convention only: red = unswitched/switched +24 V, black = 0 V, orange = lock-actuator switched branch, white = status signal. Local code/project conventions take precedence.
- Lock power: 18 AWG stranded copper reference.
- Status/sense: 22 AWG stranded control cable reference.
- Ferrules at DIN/screw terminals; no bare stranded wire under screw clamps.

See `docs/locker-wire-list-v1.csv` for the point-to-point list.

## Dead-panel continuity checks — no 24 V applied

1. Remove F0–F4.
2. Verify no continuity between `+24V_RAW` and `0V`.
3. Verify S1 pole B is open with the inner gate open and closed only with the gate fully closed.
4. Verify each door-status return closes only in the fully closed position.
5. Verify each lock-status return closes only when the bolt is physically secured.
6. Verify DO1/DO2/DO3 are not accidentally bonded to +24 V at the terminal strip.
7. Verify each actuator branch is isolated from the other two branches.

## Powered feedback-only checks — actuators still fused off

1. Install F0 only. Leave F1–F4 removed.
2. Confirm IO1 power/network operation.
3. Confirm DICOM-to-0V wiring and `CONTROL_24V` around 24 VDC.
4. Move S1/L1/L2/L3 contacts manually and confirm DI1–DI7 polarity.
5. Disconnect each field return one at a time; the corresponding DI must become 0/unsafe.
6. Run `python -m scripts.locker_bench watch --interval 0.5` and verify no chatter.

## First actuator test

1. Install F1 and F2 only; F3/F4 remain removed.
2. With inner gate **open**, verify `LOCK_24V` is approximately 0 V and a commanded DO1 cannot energize L1.
3. Close inner gate; verify `LOCK_24V` returns to approximately 24 V.
4. Confirm L1 door closed and L1 lock feedback locked.
5. Enable commissioning and perform one safe unlock.
6. Verify the sequence: DO1 ON -> lock feedback unlocked -> DO1 OFF.
7. Repeat 100 cycles before enabling L2/L3 branches.

## Important implementation boundary

This drawing is the locker-control circuit, not the robot/machine safety circuit. Robot E-stop, guarding, interlocked service access and any required safety relay/PLC remain separate. Also, do not infer or improvise the 120 VAC line-side wiring from this document.

## Vendor references

- Waveshare IO overview/wiring: https://docs.waveshare.com/Modbus_POE_ETH_IO_8CH
- Waveshare configuration: https://docs.waveshare.com/Modbus_POE_ETH_IO_8CH/Module-Parameter-Configuration
- SECO-LARM SD-997C-GCQ: https://www.seco-larm.com/product/sd-997c-gcq/
