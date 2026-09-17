# Locker one-bay purchase sheet v1

Checked: 2026-08-31 (Canada)

Purpose: order the first physical locker-control bench. **Latch/lock purchase is currently on HOLD** while an outdoor-rated parcel-locker latch is selected. All non-lock control-panel items below may proceed now.

Prices below are current listed prices captured on the date above. Taxes, international shipping, brokerage/duty and supplier minimum-order rules are excluded unless explicitly stated.

## Buy now — control / panel items

| Vendor | Qty | Part | Current price | Extended | Why |
|---|---:|---|---:|---:|---|
| Waveshare | 1 | Modbus POE ETH IO 8CH, SKU 33917 | CAD 53.79–56.18 | use CAD 56.18 planning | 8DI/8DO Modbus TCP controller |
| Mouser Canada | 1 | Mean Well HDR-60-24 | CAD 28.94 | CAD 28.94 | 24 V / 2.5 A DIN PSU |
| Mouser Canada | 1 | Hammond 1555YA2GY | CAD 101.94 | CAD 101.94 | 300×240×120 mm polycarbonate bench enclosure |
| Mouser Canada | 1 | Hammond 1554YPL | CAD 22.80 | CAD 22.80 | galvanized inner mounting panel |
| KGE Électronique | 1 | SECO-LARM SM-4201-L6Q | CAD 59.95 | CAD 59.95 | DPDT shared inner-gate contact / hard interlock |
| Canada Automation | 3 | Phoenix Contact PT 4-HESI (5×20), SKU 3211861 | CAD 8.97 | CAD 26.91 | F0/F1/F2 fuse terminals for first bay |
| Canada Automation | 1 | 35 mm perforated DIN rail, 1 m | CAD 4.95 | CAD 4.95 | cut to panel rows |
| Canada Automation | 12 | Phoenix Contact PT 2,5 feed-through terminal, SKU 3209510 | CAD 1.40 | CAD 16.80 | X1/X2/X3 and spare points |
| Canada Automation | 4 | Phoenix Contact CLIPFIX 35 end clamp, SKU 3022218 | CAD 1.09 | CAD 4.36 | retain DIN devices/terminal groups |

Known non-lock subtotal above: **~CAD 322.83**.

## HOLD — do not order latch/lock yet

The previously selected `SD-997C-GCQ + separate push-open plunger` remains electrically workable but is no longer the default purchase. Outdoor/unheated Ottawa operation introduced a cold-temperature requirement that must be resolved before freezing the latch.

### Candidate A — SECO-LARM SD-997C-GCQ

- JMAC listed price: USD 42.75 each; USD 99 minimum order.
- 3 units: USD 128.25 (~CAD 177.69 at planning USD/CAD 1.3855).
- 12/24 VDC, ~150 mA at 24 V, lock-status + door-status sensing.
- Requires a separate mechanical pop-open device in our current design.
- Exact low-temperature suitability for the outdoor locker must be confirmed before purchase.

### Candidate B — SECO-LARM CL-210M-U3BQ

- JMAC listed price: USD 44.75 each, in stock, same USD 99 minimum.
- Integrated spring feature gently pushes the door open; lock and door status monitoring; fail-secure.
- 12–24/28 V class depending current manufacturer revision.
- **Published operating temperature only down to -10 °C.** This is not sufficient evidence for an unheated Ottawa exterior locker, so do not select it solely because the mechanics are attractive.

### Candidate C — Southco R4-EM parcel-locker family — current preferred investigation

Southco explicitly uses the R4-EM family in parcel-locker applications. Relevant architecture advantages:

- gear-motor electronic rotary latch rather than simple solenoid;
- push-to-close;
- delayed-relock versions;
- kick-out spring options;
- latch-status switch options;
- some configurations offer true door-status sensing;
- corrosion-resistant steel / stainless variants intended for outdoor applications;
- mechanical override options.

Current concrete lead: `R4-EM-712-161` (delayed relock, strong kickout, cam switch, steel housing). Southco currently shows **3 units at authorized Canadian distributor Steeves Agencies, Winnipeg**. Price and exact low-temperature rating for this exact configuration are pending distributor/manufacturer confirmation. Matching striker/connector part numbers are also pending.

Do **not** substitute a different R4-EM suffix without checking trigger style, relock type, spring strength, sensing and connector configuration.

## Supplier inquiries sent 2026-08-31

- KGE `info@kge.ca`: quote requested for 3× SD-997C-GCQ + 1× SM-4201-L6Q, then follow-up asking for a colder outdoor-rated monitored cabinet/parcel lock.
- Steeves Agencies `sales@steeves.ca`: quote requested for 3× R4-EM-712-161, matching striker/connector, delivery to Ottawa, exact temperature range and recommended version with latch + door sensing.
- Southco `info@southco.com`: asked for the recommended R4-EM configuration for an unheated Ottawa parcel locker, exact temperature range, kick-out/delayed-relock option, dual sensing and matching striker/connector.

Lock decision stays on HOLD until at least the Southco/Steeves technical response is received or equivalent manufacturer documentation is found.

## Vendor links

- Waveshare IO: https://www.waveshare.com/product/modbus-poe-eth-io-8ch.htm
- Mouser HDR-60-24: https://www.mouser.ca/ProductDetail/MEAN-WELL/HDR-60-24
- Mouser Hammond 1555YA2GY: https://www.mouser.ca/fr/ProductDetail/Hammond-Manufacturing/1555YA2GY
- Mouser Hammond 1554YPL: https://www.mouser.ca/ProductDetail/Hammond-Manufacturing/1554YPL
- KGE SM-4201-L6Q: https://www.kge.ca/en/product/security/22548-track-mount-overhead-door-magnetic-contact-switch-no-nc-x2.html
- Canada Automation fuse terminal: https://canadaautomation.ca/en/product/protection-en/5x20-fuse/lever-type-fuse-holder-6mm-terminal-block-63a-250v/
- Canada Automation DIN rail: https://canadaautomation.ca/produit/bornier/accessoires-bornier/rail-din-longueur-de-2-metres/
- Canada Automation PT 2,5 terminal: https://canadaautomation.ca/en/product/terminal/push-in-terminal-block/phoenix-contact-3209510-feed-through-terminal-block-pt-25/
- Canada Automation terminal accessories/end clamps: https://canadaautomation.ca/en/category-product/terminal/accessory-terminal/
- Southco R4-EM family: https://southco.com/latches/rotary-latch-systems/rotary-latches/r4-em-electronic-rotary-latches
- Southco R4-EM-712-161: https://southco.com/en_us_int/r4-em-712-161

## Consumables / local electrical supply allowance

Buy locally or add to the Canada Automation/Mouser order:

- 5×20 mm DC-appropriate fuses: 0.5 A × several spares and 1.0 A × several spares;
- 18 AWG stranded copper reference for actuator power (final gauge to be checked against selected latch/current/run length);
- 22 AWG stranded control cable for status loops;
- ferrules sized for both gauges;
- cable glands sized to actual field cables;
- wire duct / routing hardware;
- wire markers/heat-shrink labels;
- short Ethernet patch cable;
- DIN rail screws/standoffs as required by the 1554YPL mounting panel.

Planning allowance: **CAD 50–80**. Do not freeze gland sizes or final actuator branch fuse ratings until the selected lock connector/cable/current are known.

## Budget while latch is on HOLD

Non-lock known-parts subtotal: **~CAD 322.83**.

With CAD 65 consumables allowance: **~CAD 387.83 before tax/shipping**.

Final project subtotal is intentionally not frozen until the latch, striker, connector and any door-status accessory are selected.

## Ordering sequence now

1. Order Mouser group: HDR-60-24 + 1555YA2GY + 1554YPL.
2. Order Canada Automation group: fuse terminals + DIN rail + feed-through terminals + end clamps; add fuses/ferrules/glands where convenient.
3. Order Waveshare 33917.
4. KGE SM-4201-L6Q can proceed independently because the shared inner-gate hard interlock remains required regardless of exterior latch choice.
5. **Do not order SD-997C-GCQ, CL-210M-U3BQ, Southco R4-EM, striker or pop-open mechanism until outdoor latch selection is frozen.**
6. After latch selection, update `locker-terminal-wiring-v1.md`, wire list, Modbus input map if necessary, branch fuse assumptions and 100-cycle acceptance thresholds before actuator power.
7. Power only BAY-CP until it completes 100 consecutive accepted cycles.

## Do not buy

- Hammond RP1450 — superseded; too shallow.
- A second/third I/O module — one Waveshare 8DI/8DO handles current three-bay architecture.
- Lock-specific interposing relays, striker hardware, connectors or pop-open hardware until the final latch configuration is known.
- Robot/cobot hardware — still gated behind physical locker + PostgreSQL race + dispenser acceptance.

## Acceptance before expanding beyond one powered bay

Use the existing preflight/acceptance framework, but revise lock-specific wiring and expected feedback timing after the final latch is frozen.

Only after a 100/100 consecutive PASS run should second/third actuator branches be enabled.
