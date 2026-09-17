# Locker hardware v2 — outdoor Southco R4-EM architecture

Status: technical default candidate; latch purchase awaits Canadian distributor quote
Date: 2026-08-31

This document defines the preferred outdoor-capable locker latch architecture discovered after the original SD-997C-GCQ bench design. It supersedes v1 for exterior latch selection, actuator-drive wiring, lock-bus interlock topology and PSU sizing if `R4-EM-712-161` is purchased.

## Why the latch selection changed

The original SECO-LARM `SD-997C-GCQ` can work electrically but needs a separate pop-open device and its cold-weather suitability was not sufficiently established for an unheated Ottawa exterior locker.

SECO-LARM `CL-210M-U3BQ` has an attractive integrated spring pop-open feature but its published operating range bottoms out at **-10 °C**, so it is not the preferred unheated Ottawa exterior mechanism.

Southco R4-EM 5/7-series hardware is specifically positioned for demanding/outdoor electronic access and parcel-locker applications. Current Southco documentation for the family gives:

- operating temperature down to **-40 °C** and up to +80 °C for the relevant outdoor family/drawings;
- sealed electronic actuator/switch architecture, with outdoor literature specifying IP56 protection for the actuator/switch;
- recommended 12–24 VDC supply;
- typical current under 500–600 mA at 12 VDC depending revision/configuration;
- **1 A peak/stall operating current** in current family literature;
- separate electronic control input, **25 mA max** in current Southco literature;
- latch release transit roughly 0.5–0.6 s typical and up to about 1.0–1.4 s depending exact actuator revision/configuration;
- corrosion-resistant plated-steel and stainless configurations.

Because Southco has several revisions/configurations, the final acceptance record must retain the exact drawing supplied for the purchased part rather than relying only on family summaries.

## Preferred latch candidate

`R4-EM-712-161`

- R4-EM 7-series outdoor electronic rotary latch;
- delayed relock;
- side trigger;
- strong kickout spring;
- internal latch-status switch;
- steel housing, nickel plated;
- 12–24 VDC family;
- push-to-close;
- concealed/internal installation;
- Southco stock page showed 3 units at authorized Canadian distributor Steeves Agencies, Winnipeg, during the 2026-08-31 sourcing pass.

Exact purchase price, matching striker, mating connector/harness and exact part-specific drawing are pending Steeves/Southco response.

### Striker

R4-EM 5/7 series supports the Southco large striker-bolt family `R4-90-121-XX` and cast striker `R4-90-800-10`. Freeze the exact striker only after distributor/manufacturer confirmation and a mechanical layout check.

Do not assume `R4-90-804-10` door-sensor striker compatibility with 5/7 series; Southco's published compatibility table does not mark it for this family.

## Exterior door status sensor

Use a **separate cold-rated magnetic contact** because `R4-EM-712-161` provides latch status but not true door-position sensing.

Preferred prototype reference: Tane `SD-80` recessed steel-door magnetic contact.

- designed for steel doors;
- approximately -40 °C to +60 °C operating range;
- ~28 mm standard gap;
- 22 AWG leads;
- current Canadian listing observed around CAD 7.37.

Continuity-test the actual contact + magnet before wiring; acceptance is based on measured safe-state polarity, not nomenclature or wire colour.

## Output interface — do NOT power the Southco motor from Waveshare DO

The Waveshare 33917 output is an NPN Darlington/open-drain output rated **500 mA/channel max**. Southco family literature allows **1 A peak/stall**. Therefore direct latch-motor switching by Waveshare DO is prohibited.

Use one small DIN interface relay per bay:

`RY1/RY2/RY3 = Phoenix Contact PLC-RSC-24DC/21/EX, 2909524`

- 24 VDC coil;
- ~9 mA coil current;
- SPDT 6 A power contact;
- 10 A short-duration inrush capability;
- 140 W max ohmic interrupting rating at 24 VDC;
- DIN rail;
- -40 °C to +60 °C class in the manufacturer data used for this design.

The Waveshare output only sinks the relay coil. The relay dry contact presents `LOCK_24V` to the Southco CONTROL input. The Southco latch receives its own separately fused power feed.

## Critical correction — S1 must NOT carry the latch power bus

The earlier v1 scheme routed `LOCK_24V` directly through one pole of `SM-4201-L6Q`. That is superseded.

SECO-LARM rates `SM-4201-L6Q` at only **10 W max / 1 A @ 10 VDC max**. It is a signaling contact, not a 3 A / 24 VDC lock-bus switch.

### Master interlock relay K0

Add a fourth Phoenix Contact `2909524` relay as `K0`.

- S1 pole A remains telemetry for `inner_gate_closed`.
- S1 pole B switches only the ~9 mA **K0 coil**.
- K0 is energized only while the inner gate is fully closed.
- The K0 NO power contact creates `LOCK_24V` from the protected pre-interlock bus.
- Gate opens / S1 wire breaks / control power disappears -> K0 drops -> `LOCK_24V` disappears.

Thus the magnetic position switch never carries actuator current.

This K0 path is a robust access-control interlock, **not a certified robot/machine safety function**. Robot guarding/E-stop/safety relay remains separate, and locker geometry must still prevent physical access to the robot cell.

## PSU sizing — HDR-100-24 replaces HDR-60-24

Use `Mean Well HDR-100-24`, 24 V / 3.83 A / 92 W, instead of HDR-60-24 for the preferred final architecture.

Reason: three Southco latches can theoretically approach ~3 A aggregate peak/stall current. The system must not depend on application software never issuing more than one unlock in order to keep the PSU inside its basic current envelope.

Current Canadian planning reference during this design pass: DigiKey CAD 43.01, 471 units in stock.

One-bay bench load is much lower, but use the same PSU so the accepted panel architecture scales directly to three bays.

## Revised power topology

```text
PS1 HDR-100-24 +24V
  |
  +---- F0 ---------------- CONTROL_24V ------------------------------+
  |                                                                   |
  |                                                                   +--> IO1 power
  |                                                                   +--> K0 coil feed via S1 pole B
  |                                                                   +--> RY1/RY2/RY3 relay coil +
  |                                                                   +--> feedback contact excitation
  |
  +---- F1 ---- LOCK_PRE_INTERLOCK ---- K0 NO power contact ---- LOCK_24V
                                                                    |
                                                                    +--> F2 --> L1 Southco POWER+
                                                                    +--> F3 --> L2 Southco POWER+
                                                                    +--> F4 --> L3 Southco POWER+
                                                                    +--> RY1/2/3 NO-contact source

PS1 0V -------------------------------------------------------------> IO1 GND + DICOM
                                                                      Southco GNDs

CONTROL_24V --> S1B safe contact --> K0 coil +
K0 coil - -------------------------------------> 0V
```

K0 uses a normally-open contact. Loss of K0 coil power therefore opens the latch bus.

### Waveshare DOCOM

Because DO0/DO1/DO2 now sink **relay coils powered from `CONTROL_24V`**, connect `DOCOM` to `CONTROL_24V`, not `LOCK_24V`, so the module's documented flyback-diode common matches the inductive relay-coil supply.

This is a material change from the SD-997C direct-sink v1 wiring.

## One-bay output wiring

Reference tags:

- `K0` Phoenix Contact 2909524 master lock-bus relay.
- `RY1` Phoenix Contact 2909524 BAY-CP command relay.
- `L1` Southco R4-EM-712-161.
- `DS1` Tane SD-80 exterior-door contact.

```text
# Master hard interlock control
CONTROL_24V ---- S1B safe contact ---- K0 coil +
0V ----------------------------------- K0 coil -

# Master lock bus
LOCK_PRE_INTERLOCK ---- K0 COM
K0 NO ------------------------------- LOCK_24V

# BAY-CP command relay
CONTROL_24V -------------------------- RY1 coil +
RY1 coil - --------------------------- IO1 DO0
IO1 DOCOM ---------------------------- CONTROL_24V

# BAY-CP latch power/control
LOCK_24V ---- F2 --------------------- L1 POWER +24V
0V ----------------------------------- L1 GND
LOCK_24V ----------------------------- RY1 COM
RY1 NO ------------------------------- L1 CONTROL INPUT
```

When DO0 turns on, RY1 closes and applies `LOCK_24V` to the Southco control input. The Southco motor/electronics remain separately powered from the fused `LOCK_24V` branch.

If the inner gate opens, S1B removes K0 coil power. K0 drops and removes `LOCK_24V` from both Southco power and the RY1 contact source, even if software leaves DO0/RY1 energized. IO1 and telemetry remain alive on `CONTROL_24V`.

## Inputs / Modbus map

Logical map remains unchanged:

- DI0 shared `inner_gate_closed` from S1 pole A;
- DI1 BAY-CP `outer_door_closed` from DS1;
- DI2 BAY-CP `latch_locked` from Southco latch-status switch;
- DI3/DI4 BAY-OTHER door/latch;
- DI5/DI6 BAY-OVERFLOW door/latch;
- DI7 spare/tamper;
- DO0/DO1/DO2 logical unlock commands to RY1/RY2/RY3.

Inputs remain PNP/high-level safe-state logic: `DICOM -> 0V`; a closed safe-state field contact presents `CONTROL_24V` to the corresponding DI.

## Provisional DC protection strategy

These are **bench starting values, not final code-compliant fuse selections**. Freeze only after exact latch drawing, connector wire gauge, measured current and installation method are known.

- F0 control/I-O branch: ~0.5 A starting point.
- F1 master `LOCK_PRE_INTERLOCK` bus: ~4 A time-delay starting point.
- F2/F3/F4 per Southco latch: ~1.5 A time-delay starting point each.

Why provisional: Southco allows ~1 A peak/stall, and an overly fast 1 A fuse could nuisance-open during a valid release. Conversely, oversizing defeats branch-wire protection. Final selection must coordinate conductor ampacity, latch inrush/stall duration, PSU capability and actual fuse curve.

## Software semantics

Existing driver semantics remain valid conceptually:

1. require `inner_gate_closed = true`;
2. require `outer_door_closed = true`;
3. require `latch_locked = true`;
4. energize logical unlock output (RYx);
5. observe latch-status -> unlocked;
6. observe door-status -> open due to kickout;
7. de-energize logical unlock output immediately;
8. later require door-closed + latch-locked before handoff completion.

### Timing defaults must be re-tuned

The previous 750 ms lock-feedback deadline is too aggressive for Southco 5/7-series family data.

Initial Southco bench starting values:

- latch-release verification deadline: **1500 ms**;
- absolute command-output actuation cap: **1800 ms**;
- then use the automated 100-cycle log to derive p50/p95/max and freeze tighter production values with margin.

Do not lengthen timeouts to conceal mechanical binding.

## One-bay procurement delta from v1

Remove / do not order for the exterior latch path:

- SD-997C-GCQ;
- Lee Valley pop-open plunger as a required part;
- HDR-60-24;
- direct Waveshare-to-latch motor wiring;
- direct S1-to-`LOCK_24V` power switching.

Add for BAY-CP panel:

- 1 × HDR-100-24;
- 1 × K0 Phoenix Contact 2909524 master interlock relay;
- 1 × RY1 Phoenix Contact 2909524 command relay;
- 1 × R4-EM-712-161;
- 1 × matching Southco striker (TBD);
- 1 × mating connector/harness or pigtail (TBD);
- 1 × Tane SD-80 door contact.

Final 3-bay build uses K0 + RY1/RY2/RY3 = **four interface/master relays total** and three latch/door-sensor sets.

## Open procurement items

Supplier inquiries sent 2026-08-31:

- Steeves Agencies: price/stock/shipping for 3× R4-EM-712-161, correct striker and connector, temperature confirmation and alternative dual-sensing configuration.
- Southco: requested recommended exact outdoor Ottawa configuration and accessories.
- KGE: asked for cold-rated SECO-LARM/equivalent alternative in addition to prior SD-997C quote.

Do not order the Southco latch until Canadian delivered price and exact striker/connector are confirmed.

## References

- Southco R4-EM family: https://southco.com/latches/rotary-latch-systems/rotary-latches/r4-em-electronic-rotary-latches
- Southco R4-EM family literature: https://media.southco.com/media/static/Literature/r4-em.en.pdf
- Southco outdoor 5/7-series literature: https://files.southco.com/static/Literature/r4-em-od.en.pdf
- Southco striker catalog: https://files.southco.com/static/Literature/r4-em-all2.en.pdf
- Waveshare 33917 wiring: https://docs.waveshare.com/Modbus_POE_ETH_IO_8CH
- Phoenix Contact 2909524: https://www.phoenixcontact.com/en-ca/products/relay-module-plc-rsc-24dc21ex-2909524
- Mean Well HDR-100-24: DigiKey Canada part 1866-2233-ND
- SECO-LARM SM-4201-L6Q: https://www.seco-larm.com/product/sm-4201-l6q/
