# DCF77 Receiver (self-tuning)

An open-source receiver for the 77.5 kHz DCF77 time signal. Only the ferrite antenna is external, and the board tunes its resonance itself, so a home-wound antenna does not have to hit its inductance exactly. An STM32F103 samples the amplified carrier, demodulates it with a Goertzel filter and decodes the time. The result goes out over USB (virtual COM port), I²C, SPI or UART, with a one-pulse-per-second TICK and the raw pulse.

```
ferrite rod ──┬── tank node ── TLV9062 (x11) ── TLV9062 (x9.2) ── MCU ADC
 (L ≈ 10 mH)  │
              ├── 330 pF fixed C0G
              ├── 10/15/27/56 pF C0G bank via 74HC4066   coarse, 16 steps
              ├── 1SV281 varactor ← MCP4725 DAC          fine
              └── 2.2 pF ← MCU PWM tone                  calibration without a signal
```

**Tuning loop:** sweep the 16 bank codes, climb on the DAC to the carrier peak, then track. Re-sweep on signal loss.

## How far can the antenna be off?

The tuner covers a total tank capacitance of 365–494 pF: 330 pF fixed, 25 pF assumed stray, 0–108 pF bank and about 10–31 pF varactor. At 77.5 kHz that means:

| | Inductance | Versus 10 mH |
|---|---|---|
| Lowest the tuner can reach | 8.5 mH | −15 % |
| Highest the tuner can reach | 11.6 mH | +16 % |

- **Winding:** aim for 10 mH. Inductance goes with turns squared, so the turn count can be off by about ±6 %.
- **Temperature:** drift of about ±1 % uses part of the margin, so staying within 9–11 mH keeps it.
- **Self-capacitance:** the 25 pF stray figure includes the winding's own capacitance. A winding with much more (typically a multi-layer one) shifts the window down. Measure the finished antenna if you can.
- **Q:** the analysis assumes Q = 150. The switches and bias resistor reduce it to 110–135, giving 570–710 Hz bandwidth, enough for the 100/200 ms pulses. The tuner only fixes the frequency, so a low-Q winding still loses signal.
- **Resolution:** the varactor span (21 pF) is larger than the largest coarse step (10 pF), so there are no gaps. One DAC step moves the resonance by about 0.1 Hz.

These figures come from `analysis/frontend.py` (`python3 -I analysis/frontend.py`). The varactor curve is fitted to the 1SV281's distributor figures (8.7 pF at 4 V, ratio 2.0), not its datasheet curve, so treat the window edges as roughly ±1 % uncertain.

## Simulation

The Analog sheet simulates in KiCad (Inspect > Simulator), with models in `models/`. Use `.tran 0.5u 200m` without `uic`. The antenna carrier is keyed like DCF77 (`tred` on J1: 100m for a 0, 200m for a 1). The MCU and power sheets are excluded.
