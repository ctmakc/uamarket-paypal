# Locker control panel layout v1

Status: mechanical assembly reference
Date: 2026-08-31

This document defines the physical control-panel layout for the first locker bench and the later three-bay installation. It complements `locker-terminal-wiring-v1.md`; it does not define the upstream 120 VAC branch circuit.

## Enclosure correction

The previously referenced Hammond `RP1450` enclosure is **superseded** for this build. Its available internal depth is too small for a Mean Well HDR-60-24 mounted on DIN rail with practical wiring clearance.

For the **one-bay bench**, use Hammond `1555YA2GY` or an equivalent polycarbonate enclosure around **300 x 240 x 120 mm** with a mounting plate/usable mounting plane of roughly **285 x 225 mm** and about **109 mm** internal depth.

For the **final three-bay control panel**, do not force the 47-wire panel into the bench box. Reserve an enclosure in approximately the **16 x 12 x 6 in / 406 x 305 x 152 mm class**. The final part number may change with local availability, gland count and inspection requirements; the dimensional class is the design requirement.

## One-bay bench mounting plane

Reference orientation: enclosure portrait/landscape may be chosen to suit the actual gland side, but keep mains/PSU physically separated from low-voltage field wiring.

Recommended three horizontal DIN rows on the ~285 x 225 mm mounting plane:

```text
TOP / mains-entry side

R1  ---------------------------------------------------------
    PS1 HDR-60-24 | F0 | F1 | F2 | spare fuse position

       >=25 mm vertical wireway / service clearance

R2  ---------------------------------------------------------
    IO1 Waveshare 8DI/8DO | Ethernet bend/service space

       >=25 mm vertical wireway / service clearance

R3  ---------------------------------------------------------
    X1 DC distribution | X2 feedback | X3 actuator | spares

BOTTOM / field-cable gland side
```

Reference rail centre lines on a 285 mm-high working plane: approximately `Y=55 mm`, `Y=145 mm`, and `Y=215 mm`. These are assembly targets, not precision dimensions; shift them to preserve terminal screwdriver access and cable bend radii.

## Final three-bay panel zoning

The final 16x12x6-class panel should reserve four zones:

1. **Power zone** — PS1, DC branch protection, service disconnect/line-side separation as required by the qualified installer.
2. **I/O zone** — IO1 and Ethernet service loop; keep network cable away from high-current lock conductors where practical.
3. **Terminal zone** — X1/X2/X3 and at least 20% spare terminal capacity.
4. **Cable-entry zone** — separate glands for mains, Ethernet, feedback/control, and lock-power field bundles.

Keep at least ~20% free DIN-rail and panel area after the first three bays. Do not consume the spare DI/DO merely because they exist.

## Cable-entry convention

Preferred physical separation:

- mains entry near PS1 only;
- Ethernet entry near IO1;
- low-current feedback cables enter nearest X2;
- lock actuator cables enter nearest X3;
- field cable shields/drains, if used, terminate according to the selected cable/device practice rather than being improvised onto signal 0 V.

All cable glands must provide strain relief. No field conductor should pull directly on IO1 terminals.

## Exterior-door pop-open mechanism

The selected fail-secure solenoid is paired with a **spring plunger / compression spring / magnetic push-open mechanism** so the exterior door automatically moves outside the `door_closed` sensor zone as soon as the bolt releases.

Mechanical acceptance target for the first bay:

- door moves outward without a human pulling it;
- target initial pop travel: **10–20 mm**;
- travel is sufficient to make `outer_door_closed = 0` reliably;
- door must not bounce back into the closed-sensor zone;
- spring force must not prevent the door from being comfortably pushed closed and re-latched;
- latch/bolt must not be side-loaded enough to make release intermittent.

Software v0.11 therefore does not treat an energized coil or even `lock_feedback = unlocked` alone as successful courier access. Success requires both lock-release feedback and physical door-open feedback before the hard actuation deadline.

## Recommended unlock timing starting point

Initial commissioning values:

```dotenv
LOCKER_UNLOCK_PULSE_MS=1500
LOCKER_UNLOCK_VERIFY_TIMEOUT_MS=750
```

`LOCKER_UNLOCK_PULSE_MS` is a **maximum actuation window**, not a fixed dwell. The driver turns the coil off immediately after the lock releases and the door-open input becomes true. It also turns the coil off on every error path.

Tune these values only from physical 100-cycle data. Do not extend them merely to hide a mechanically sticky latch; fix alignment/spring/latch friction first.

## Bench build order

1. Fit enclosure, DIN rails, wire duct and glands without devices.
2. Dry-place PS1/IO1/fuses/terminals and prove covers can close without conductor compression.
3. Fit PS1 and DC protection.
4. Fit IO1 and Ethernet service loop.
5. Fit X1/X2/X3 terminals and labels.
6. Wire feedback circuits before actuator circuits.
7. Perform dead-panel checks from `locker-terminal-wiring-v1.md`.
8. Fit the physical lock and pop-open plunger to a representative door/frame jig.
9. Commission feedback-only with F1/F2 removed.
10. Only then energize the first lock branch and start the 100-cycle acceptance protocol.

## Mechanical freeze after acceptance

After 100 consecutive accepted cycles, record and freeze:

- enclosure and mounting layout revision;
- lock bracket position and shim thickness;
- pop-open spring/plunger model and compression/preload;
- measured door pop distance;
- sensor bracket positions;
- final unlock/verification timeouts;
- fuse ratings and measured actuator current;
- photos of the accepted panel and door mechanism.
