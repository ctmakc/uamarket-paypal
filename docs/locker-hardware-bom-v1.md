# Locker hardware BOM v1 — 3 carrier bays

Status: bench/prototype reference design

Date: 2026-08-31

This profile implements three carrier bays (`BAY-CP`, `BAY-OTHER`, `BAY-OVERFLOW`) with one shared inner loading gate. The design keeps the existing `ModbusLockerDriver` protocol and uses a low-cost Waveshare Modbus TCP I/O module for the prototype. A higher-end I/O block such as Advantech ADAM-6050 can replace it later without changing the cloud/edge state model.

## Selected prototype hardware

| Qty | Part | Purpose | Planning price | Notes |
|---:|---|---|---:|---|
| 1 | Waveshare Modbus POE ETH IO 8CH, SKU 33917 | 8DI / 8DO Modbus TCP I/O | USD 39.99 (~CAD 55.42 at 1 USD = 1.38577 CAD) | 7–36 VDC, 8 isolated DI, 8 open-drain DO, 500 mA max/channel |
| 1 | Mean Well HDR-60-24 | 24 VDC DIN-rail PSU | CAD 29.91 | 24 V / 2.5 A / 60 W. Three locks draw only ~0.45 A total at 24 V, leaving large headroom |
| 3 | SECO-LARM SD-997C-GCQ | Fail-secure cabinet/locker lock | USD 42.75 each (~CAD 59.24 each) | 12/24 VDC; 150 mA at 24 V; selectable fail-safe/fail-secure; built-in lock-status microswitch and door-status reed switch |
| 1 | SECO-LARM SM-4201-L6Q or equivalent DPDT magnetic contact | Shared inner-gate sensing + hardwired power interlock | CAD 59.95 | One pole reports `inner_gate_closed`; second pole physically interrupts the common +24 V lock feed when the gate opens |
| 4 | DIN-rail 5x20 mm fuse terminal blocks | Main + per-lock branch protection | ~CAD 9.42 each | 1 main branch + 3 lock branches |
| 1 | Hammond RP1450 or equivalent IP65 DIN enclosure | Control enclosure | CAD 60.48 | 220 x 165 x 60 mm; increase depth if terminal count/cable glands require it |
| lot | DIN rail, terminal blocks, ferrules, cable glands, 18–22 AWG wire, fuses, labels | Panel build | CAD 50–90 planning allowance | Use ferrules and labeled terminals; no loose splices |

Approximate electronics/control hardware total for three bays: **~CAD 490 before tax/shipping**, using the current USD/CAD planning conversion and the allowances above. The cabinet/locker fabrication itself is separate.

For a one-bay bench, buy one lock and only the required branch protection; the same Waveshare module and PSU can later expand to all three bays.

## Why this I/O module fits three bays

The final topology uses one shared internal loading gate, so only one `inner_gate_closed` input is needed for all bays.

Input allocation:

| Physical terminal | Modbus zero-based address | Signal |
|---|---:|---|
| DI1 | 0 | shared `inner_gate_closed` |
| DI2 | 1 | `BAY-CP outer_door_closed` |
| DI3 | 2 | `BAY-CP lock_feedback_locked` |
| DI4 | 3 | `BAY-OTHER outer_door_closed` |
| DI5 | 4 | `BAY-OTHER lock_feedback_locked` |
| DI6 | 5 | `BAY-OVERFLOW outer_door_closed` |
| DI7 | 6 | `BAY-OVERFLOW lock_feedback_locked` |
| DI8 | 7 | spare / enclosure tamper / future parcel-presence input |

Output allocation:

| Physical terminal | Modbus zero-based coil | Signal |
|---|---:|---|
| DO1 | 0 | `BAY-CP unlock` |
| DO2 | 1 | `BAY-OTHER unlock` |
| DO3 | 2 | `BAY-OVERFLOW unlock` |
| DO4–DO8 | 3–7 | spare |

Waveshare documents relay/output channels 1–8 at Modbus coil addresses `0x0000–0x0007`, read with FC01 and written with FC05/FC0F. Input channels are read with FC02, zero-based starting at address 0. Keep the module in Normal control mode; do not enable module-side linkage/toggle modes for locker unlock outputs.

## Exact `LOCKER_MODBUS_MAP_JSON`

```json
{
  "BAY-CP": {
    "inner_gate_di": 0,
    "outer_door_di": 1,
    "lock_feedback_di": 2,
    "unlock_coil": 0
  },
  "BAY-OTHER": {
    "inner_gate_di": 0,
    "outer_door_di": 3,
    "lock_feedback_di": 4,
    "unlock_coil": 1
  },
  "BAY-OVERFLOW": {
    "inner_gate_di": 0,
    "outer_door_di": 5,
    "lock_feedback_di": 6,
    "unlock_coil": 2
  }
}
```

## 24 V power / unlock wiring

Prototype logic uses **fail-secure** operation: loss of power leaves the exterior door locked.

```text
120 VAC
  -> protected 24 V PSU
      +24 V
        -> main DC fuse (suggested 1 A for initial 3-lock prototype)
        -> inner-gate DPDT pole B, CLOSED ONLY when inner gate is physically closed
        -> LOCK_BUS_24V
             -> 0.5 A fuse -> BAY-CP lock +
             -> 0.5 A fuse -> BAY-OTHER lock +
             -> 0.5 A fuse -> BAY-OVERFLOW lock +
             -> Waveshare DOCOM

BAY-CP lock -       -> Waveshare DO1
BAY-OTHER lock -    -> Waveshare DO2
BAY-OVERFLOW lock - -> Waveshare DO3

24 V PSU 0 V -> Waveshare supply 0 V
```

The Waveshare outputs are NPN open-drain and are rated up to 500 mA/channel. The selected lock draws about 150 mA at 24 V, so an interposing relay is not required for this prototype load. `DOCOM` must be wired according to the Waveshare output diagram because it is the common for the output freewheel diodes.

The inner-gate series contact is defense-in-depth at the electrical layer: even if software or the Modbus module erroneously commands an unlock output ON, opening the shared inner gate removes lock actuator power.

For the final robot-cell design, machine safety remains separate from this locker-control circuit. The dog-leg/pass-through geometry must prevent courier reach into the robot cell, and robot safety functions must remain in the dedicated safety circuit.

## Input wiring principles

Use dry-contact mode for door/lock feedback and wire contacts so **safe/normal physical state produces logical `1`**:

- shared inner-gate contact closed only when the gate is fully closed;
- outer-door contact closed only when the exterior door is fully closed;
- lock-status contact closed only when the deadbolt is physically locked.

This makes a broken wire tend toward logical `0` / unsafe rather than falsely reporting safe state.

The SD-997C-GCQ already includes separate lock-status and door-status switches, so no separate exterior reed switch is required for each bay.

Follow the Waveshare vendor passive-input wiring diagram for DI/DGND/DICOM terminals; do not improvise terminal polarity. The module supports passive dry-contact input with DICOM floating.

## Commissioning sequence

1. Build the panel with all lock actuator branch fuses removed.
2. Configure the Waveshare module on an isolated LAN; set a static IP and Modbus TCP port 502.
3. Ensure output/control channels are in Normal mode, not linkage/toggle mode.
4. Run `python -m scripts.locker_bench status BAY-CP` and confirm the driver connects.
5. Install only the three feedback circuits first. Move each gate/door/bolt by hand and confirm the expected logical state changes.
6. Confirm opening the inner gate changes all bays to `safe_to_unlock=false`.
7. With a multimeter, verify the hardwired gate contact removes voltage from `LOCK_BUS_24V` when the inner gate opens.
8. Insert the fuse for one lock only.
9. Enable edge commissioning explicitly and run one test unlock. Verify `DO ON -> lock feedback UNLOCKED -> DO OFF`.
10. Repeat at least 100 cycles on the first lock before wiring the remaining two branches.
11. Intentionally disconnect each feedback wire and confirm the system fails closed.
12. Only after bench acceptance connect the edge daemon/cloud commissioning path.

## Acceptance criteria before installation in a physical locker

- No unlock write occurs when `inner_gate_closed == false`.
- No unlock write occurs when `outer_door_closed == false`.
- No unlock write occurs when lock feedback already says unlocked.
- Unlock pulse always returns OFF even if feedback verification fails.
- Opening the hardwired inner-gate contact physically prevents lock current independent of software.
- A broken feedback conductor never reports a safe state.
- Stale cloud unlock commands expire and cannot actuate after reconnect.
- Device-scoped edge credentials prevent another edge controller from consuming this locker’s commands.

## Production upgrade option

If the prototype proves reliable but a more conventional industrial I/O block is desired, Advantech ADAM-6050 provides 12 isolated DI + 6 DO, 10–30 VDC and Modbus/TCP. The current Canadian DigiKey listing is about CAD 393.45. Keep the application-level address map behind the existing driver abstraction so this replacement does not change WMS/locker state semantics.

## Vendor references captured 2026-08-31

- Waveshare product: https://www.waveshare.com/product/iot-communication/wired-comm-converter/modbus-poe-eth-io-8ch.htm
- Waveshare protocol: https://docs.waveshare.com/RS232-RS485-CAN-DALI2/Modbus_POE_ETH_IO_8CH/Development-Protocol
- Mean Well HDR-60-24: https://www.digikey.ca/en/products/detail/mean-well-usa-inc/HDR-60-24/7703804
- SECO-LARM SD-997C-GCQ: https://www.seco-larm.com/product/sd-997c-gcq/
- SECO-LARM SM-4201-L6Q Canadian listing: https://www.kge.ca/en/product/security/22548-track-mount-overhead-door-magnetic-contact-switch-no-nc-x2.html
- Phoenix-style 5x20 mm fuse block benchmark: https://aptico.ca/automation-products/terminal-blocks-and-accessories/
- Hammond RP1450 Canadian listing: https://canada.newark.com/hammond/rp1450/enclosure-din-rail-polycarbonate/dp/04N9959
- Advantech ADAM-6050 Canadian benchmark: https://www.digikey.ca/en/products/detail/advantech-corporation/ADAM-6050-D1/17748029
