# D-V1: analog class D amplifier (discrete, no class D IC)

Mono, bridge-tied load (BTL), closed loop, 24 V in, short-circuit protected. About 30 W at 0.14 % THD into 4 ohm
(simulated); it clips around 35-40 W because of the duty limit. Schematic only (no PCB yet). The speaker floats between
OUT_A and OUT_B (neither pin is GND, no DC-block cap).

## Architecture

```
AUDIO_IN -> 1 uF -> INAC -----------------------------------> channel B: integrator -> 2 PWM comparators -> IR2181 -> half bridge -> 15 uH -> OUT_B
                      \-> inverter (-1, around VREF) -> INV -> channel A: (same)                                                 -> 15 uH -> OUT_A
triangle (250 kHz, 1.8 Vpp around VREF) feeds all four PWM comparators
per channel: switch node -> 38.3k / 10k divider + 470 pF -> 15k -> integrator (68 pF)
             error -> 220k / 82k attenuator to VREF (ECMP_x) -> PWM comparators   (max duty ~87 %)
```

- **Triangle**: TLV3501 comparator with hysteresis + TLV9061 integrator, f = 1 / (1.6 Ri Ct) = 250 kHz.
- **Channels**: identical (error integrator + two TLV3501 comparators `e > tri` and `tri > e`). Channel A gets the
  inverted input, so the two legs swing in opposite directions.
- **Duty limit**: the error is attenuated (x0.27) before the comparators so the PWM never reaches 100 %: a bootstrapped
  half bridge needs the low side to conduct every cycle to refresh the bootstrap cap. 220k/82k so it does not load VREF.
- **VREF**: 10k/10k + 10 uF divider followed by a TLV9061 unity buffer.
- **Dead time**: IR2181 has none, so each comparator output goes through 2.2 k + 120 pF with a 1N4148W across the
  resistor (rising edge delayed ~150 ns, falling edge not). The 2N7002 pull-downs add ~30 pF per node, included.
- **Power stage**: IRFR3806 (60 V, TO-252) x4, bootstrapped high sides (1N4148W + 10 R + 1 uF).
- **Output filter** (sized for the bridge): per leg 15 uH + 220 nF to GND, 680 nF across the speaker, differential
  corner ~28 kHz (Butterworth into 4 ohm); plus **damping** per output: 6.8 ohm + 470 nF to GND.
  Gain is flat to 20 kHz (-0.2 dB). Carrier ripple at the speaker: 1-2 mV rms.
- **Rails**: 24 V in, L7812 -> 12 V (gate drive), L78L05 -> 5 V (logic).
- **Gain**: 22 V/V. 0.7 V peak in gives ~15.5 V peak across the speaker.

### Why the damping network matters
The 15 uH + 220 nF (per leg) common-mode LC has nothing across it (the speaker only loads the differential mode), and
the feedback is taken before the filter, so it cannot see it. Without damping the common-mode voltage at the outputs
rang up to -40 / +65 V in simulation, tripped the protection and, on a real board, would be audible as hash and
could kill the FETs. 6.8 ohm (about sqrt(L/C)) + 470 nF (2x the filter cap) damps it to a few mV.

## Short-circuit protection

- 25 mohm shunt in each low-side FET source (2512 package). The gate drivers keep COM on GND.
- One TLV3501 per shunt: `+` = SENSE through 10k (+470 pF filter), `-` = VTH (5 V divider 100k/5.1k = 0.243 V).
  Trip at roughly 0.267 V / 25 mohm = **~10 A** (filtered).
- The comparator outputs are diode-ORed into **FAULT**, which feeds back through 100k to both `+` inputs: a
  **latch** (reset by power-cycling).
- FAULT turns on four 2N7002 (Q5-Q8) that pull the HIN / LIN inputs of both IR2181 low: all four power FETs off.
- Simulated (netlist of this sheet, 0.7 V in, 4 ohm, short across the speaker terminals at the signal peak):
  latched **27 us** after the short starts, output 0.001 V afterwards, FAULT held at 4.5 V, shunt current 0.02 A,
  no false trip in normal running (FAULT max 0.04 V).
- A test is built into the sheet: a text block near the bottom shorts OUT_A to OUT_B at **t = 6.25 ms**
  (run 8 ms). Delete that text to remove it.

## Simulation inside KiCad

Every active part carries `Sim.*` fields pointing to `models/DV1_models.lib` (behavioural models: op amp,
comparator, IR2181-class driver with bootstrap and VBS UVLO, 60 V power MOSFET, 2N7002, regulators, 1N4148W,
differential probe). The sheet has a 24 V source, a 1 kHz 0.3 V sine, a 4 ohm load and these directives:

```
.tran 20n 8m uic
.options method=gear
.ic ...            (full start state: VREF, error amps, triangle, switch nodes, bootstrap caps, FAULT)
```

- **uic and .ic are required.** The error integrators are open loop at DC, so the solver's DC operating point either
  fails to converge or lands in a parked state. If KiCad shows garbage, open the simulation settings and tick
  *skip initial operating point* (UIC); the `.ic` text on the sheet then sets the start state.
- **`method=gear`** is needed too: the default trapezoidal integration rings numerically after every 24 V edge
  (alternating-sign spikes of 1-2 V on the shunt), which produced false protection trips and visible "noise".
- Plot **`V(/OUT_DIFF)`**: a sim-only probe (DIFFPROBE) that outputs OUT_A - OUT_B against GND. `/OUT_A` and
  `/OUT_B` alone are two sines around 12 V in antiphase.

`tools/check_sim.py [ampl] [f] [tstop] [rload]` exports the netlist with kicad-cli and runs it in KiCad's
ngspice.dll (short test stripped). `tools/protection_test.py [ampl]` runs the short-circuit test,
`tools/shoot_through.py` checks gate overlap. Run them one at a time (they share `sim/dv1.cir`).

| input | load | out peak | gain | THD 2..9 |
|---|---|---|---|---|
| 0.3 V, 1 kHz | 4 ohm | 6.6 V | 22.1 | 0.11 % |
| 0.3 V, 1 kHz | 8 ohm | 6.6 V | 22.1 | 0.07 % |
| 0.7 V, 1 kHz | 4 ohm | 15.5 V (~30 W) | 22.1 | 0.14 % |
| 0.3 V, 20 kHz | 4 ohm | 6.5 V | 21.6 | 0.61 % |

No shoot-through: both gate-source voltages never exceed 2 V together (worst case 1.7 V, the IRFR3806 threshold is
2-4 V: thin margin, tune the dead-time caps on the real board). The models are generic stand-ins with datasheet
headline numbers, not vendor models. The 40-90 A spikes the shunt shows are reverse recovery in a model with no wiring
inductance, so the 470 pF / 10k sense filter and the 10 A threshold need tuning on hardware.

## How the sheet was built

`tools/gen_sch.py` wrote the first (single channel) version. The sheet has since been edited in KiCad, so do NOT
re-run it. Later changes were applied in place by one-off scripts: `patch_startup.py` (duty limit, VREF buffer),
`patch_btl.py` (copy channel A to B on an A2 sheet, speaker block, probe), `patch_protect.py` (shunts, comparators,
latch, pull-downs), `patch_damping.py` (output damping, options, ic) and `patch_filter2.py` (filter values).

## Open points (check before ordering)

1. **TLV3501 SHDN polarity**: the KiCad symbol has a SHDN pin on the SOT-23-6; datasheet summaries I found
   contradict each other. All SHDN pins are on net `CMP_EN`, selected by solder jumper JP1 (+5 V or GND).
   Confirm in the TI datasheet before closing it. The pin numbering of the stock symbol also needs a check.
2. **No LCSC numbers yet.** MPNs are in the `MPN` fields: TLV9061IDBVR, TLV3501AIDBVR, IR2181S, IRFR3806TRPBF,
   2N7002, 1N4148W, L7812CV, L78L05ABUTR, SMBJ26CA. The 15 uH inductors need Isat >= 8 A (shielded); the 25 mohm
   shunts need 1 W (2512).
3. The protection is a latch with no indicator and no reset button (power-cycle). No thermal or DC-offset protection,
   no mute, no soft start (the VREF RC gives ~100 ms on real power-up).
4. Max duty 87 % clips at ~35-40 W. Raising the 82k attenuator resistor towards 100k gives more power but leaves less
   low-side time to refresh the bootstrap: only after checking start-up on the board.
5. DC offset at the speaker is set by the 0.1 % divider pairs (38.3k, 10k) of both channels: a few mV to ~80 mV.
6. Gate-drive current doubled with two channels: recheck the L7812 dissipation (about 0.5-1 W).
7. The sheet was checked by ERC (0 errors, 1 expected warning for the probe label) and by simulating its exported
   netlist, not by eye and not in the KiCad GUI.
