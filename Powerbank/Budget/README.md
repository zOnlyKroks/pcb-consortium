# Budget 18650 Powerbank

1S powerbank with 4x 18650 in parallel (about 40-50 Wh with 3.0-3.4 Ah cells). One highly integrated SoC (SW6106) does the charging, the boost and the USB protocols. Built for JLCPCB economic assembly, all parts on the top side.

**Status:** schematic done (ERC 0 violations, netlist matches an independent net spec, 41/41 nets). Board is **placed, not routed** (130 x 90 mm, 2 layers). DRC shows 0 errors other than the unrouted ratsnest, and schematic parity is 0.

## Architecture

| Block | Parts | Notes |
|---|---|---|
| Power SoC | SW6106 (iSmartware) | 4 A switch-mode charger, 18 W synchronous boost, PD3.0 / QC3.0 / AFC / FCP / PE / SFCP out, PD / AFC / FCP in, 4-LED gauge, key input |
| Ports | USB-C (J1) + USB-A (J2) | Each has an AO3420 power-path switch (Q4/Q5) driven by the SoC. USB-C does PD in and out; USB-A is QC/AFC/FCP out only. Micro-B is not used (VBUS_B tied to GND, GATE_B/DPB/DMB open). |
| Power stage | L1 2.2 uH, R1 5 mOhm shunt, C1-C4, C7-C10 | Follows the SW6106 typical application circuit |
| Cell protection | DW01A + 3x FS8205A in parallel | The SW6106 has no cell protection of its own (only a 2.9 V UVLO). Each FS8205A is two FETs in series (about 50 mOhm), so three in parallel are about 17 mOhm, and the DW01A overcurrent trip (about 0.15 V) lands near 9 A. Boost peak at 18 W and 3.0 V is about 6.7 A. |
| Gauge | D1-D4 (charlieplex on LED1-3), D5 fast-charge LED | Press SW1 to show the level |
| NTC | RT1 10k (B3380) | Charge and boost temperature protection. Place it touching a cell. |

Output: 5 V / 3 A, 9 V / 2 A, 12 V / 1.5 A (18 W max). Both ports on at once give 5 V only. Charging: 5 V in = 2.5 A, 9 V / 12 V in = 4 A to the pack (4 A = 0.33 C with 4 cells).

Ground naming: `GND` = PACK- (system ground, after the protection FETs); `CELL_N` = cell stack bottom (DW01A VSS); `VBAT` = cell +.

## Things to check before ordering

- **SW6106 reference circuit.** The typical-application figure in DS008 v2.2 is low resolution. The 100 nF across the shunt, the 22 uF caps at the inductor node / BAT / VOUT, the 1 uF VDRV and the 10 uF VCC are read from the block diagram and figure. Compare them with the official reference design from iSmartware.
- **LED charlieplex order.** LED1-4 are wired per the 4-LED figure in the datasheet. If the bar lights in the wrong order or one LED is dark, swap the polarity of that LED.
- **USB-A part C42570 (JTJ USB-AF-10.0-032).** The footprint is the EasyEDA one: SMD signal pads, through-hole shield legs. Confirm JLC economic assembly accepts it (or hand-solder the legs). The USB-C (C165948) also has through-hole shield legs.
- **Basic vs extended.** Not verified (no JLC parts API access here). The SoC, DW01A, FS8205A, AO3420, inductor, shunt, both USB connectors, holder and switch are almost certainly extended parts (about 3 USD each on economic). The 0603/0805/1206 passives were taken from the V2 BOM, which was checked on 2026-10-24.
- **AO3420 (C358680).** Listed as AOS, marked "not for new designs" at DigiKey. Fallback: MSKSEMI AO3420 C5379109 (18 mOhm), same footprint.
- **CPL rotations** need the usual JLC correction pass (QFN, TSSOP, SOT-23, USB connectors); I did not generate a CPL.
- **Cells.** All four are in parallel with no per-cell protection. Insert cells at the same voltage, same type, and ideally from the same batch. A per-cell fuse is not fitted (budget).

## Board

- 130 x 90 mm, 2 layers, 4 holders on the left (all + up, so VBAT is the top bus and CELL_N the bottom bus), electronics on the right strip, USB ports on the right edge with the gauge LEDs and key beside them.
- Mounting holes: 4x M3 (H1-H4). H1/H2 sit between the holders and the electronics.
- Layers / stackup: 2 copper layers (F.Cu, B.Cu), JLC 1.6 mm FR4, 1 oz (35 um) copper, HASL. B.Cu carries a GND pour (0.3 mm clearance, thermal reliefs, 0.5 mm from the edge). Economic assembly is single-sided, so all parts are on F.Cu and B.Cu is routing + ground.
- Net classes: `Default` 0.25 mm track / 0.2 mm clearance / via 0.6 / 0.3 drill; `Power` (GND, VOUT, VBUS_x switch nodes, SW, BATCSP) 0.8 mm track / via 0.8 / 0.4; `HighCurrent` (VBAT, CELL_N) 2.0 mm track / via 1.0 / 0.5. Use pours where a 2 mm track does not fit.
- Predefined track widths (mm): 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0. Predefined vias (pad / drill): 0.6 / 0.3, 0.8 / 0.4, 1.0 / 0.5.
- Design rules (JLC 2-layer): min clearance 0.1, track 0.15, via 0.6 / 0.3 (0.15 annular), copper to edge 0.3, hole to hole 0.5, silk text 1.0 mm high / 0.15 thick.
- The USB-C footprint has pads 0.1 mm apart (inherent to the part); the J1 pads carry a 0.09 mm local clearance.
- U1: the four thermal vias share pad 41 (GND). Fill the EP with the planned via pattern when routing.

### Routing notes (for later)

- **High current** (about 6-9 A): VBAT bus (holder tops -> R1 -> U1 BAT), CELL_N bus (holder bottoms -> Q1-Q3 S1 pins), Q1-Q3 S2 to GND, and VOUT to Q4/Q5. Use wide copper or pours.
- **GND:** the second layer is meant as a GND plane with vias at U1 EP and the FET sources.
- **SW6106:** keep the SW-L1 loop (L1 above U1) and C1 (BST) tight; C7-C10 close to the VOUT pads.
- **Shunt R1:** route BATCSP/BAT Kelvin from the pads; C3 sits at the pads.
- **Q1-Q3:** the three FS8205A share OD (gate 1) and OC (gate 2) nets from U2; keep those short.
- **DW01A:** R2 (VM) goes to GND, C13 (VCC to CELL_N) right at U2.

## Files

- `Budget.kicad_sch` single-sheet schematic, `Budget.kicad_pcb` placed board
- `lib/Budget.kicad_sym`, `lib/Budget.pretty` project symbols and footprints (SW6106, DW01A, FS8205A, USB, holder, inductor, ...)
- `jlcpcb/BOM-Budget.csv` BOM with LCSC numbers (38 parts, 20 unique)
