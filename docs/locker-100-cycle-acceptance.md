# Locker one-bay 100-cycle acceptance protocol

Status: required before adding BAY-OTHER / BAY-OVERFLOW
Date: 2026-08-31

The first physical BAY-CP mechanism must complete **100 consecutive accepted unlock/open/reclose/relock cycles** before the second and third actuator branches are enabled.

A critical failure resets the consecutive-pass counter to zero after the fault is corrected. Do not average critical safety failures away.

Use `docs/locker-100-cycle-log.csv` as the execution record.

## Preconditions

Before Cycle 1:

- dead-panel continuity checklist passed;
- feedback-only commissioning passed;
- wire-break tests produce unsafe state;
- hardwired inner-gate interlock proven with a multimeter;
- only F1 + BAY-CP branch F2 installed; F3/F4 removed;
- pop-open spring/plunger installed;
- `locker_bench preflight` passes;
- `locker_bench watch` is stable without input chatter;
- commissioning mode explicitly enabled only for the duration of testing.

## Per-cycle sequence

For every cycle:

1. Confirm inner gate closed.
2. Push exterior door fully closed and verify lock feedback locked.
3. Record supply voltage before unlock.
4. Issue one commissioning unlock.
5. Measure/record time to `lock_feedback = unlocked`.
6. Measure/record time to `outer_door_closed = 0`.
7. Confirm unlock coil is OFF after physical door opening.
8. Measure approximate pop-open distance.
9. Open the door farther by hand, then close it normally.
10. Confirm door closed + lock feedback locked again without manipulating the bolt by hand.
11. Record PASS/FAIL and any abnormal sound, friction, chatter or delayed state transition.

## Zero-tolerance critical failures

Any one of these is a critical FAIL:

- unlock output energizes while inner gate is open;
- hardwired inner-gate contact fails to remove lock-bus power;
- coil remains energized beyond configured maximum actuation window;
- lock feedback reports unlocked but door fails to leave closed-sensor zone;
- door pops open and bounces back into a false closed state;
- broken feedback wire reports a safe state;
- wrong bay/output actuates;
- lock does not re-secure when the door is normally closed;
- actuator or wiring shows abnormal heating, smell, insulation damage or repeated fuse operation.

## Timing criteria

Initial software limits:

- lock-release verification deadline: 750 ms;
- total maximum actuation window: 1500 ms.

The actual accepted mechanism should normally complete much faster than the maximum. After the 100-cycle run, review p50/p95/max release and door-open times and choose production limits with reasonable margin rather than leaving an unnecessarily long energized window.

## Mechanical criteria

- target pop-open travel: 10–20 mm;
- 100/100 cycles must leave the closed-sensor zone without a person pulling the door;
- no latch binding caused by side load;
- door closes with normal human force;
- bolt seats consistently without needing to lift/push the door sideways.

## Electrical criteria

Record at least beginning/mid/end supply voltage and measured actuator current during the run. Investigate material voltage drop, intermittent contact, terminal heating or fuse discoloration.

After Cycle 100, inspect and re-torque terminals according to component requirements; do not blindly over-tighten spring/cage-clamp terminals.

## Acceptance output

The bench is accepted only when:

- 100 consecutive cycles are PASS;
- all critical-failure counts are zero;
- final physical lock/sensor/spring positions are marked or dimensioned;
- final software timing values are recorded;
- final wiring/fuse configuration is recorded;
- photographs of the accepted mechanism and panel are stored with the build record.

Only then install F3/F4 and replicate the frozen mechanism for the other two bays.
