# NixiClockV1

A clock with six IN-16 nixie tubes in one row, showing `hh:mm:ss`. It sets itself over WiFi (NTP) and has no buttons for setting the time.

| | |
|---|---|
| Tubes | 6 × IN-16, multiplexed 1:6. Hours / minutes / seconds pairs are 17 mm apart, with 23 mm between pairs. The commas of tubes 2 and 4 blink as separators. |
| Time | ESP32-C3-WROOM-02 with SNTP (`pool.ntp.org`), re-synced every hour. The POSIX time zone includes the DST rules (default Europe/Berlin). |
| Power | **One USB-C port for power and flashing.** A CH221K (SOT-23-6) asks any USB PD charger (≥ 18 W) for 9 V. D+/D− go straight to the ESP32-C3. AMS1117 3.3 V for the logic, LM3478 boost to 185 V for the tubes. |
| 9 V terminal | J102 WJ500V-5.08-2P at the back edge, wire entry facing out, for a housing cut-out. Inject 7–12 V by hand. It is diode-OR'ed with USB (SS34 each), so it never back-feeds the USB port, and it is reverse-polarity safe. |
| USB without PD | A plain 5 V port (PC) powers the ESP32 for flashing and WiFi. The tubes stay dark because the firmware only enables the HV when VIN > 7 V. |
| Board | 128 × 60 mm, **4 layers, JLCPCB standard stackup JLC04161H-7628** (1.6 mm: 1 oz outer, 0.5 oz inner, 7628 prepreg 0.21 mm, core 1.065 mm), JLC standard tier, single-sided SMD (hand-solderable) plus the THT tubes and terminal |

**Status (2026-10-21):** the schematic and board setup are done and the board is placed, but it is **not routed** (on request).
- ERC: 0 violations.
- DRC: 0 errors and 0 schematic-parity issues. The only items are the expected unconnected nets, plus 3 notes about connector silkscreen at the board edge (J101, J102).
- Schematic placement is functional, not polished. You're tidying it in KiCad, so don't re-run `gen_sch.py` afterwards.

## Files
- `NixiClockV1.kicad_sch`: root sheet plus `power.kicad_sch`, `mcu.kicad_sch` and `display.kicad_sch`.
- `NixiClockV1.kicad_pcb`: placed board, 4 layers (F.Cu / In1.Cu / In2.Cu / B.Cu). The inner layers are still empty; planned use is In1 = GND plane, In2 = GND / VIN / +3V3 pours, no HV on the inner layers. Net classes are HV (0.5 mm clearance), HV_SW, Power and Default.
- `lib/`: IN-16 symbol and footprint, TS-1187A switch, `+HV` / `VIN` power symbols, and the ESP32-C3-WROOM-02 footprint with 0.3 mm thermal holes.
- `bom.csv`: BOM grouped by LCSC number.
- `firmware/`: PlatformIO / Arduino-ESP32 3.x project.
- `tools/`:
  - `build_lib.py` builds the library.
  - `design.py` holds the part and net truth table.
  - `gen_sch.py` generates the schematic.
  - `check_netlist.py` checks the schematic netlist against `design.py`.
  - `make_pcb.py` creates the board from the netlist and places it.
  - `set_stackup.py` switches an existing board to the 4-layer JLC stackup in place, keeping hand edits.
  - `place_hv.py` re-places only the HV converter parts for minimum loop area, in place.

  Re-running `gen_sch.py` or `make_pcb.py` overwrites hand edits.

## How it works
**Input.**
- The CH221K (U2) follows WCH's CH221K reference circuit (CH224 manual V2.1, section 6.4): R120 1 kΩ from the fused VBUS into VDD, C108 1 µF on VDD, R104 20 kΩ from CFG to VDD = 9 V request, R110 / R113 5.1 kΩ on CC1 / CC2. PG (open drain) goes to IO3 with the ESP32's internal pull-up.
- Its own DP/DM pins are left open, so its QC/BC1.2 handshakes can't disturb the ESP32's USB data.
- PG goes to IO3 (`PD_OK_N`, low when 9 V has been negotiated).
- VIN is divided by 22k/122k into IO1 (`VIN_SNS`).

**HV supply.**
- LM3478 current-mode boost (datasheet SNVS085Y), about 110 kHz (R105 200 kΩ), DCM.
- Q101 HSU5N25 (250 V, Vth 3 V; the LM3478 drives the gate with only 7.2 V), D103 ES1J (600 V), L101 100 µH / 2.3 A.
- Current limit: 156 mV / 0.1 Ω ≈ 1.5 A.
- Output: HV = 1.26 V × (1 + 2 MΩ / 13.7 kΩ) = **185 V**. The IN-16 strikes at ≤ 170 V and burns at about 150 V.
- `HV_OFF` (IO10, pulled high by R112) pulls FA/SD above the 1.35 V shutdown threshold through D104. The boost only runs once the firmware drives it low, so a crashed or unprogrammed ESP32 leaves the tubes dark.
- Compensation is R111 10 kΩ + C112 100 nF on COMP. This is a starting value; check the HV ripple and the load-step response on the bench.

**Display drive.**
- 3 × 74HC595 (24 bits) feed 12 cathode sinks and 6 anode switches.
- The cathode sinks are MMBTA42 constant-current sinks. The base is driven directly from the 595, so Ie = 2.65 V / Re:
  - digits: 3.9 mA peak (680 Ω), 0.65 mA mean;
  - commas: 1.2 mA peak (2.2 kΩ).
- The tube current therefore doesn't depend on the HV or on tube-to-tube burn voltage, and no anode resistors are needed.
- Anode switches: MMBTA92 high side, switched by an MMBTA42 that sinks 0.27 mA.
- Each tube gets a 2 ms slot (83 Hz refresh). Everything is blanked for 200 µs at each slot change to prevent ghosting.

**Converter layout** (set by `tools/place_hv.py`). When routing, keep these:
- **Commutation loop** (fast edges): Q101 tab (drain) → D103 → C107 1 nF 2 kV → GND → R101 → Q101 source. The parts sit tab-up and closed around the FET body: D103 anode 1.5 mm from the tab, C107 under the cathode, C107 GND 4 mm from R101 GND. Route it on F.Cu with short, wide copper. Put a GND via at C107 and at R101 into the solid In1 GND plane, and don't cut In1 under this area.
- **Switch node** (L101.2, Q101 tab, D103 anode): one small F.Cu island, no larger than needed. No other traces under it on In2/B.Cu. HV_SW clearance is 0.5 mm.
- **Gate drive:** U102 DR → R103 → gate is about 5 mm. Return through PGND (pin 5) to the GND plane next to R101.
- **ISEN:** a separate Kelvin trace from R101's upper pad to U102 pin 1, not shared with the power path. Keep it away from the switch node (In2/B.Cu under the controller is fine).
- **FB:** R108/R109 sit at the FB pin, so the high-impedance node stays short. Only the 1 MΩ R107 connects to +HV, over a DC trace (HV class, 0.5 mm clearance).
- **C111** sits at U102 VIN (pin 8), C105 at the L101 VIN pad. AGND/PGND go to the same In1 plane through their own vias.

Shift register bit map (bit 0 = U301.QA):

| U301 QA..QH | U302 QA..QH | U303 QA..QB |
|---|---|---|
| K0..K7 | K8, K9, comma L, comma R, A1..A4 | A5, A6 |

## Assembly notes
- **The tubes' anode lead (white-coated lead, datasheet pin 1) goes into the pad marked `A`, which is at the back of the board.** Digits face the front edge (the ▼ marks). Bend and solder the leads at least 5 mm from the glass.
- Fit and test the HV supply before the tubes:
  1. Power from a PD charger or 9 V on J102, and flash the firmware (or pull IO10 low).
  2. Measure TP101 against TP102. It should read 185 V ± 5 %.
- **185 V DC is dangerous.** C106 keeps its charge for about 5 s after power-off (the divider bleeds it).
- Hand-soldering the ESP32-C3-WROOM-02: it has castellated pads. The ground pad can be soldered from the back through its 4 holes.

## Firmware (`firmware/`)
- Build and flash: `pio run -t upload` over the same USB-C port, from a PC or through a USB-C cable. If USB doesn't enumerate, hold BOOT while pressing RESET.
- The HV starts when VIN > 7 V and stops below 6.5 V (`VIN_HV_ON` / `VIN_HV_OFF`), so it works from PD and from J102.
- First power-up: connect a phone to the WiFi **NixiClock-Setup**, choose your network, and optionally enter another POSIX time zone. The tubes cycle digits until the time arrives.
- To forget WiFi: hold BOOT for 5 s while plugging in.
- Night dimming 23:00–07:00 (`NIGHT_FROM`, `NIGHT_TO`, `BRIGHT_*`).
- Every 10 minutes all cathodes are run through for about 1 s against cathode poisoning; at 03:00 this runs for 1 minute.
- `SEPARATOR_RIGHT_COMMAS`: chooses which commas blink. Flip it if the commas come out on the wrong side of the digits.

The firmware has **not been compiled yet**: no ESP32 toolchain is installed on this machine.

## Things to check
- Which comma is left and which is right (pins 5 / 10) is derived from the bottom-view pinout drawing. The firmware has a flag in case it is mirrored.
- The anode-at-the-back orientation comes from the PV Electronics "Frank 2 IN-16" kit manual. Check one tube before soldering all six.
- J102 orientation: I read the wire-entry side of KiCad's MKDS-1,5 footprint as the side with the pin-1 chamfer, and turned it toward the back edge. Check the first board before cutting the housing.
- PD chip: CH221K, LCSC C5125736.
- LCSC numbers come from the local JLC parts snapshot and earlier projects. Check stock and price before ordering. The tubes have no LCSC number.

## Cost (estimate, one clock, LCSC retail with MOQ, without tubes, charger or shipping)
| Item | ≈ USD |
|---|---|
| ESP32-C3-WROOM-02-N4 | 3.10 |
| HV parts (LM3478, HSU5N25, APH1040 100 µH, ES1J, 2.2 µF 250 V) | 1.40 |
| USB PD: CH221K | 0.15 |
| 3 × 74HC595, 18 × MMBTA42, 6 × MMBTA92 | 0.90 |
| Connectors (USB-C, WJ500V), LDO, diodes, fuse, switches | 0.90 |
| Passives (about 20 lines, bought at reel-strip MOQ) | 3–5 |
| PCB 128 × 60 mm, 4 layers, 5 pcs at JLC | get a JLC quote: more than the 2-layer $5–8 |
| **Total (parts only)** | **≈ 10–12** |
