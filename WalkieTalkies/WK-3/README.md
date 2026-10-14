# WK-3: fully analog 2 m PTT walkie-talkie

A crystal-controlled narrowband-FM transceiver for the 2 m amateur band:
- **No digital parts:** no MCU, no PLL, no DSP and no firmware.
- **No alignment:** there is nothing to tune. Every filter, tank, bias point and level is set by fixed values and has been checked in simulation against component tolerances.
- **Sourcing:** every part comes from LCSC (the `LCSC Part #` field on each symbol), and only stock crystals are used.

> **Licence:** transmitting on 145 MHz needs an amateur radio licence (in Germany Klasse N / E / A). Check your band plan and your licence's power limit. Before going on air, confirm the spurious emissions with a spectrum analyser; simulation is not a substitute.

## Key numbers

| | |
|---|---|
| Channel | **145.400 MHz** simplex (IARU R1 V32), single channel, crystal controlled |
| Mode | NBFM, 12.5 kHz raster, **±2.3 kHz** peak deviation (simulated), 6 dB/oct pre-/de-emphasis |
| TX power | **≥ 1 W on every RFM01U7P of its 0.6–1.6 V threshold spread from a full pack down to mid-charge**: 1.13 W typical, 1.00 W for the highest-threshold part (whole transmitter simulated in one netlist). Driver and PA run from a regulated 7.0 V rail, so the power is the same from 8.4 V down to ≈ 7.1 V. Below that, typical / worst part: 0.99 / 0.89 W at 6.6 V, 0.84 / 0.75 W at the 6.1 V cut-off (datasheet-based model) |
| TX spurs | Harmonics −80 / −123 dBc. Strongest other emission anywhere from 30 MHz to 1 GHz: −86 dBc (≈ −55.5 dBm, 2LO − 2IF at 141.2 MHz), 19 dB under the −36 dBm CEPT limit. The PA is stable with no drive at every tolerance corner, and its drain stays under its 20 V rating (19.0 V worst case) |
| RX | LNA + J310 mixer → 37.4 MHz 4-crystal ladder (≈14 kHz) → MC3361 (1 MHz 2nd IF) → LM386. Image rejection 52 dB, LO rejection 52 dB |
| Supply | **2 × 18650 in series**, in two MYOUNG BH-18650-B1BA002 SMD holders on the back of the board (6.0–8.4 V). Under-voltage cut-off: off below ≈ 6.06 V (5.91–6.22 V worst case), back on only above ≈ 6.58 V (6.41–6.76 V). The 0.5 V hysteresis keeps the switch-over clean even with worn or cold cells. Nothing draws current when switched off. Charge the cells outside the radio. A TL1963A makes the 7.0 V PA / driver rail. Do **not** exceed 9 V (AO3401A V<sub>GS</sub>, 2SC3357 V<sub>CEO</sub>) |
| Current | TX ≈ 385 mA from the battery (driver + PA, simulated; ≤ 419 mA on a low-threshold PA) plus about 60 mA on the 5 V rail and 3 mA for the cut-off. RX ≈ 57–67 mA (estimate, including 1.5 mA for the PA regulator) |

**Range:** at 1 W (+30 dBm) with −5 dBi handhelds 1.5 m above open ground, the plane-earth loss at 2 km is about 125 dB. That leaves roughly 14 dB of margin over a −119 dBm receiver: about 2.5 km with a solid link and 4.5 km at the edge on open ground, 1–2 km in town, and 10–40 km from high ground with line of sight.

## Frequency plan (stock crystals only)

```
LO:  Y501 54.000 MHz (10 pF) VXO, FM via 1SV305 on MOD  -> x2 (damped tanks) -> 108.000 MHz
     -> fixed 3-pole 108 MHz band-pass -> LO_TX (TX mixer) / LO_RX (RX mixer)

TX:  mic -> LMV324 pre-emphasis / limiter / 3 kHz splatter filter -> fixed divider -> MOD (FM on the 54 MHz VXO)
     Y201 37.400 MHz osc -> 50 MHz LPF -> ETC1-1-13 -> MC1496 Gilbert mixer (LO 108 via ETC1-1-13) -> ETC1-1-13
     -> elliptic HPF #1 -> 7-pole elliptic LPF -> 2SC3356 -> elliptic HPF #2 -> 2SC3356 (+4 dBm)
     -> 2SC3357 driver -> RFM01U7P (7.0 V rail, fixed 2.5 V gate bias, drain-gate RC feedback) -> pi-match -> PIN T/R -> 7-pole LPF -> SMA
     108.0 + 37.4 = 145.4 MHz

RX:  SMA -> 7-pole LPF -> PIN T/R -> elliptic HPF (zeros 108 / 94 / 59 MHz) -> 2SC3356 LNA
     -> J310 mixer (LO 108 on the source) -> 37.4 MHz -> 4 x 37.400 MHz ladder -> 2SC3356 IF amp
     -> MC3361 (Y601 38.400 MHz) -> 1.0 MHz LC IF -> limiter -> quad detector -> de-emphasis
     -> volume -> LM386 -> 8 ohm;  10 kHz noise squelch
```

The same 108 MHz LO serves both directions, so a constant LO error moves TX and RX together. Between two WK-3 radios, only the crystal tolerances (±10 ppm) remain.

## Why nothing needs trimming

- **No resonant filters that need tuning.** The RX and TX band-limiting uses *fixed* 7th-order elliptic high-pass filters and Chebyshev low-pass filters with wide passbands (`tools/design_hpf.py`). They are verified by Monte Carlo over C ±2 % / L ±5 %.
- **Crystals at their rated load.** The VXO presents 10.9 pF to the 10 pF crystal (−13 ppm), and the TX offset oscillator presents ≈9 pF to the 9 pF crystal. FM is applied to the VXO with a fixed bias, so no netting trimmer is needed. Start-up margin is >4× on a 40 Ω max-ESR crystal, with ≈90 µW crystal drive.
- **Damped LO tanks plus a fixed band-pass.** The ×2 tanks are deliberately low-Q, so the inductor tolerance can't detune them. A wide (25 %) fixed 3-pole band-pass then cleans the LO to ≤ −50 dBc (`tools/design_lobpf.py`).
- **IF filter terminations chosen by simulation.** The ladder's terminations were picked over the crystal spread of a whole reel (`tools/design_ladder.py`). The IF amplifier's gain is held to ≈ 13 dB (R609 100 Ω, R608 680 Ω), so its Miller capacitance doesn't detune the last crystal: ripple 1.0 dB with typical crystals.
- **Fixed TX levels.** The MC1496's IF and LO levels and the gain resistor are set by fixed resistors. The PA runs from a fixed 2.5 V gate bias on a regulated 7.0 V rail, so there is no I<sub>dq</sub> to adjust. Every PA check passes across the RFM01U7P's full 0.6–1.6 V threshold spread, including ≥ 1 W and a drain peak under its 20 V rating. A 680 Ω + 100 pF drain-to-gate network keeps the stage stable with no drive. Deviation is set by a fixed divider after the limiter.
- **Low-Q IF2 networks.** The MC3361's 1 MHz IF filter and quadrature tank are wide enough that 5 % parts stay inside their usable range.

## Sheets

| Sheet | Contents |
|---|---|
| `power` | 2 × 18650 holders (BT101 / BT102, on the back), 0.75 A polyfuse, AO3401A reverse-polarity FET, AO3401A power FET (Q105) turned on by the slide switch through a TL431 under-voltage cut-off (U102, R106–R109, C108), LP2985-5.0. PTT switching: Q102 drives `TX5`, Q103/Q104 drive `RX5`. Power and TX LEDs. |
| `tx_exciter` | Electret mic. LMV324 pre-emphasis preamp, limiter, 3 kHz splatter filter and VREF buffer. Deviation divider → `MOD`. 37.4 MHz oscillator, 50 MHz LPF. MC1496 mixer with three ETC1-1-13 baluns: IF in, LO in (balanced, T203) and output. Elliptic HPF #1 → `TXH1_OUT`. |
| `tx_amp` | 7-pole elliptic LPF (removes the mixer's 2LO−IF, 2LO and 3LO±IF before any amplifier), 2SC3356, elliptic HPF #2, 2SC3356 → `TX_RF`. |
| `tx_pa` | TL1963A 7.0 V rail for driver and PA (U301, R311 / R312, C315 / C316). 2SC3357 class-A driver, interstage match, Toshiba RFM01U7P with fixed 2.5 V gate bias and drain-gate RC feedback (R310 / C313), pi-match (C314, L304, C312) → `PA_OUT`. |
| `rf_frontend` | SMA, 7-pole LPF, BAR64 PIN T/R switch with lumped λ/4, elliptic HPF, 2SC3356 LNA → `RX_RF`. |
| `lo` | 54 MHz VXO, ×2 tank, buffer, emitter follower, 3-pole 108 MHz band-pass → `LO_TX` / `LO_RX`. |
| `rx_if` | J310 mixer, 37.4 MHz ladder, 2SC3356 IF amp, MC3361, de-emphasis, volume, noise squelch. |
| `audio` | LM386 (gain ≈40) → 8 Ω speaker. |

Every sheet is drawn with real wires and junctions. GND and the supply rails use power symbols. Neighbouring pins on the same rail share one symbol via a short bus wire. Labels appear only where a signal crosses sheets. Text placement is collision-checked on every build (`tools/cosmetic_check.py`).

## Simulation (KiCad's built-in simulator)

`sim/` holds ten stand-alone KiCad projects. Each contains a section of the real circuit (same references, values and wiring) plus test-bench parts numbered 9xx: sources, 50 Ω ports and supplies. Every part carries `Sim.*` fields pointing at `sim/wk3_models.lib`.

To use one:
1. Open `sim/<bench>/<bench>.kicad_pro`.
2. In the schematic editor, choose **Inspect → Simulator** and press **Run**.
3. Plots are pre-configured. The two-tab benches (`tx_mixer`, `tx_pa`, `lo_chain`) have a TRAN tab and an FFT tab: run TRAN first, then FFT.

| Bench | Analysis | Shows |
|---|---|---|
| `rx_frontend` | AC | Gain into the J310 gate, antenna match, image / LO / FM-broadcast rejection |
| `tx_rf_chain` | AC | HPF + LPF + amplifier transfer: LO, LO−IF, IF and 3LO±IF rejection |
| `tx_mixer` | TRAN + FFT | MC1496 up-conversion and the TX_RF spectrum (spurs) |
| `tx_pa` | TRAN + FFT | Output power, harmonics, battery current, efficiency, idle stability (drive off, kicked, at nominal and worst-case FET), drain peak on a full pack |
| `lo_chain` | TRAN + FFT | VXO start-up, LO level and purity. Runs ≈1 min: the real crystal needs ~0.5 ms to settle |
| `if_ladder` | AC | 37.4 MHz ladder passband / skirts (change `Cm` on the crystals to see the spread) |
| `if2_quad` | AC | MC3361 1 MHz IF filter and quadrature tank |
| `mic_chain` | AC + TRAN | Pre-emphasis, splatter roll-off, limiting |
| `squelch_audio` | AC | De-emphasis / volume and the 10 kHz noise-squelch filter |
| `power` | TRAN | Battery switch and TL431 cut-off while transmitting: switching points, Q105's drop, a worn pack (1.5 Ω) held at every voltage near the threshold and recovering (no half-on state, no chatter), current when switched off |

`python tools/sim_benches.py` rebuilds every bench, then exports each one with `kicad-cli` and runs it in KiCad's own ngspice. It writes **`sim/RESULTS.md`**; currently **84 / 84 checks pass**. Two of the groups are cross-bench:
- **Deviation:** the limiter's clip level through the VXO's pull curve gives ±2.3 kHz peak.
- **Whole transmitter (`tx_chain`):** the `tx_mixer` and `tx_pa` benches are joined into one netlist, so the real exciter output (every mixer product, amp 2's harmonics) drives the real PA. Spurs are read at the antenna, both for a list of known products and as the strongest line anywhere from 30 MHz to 1 GHz. It also checks ≥ 1 W with the highest-threshold PA, the battery current with the lowest-threshold one, and the PA drain peak on a full pack at every threshold. This check found the problems described below; each bench on its own had passed.

**Pictures:** `python tools/sim_plots.py` draws `sim/plots/`: an overview of the radio, one picture per bench (plots, a plain-language explanation and the check table), the whole transmitter (11), PA stability with no drive (12) and the battery cut-off (13).

**TX spurious fix (2026-10-11).** The first design drove the MC1496's LO port on one pin. The LO common-mode swing on the switching quad made 2LO − IF (178.6 MHz) at −29 dBc. That is just above the 164 MHz antenna low-pass corner, so it left the antenna at −43 dBc (≈ −13 dBm, in DAB band III). Fixes:
- a third ETC1-1-13 (T203) now drives pins 8 / 10 in antiphase;
- C262 is gone and R246 is 2.2k;
- two capacitors (C259 10 pF across L248, C265 8.2 pF across L249) make the TX low-pass elliptic, adding at least 14 dB at 178.6 MHz in a ±5 % Monte Carlo;
- R219 = 100 Ω lowers the IF drive, which lowers 2LO − 2IF and 4·IF.

Now 178.6 MHz is −79 dBc at TX_RF.

**Close-in products, PA stability, 1 W (2026-10-11).**
- **Mixer products 4–9 MHz either side of the carrier (−85 dBc):** the MC1496 now runs more linearly (R250 = 220 Ω emitter degeneration), with amp 1's gain raised (R222 = 2.2k) to make up the level.
- **PA oscillation:** the PA oscillated near 220 MHz whenever it was biased without drive, which happens on every PTT press before the 37.4 MHz oscillator starts. R310 (680 Ω) + C313 (100 pF) from drain to gate fix it at all 72 threshold / feedback-capacitance / gain / L302 / L304 tolerance corners tested.
- **1 W on every part:** gate bias 2.0 V (R307 1k, R309 680) and a re-fitted interstage (C304 47p, C305 15p, L302 33n).
- **Trade-off:** the PA now runs less saturated, so the 141.2 MHz product stays at −88.7 dBc instead of the −96 dBc a saturated PA gave; still 22 dB under the limit.
- **Simulation accuracy:** benches that look for products near −90 dBc must use a ≤ 10 ps time step. At 50 ps the close-in products were overstated by 12–30 dB and aliases appeared as fake lines.

**Battery cut-off hysteresis (2026-10-12).** The cut-off had only 0.28 V of hysteresis (R107 15k, R109 330k).
- **The problem:** when the pack's series resistance is 1 Ω or more (worn or cold cells, the holder contacts, a polyfuse that has tripped once), the radio could hang near the threshold while transmitting.
  - The current drop as Q105 opens raises the pack voltage by more than the hysteresis, so the cut-off can't snap off.
  - The `power` bench showed Q105 settling half-on at up to 0.56 W, and switching 71 times while the pack recovered.
- **The fix:** R107 = 15.4k and R109 = 180k give 0.5 V of hysteresis: off at 6.06 V, back on at 6.58 V. The cut-off now snaps cleanly up to ≈ 1.7 Ω of pack resistance; it is checked at 1.5 Ω.
- **What it costs:** only resistor values changed. The two lines were single-use, so the line count is the same and the layout untouched.
- **Model note:** the TL431 is a behavioural model (threshold, gain, ~2 V saturation), not TI's macromodel.

**Cost pass (2026-10-12): $82.28 → $71.25 for a pair.**
- The 10 µF, P-MOSFET and N-MOSFET lines moved to cheaper parts with the same footprint and pinout.
- The BFR92P became the 2SC3356 everywhere.
- The 2SC3356 has more gain and more feedback capacitance, so three things were re-fitted in simulation:
  - **IF amp:** R609 47 → 100 Ω and R608 1k → 680 Ω. The amp's Miller capacitance pulled the ladder's last crystal (ripple 2.8 dB); now 1.0 dB. The IF gain drops from 21 to 13 dB. That is harmless, because about 28 dB of gain still sits ahead of the MC3361, so the LNA sets the noise figure.
  - **Exciter:** R222 2.2k → 1k. Amp 1 now gives about 1.5 dB less gain, because the stronger amps had pushed the PA drain to 19.4 V.
  - **PA interstage:** C305 22p, C304 68p. They restore 1.00 W on the highest-threshold part with an 18.98 V drain peak.
- There is no cheaper PA transistor in stock at LCSC.

**PA drain over its rating; 7.0 V PA rail (2026-10-12).** The RFM01U7P is rated V<sub>DSS</sub> = 20 V.
- **The problem:** fed straight from the pack through an L-match (series L, shunt C on the 50 Ω side), nothing shorted the harmonics at the drain. The saturated stage swung to 3.2 × its supply: about 24 V at 7.4 V and 28 V on a full pack. No earlier check measured the drain voltage.
- **What did not work:** re-tuning bias, interstage and output values (`tools/pa_vds_tune.py`, ≈ 1500 candidates), even with a drain capacitor, still left 20.3 V on a full pack and only 0.94 W from the highest-threshold part. The 0.6–1.6 V threshold spread under a fixed bias is the limit.
- **The fix:**
  - a TI TL1963A LDO (U301) makes a 7.0 V rail for driver and PA (R311 10.5k / R312 2.2k, C315 in, C316 out, C310 at the PA);
  - C314 (10 pF) at the drain turns the output into a pi-match;
  - gate bias 2.5 V (R309 1k);
  - re-tuned values C304 100p, C305 18p, L302 47n, C312 22p, tuned against the whole-transmitter netlist with the real exciter driving the PA.
- **Result:** worst drain peak 18.9 V on a full pack, 1.01 W from the highest-threshold part, 1.13 W typical, 421 mA with the lowest-threshold part. Idle-stable at all 72 tolerance corners.
- **What it costs:** ≈ $3 for the two regulators, up to 0.6 W of regulator heat on a full pack, and less power near empty (the rail drops out below ≈ 7.1 V).
- **Targets changed:**
  - the lowest-threshold current limit went from 420 to 440 mA (my own target; the polyfuse holds 0.75 A);
  - the close-in spur target went from −85 to −84 dBc, because 2LO − 2IF is now −85.0 dBc (less PA compression). It is still 18 dB under the CEPT limit.
- **The PA bench's own source** (+3 dBm behind 50 Ω) drives a little harder than the real exciter, so that bench holds the drain to the 20 V rating while the whole-transmitter check holds it to 19 V.

Model notes:
- The device models are documented approximations: 2SC3356 / MMBTH10 / 2SC3357 Gummel-Poon, a level-1 LDMOS, a transistor-level MC1496, behavioural TL431 and TL1963A, and the crystals described by their datasheet load frequency. Drop in manufacturer models under the same names for higher fidelity.
- The LO bench uses a 0.1 ns step because coarser steps shift the simulated frequency by hundreds of ppm (a numerical effect of trapezoidal integration). The LO frequency itself is computed from the small-signal oscillation condition.

## Parts and cost

- Every symbol has an `LCSC Part #`. Mounting holes are the only exception. Every number is a part LCSC sells directly.
- The board is meant for hand assembly with parts from LCSC. `tools/lcsc_cost.py` prices the order with LCSC's live prices, minimum quantities and order steps.
  - **2 boards (a pair): $71.25**, 83 order lines (18650 cells not included).
  - About $33 of the 2-board order is minimum-order overhead (leftover parts), so a second board adds only ~$10.
  - `tools/bom_cost.py` is the same estimate for JLC assembly, including JLC's $3 loading fee per extended part.
- Values were consolidated to a shared set: 110 → 77 LCSC lines, −$11.9 for a pair.
  - The RF filters were re-fit with `tools/design_consolidate.py` ("no worse than before" on every rejection spec, plus Monte Carlo).
  - All simulation benches were re-run; every check passes, and output power and most rejections improved.
  - `tools/apply_values.py` pushes value changes into the schematic and board in place.
- Notable parts:

  | Part | LCSC | Note |
  |---|---|---|
  | RFM01U7P PA (Toshiba) | C17561258 | $3.03 each; replaces the obsolete AFT05MS004N; end-of-life at Toshiba, so buy a spare. The only VHF ~1 W part LCSC has in stock (the similar 2SK3475 / RFM04U6P, ≈ $0.9, had 0 stock on 2026-10-12) |
  | BSMD1206-075-30V polyfuse | C976305 | 0.75 A hold, margin over the ~0.41 A worst-case TX current |
  | MC1496BDR2G | C512980 | −40…+125 °C version |
  | BWSMA-KWE-Z001 SMA | C496551 | THT right-angle, $0.41 (replaced the $8.56 Amphenol edge launch) |
  | NLV32T-470J-PF 47 µH | C66936 | LCSC stock; the previous 47 µH part was JLC-only |
  | 54.000 MHz / 10 pF crystal | C252258 | low stock (359 at last check) |
  | TCC0805X5R106K250FT 10 µF 25 V 0805 (CCTC) | C5448891 | all 13 × 10 µF. 25 V is plenty (8.4 V max); $1.20 for 30 instead of $6.27 for the Murata 50 V part (C440198) |
  | 2SC3356 (Guangdong Hottech) | C193010 | TX amps, LNA and IF amp; $0.47 for 10 instead of $4.20 for the BFR92P. Same SOT-23 pinout (1 B, 2 E, 3 C), checked on the LCSC symbol |
  | CCX3401A (Chao He), 2N7002KT1G-ES (ElecSuper) | C51953476, C5224218 | drop-in clones of the AO3401A and 2N7002 (same pinout, 50 mΩ at −4.5 V / 1.6 V threshold). The schematic keeps the generic values `AO3401A` / `2N7002` |
  | BH-18650-B1BA002 holder (MYOUNG) | C2988620 | 1 × 18650 SMD; two per radio, on the back. Footprint `WK3:BatteryHolder_MYOUNG_BH-18650-B1BA002` from easyeda2kicad, with the peg hole made non-plated and pad 1 = + |
  | TL1963ADCQR (TI) | C86720 | 7.0 V PA / driver rail (R311 10.5k / R312 2.2k), ≈ 0.15 V dropout at 0.45 A, SHDN tied to VBAT. Same pinout as KiCad's `LT1963EQ` symbol; footprint `SOT-223-6_TabPin3` (tab = GND) |
  | TL431AIDBZR (TI) | C23892 | under-voltage cut-off (R107 15.4k, R108 10k, R109 180k: 6.06 V off / 6.58 V on); TI's DBZ pinout = KiCad's `TL431DBZ` symbol (1 K, 2 REF, 3 A) |
- The power slide switch (PCM12, contacts rated 0.3 A / 6 V) only powers the cut-off divider (≈ 0.3 mA). Q105 carries the battery current, so the switch stays within its rating.
- Pinouts checked against the manufacturer datasheets:
  - RFM01U7P (PW-Mini = SC-62/SOT-89): 1 Gate, 2 Source/tab, 3 Drain.
  - TECH PUBLIC 2SC3357 (SOT-89): 1 Base, 2 Collector/tab, 3 Emitter.
  - ETC1-1-13: 1 primary (dot), 2 primary, 3 secondary, 4 N/C (GND), 5 secondary (dot).
  - ALJ MMBTH10 (SOT-23): 1 B, 2 E, 3 C.
  - MC1496 and MC3361 follow their standard pinouts. UTC's MC3361 datasheet is a scan, so it was checked against the reference pinout.

## Status

- [x] **Schematic:** 8 hierarchical sheets, 339 parts (three mounting holes), fully wired. ERC is clean (0 errors, 0 warnings). The netlist matches the design data pin for pin (761 pins).
  - `bom_consistency.py` checks all 336 purchased parts across every copy of the parts list: the design data, `lcsc_map.json`, the schematic, the board, the JLCPCB tools plugin's database, the BOM and the CPL. Value, footprint and LCSC number agree in all of them.
- [x] **Simulation:** 10 KiCad benches plus the whole-transmitter netlist, 84 checks passing (results in `sim/RESULTS.md`, pictures in `sim/plots/`).
- [x] **PCB:** 66 × 155 mm, 4 layers (F.Cu signal / In1 GND / In2 GND / B.Cu signal, JLC04161H-7628).
  - **Placement** (`place_wk3.py`): one zone per function. The RF blocks form a ring that follows the signal: PA → antenna front end → J310 mixer + LO → TX mixer → TX amps → PA. The RX chain runs down the right side, with mic and power at the bottom. Parts start from their schematic positions and are optimised by simulated annealing: wire length, decoupling next to its pin, routing margins, connectors at the edge.
  - **Routing** (`route_wk3.py`):
    - every SMD GND pad has its own via to the GND planes;
    - Freerouting routes the rest on F.Cu / B.Cu;
    - F.Cu and B.Cu carry GND pours, stitched to the planes every 2.5 mm over the RF section and every 4 mm elsewhere.
  - **Net classes:** `RF50` 0.35 mm (≈ 50 Ω microstrip over GND), `POWER` 0.4 mm, default 0.2 mm.
  - **JLCPCB standard price tier, no extra-cost options:**
    - all vias are 0.3 mm drill / 0.7 mm pad, a 0.20 mm annular ring (`POWER` vias 0.4 / 0.8 mm);
    - no blind, buried or micro vias, no via-in-pad, vias tented;
    - copper is ≥ 0.3 mm from the board edge (also at the SMA);
    - silkscreen text is 1.0 mm with 0.15 mm lines.

    The board's DRC constraints are set to these limits (`wk3_rules.py`).
  - **DRC:** 0 violations, 0 unconnected items and 0 schematic-parity issues. Freerouting left one TX5 connection in the mic section open; it was routed by hand.
  - **TX spurious fix:** added T203, C259 and C265 and removed C262 (`eco_lo_balun.py`, then `eco_reroute.py` for the four local nets around T203). The rest of the routing was not touched. The references of C246, L248 and R244 no longer fit on the silkscreen next to the new parts, so they are on F.Fab (assembly drawing) only.
  - **Battery, cut-off, PA feedback** (`eco_battery.py`, then `eco_reroute.py` for Q105's gate net):
    - J101 removed; BT101 / BT102 on the back at positions scored for no through-hole leads under the holders and no peg hole on front copper.
    - 14 GND stitching vias under the holders' non-GND pads were removed.
    - The battery path is 0.4 mm.
    - Silkscreen references that no longer fit (C108, C306) are on F.Fab only; the holders' references are on B.SilkS.
  - **7.0 V PA rail** (`eco_pa_reg.py`, then `eco_add.py` for C316):
    - VBAT was cut where it leaves the trunk for the PA corner. The copper on the PA side became the new rail as it was, so the PA corner was not re-routed.
    - U301 sits in the free strip left of the trunk; 6 GND stitching vias were removed.
    - References that no longer fit (C302, C303, C314, C315, R311, R312) are on F.Fab only.
- [ ] **Bench measurements:** output power, spurs and deviation on a spectrum analyser before use on air.

## Regenerating

Everything is generated from data in `tools/`, using KiCad 10's Python (`C:/Program Files/KiCad/10.0/bin/python.exe`):

| File | Role |
|---|---|
| `wk3_design.py` | Every part, value, footprint and pin→net map, plus the custom MC3361 / MC1496 symbols |
| `wk3_layout.py` | Hand placement per sheet (1.27 mm grid units) |
| `wired.py` | Router, power symbols, labels, collision-free text placement, margins and paper size |
| `build_wired.py` | Builds the schematic through the KiCAD-MCP-Server backend (overwrites the `.kicad_sch` files) |
| `cosmetic_check.py` / `scene_png.py` | Dry-run text-collision report / debug render of a sheet |
| `pcb_wk3.py`, `pcb_parity.py` | Footprint sync, stack-up, outline, placement, net classes, schematic parity |
| `sch_geom.py` | Dumps schematic part / pin positions (`sch_geom.json`) as the placer's starting point |
| `place_wk3.py` | Floorplan zones, annealing placement, silkscreen reference placement |
| `route_wk3.py` | GND planes and fan-out vias, Freerouting run, GND pours, stitching vias |
| `wk3_rules.py` | Net classes and JLCPCB design rules in the project file |
| `sim_benches.py`, `ngspice.py` | KiCad simulation benches and their automated verification |
| `design_hpf.py`, `design_ladder.py`, `design_lobpf.py` | Fixed-filter design scripts (E-series values + Monte Carlo) |
| `lcsc_assign.py`, `lcsc_cost.py`, `bom_cost.py`, `check_netlist.py` | LCSC part numbers, LCSC order cost (hand assembly), JLC assembly cost, netlist cross-check |
| `design_consolidate.py`, `apply_values.py`, `jlc_dropins.py` | Filter re-fit on the shared value set, in-place value updates, basic-part drop-in search |
| `pa_retune.py`, `pa_robust.py` | PA bias / match search on the bench netlist, checked over the transistor's threshold spread |
| `pa_vds_tune.py` | PA re-tune on the whole-transmitter netlist: drain peak on a full pack, ≥ 1 W on the highest-threshold part, current on the lowest, harmonics |
| `eco_power_switch.py`, `eco_lo_balun.py`, `eco_battery.py`, `eco_pa_reg.py`, `eco_add.py` | In-place board changes (gate-switched power FET; LO balun + elliptic TX LPF; 18650 holders + cut-off + PA feedback; 7.0 V PA rail; generic add-parts): add parts, route only the new connections |
| `lcsc_sync.py` | Brings `lcsc_map.json`'s reference lists in line with the design after parts were added, removed or changed value |
| `lcsc_replace.py`, `set_part.py` | Swap an LCSC number everywhere / change one part's value and LCSC number everywhere: map, schematic, board, the JLCPCB plugin's database (it builds the BOM from that, not from the board), BOM and CPL |
| `bom_consistency.py` | Checks that the design data, `lcsc_map.json`, schematic, board, plugin database, BOM and CPL agree on every part |
| `jlc_sync.py` | After an ECO: brings the JLCPCB plugin's database, BOM and CPL in line with the board (regenerate the production files in the plugin before ordering) |
| `rebuild_sheets.py` | Rebuilds single schematic sheets in place after parts were added or removed |
| `eco_reroute.py` | Rips up and re-routes a few nets with everything else locked; drops stray vias, adds GND vias, re-places silkscreen references |
| `sim_plots.py` | Pictures of every simulation plus an overview of the radio (`sim/plots/`) |

To rebuild, delete the generated `*.kicad_sch`, `*.kicad_pro`, `*.kicad_pcb`, `WK3.kicad_sym` and `sym-lib-table`, then run:

```bash
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/build_wired.py
```

Then build the board with KiCad's Python. Close the project in KiCad first: an open session writes its old settings back over `WK-3.kicad_pro`.

```bash
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/sch_geom.py
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/pcb_wk3.py
JAVA="<path to java.exe>" "C:/Program Files/KiCad/10.0/bin/python.exe" tools/route_wk3.py <freerouting.jar> <work dir>
```

`pcb_wk3.py` syncs the footprints, places them and writes the rules. `route_wk3.py` does the fan-out, routing, pours and stitching, and prints any connections it leaves open.

Use the Freerouting jar from KiCad's Freerouting plugin (`Documents/KiCad/10.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/`, version 2.4.1) with Java 21 or newer. The native `freerouting-cli` 2.5.0 build crashes on this board.
