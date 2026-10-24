# ECP5 emulation board (LFE5U-25F, caBGA-256)

FPGA board for emulating our custom MCUs and soft cores. Schematic done; PCB placed, fanned out and routed (DRC: 0 unconnected, 0 clearance errors).

## What's on it

| Block | Part | Notes |
|---|---|---|
| FPGA | LFE5U-25F-6BG256C (C1521614) | 24k LUT, 56 DSP, 1 Mbit BRAM. Same footprint and pinout as the -7BG256I placed in the symbol. All banks run at 3.3 V. |
| Config | W25Q32JVSSIQ, 4 MB QSPI | Master SPI boot (CFG = 010). The rest of the flash is free for user data. Buttons for PROGRAMN and a DONE LED. |
| USB | USB-C + CH347F | JTAG to the ECP5 (`openFPGALoader -c ch347`). UART0 + SPI go to bank 7 for the emulated core. Board power comes from USB (1.1 A PTC). |
| RAM | W9812G6KH-6, 16 MB SDR, x16 | 166 MHz. The footprint also fits the 32 MB W9825G6KH; route spare ball M15 to pin 36 (A12) for that. |
| Clock | 25 MHz oscillator on P6 | P6 is the PLL input LLC_GPLL0T_IN. |
| Video | 12-bit VGA (4-4-4 resistor DAC) + HDMI connector | HDMI carries DVI as LVCMOS33D pairs, plus DDC and HPD. |
| Audio | 3.5 mm line out | PWM / sigma-delta through an RC filter. |
| User I/O | 8 LEDs, 8 DIP switches, 4 buttons, 4-digit 7-segment, microSD | |
| Expansion | 4x PMOD (A/B on bank 0, C/D on bank 2) | Also a 40-pin header with 34 GPIO, +5 V, +3.3 V and GND. |
| Power | 2x SY8089 buck (3.3 V, 1.1 V), AP2112K-2.5 LDO (VCCAUX) | |

## Files

- `LFE5U-25F-7BG256I.kicad_sch` is the root sheet. It holds the FPGA units as placed in KiCad, moved right by 63.5 mm so they sit inside the A3 frame. The sub-sheets are power, config, usb_jtag, sdram, video_audio and user_io.
- `constraints/LFE5U-25F-7BG256I.lpf` holds the pin constraints for nextpnr-ecp5 / Diamond: 180 ports, with PULLMODE set for the switches, buttons and SD. Build with `nextpnr-ecp5 --25k --package CABGA256 --speed 6`.
- `tools/design.py` assigns every ball to a net. It is the single source for the schematic labels, the LPF and the netlist check.
- `tools/gen_sch.py` generates every sheet. Re-run it after editing `design.py`. Before re-running, diff `.history` for edits made in KiCad.
- `tools/check_netlist.py` exports the netlist and checks it against `design.py` plus the local nets. It still expects the old references J503/J601 for the audio jack and microSD, which are now CN1/Card1.
- `tools/place_pcb.py` places the PCB, then `tools/fanout_pcb.py` does the BGA and plane fan-out.
- `tools/route_prep.py`, `route_finish.py`, `route_cleanup.py` and `route_leftovers.py` do the routing (see Routing below).
- `tools/build_lib.py` builds `libs/fpga_board.kicad_sym` (SY8089, CH347F).

## PCB

The board is 100 x 100 mm, 6 layers, 1.6 mm thick:

| Layer | Use |
|---|---|
| F.Cu | signals |
| In1 | GND |
| In2 | signals |
| In3 | signals |
| In4 | +3V3, with a +1V1 island under the BGA |
| B.Cu | signals |

It started out as 4 layers. Freerouting stalled there at about 60 unrouted connections on two signal layers, so the board went to 6 layers. The stackup in the board file is JLC's 1.6 mm 6-layer build: 2313 prepreg on the outsides, 0.565 mm cores, and 2116 prepreg in the middle. The values are nominal, because the board is ordered without impedance control. In2 and In3 sit only about 0.13 mm apart, so long parallel runs between them should be avoided.

All parts are on the top side. `tools/place_pcb.py` does the placement: it only moves footprints and sets up the layers, rules and net classes. `tools/fanout_pcb.py` then does the BGA and plane fan-out, and the routing tools do the rest (see below). The edges follow the FPGA banks:

| Edge | What's there | Bank |
|---|---|---|
| Top | PMOD A, PMOD B | 0 |
| Top | HDMI, VGA | 1 |
| Right | microSD, audio, PMOD C/D, with the SDRAM just inside | 2 / 3 |
| Left | USB-C, GPIO header, with power and the CH347 next to the USB | 7 / 6 |
| Bottom | 7-segment, LEDs, DIP switches, buttons; flash and config sit under the BGA | 6 / 8 |

The middle of each BGA side is kept free for fan-out, and the FPGA decoupling sits in the four corners.

### Fan-out

`tools/fanout_pcb.py` escapes all 197 used balls. Each escape ends 1.6 mm outside the outer ball row, so routing starts outside the BGA.

| Balls | Escape |
|---|---|
| Ring 0 (outer row) | F.Cu, straight out |
| Ring 1 | F.Cu, through the channel between two ring-0 balls |
| Ring 2, where a ring-0 channel is still free (8 balls) | F.Cu, straight out, no via |
| Remaining rings 2-5 (94 balls) | Dog-bone via, then a 0.1 mm B.Cu track. A small maze router picks each via's interstitial together with its path. |
| GND, +3V3, +1V1 | Dog-bone via to the plane. F7 and H7 (+3V3 deep in the core) link to their neighbour on F.Cu. |

Why the maze router: straight lanes jam. The ring-2 vias form a wall that passes one track per gap, and between two walls there is room for only one sideways track.

The In4 +1V1 island is shaped around the core. It covers the core square, then runs up an arm through the middle of the top side (no vias in that interstitial column), then along a bar above the BGA. The bar carries all six 100 nF +1V1 caps and C220 from the regulator. For that, C224/C225 swapped places with C242/C243.

The inner planes use 0.1 mm clearance and 0.1 mm minimum width, so copper still flows between two vias 0.8 mm apart. Without that, the 3.3 V plane and the 1.1 V island broke into pieces.

Every other GND/+3V3/+1V1 SMD pad gets a stub and via into its plane where one fits. All fan-out copper is locked, so Freerouting keeps it. Nine plane pads had no room for a via (the regulator side of +1V1, the J502 GND pins, U301 pin 6). Routing ties them to the nearest via of their net. Re-running the script strips the fan-out and redoes it. It refuses to run once there are unlocked (routed) tracks.

Vias must stay out of the In4 arm above the BGA (x 42.4-45.6 mm, y 27-32 mm from the board corner). It is the only feed into the 1.1 V core. A no-via rule area named "+1V1 arm" enforces this, both in DRC and in the Freerouting DSN.

### Routing

1. `tools/route_prep.py` writes `route/LFE5U-25F-7BG256I.dsn`. It takes the plane nets out of the job: Freerouting doesn't treat inner planes as connections, so their fixed copper becomes a netless obstacle. The nine via-less plane pads are routed as small `<net>__<n>` nets to the nearest via of their net. The router's via types are named from the layer count (`Via[0-5]_...` on 6 layers). Earlier the 4-layer names were left in, and Freerouting then could hardly place any vias.
2. Freerouting 2.4.1 from the KiCad plugin, headless:
   `java -Djava.awt.headless=true -jar freerouting-2.4.1.jar -de LFE5U-25F-7BG256I.dsn -do LFE5U-25F-7BG256I.ses -mp 100 -mt 8 --gui.enabled=false --router.job_timeout="01:30:00"`
   It stopped on its own after 28 passes (20 min) with 8 connections open. `route/watch.ps1` shows its progress.
3. `tools/route_finish.py` imports the session, and `tools/route_cleanup.py` strips the copper that leads nowhere. With In2/In3 free, Freerouting mostly left each BGA via on an inner layer, so most 0.1 mm B.Cu escapes ended up as dead ends. Cleanup uses KiCad's DRC to decide what dangles. It trims a track back to a junction rather than deleting it, and it undoes any round that would open a connection.
4. `tools/route_leftovers.py` routes what is still open. It is a 0.05 mm grid router on the four signal layers with rip-up and reroute: other nets' unlocked routing is a soft obstacle, and whatever it crosses gets rerouted. Fan-out, pads and plane copper are hard obstacles. Afterwards it bridges near misses that the grid saw as joined. It routed the last 6 (the HDMI pairs, HDMI_SCL, CH_RXD, GPIO32, PMODD6) after moving a few HDMI/VGA/PMOD-B neighbours.

What DRC still reports is cosmetic: 10 dead-end stubs of 0.02-0.5 mm and 5 vias that join two tracks on one layer, all around the top edge of the BGA. Silk-to-edge and Card1's courtyard were there before routing.

The HDMI pairs are not length-matched or coupled. That's fine at DVI 640x480 (25 MHz pixel clock); higher modes need them redone by hand.

## Notes for layout

- ERC: the remaining warnings come from the LCSC FPGA symbol, whose pins are all "unspecified". The "pin not driven" errors have the same cause: KiCad does not treat an unspecified pin as a driver. Setting the bank pins to bidirectional in the LCSC symbol would clear both.
- microSD (Card1) and audio (CN1) now use the LCSC footprints. The library copies are fixed: the locating pegs are NPTH and the microSD courtyard is a plain rectangle. Run *Update Footprints from Library* on Card1 to pull the courtyard fix in. The HDMI and VGA footprints are still close stock matches. Swap them for the exact LCSC parts with easyeda2kicad before placement. Do the same for the CH347F QFN-28 exposed-pad size.
- Vias come in two sizes:
  - **BGA: 0.2/0.45 mm** (0.125 mm ring). JLC only charges extra for a 0.2 mm hole when the pad is under 0.45 mm. JLC's via rule is a pad at least 0.1 mm larger than the hole, so the ring only needs 0.05 mm.
  - **Cap fan-out: 0.3/0.7 mm**, falling back to 0.3/0.6 mm.
- Inside the package everything runs at 0.1 mm: tracks and gaps on B.Cu, the Power and TMDS net-class clearance, and the plane clearance and minimum width. JLC's multilayer standard is 0.09 mm.
- JLCDFM marks the 0.1 mm tracks, the via rings and the audio jack's 0.5 mm slots as "Danger". It is grading against the 2-layer limits. JLC's multilayer limits are 0.09 mm track/space and 0.35 mm plated slots.
- The fan-out script turns on "subtract soldermask from silkscreen", so the gerbers carry no silk on pads or holes.
- LCSC BOM cost on 2026-10-18 at minimum order quantities: $55.36 for one board, $84.71 for two.
