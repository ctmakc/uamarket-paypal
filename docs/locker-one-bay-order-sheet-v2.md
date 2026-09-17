# Locker one-bay purchase sheet v2 — Southco outdoor architecture

Checked: 2026-08-31 (Canada)

Status: **buy control-panel items now; latch/striker/connector quote pending**.

This sheet supersedes `locker-one-bay-order-sheet-v1.md` for the preferred outdoor architecture. The technical default latch candidate is Southco `R4-EM-712-161`, based on Southco's cold/outdoor 5/7-series documentation and parcel-locker use case. Do not place the latch order until Steeves/Southco confirms Canadian price plus exact striker/connector.

## Buy now — independent of final latch quote

| Vendor | Qty | Part | Planning price CAD | Notes |
|---|---:|---|---:|---|
| Waveshare | 1 | Modbus POE ETH IO 8CH, SKU 33917 | 56.18 | 8DI/8DO Modbus TCP edge I/O |
| DigiKey Canada | 1 | Mean Well HDR-100-24 | 43.01 | 24 V / 3.83 A / 92 W; replaces HDR-60-24 |
| Mouser Canada | 1 | Hammond 1555YA2GY | 101.94 | deep one-bay bench enclosure |
| Mouser Canada | 1 | Hammond 1554YPL | 22.80 | inner steel mounting panel |
| KGE Électronique | 1 | SECO-LARM SM-4201-L6Q | 59.95 | shared inner-gate DPDT sensing contact; **signal only** |
| Canada Automation | 3 | Phoenix Contact PT 4-HESI 5×20 fuse terminal | 26.91 | F0/F1/F2 bench branches |
| Canada Automation | 1 | 35 mm DIN rail, 1 m | 4.95 | panel rails |
| Canada Automation | 12 | Phoenix Contact PT 2,5 | 16.80 | X1/X2/X3 terminals and spares |
| Canada Automation | 4 | Phoenix Contact CLIPFIX 35 | 4.36 | end clamps |
| DigiKey Canada | 2 | Phoenix Contact 2909524 PLC-RSC-24DC/21/EX | 30.02 ea / 60.04 | K0 master interlock + RY1 BAY-CP command relay |
| TremTech / Tane | 1 | Tane SD-80 magnetic steel-door contact | 7.37 | DS1 independent door-status input, -40…+60 °C |

### Known one-bay subtotal before latch/striker/connector

**CAD 404.31** before tax/shipping.

Add a planning allowance of **CAD 65** for fuses, wire, ferrules, glands, wire duct, labels and small panel hardware.

Current controllable one-bay spend before latch: **~CAD 469.31** before tax/shipping.

## Why HDR-100-24 replaced HDR-60-24

Southco family literature allows about **1 A peak/stall current per latch**. Three final bays could therefore approach ~3 A aggregate peak under a fault/concurrency scenario. `HDR-100-24` provides 24 V / 3.83 A and avoids designing the electrical envelope around the assumption that software will always unlock only one bay.

Current DigiKey Canada planning reference on 2026-08-31: CAD 43.01, 471 in stock.

## Why K0 was added

The previous concept used one pole of `SM-4201-L6Q` to break `LOCK_24V` directly. Do **not** build that version.

The SECO-LARM magnetic contact is rated only 10 W max / 1 A @10 VDC max; it is not a 24 V multi-latch power switch.

Revised architecture:

- S1 pole A -> DI0 telemetry;
- S1 pole B -> only the ~9 mA coil of master relay `K0`;
- K0 NO 6 A power contact creates/removes `LOCK_24V`;
- K0 de-energized = all exterior latch power removed;
- RY1 is a separate per-bay command relay driven by Waveshare DO0.

The final 3-bay panel therefore uses **four Phoenix 2909524 modules total**: K0 + RY1 + RY2 + RY3. The one-bay bench buys two.

## HOLD — Southco latch package pending quote

### Preferred latch

Southco `R4-EM-712-161`:

- electronic rotary push-to-close latch;
- delayed relock;
- strong kickout spring;
- internal latch-status switch;
- steel/nickel-plated housing;
- 12–24 VDC family;
- outdoor 5/7-series documentation reaches -40 °C class;
- actuator/switch outdoor literature specifies IP56;
- current family literature specifies 1 A peak/stall current and 25 mA max control-input current;
- release transit is configuration/revision dependent and can approach ~1.0–1.4 s max;
- Southco stock page showed 3 units at Steeves Agencies, Winnipeg during this sourcing pass.

Public secondary-market prices are not used as the Canadian procurement price. Wait for Steeves/Southco quote.

### Striker — exact part pending

Compatible 5/7-series options include:

- `R4-90-121-10` / `R4-90-121-20` large striker-bolt family;
- `R4-90-800-10` cast striker without integrated door sensor.

Freeze exact striker after Steeves/Southco recommendation and mechanical alignment review.

### Connector/harness — pending

Exact mating connector/harness/pigtail is to be confirmed before order and retained with the build record.

### Why separate door sensor

The selected `712-161` candidate carries latch-status feedback but not true door-position sensing. Use the separate Tane SD-80 on DI1.

This preserves the logical safety model:

`inner_gate_closed + outer_door_closed + latch_locked`.

## Interface relay requirement

Do not power the Southco internal motor from a Waveshare DO. Waveshare DO max is 500 mA/channel while Southco family literature allows 1 A peak/stall.

Use Phoenix Contact `2909524`:

- K0: hard-interlock lock-bus relay;
- RY1: BAY-CP control-interface relay;
- Waveshare DO sinks only ~9 mA RY1 coil current;
- RY1 dry contact applies `LOCK_24V` to the Southco control input;
- Southco motor/electronics get separately fused `LOCK_24V` power.

Phoenix rates this relay at 6 A limiting continuous current, 10 A short inrush, and 140 W ohmic switching at 24 VDC. This is comfortably above the planned aggregate latch bus, subject to the usual final load/fuse verification.

See `docs/locker-southco-r4-em-v2.md`.

## Provisional fuse allowance

Do not order a large batch of final fuse values yet. Initial bench engineering targets are:

- F0 control/I-O: ~0.5 A;
- F1 master latch bus: ~4 A time-delay;
- F2 BAY-CP latch branch: ~1.5 A time-delay;
- later F3/F4 same class if physical measurements support it.

These values are **not frozen**. Exact latch drawing, actual current/inrush, wire gauge, run length and fuse curve must be checked before final production selection.

## Consumables

Keep CAD 50–80 allowance, planning midpoint CAD 65:

- small quantity of candidate 5×20 fuses plus spares;
- 18 AWG stranded power wire reference;
- 22 AWG control/sense wire;
- ferrules;
- cable glands after actual cable OD is known;
- wire duct;
- permanent wire markers;
- Ethernet patch cable;
- DIN mounting hardware.

## Buy sequence

1. DigiKey: HDR-100-24 + **2× Phoenix 2909524** for the one-bay bench.
2. Mouser: 1555YA2GY + 1554YPL.
3. Canada Automation: fuse terminals + DIN rail + PT2.5 + CLIPFIX + convenient consumables.
4. Waveshare: SKU 33917.
5. KGE: SM-4201-L6Q can proceed as the low-current inner-gate sensing/interlock-control device.
6. TremTech/Tane: 1× SD-80 for BAY-CP; final build needs 3.
7. Wait for Steeves/Southco response before ordering R4-EM latch, striker and mating connector/harness.
8. Power only BAY-CP until 100-cycle acceptance passes.

## Requests already sent

- `info@kge.ca`: cold-rated monitored cabinet/parcel-locker option and previous SECO-LARM quote.
- `sales@steeves.ca`: 3× R4-EM-712-161, striker/connector, Ottawa delivery, temperature and sensor configuration.
- `info@southco.com`: recommended exact R4-EM configuration for unheated Ottawa parcel locker.

## Technical references

- `docs/locker-southco-r4-em-v2.md`
- `docs/locker-terminal-wiring-v2-southco.md` once frozen in repo
- `docs/locker-panel-layout-v1.md`
- `docs/locker-100-cycle-acceptance.md`
- `scripts/locker_acceptance.py`

## Acceptance rule

Cold rating and industrial provenance do not replace physical acceptance. BAY-CP still requires 100 consecutive PASS cycles, including hard-interlock tests, latch release, kickout/open detection, command relay de-energization, close/relock and sensor stability before RY2/RY3 are enabled.
