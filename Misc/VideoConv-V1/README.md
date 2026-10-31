# VideoConv-V1: analog video to HDMI + VGA converter

"Works with whatever you throw at it": SCART (RGB, composite, S-Video), component YPbPr up to 1080p, composite.
Hand-solderable (no BGA). **Schematic only**: no PCB, no simulation, and the FPGA gateware is a specification, not code.

```
SCART  ---R,G,B--------------------------------------+
RCA Y/Pb/Pr --75R-0.1u-----------------------------> TVP7002 --24-bit RGB/YCbCr + sync + pixel clock--+
SCART pin 20 / RCA CVBS --attenuate-> TVP5150 --BT.656 8-bit + 27 MHz--------------------------------+--> iCE40HX4K
SCART pin 15 (S-Video C) ------------^                                                               |  line-double / bob-deinterlace /
SCART pin 16, pin 8 --comparators--------------------------------------------------------------------+  YCbCr->RGB / HD pass-through
                                                  I2C <------------------------------------------------+
                                                                  24-bit RGB + DE/HS/VS/clk -> TFP410 -> TPD12S016 -> HDMI (DVI video)
                                                                  6-bit R-2R DACs x3 + HS/VS -> DE-15 VGA
```
All analog inputs go through ESD clamps (USBLC6-4SC6, or a bidirectional TVS on the audio pair) at the connector.

## Schematic structure (hierarchical)
`VideoConv-V1.kicad_sch` is the root: one sheet symbol per block, with sheet pins and net labels for every signal that crosses
between blocks. The blocks live in `sheets/`:

| sheet | content |
|---|---|
| `Power` | USB-C 5 V, TVS + PTC, 3.3 V and 1.9 V bucks, 1.8 V and 1.2 V LDOs, ferrite-filtered analog rails, power flags |
| `Inputs` | SCART + RCA jacks, 75 ohm terminations, ESD arrays, TVP5150 attenuators + CVBS jumper, SCART pin 16 / 8 comparators, audio out |
| `TVP7002` | the digitiser, 22 ohm output arrays, PLL filter, unused-input terminations, decoupling |
| `TVP5150` | the decoder, 14.31818 MHz crystal, reference caps, strap resistors |
| `FPGA` | iCE40HX4K (5 symbol units: 4 I/O banks + power/config), 27 MHz oscillator, SPI flash, programming header, MODE button, LEDs, I2C pull-ups |
| `HDMI` | TFP410 with its strap network, TPD12S016, HDMI connector |
| `VGA` | three 6-bit R-2R ladders, sync resistors, DE-15 |

Supply rails (`+3V3`, `+1V9A`, ...) are global power symbols and need no sheet pins. The generator (`tools/gen_sch.py`, assembled from
the layout engine + `hier_part.py` + `design_part.py`) routes every part to the sheet selected with `sh.S("Name")`; any net
label used on more than one sheet automatically becomes a hierarchical label there and a sheet pin + label on the root.

## Why this architecture
The converter has to cope with 15 kHz sources (240p consoles, 480i/576i), 31 kHz (480p), HD component, sync-on-green,
composite sync and VCR-grade CVBS. No single chip does that and also produces a modern output, so:

| block | part | job |
|---|---|---|
| analog front end 1 | TVP7002 (TI, 100-pin HTQFP) | 3x 10-bit 165 MSPS ADC, 3 inputs per colour, 3 sync-on-green slicers, H-PLL: SCART RGB + component, SD to 1080p |
| analog front end 2 | TVP5150AM1 (TI, 32-pin TQFP) | NTSC/PAL/SECAM decoder, 4-line comb filter, CVBS or S-Video, BT.656 out |
| processing | iCE40HX4K-TQ144 | line buffers in BRAM (line-doubling, bob-deinterlace), colour-space conversion, HD pass-through, I2C master for the two chips, SCART sensing |
| output 1 | TFP410 + TPD12S016 | 24-bit RGB -> TMDS (DVI video, accepted by HDMI sinks); TPD12S016 = ESD, DDC / hot-plug level shifting, current-limited 5 V |
| output 2 | 12 resistors per channel | 6-bit R-2R DACs into 75 ohm, HS/VS direct (VGA monitors and capture cards) |

The FPGA configures both decoders over I2C (no separate MCU): a small sequencer replays one register table per input
mode, selected with the MODE button or from the SCART signals. TFP410 is pin-strapped and needs no I2C.

## Inputs and how they map
| connector | signal | goes to |
|---|---|---|
| SCART pins 15 / 11 / 7 | R, G, B (0.7 Vpp) | TVP7002 RIN_1 / GIN_1 / BIN_1, 75 ohm + 0.1 uF each |
| SCART pin 20 | CVBS or composite sync | TVP7002 SOGIN_1 (1 nF) and TVP5150 AIP1A through the attenuator (jumper position "B") |
| SCART pin 15 | S-Video chroma | TVP5150 AIP1B (same node as red) |
| SCART pin 16 | fast blanking (RGB active) | 75 ohm load -> comparator -> FPGA `SC_RGB` (high when above 0.7 V) |
| SCART pin 8 | function switch (aspect / AV) | /4.3 divider -> two comparators -> FPGA `SC_FS1` (above 3 V) and `SC_FS2` (above 8 V) |
| RCA Y, Pb, Pr | component (SoG on Y) | TVP7002 GIN_2 / BIN_2 / RIN_2, SOGIN_2 |
| RCA CVBS | composite | TVP5150 AIP1A (jumper position "A") |
| SCART pins 2 / 6 | audio | 3.5 mm line out (analog pass-through, no HDMI audio) |

Pin 8 states per SCART: 0 to 2 V = none / TV, 4.5 to 7 V = 16:9, 9.5 to 12 V = 4:3 (SC_FS1 high only = 16:9, both high = 4:3).
Auto-select rule for the gateware: SC_RGB high -> SCART RGB path, otherwise composite / S-Video; the button overrides.
Comparators are an LM339 on 5 V with 3.3 V threshold dividers (0.71 V and 1.87 V after the /4.3 divider) and 10 k pull-ups to 3.3 V.

Unused TVP7002 inputs (RIN_3/GIN_3/GIN_4/BIN_3, SOGIN_3) and its HSYNC/VSYNC/CLAMP/COAST/TMS/PWDN pins are terminated as
the datasheet says. A PC VGA input is not included.

## Input protection
- 12 signal lines through three USBLC6-4SC6 (SOT-23-6, 4 channels each, clamp to +5 V and GND, about 3.5 pF), one per
  group: SCART RGB + CVBS, component + RCA CVBS, pin 16 + the pin 8 divider node. Pin 8 itself (up to 12 V) is protected
  by the 33 k series resistor, so the clamp sits on the divided node.
- SCART audio is bipolar, so it gets bidirectional TVS diodes (SMF5.0CA) instead of the clamp arrays.
- HDMI side: TPD12S016 gives 15 kV ESD on TMDS / DDC / HPD / CEC and 5 V current limiting.
- Note: the clamp arrays reference the board's 5 V rail; with the board unpowered, a source driving the inputs only
  leaks a little current into that rail.

## HD inputs (720p / 1080i / 1080p)
Hardware: TVP7002 samples up to 165 MSPS (sync-on-green tri-level sync handled by its slicers), DATACLK goes to an FPGA
global clock pin, TFP410 accepts 25 to 165 MHz, and the FPGA can generate or pass 74.25 / 148.5 MHz. `gateware/tvp7002_modes.csv`
lists the H-PLL settings (PLLDIV, VCO range, charge-pump current) for 480i/p, 576i/p, 720p, 1080i and 1080p, taken from
datasheet Table 4 (the register pairs were checked: reg 01h/02h encode the PLLDIV total for every row).

Gateware specification for HD:
1. Mode detect: read the TVP7002 line/frame status (or measure HS/VS in the FPGA) and pick a row of the table; HD mode =
   pixel clock >= 74.25 MHz.
2. HD data path = **pass-through**: TVP7002 DATACLK is the system clock, data goes through a few register stages, DE is made
   from the HS/VS pulses and the active-video counters (TVP7002 can also output a data-enable on FIDOUT via register 17h),
   output clock IDCK = DATACLK delayed by one stage. No scaling: the sink must accept 720p / 1080i / 1080p (all HDMI TVs do).
3. Component 4:2:2 / YCbCr -> RGB with BT.709 for HD (BT.601 for SD); TVP7002 can also do the colour-space conversion itself
   (its CSC block defaults to the HDTV coefficients).
4. 1080i from a console is passed as interlaced (no deinterlacing in v1).
5. VGA out on HD: the 6-bit R-2R stage runs at 74 MHz with about 75 ohm source impedance, so expect softer edges than HDMI;
   use HDMI for HD.

SD path as before: TVP7002 oversamples 15 kHz sources at 27 MHz (PLLDIV 1716 / 1728, see the CSV), the FPGA keeps every
second pixel in, reads at 27 MHz, and doubles lines (240p -> 480p) or bob-deinterlaces (480i -> 480p). Output clock = input
sample clock, locked, no frame buffer.

## Numbers I took from the datasheets (all in `datasheets/`)
- **TVP7002**: 1.9 V analog/digital core (1.8 to 2.0 V), 3.3 V analog and I/O; inputs AC coupled with 0.1 uF; SOG coupled
  with 1 nF; PLL loop filter = 1.5 k + 0.1 uF on FILT1 and 4.7 nF on FILT2 to PLL_F; I2C 0xB8 with I2CA low (2.2 k);
  27 MHz external reference; 8 MSBs of each colour through 22 ohm.
- **TVP5150AM1**: 1.8 V core/analog (ferrite-filtered analog rail), 3.3 V I/O; maximum input 0.75 Vpp, so CVBS goes through
  24.9 + 49.9 ohm (75 ohm termination, x0.67) with an 820 pF anti-alias cap; 14.31818 MHz crystal, 27 pF loads, 100 k parallel;
  REFP / REFM 1 uF; I2CSEL high = 0xBA; INTREQ pin pulled down.
- **TFP410** (pin-strap): VREF = DVDD, BSEL high (24-bit single edge), EDGE high (rising), ISEL / DSEL / DKEN / CTL / RESERVED low,
  PD high, TFADJ 510 ohm 1 % to TVDD, IDCK- low. D23..16 red, D15..8 green, D7..0 blue.
- **TPD12S016PW** (source-port part, replaces the TPD12S520 of the first version): TMDS pins connect directly to controller and
  connector; VCCA = 3.3 V, VCC5V = 5 V, 5V_OUT -> HDMI pin 18 (current-limited); CT_HPD pulled high enables the part, HPD_A drives
  both the FPGA and LS_OE (datasheet Fig. 15, "one control line" mode); SCL_A/SDA_A to the FPGA (internal pull-ups on both
  sides, none added); CEC_B to the connector, CEC_A open. The order of the 8 TMDS pins within their group is only a routing
  convenience (inferred from the pin-function table).
- **AP62300** bucks (TSOT-23-6 pinout 1 GND, 2 SW, 3 VIN, 4 FB, 5 EN, 6 BST): 3.3 V (R1 31.6 k, R2 10 k, L 3.3 uH, 10 uF in, 2x22 uF out)
  and 1.9 V (R1 13.7 k, L 2.2 uH) from 5 V. Rails: 5 V (USB-C) -> 3.3 V, 1.9 V, 1.8 V LDO, 1.2 V LDO; ferrite-filtered analog copies.

## FPGA
iCE40HX4K-TQ144, 99 constrained pins (`gateware/pins.pcf`, generated from the schematic): bank 3 = TVP7002 data (pixel clock on a
global-buffer pin), bank 2 = TVP5150 BT.656 + I2C + UI, bank 0 = TFP410 data, bank 1 = VGA DAC bits, TFP410 VSYNC, 27 MHz clock,
HPD, DDC, SCART sense. All banks 3.3 V. Config: W25Q32JV SPI flash, a 7-pin programming header (hold CRESET low to program
externally), CDONE LED. Remaining gateware work: I2C sequencer + register ROM per mode, BT.656 decoder, line buffer
(line-double / bob), HD pass-through, timing generators, test pattern, SCART auto-select. Nothing of this is written yet.

## Verification done
- Generated with `tools/gen_sch.py` (= engine + `design_part.py`, symbols from `gen_symbols.py`); ERC: **0 errors**, 4 warnings
  (all intentional: I/O pins tied to GND on a net carrying the GND power flag, and the GND alias labels `TV_UNUSED` / `FPGA_GND0` / `TF_LO`).
- `tools/check_nets.py` exports the (hierarchical) netlist with kicad-cli and compares **all 882 intended pin connections** with KiCad's nets:
  0 mismatches across the sheet boundaries, no merged nets (this found and fixed a real GND-to-3.3 V short during layout).
- TVP7002 symbol checked against the datasheet pin diagram (97 of 100 entries by script, the other 3 by hand); TVP5150 spot-checked;
  TPD12S016 from the pin-function table; AP62300 pinout checked per package column.
- Footprints exist in KiCad stock except the SCART and RCA jacks.

## Not done / open points
1. **No PCB.** Analog video wants a 4-layer board with a solid ground plane; put the USBLC6 arrays and TPD12S016 right at their connectors;
   the TVP7002 exposed pad footprint (TQFP-100 EP 5x5 here) must be checked against TI's PZP drawing.
2. **No gateware, no simulation.** Nothing here has been powered up.
3. SCART / RCA jack footprints and part numbers. LCSC numbers are in the schematic (property `LCSC Part #`) and in `bom.csv`; J6 (SCART), J7 (3.5 mm jack), SW1 (C&K RS282G05A3) have no LCSC equivalent, L1/L2/FB1-6 are LCSC substitutes (see `tools/add_lcsc.py`).
4. HDMI is video only (no audio, no InfoFrames), CEC is only passed to the connector. Audio is the SCART/analog line out.
5. 1080i / 1080p out of the box is pass-through only (no scaling), VGA out at HD is marginal (see above).
6. SCART pin 8 / 16 sensing uses fixed thresholds (no hysteresis); a noisy console may need a 100 nF on the comparator inputs.
7. TVP7002 is rated 0 to 70 C. Inductors / ferrites / crystal: values from datasheets, parts not chosen (inductors Isat >= 4 A, shielded).
8. The TPD12S016 TMDS pin order and the AP62300 pin numbering are taken from the datasheet text, not from a pin drawing I could view.
