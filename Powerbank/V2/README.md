# PowerbankV2

The pack is 4S2P 18650 (8 cells in on-board holders, about 100 Wh with 3.4 Ah cells). It has two USB-C PD ports, and each one charges the pack and powers devices. The board is built with JLC PCBA.

**Status:** the schematic is done (ERC 0, netlist check 0 mismatches). The board is set up and **placed, not routed**.

## Architecture

| Block | Parts | Notes |
|---|---|---|
| Port A / Port B (identical) | TPS25751D PD controller + BQ25798 buck-boost charger | TI's TIDA-050047 pairing. The PD controller drives the charger over I2C (no MCU, no firmware). DRP: **45 W out** (15 V/3 A or 20 V/2.25 A, TI's rating) and **up to 66 W in**. |
| Pack protection | BQ7791501 + 2x AON6512 low-side FETs, 2 mOhm shunt, 20 A fuse | Thresholds: OV 4.25 V, UV 2.8 V, OCD1 17.5 A, SCD 60 A, OCC 10 A. Passive balancing at about 20 mA (RIN 100 R). |
| 5 V (PP5V) | TPS54531 buck from VBAT (TIDA-050047 values) | Supplies 5 V sourcing and VCONN for both ports. |
| 3.3 V (VIN_3V3) | ME6211 from 5 V | **SW401 PD RESET** pulls its enable low, so both TPS25751s reboot and reload their EEPROMs (when no cable is plugged in). |
| Fuel gauge | LM339 + TL431 ladder, 4 LEDs | Press **SW402**. 1 to 4 LEDs light above 3.09 / 3.40 / 3.61 / 3.81 V per cell. No standby current. |

Ground naming: `GND` = PACK- (system ground, after the protection FETs); `-BATT` = cell stack bottom (BQ77915 VSS); `+BATT` = VBAT (pack + after the fuse).

## Configuring the PD controllers (required before first use)

Each TPS25751D loads its patch and configuration from its own EEPROM (U202 / U302, CAT24C512) at boot. Without a valid image the ports do nothing.

1. Open TI's web-based **TPS25751 Application Customization Tool** and generate one image per port (both can use the same settings):
   - DRP (source + sink). Sink up to 20 V / 3.25 A (66 W). Source 5 / 9 / 15 V at 3 A and 20 V at 2.25 A (45 W).
   - Liquid detection: **No**. BC1.2: on, if the tool offers it (GPIO4/5 go to D+/D-).
   - Charger: **BQ25798**. Charge voltage **16.6 V** (4.15 V/cell, leaves margin to the 4.25 V OV trip). Charge current **3 A** per port; both ports at 3 A = 6 A, below the 10 A OCC limit. Pre-charge 400 mA. Termination 400 mA. VINDPM 5 %, INDPM 0 %.
   - Export -> **Generate Full Flash Binary**.
2. **First flash (blank EEPROM):** insert the cells. A blank EEPROM gives the TPS25751 nothing to load, so it waits and leaves its I2Cc bus idle. Solder a pin header into **J202** (port A) / **J302** (port B). Pinout: `1 EE_VCC, 2 3V3, 3 SCL, 4 SDA, 5 GND`. Write the .bin to I2C address 0x50 from offset 0 with any 3.3 V USB-I2C adapter (MCP2221A, FT232H, Pi Pico, CH341A with the 3.3 V mod). Use only SCL/SDA/GND; don't feed power from the adapter. Then press **PD RESET**.
3. **Re-flash later:** cut the bridged solder jumper **JP201 / JP301** once. From then on a shunt on J202/J302 pins 1-2 powers the EEPROM in normal use. To flash: pull the shunt, press PD RESET (the chip boots without its EEPROM and leaves the bus alone), refit the shunt, flash, press PD RESET again.

The TPS25751 I2Ct (host) ports of both chips share J401 (`1 3V3, 2 SCL, 3 SDA, 4 IRQ, 5 GND`). Port A is at 0x20, port B at 0x21. That bus is optional (TI GUI / debugging).

## Board

- 191 x 130 mm, 4 layers, JLC04161H-7628. The layer plan below is a suggestion only; In1 holds an unfilled GND zone, In2 and B.Cu are empty:
  - F.Cu: parts
  - In1: GND
  - In2: VBAT / power
  - B.Cu: signals
- Rules: JLC standard tier (0.3/0.7 mm vias, 0.3 mm copper to edge, 1.0 mm silk text). Net classes: Default 0.2/0.15; Power 1.0 mm track. VBAT, BATN, CELLx, GND, VBUS/PPHV/PMID/SYS/SWx and +5V are in the Power class.
- The TPS25751D footprint (`PowerbankV2:Texas_REF0038A_..._Via0.3`) is KiCad's TI land pattern with two changes: 0.3 mm thermal vias, and a footprint-local 0.1 mm clearance, because TI's merged power pads are 0.125 mm apart.
- The holders alternate orientation (BT101/102 + up, BT103/104 + down, ...), so each series link is a short top or bottom pad-to-pad hop:
  - BATN: bottom of BT101/102. The shunt and FETs sit right below.
  - CELL4 (+): bottom of BT107/108. The fuse sits right below.
- DRC: 0 errors besides unrouted ratsnest and cosmetic silk overlaps (ref-des over pads). Schematic parity is 0.

### Routing notes (for later)

- **High current** (about 9 A peak, both ports at 45 W): the paths below should be wide copper or pours. VBAT feeds both BQ25798 BAT pins, the buck and the fuse; best is a plane on In2.
  - BATN -> R111 -> Q101 -> Q102 -> GND
  - CELL4 -> F101 -> VBAT
  - the CELLx series links
- **R111:** route SRP/SRN Kelvin-style from the shunt pads (R112/R113 at the pads, C108-C110 at the IC).
- **BQ25798:** keep the SW1-L-SW2 loop and the PMID/SYS caps tight; many GND vias under the IC.
- **TPS25751D:** fill the EP (pad 39 GND) with vias to In1. DRAIN (pins 15/30/40) connects to nothing else; give it copper area only.
- **Cell sense lines** (CELL1-4 to R102-R105): thin traces are fine (balancing about 20 mA). CELL1 and CELL3 links are at the top edge of the holders.

## Parts and sourcing (JLC, checked 2026-10-24)

- **TPS25751DREFR C30169739: only about 21 in stock at JLC**, and each board needs 2. Alternative: TPS25751ADREFR C55162188. Pre-order with JLC if needed.
- Not usable: IP2368, IP5389 and SW6306 had 0 stock at JLC and LCSC, which is why this design uses TI parts.
- BQ25798 C2876593, BQ7791501PWR C2876947, TPS54531DDAR C50605, CAT24C512WI C79986, TVS2200 C523793, HRO TYPE-C-31-M-12 C165948, MYOUNG BH-18650-B1BA002 C2988620 (x8), AON6512 C485679 (x2).
- J202, J302, J401 (pin headers) are DNP.

## Cautions

- Use **matched, equally charged, high-drain cells**, for example 30Q/35E class. At full load each cell carries about 4.5 A. Check the holder's contact current rating.
- 8 x 3.5 Ah cells is about 101 Wh, just over the 100 Wh airline limit. 3.4 Ah cells stay under it.
- The BQ77915's OCC (10 A) trips if both ports charge at a high current; keep the per-port charge current at 3 A in the TI tool.

## Files and tools

- `datasheets/`: tps25751, bq25798, bq77915, tiduey1 (TIDA-050047).
- `tools/build_lib.py`: builds `lib/PowerbankV2.kicad_sym` and `.pretty` (BQ77915, TPS54531, MOSFET, switch symbols; holder/fuse/inductor footprints from easyeda2kicad output in `lib/lcsc`).
- `tools/design.py`: the intended pin -> net table. `tools/check_netlist.py` compares the KiCad netlist with it.
- `tools/gen_sch.py`: generates the schematic. **Don't re-run it after editing the sheets in KiCad.**
- `tools/make_pcb.py`: builds the board from the netlist (outline, stack-up, placement). **Don't re-run it after editing the PCB by hand.**
