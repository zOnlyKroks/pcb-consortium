"""Make the boost + Cockcroft-Walton simulation reach ~400 V (in-place edit of gamma-spectrometer.kicad_sch).

Why 400 V did not come out: each CW stage (2 diodes + 2 capacitors) adds about one pump amplitude (the boost output, ~30 V), so the
2-stage ladder gave ~60 V.  Also the open-loop boost needs a regulation stand-in (zener clamp on the boost output, as a boost IC
with feedback would do), a small inductor and a duty cycle high enough to reach ~30 V.
  * L1 10 mH -> 100 uH, gate pulse 8.5 us of 10 us (50 ns edges)
  * D14 zener clamp (bv = 30 V) on the boost output
  * ladder extended from 2 to 12 stages (10 new stages in 5 rows below, chained with labels HVA_n / HVB_n), Rload1 + OUT moved to the end
"""
import copy, os, re, sys, uuid
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import q, find, find_all, unq, dump
SCH = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")
t = open(SCH, encoding="utf-8").read()


def closing(t, s):
    d, i = 0, s
    while True:
        c = t[i]
        if c == '"':
            i = t.index('"', i + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i
        i += 1


def indent(text, n=1):
    return "".join(("\t" * n + l) if l.strip() else l for l in text.splitlines(True))


def sym_block(t, ref):
    k = t.index('(property "Reference" "%s"' % ref)
    a = t.rindex("\n\t(symbol\n", 0, k) + 1
    return a, closing(t, a + 1) + 1


def remove_wire(t, p1, p2):
    k = t.index("(xy %s %s) (xy %s %s)" % (p1 + p2))
    a = t.rindex("\t(wire\n", 0, k)
    b = closing(t, a + 1) + 1
    return t[:a] + t[b:].lstrip("\n") if t[b] == "\n" else t[:a] + t[b:]


if "HVA_1" in t:
    print("already done"); sys.exit(0)
# ---- 1. parameters
t = t.replace('(property "Value" "10 mH"', '(property "Value" "100 uH"', 1)
assert "y1=0 y2=5 td=2n tr=2n tf=2n tw=5u per=10u" in t
t = t.replace("y1=0 y2=5 td=2n tr=2n tf=2n tw=5u per=10u", "y1=0 y2=5 td=2n tr=50n tf=50n tw=8.5u per=10u")
# ---- 2. take the load and the OUT label off row 0
t = remove_wire(t, ("346.71", "177.8"), ("363.22", "177.8"))
a, b = sym_block(t, "Rload1"); t = t[:a] + t[b:]
m = re.search(r'\t\(label "OUT"\n(?:\t\t[^\n]*\n)*?\t\)\n', t)
t = t[:m.start()] + t[m.end():]
for mm in re.finditer(r'\t\(symbol\n\t\t\(lib_id "power:GND"\)\n\t\t\(at 363\.22 ([\d.]+) \d+\)', t):
    a = mm.start(); b = closing(t, a + 1) + 1; t = t[:a] + t[b:]; break

t = remove_wire(t, ("245.11", "167.64"), ("252.73", "167.64"))
# ---- 3. new parts / wires / labels
import gen_sch as g
root_uuid = re.search(r'\(uuid "([0-9a-f-]+)"\)', t).group(1)
g.LIBS = {"lcsc_imported": os.path.join(PRJ, "libs", "lcsc", "symbols", "lcsc_imported.kicad_sym")}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/" + root_uuid
sh = g.Sheet()
sh.npwr, sh.nflg = 600, 600
DIODE = "lcsc_imported:UF4007_C84067"
DX = {"Sim.Library": "uf4007_spice.lib", "Sim.Name": "UF4007", "Sim.Device": "SUBCKT", "Sim.Pins": "1=A 2=K", "LCSC": "C84067", "Manufacturer": "星海"}
DFP, CFP = "lcsc_footprints:C84067_DO-41_BD2_4-L4_7-P8_70-D0_9-FD", "Capacitor_SMD:C_0603_1608Metric"
ncap, ndio = [14], [14]


def cap(x, y):
    ncap[0] += 1
    return sh.add("C%d" % ncap[0], "Device:C", x, y, rot=90, value="100 nF", fp=CFP, fields="T")


def dio(x, y, rot):
    ndio[0] += 1
    return sh.add("D%d" % ndio[0], DIODE, x, y, rot=rot, value="UF4007_C84067", fp=DFP, fields="R", extra=dict(DX))


def W(*p):
    sh.wire(*p)


def row(yt, la, lb, last=False):
    yb = round(yt + 10.16, 2)
    W((264.16, yt), (266.7, yt)); sh.label(la, (264.16, yt), 180)
    cap(270.51, yt); W((274.32, yt), (283.21, yt), (303.53, yt))
    cap(317.5, yt); W((303.53, yt), (313.69, yt)); W((321.31, yt), (325.12, yt), (346.71, yt))
    dio(283.21, yt + 5.08, 90); dio(303.53, yt + 5.08, 270); dio(325.12, yt + 5.08, 90); dio(346.71, yt + 5.08, 270)
    W((280.67, yb), (283.21, yb)); sh.label(lb, (280.67, yb), 180)
    cap(294.64, yb); W((283.21, yb), (290.83, yb)); W((298.45, yb), (303.53, yb), (325.12, yb), (335.28, yb))
    cap(339.09, yb); W((342.9, yb), (346.71, yb))
    return yb


# row 0 (the existing 2 stages) hands its two chain ends to row 1
sh.label("HVA_1", (346.71, 167.64), 0); sh.label("HVB_1", (346.71, 177.8), 0)
ys = [round(199.39 + 17.78 * r, 2) for r in range(5)]
for r, yt in enumerate(ys, start=1):
    yb = row(yt, "HVA_%d" % r, "HVB_%d" % r)
    if r < 5:
        sh.label("HVA_%d" % (r + 1), (346.71, yt), 0); sh.label("HVB_%d" % (r + 1), (346.71, yb), 0)
    else:
        W((346.71, yb), (363.22, yb)); sh.label("OUT", (363.22, yb), 0)
        sh.add("Rload1", "Device:R", 363.22, yb + 3.81, value="100M", fp="Resistor_SMD:R_0603_1608Metric", fields="R")
        W((363.22, yb + 7.62), (363.22, yb + 10.16)); sh.power("GND", (363.22, yb + 10.16))
# zener clamp on the boost output (stand-in for the boost IC's regulation): cathode on the rail D10 -> C10, anode GND
t_wire_fix = True
sh.add("D14", "Device:D_Zener", 248.92, 171.45, rot=270, value="30V", fp="Diode_SMD:D_SOD-123", fields="L",
       extra={"Sim.Device": "D", "Sim.Pins": "1=K 2=A", "Sim.Params": "bv=30 ibv=1m is=1n n=1.1 rs=1"})
W((248.92, 175.26), (248.92, 177.8)); sh.power("GND", (248.92, 177.8))
W((245.11, 167.64), (248.92, 167.64)); W((248.92, 167.64), (252.73, 167.64))
g.finish(sh)
pieces = []
for (x, y) in sh.junctions:
    pieces.append(dump(["junction", ["at", g.fmt(x), g.fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]]))
for w in sh.wires:
    pieces.append(dump(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]]))
for (name, x, y, ang) in sh.labels:
    just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
    pieces.append(dump(["label", q(name), ["at", g.fmt(x), g.fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                        ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()], ["uuid", q(g.uid())]]))
embedded = set(re.findall(r'\n\t\t\(symbol "([^"]+)"\n', t))
libsyms = ""
for lid in sh.lib_ids:
    if lid not in embedded:
        s = copy.deepcopy(g.flat_symbol(lid)); s[1] = q(lid)
        libsyms += indent(dump(s), 2).rstrip("\n") + "\n"
for key in sh.order:
    pieces.append(dump(g.sym_instance(sh, sh.parts[key])))
body = "".join(indent(p, 1).rstrip("\n") + "\n" for p in pieces)
if libsyms:
    le = closing(t, t.index("(lib_symbols"))
    t = t[:le] + "\n" + libsyms.rstrip("\n") + "\n\t" + t[le:]
m = re.search(r"\n\t\(sheet_instances", t)
t = t[:m.start() + 1] + body + t[m.start() + 1:]
open(SCH, "w", encoding="utf-8").write(t)
print("ladder: 12 stages; new parts", len(sh.order))
