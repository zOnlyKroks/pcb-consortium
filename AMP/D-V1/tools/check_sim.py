"""Simulate the netlist KiCad exports from D-V1.kicad_sch and report gain / THD / DC.

    kicad-cli sch export netlist --format spice -o sim/dv1.cir D-V1.kicad_sch   (done here)
    python -I check_sim.py [ampl_V] [f_Hz] [tstop_s] [rload_ohm]
"""
import os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import numpy as np
from ngrun import run

KCLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def export():
    out = os.path.join(PRJ, "sim", "dv1.cir")
    subprocess.run([KCLI, "sch", "export", "netlist", "--format", "spice", "-o", out,
                    os.path.join(PRJ, "D-V1.kicad_sch")], check=True, capture_output=True)
    return open(out).read()


def main():
    ampl = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
    f = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    tstop = float(sys.argv[3]) if len(sys.argv) > 3 else 4e-3
    rload = sys.argv[4] if len(sys.argv) > 4 else "4"
    net = export()
    net = re.sub(r"(?im)^\.end\s*$", "", net)
    net = re.sub(r"(?im)^(SSHORT|VSHORT|\.model SWSHORT).*$", "", net)   # drop the short-circuit test
    net = re.sub(r"(?im)^\.tran.*$", ".tran 20n %g uic" % tstop, net)
    net = re.sub(r"SIN\( 0 [\d.]+ [\d.kK]+", "SIN( 0 %g %g" % (ampl, f), net)
    net = re.sub(r"(?m)^(R\d+ (?:/OUT_A /OUT_B|/OUT_B /OUT_A)) 4$", lambda m: m.group(1) + " " + rload, net)
    for pair in filter(None, os.environ.get("SUBST", "").split(";")):      # e.g. "/E_A 100p=/E_A 68p;..."
        a, b = pair.split("=")
        assert a in net, a
        net = net.replace(a, b)
    net += os.environ.get("EXTRA", "").replace(";", chr(10)) + chr(10)
    names = ["time", "v(/out_diff)", "v(/out_a)", "v(/out_b)", "v(/tri)", "v(/audio_in)"]
    vec, log = run(net, names)
    if not vec["time"]:
        print(log[-2000:]); sys.exit("no data")
    t = np.array(vec["time"]); d = np.array(vec["v(/out_diff)"])   # OUT_A - OUT_B (sim probe)
    n = max(1, int(round(tstop / 2 * f)))
    t1 = t[-1]; t0 = t1 - n / f
    tt = np.arange(t0, t1, 100e-9); y = np.interp(tt, t, d)
    F = np.fft.rfft(y - y.mean()) / len(y) * 2
    a1 = abs(F[n]); thd = np.sqrt(sum(abs(F[h * n]) ** 2 for h in range(2, 10))) / a1
    tri = np.array(vec["v(/tri)"]); m = t > tstop / 2
    x = tri[m] - 2.5; cr = t[m][1:][(x[:-1] < 0) & (x[1:] >= 0)]
    print("input %.3f V @ %g Hz, load %s ohm" % (ampl, f, rload))
    print("  out amplitude %.2f V  gain %.2f V/V  THD(2..9) %.3f %%  dc %.3f V" % (a1, a1 / ampl, thd * 100, y.mean()))
    F2 = np.fft.rfft(y - y.mean()) / len(y) * 2; fr = np.fft.rfftfreq(len(y), 100e-9); car = (fr > 150e3) & (fr < 400e3)
    print("  carrier ripple on the load: %.1f mV rms" % (np.sqrt((np.abs(F2[car]) ** 2).sum() / 2) * 1e3))
    print("  triangle %.2f Vpp  fsw %.1f kHz" % (tri[m].max() - tri[m].min(), 1 / np.mean(np.diff(cr)) / 1e3))


if __name__ == "__main__":
    main()
