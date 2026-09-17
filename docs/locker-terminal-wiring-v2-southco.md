# Locker terminal wiring v2 — Southco R4-EM outdoor architecture

Status: assembly reference for Southco-based BAY-CP bench and later 3-bay expansion
Date: 2026-08-31

This document **supersedes `locker-terminal-wiring-v1.md` for actuator power, inner-gate hard-interlock power switching, Waveshare DOCOM, PSU sizing and exterior latch wiring** when the Southco R4-EM architecture is used.

The old v1 document remains useful historical context, but **do not build the v1 direct-S1/direct-lock-output circuit**.

This document covers the 24 VDC secondary/control side only. Upstream 120 VAC branch wiring, disconnecting means, bonding/grounding and applicable inspection/code work remain outside this drawing.

## Device tags

| Tag | Device / function |
|---|---|
| PS1 | Mean Well HDR-100-24, 24 V / 3.83 A DIN PSU |
| IO1 | Waveshare Modbus POE ETH IO 8CH |
| S1 | SECO-LARM SM-4201-L6Q DPDT shared inner-gate position contact; **signal current only** |
| K0 | Phoenix Contact 2909524 master `LOCK_24V` interlock relay |
| RY1 | Phoenix Contact 2909524 BAY-CP unlock-command interface relay |
| RY2 | same, BAY-OTHER, after expansion |
| RY3 | same, BAY-OVERFLOW, after expansion |
| L1 | Southco R4-EM-712-161 candidate, BAY-CP |
| L2 | same, BAY-OTHER after expansion |
| L3 | same, BAY-OVERFLOW after expansion |
| DS1 | Tane SD-80 BAY-CP outer-door sensor |
| DS2 | Tane SD-80 BAY-OTHER outer-door sensor |
| DS3 | Tane SD-80 BAY-OVERFLOW outer-door sensor |
| F0 | control/I-O branch fuse, provisional ~0.5 A |
| F1 | master lock-bus fuse, provisional ~4 A time-delay |
| F2 | BAY-CP latch branch fuse, provisional ~1.5 A time-delay |
| F3 | BAY-OTHER latch branch fuse, provisional ~1.5 A time-delay |
| F4 | BAY-OVERFLOW latch branch fuse, provisional ~1.5 A time-delay |
| X1 | internal 24 V source/bus terminals |
| X2 | field status/sense terminals |
| X3 | latch power/control field terminals |

Fuse values above are engineering starting points only; freeze after exact purchased latch drawing, conductor selection and measured current/inrush.

## Fundamental rules

1. `CONTROL_24V` remains powered while the inner gate is open so IO1 and diagnostics remain alive.
2. `LOCK_24V` exists only while K0 is energized.
3. K0 is energized only through the **safe/closed pole B of S1**.
4. S1 never carries latch/motor current. It carries only K0 coil current (~9 mA).
5. K0 uses its NO contact: loss of S1/contact/control power drops K0 and removes `LOCK_24V`.
6. Southco latch motor/electronics are powered from separately fused `LOCK_24V`; they are **not** powered through a Waveshare DO.
7. Waveshare DO0/1/2 sink only RY1/2/3 relay coils (~9 mA each).
8. `IO1 DOCOM -> CONTROL_24V` because the inductive loads on DO are relay coils supplied from `CONTROL_24V`.
9. `IO1 DICOM -> 0V`; all status inputs are PNP/high-level safe-state inputs.
10. This is an access-control interlock, not the robot safety circuit. Robot E-stop/guarding/safety relay remains separate.

## Power topology

```text
PS1 HDR-100-24 +24V
  |
  +---- X1.01 +24V_RAW
          |
          +---- F0 ---- X1.03 CONTROL_24V -----------------------------+
          |                                                             |
          |                                                             +--> IO1 +V
          |                                                             +--> S1A telemetry common
          |                                                             +--> S1B interlock common
          |                                                             +--> RY1/RY2/RY3 coil +
          |                                                             +--> DS1/DS2/DS3 contact commons
          |                                                             +--> L1/L2/L3 latch-switch commons
          |
          +---- F1 ---- X1.04 LOCK_PRE_INTERLOCK ---- K0 COM
                                                    K0 NO ---- X1.05 LOCK_24V
                                                                  |
                                                                  +--> F2 --> L1 POWER+
                                                                  +--> F3 --> L2 POWER+
                                                                  +--> F4 --> L3 POWER+
                                                                  +--> RY1/RY2/RY3 COM

PS1 0V ---- X1.02 0V ----------------------------------------------+--> IO1 GND
                                                                   +--> IO1 DICOM
                                                                   +--> K0 coil -
                                                                   +--> L1/L2/L3 GND
```

## K0 master hard-interlock control

```text
CONTROL_24V --> S1 pole B COM
S1B SAFE/CLOSED return --> K0 coil +
0V ---------------------> K0 coil -

LOCK_PRE_INTERLOCK --> K0 COM
K0 NO -------------> LOCK_24V
K0 NC -------------> unused / isolated
```

Acceptance condition: with S1/gate open, K0 must be physically de-energized and `LOCK_24V` must measure approximately 0 V even if any Waveshare DO is commanded ON.

## S1 telemetry pole

```text
CONTROL_24V --> S1 pole A COM
S1A SAFE/CLOSED return --> X2.01 --> IO1 DI1 (zero-based address 0)
```

Do not infer contact selection from wire colour. Identify both S1 poles and safe-state contacts with a continuity meter.

## Waveshare common wiring

```text
IO1 DICOM --> 0V
IO1 DOCOM --> CONTROL_24V
```

This differs from v1. `DOCOM` is now tied to the supply feeding RY1/RY2/RY3 coils so the Waveshare output-stage flyback path matches the inductive load supply.

## BAY-CP command relay RY1

```text
CONTROL_24V --> RY1 coil +
RY1 coil - --> IO1 DO1  (zero-based coil address 0)

LOCK_24V --> RY1 COM
RY1 NO --> X3.03 --> L1 CONTROL INPUT (Southco pin 3 / orange in family literature)
RY1 NC --> unused / isolated
```

## BAY-CP Southco latch L1

Southco R4-EM family connector convention used by this design; confirm against the exact purchased part drawing before termination:

| Southco pin | Family wire colour | Function | v2 connection |
|---:|---|---|---|
| 1 | Brown | Ground | X3.02 -> 0V |
| 2 | Red | Power 12–24 VDC | X3.01 <- F2 output `L1_POWER+` |
| 3 | Orange | Control signal | X3.03 <- RY1 NO |
| 4 | Black | Latch microswitch common | CONTROL_24V |
| 5 | Blue | Microswitch N.O. | X2.03 -> DI3 if continuity test proves this is `locked=true` |
| 6 | Grey | Microswitch N.C. | insulated spare unless exact purchased configuration requires otherwise |

The Southco family literature describes the optional microswitch as closing upon latch closure. Nevertheless, verify pins 4/5/6 on the actual unit with a continuity meter before connecting 24 V sense voltage.

## BAY-CP independent door sensor DS1

```text
CONTROL_24V --> DS1 safe-contact common
DS1 return CLOSED only when outer door is fully closed --> X2.02 --> IO1 DI2
```

DS1 is separate from latch status. The two inputs answer different questions:

- DI2 / `outer_door_closed`: is the physical door actually closed?
- DI3 / `latch_locked`: is the rotary latch mechanically in the locked state?

Both must be true before an unlock command is accepted.

## Exact Modbus map

Physical terminal numbering on IO1 is one-based; software addresses are zero-based.

| IO1 terminal | Address | Signal |
|---|---:|---|
| DI1 | 0 | shared `inner_gate_closed` |
| DI2 | 1 | BAY-CP `outer_door_closed` |
| DI3 | 2 | BAY-CP `latch_locked` |
| DI4 | 3 | BAY-OTHER `outer_door_closed` |
| DI5 | 4 | BAY-OTHER `latch_locked` |
| DI6 | 5 | BAY-OVERFLOW `outer_door_closed` |
| DI7 | 6 | BAY-OVERFLOW `latch_locked` |
| DI8 | 7 | spare/tamper |
| DO1 | 0 | BAY-CP RY1 command |
| DO2 | 1 | BAY-OTHER RY2 command |
| DO3 | 2 | BAY-OVERFLOW RY3 command |
| DO4–DO8 | 3–7 | spare |

K0 is intentionally **not software-controlled**.

## Terminal schedule

### X1 — internal DC buses

| Terminal | Net | Connections |
|---|---|---|
| X1.01 | `+24V_RAW` | PS1 +24 V; F0 input; F1 input |
| X1.02 | `0V` | PS1 0 V; IO1 GND/DICOM; K0 coil -; Southco grounds |
| X1.03 | `CONTROL_24V` | F0 output; IO1 power; DOCOM; relay coils; status-contact excitation |
| X1.04 | `LOCK_PRE_INTERLOCK` | F1 output -> K0 COM |
| X1.05 | `LOCK_24V` | K0 NO output -> F2/F3/F4 + RY1/2/3 COM |
| X1.06 | spare | reserved |

### X2 — status returns

| Terminal | Signal | Destination | Safe logical state |
|---|---|---|---|
| X2.01 | S1A inner-gate return | DI1 | gate fully closed = 1 |
| X2.02 | DS1 BAY-CP door return | DI2 | door fully closed = 1 |
| X2.03 | L1 latch-status return | DI3 | latch locked = 1 |
| X2.04 | DS2 BAY-OTHER door return | DI4 | door closed = 1 |
| X2.05 | L2 latch-status return | DI5 | latch locked = 1 |
| X2.06 | DS3 BAY-OVERFLOW door return | DI6 | door closed = 1 |
| X2.07 | L3 latch-status return | DI7 | latch locked = 1 |
| X2.08 | spare/tamper | DI8 | application specific |
| X2.09 | `CONTROL_24V` field sense feed | sensor/switch commons | +24 V protected |

### X3 — latch field connections

| Terminal | Net | BAY-CP connection |
|---|---|---|
| X3.01 | `L1_POWER+` | F2 output -> Southco pin 2 |
| X3.02 | `L1_GND` | 0V -> Southco pin 1 |
| X3.03 | `L1_CONTROL` | RY1 NO -> Southco pin 3 |
| X3.04 | `L1_SWITCH_COM` | CONTROL_24V -> Southco pin 4 |
| X3.05 | `L1_SWITCH_NC_SPARE` | Southco pin 6, insulated/spare |
| X3.06 | `LOCK_24V_TEST` | protected service test point |
| X3.07 | `CONTROL_24V_TEST` | protected service test point |
| X3.08 | `0V_TEST` | protected service test point |

For final three-bay build, add an equivalent field-terminal group per latch rather than doubling conductors under one terminal unless that terminal is explicitly rated/configured for it.

## Provisional fuse schedule

| Fuse | Starting value | Function |
|---|---:|---|
| F0 | ~0.5 A | IO1, K0/RYx coils, feedback sensing |
| F1 | ~4 A time-delay | aggregate lock bus before K0 |
| F2 | ~1.5 A time-delay | BAY-CP Southco power branch |
| F3 | ~1.5 A time-delay | BAY-OTHER after expansion |
| F4 | ~1.5 A time-delay | BAY-OVERFLOW after expansion |

**Not frozen for production.** Final fuse/current protection must be coordinated with actual Southco revision, harness wire gauge, field wire gauge, measured startup/stall behavior and the chosen fuse time-current curve.

## Dead-panel checks — no 24 V applied

1. Remove F0–F4.
2. Verify no short from `+24V_RAW` to 0V.
3. Verify S1A and S1B both change only at the intended fully-closed inner-gate position.
4. Verify S1B does **not** connect to `LOCK_PRE_INTERLOCK` or latch power; it goes only to K0 coil +.
5. Verify K0 COM/NO/NC terminals by relay datasheet/continuity, not assumption.
6. Verify K0 NO is open with K0 de-energized.
7. Verify RY1 NO is open with RY1 de-energized.
8. Verify DS1 changes state only when the exterior door leaves/enters the accepted closed zone.
9. Verify Southco pins 4/5/6 continuity in locked/unlocked mechanical states.
10. Verify each latch power branch is isolated from the others.

## Powered feedback-only commissioning

1. Install F0 only. F1–F4 remain removed.
2. Confirm PS1 output near 24 V and IO1 online.
3. Confirm `DICOM=0V`, `DOCOM=CONTROL_24V`.
4. Inner gate closed -> DI1=1 and K0 coil energizes, but no latch power exists because F1 is absent.
5. Inner gate open -> DI1=0 and K0 coil drops.
6. Disconnect S1A return -> DI1 must go unsafe/0.
7. Disconnect S1B return -> K0 must drop.
8. Exercise DS1 and latch switch manually; verify safe-state polarity.
9. Run `locker_bench watch`; reject chatter/ambiguous sensor positions.

## First lock-bus test — latch still disconnected

1. Keep latch L1 unplugged.
2. Install F1.
3. Gate open -> K0 de-energized -> `LOCK_24V` approximately 0 V.
4. Gate closed -> K0 energized -> `LOCK_24V` approximately 24 V.
5. Open gate while measuring `LOCK_24V`; verify immediate collapse regardless of DO commands.
6. Command DO1 with L1 still disconnected: RY1 may click, but gate-open condition must still leave RY1 COM/NO source without `LOCK_24V`.

## First BAY-CP actuator test

Only after all prior checks:

1. Confirm exact Southco part drawing, striker and harness.
2. Install F2 and connect L1.
3. Confirm initial `door_closed=1`, `latch_locked=1`, `inner_gate_closed=1`.
4. Run one commissioning unlock.
5. Expected sequence: DO1 ON -> RY1 closes -> Southco control HIGH -> latch feedback unlocks -> kickout causes DS1 door-open -> DO1 OFF / RY1 drops.
6. Verify command output never remains active past configured cap.
7. Close door normally -> `door_closed=1` + `latch_locked=1` without manual manipulation of latch.
8. Open inner gate and prove a software unlock cannot produce latch motion.
9. Then run 100 consecutive physical acceptance cycles before adding L2/L3.

## Important boundary

K0/S1 provides a fail-deenergized locker actuator interlock. It is **not represented as a certified personnel-safety relay or robot safety function**. The physical pass-through/dog-leg must prevent reach into the garage/robot zone, and robot machine safety must use its own appropriate guarding, interlocks, E-stops and safety-rated control architecture.

## Primary references

- Southco R4-EM family literature: https://media.southco.com/media/static/Literature/r4-em.en.pdf
- Southco outdoor R4-EM 5/7 series: https://files.southco.com/static/Literature/r4-em-od.en.pdf
- Phoenix Contact 2909524: https://www.phoenixcontact.com/en-ca/products/relay-module-plc-rsc-24dc21ex-2909524
- SECO-LARM SM-4201-L6Q: https://www.seco-larm.com/product/sm-4201-l6q/
- Waveshare Modbus IO: https://docs.waveshare.com/Modbus_POE_ETH_IO_8CH
- Mean Well HDR-100-24: DigiKey Canada 1866-2233-ND
