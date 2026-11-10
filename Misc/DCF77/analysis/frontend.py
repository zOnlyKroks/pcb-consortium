"""Tuned front-end analysis for the DCF77 receiver.

Models the ferrite antenna as a parallel LC with finite Q, a coarse switched
C0G bank plus a varactor fine-tune, and checks that the tuning range covers
antenna/temperature tolerance with a step small enough relative to bandwidth.
All numbers are estimates; edit PARAMS and rerun.
"""
import math
from dataclasses import dataclass
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

F0 = 77_500.0
K_BOLTZ = 1.380649e-23
TEMP_K = 300.0


@dataclass
class Params:
    L: float = 10e-3          # antenna inductance
    Q0: float = 150.0         # unloaded antenna Q
    L_tol: float = 0.08       # rod permeability / winding tolerance (+/-)
    L_temp: float = 0.01      # temperature drift (+/-)
    c_stray: float = 25e-12   # antenna self-capacitance + PCB + LNA input
    c_fixed: float = 330e-12  # fixed C0G in parallel
    coarse: tuple = (10e-12, 15e-12, 27e-12, 56e-12)  # switched C0G bits
    # Toshiba 1SV281 fitted to 8.7 pF @ 4 V and C1V/C4V = 2.0 (distributor listings,
    # not the datasheet curve). Cj(V) = cj0 / (1+V/vj)**m. Same fit as models/dcf77_models.lib.
    cj0: float = 31.9e-12
    vj: float = 0.7
    m: float = 0.683
    c_ser: float = 1e-9    # series cap isolating varactor from the tank
    r_on: float = 150.0       # 74HC4066 on-resistance at 3.3 V (worst case, estimate)
    r_bias: float = 10e6      # varactor bias resistor
    dac_bits: int = 12
    vdd_dac: float = 3.3
    field_mv_m: float = 1.0   # DCF77 field strength, weak-signal case
    turns: int = 300
    mu_eff: float = 100.0
    rod_dia: float = 10e-3


P = Params()


def varactor_c(v: np.ndarray, p: Params = P) -> np.ndarray:
    cj = p.cj0 / (1 + v / p.vj) ** p.m
    return 1 / (1 / cj + 1 / p.c_ser)


def resonance(L: float, c_total: float) -> float:
    return 1 / (2 * math.pi * math.sqrt(L * c_total))


def needed_c(L: float, f: float = F0) -> float:
    return 1 / ((2 * math.pi * f) ** 2 * L)


def coarse_values(p: Params = P) -> np.ndarray:
    vals = []
    for code in range(2 ** len(p.coarse)):
        vals.append(sum(c for i, c in enumerate(p.coarse) if code >> i & 1))
    return np.sort(np.array(vals))


def main() -> None:
    p = P
    c_nom = needed_c(p.L)
    print(f"Nominal tank C for L={p.L*1e3:.1f} mH @ {F0/1e3:.1f} kHz: {c_nom*1e12:.0f} pF")

    v = np.linspace(0, p.vdd_dac, 2 ** p.dac_bits)
    cv = varactor_c(v)
    print(f"Varactor branch: {cv.min()*1e12:.1f}..{cv.max()*1e12:.1f} pF "
          f"(span {(cv.max()-cv.min())*1e12:.1f} pF) over 0..{p.vdd_dac} V")

    coarse = coarse_values()
    print(f"Coarse bank steps: {np.diff(coarse).min()*1e12:.0f} pF min step, "
          f"max {coarse.max()*1e12:.0f} pF")

    # Required C range over L tolerance + temperature
    l_lo = p.L * (1 - p.L_tol - p.L_temp)
    l_hi = p.L * (1 + p.L_tol + p.L_temp)
    c_req_max = needed_c(l_lo)
    c_req_min = needed_c(l_hi)
    print(f"Required total C over tolerance: {c_req_min*1e12:.0f}..{c_req_max*1e12:.0f} pF")

    base = p.c_fixed + p.c_stray
    c_min = base + coarse.min() + cv.min()
    c_max = base + coarse.max() + cv.max()
    print(f"Available total C: {c_min*1e12:.0f}..{c_max*1e12:.0f} pF")
    ok = c_min <= c_req_min and c_max >= c_req_max
    print("Coverage of tolerance range:", "OK" if ok else "INSUFFICIENT")

    # Gaps between coarse codes must be covered by the varactor span
    gap = np.diff(coarse).max()
    span = cv.max() - cv.min()
    print(f"Largest coarse step {gap*1e12:.0f} pF vs varactor span {span*1e12:.1f} pF -> "
          f"{'seamless' if span >= gap else 'GAP BETWEEN CODES'}")

    # Fine resolution vs bandwidth
    bw = F0 / p.Q0
    dc_step = np.min(np.abs(np.diff(cv)))
    df_step = F0 * dc_step / (2 * (base + coarse[len(coarse)//2] + cv.mean()))
    print(f"Tank bandwidth @ Q={p.Q0:.0f}: {bw:.0f} Hz; finest tuning step "
          f"{df_step*1e3:.2f} mHz -> far below BW/10 = {bw/10:.0f} Hz")

    # Impedance, noise, signal
    Rp = p.Q0 * 2 * math.pi * F0 * p.L
    vn_density = math.sqrt(4 * K_BOLTZ * TEMP_K * Rp)
    vn_total = vn_density * math.sqrt(bw * math.pi / 2)
    h = (p.field_mv_m * 1e-3) / 377.0
    b = 4e-7 * math.pi * h
    area = math.pi * (p.rod_dia / 2) ** 2
    emf = 2 * math.pi * F0 * p.turns * area * p.mu_eff * b
    v_res = emf * p.Q0
    print(f"Tank R_p at resonance: {Rp/1e3:.0f} kOhm, thermal noise density "
          f"{vn_density*1e9:.0f} nV/rtHz, integrated {vn_total*1e6:.2f} uV")
    print(f"Signal @ {p.field_mv_m} mV/m: EMF {emf*1e6:.2f} uV, across tank {v_res*1e6:.0f} uV, "
          f"SNR {20*math.log10(v_res/vn_total):.0f} dB")
    print(f"Required LNA input impedance >> {Rp/1e3:.0f} kOhm "
          f"(use CMOS/JFET input, input C < 5 pF)")

    # Q loss from the coarse-bank switches and the varactor bias resistor
    w0 = 2 * math.pi * F0
    g_tank = 1 / Rp
    g_bias = 0.96 / p.r_bias
    full = sum(p.coarse)
    mid = p.coarse[1] + p.coarse[2]
    for r_on in (75.0, p.r_on):
        for label, c_sw in (("mid code", mid), ("all caps on", full)):
            g_sw = (w0 * c_sw) ** 2 * r_on
            rp_eff = 1 / (g_tank + g_sw + g_bias)
            q_eff = rp_eff / (w0 * p.L)
            print(f"Ron {r_on:.0f} ohm, {label} ({c_sw*1e12:.0f} pF switched): "
                  f"Q {q_eff:.0f} (bw {F0/q_eff:.0f} Hz), SNR change {20*math.log10(q_eff/p.Q0):+.1f} dB")

    # Plots: tank response at nominal and +/-10% L, with tuning
    f = np.linspace(70e3, 85e3, 4000)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for dl, ls in ((-0.09, "--"), (0.0, "-"), (0.09, ":")):
        L = p.L * (1 + dl)
        # untuned
        c = c_nom
        w = 2 * math.pi * f
        y = 1 / Rp + 1j * (w * c - 1 / (w * L))
        ax[0].plot(f / 1e3, 20 * np.log10(np.abs(1 / y) / Rp), ls,
                   label=f"L {dl*100:+.0f}% untuned")
    ax[0].set_xlabel("kHz"); ax[0].set_ylabel("dB rel. peak"); ax[0].set_ylim(-40, 3)
    ax[0].axvline(77.5, color="k", lw=0.5); ax[0].legend(); ax[0].grid(alpha=0.3)
    ax[0].set_title("Untuned tank vs L tolerance")

    ax[1].plot(v, cv * 1e12)
    ax[1].set_xlabel("Varactor bias (V)"); ax[1].set_ylabel("pF")
    ax[1].set_title("Varactor branch capacitance"); ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(__file__.replace("frontend.py", "frontend.png"), dpi=130)


if __name__ == "__main__":
    main()
