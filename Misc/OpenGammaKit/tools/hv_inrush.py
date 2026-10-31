"""hv_multiplier: limit the boost input current.  During start-up the ladder is empty, the inductor does not demagnetise (85 % duty) and the
simulated coil current ran up to ~9 A (saturates L1, overloads the SOT-23 FET, trips the PTC / USB).  R24 = 10 R (2512, 1 W) in series with the
5 V feed + C39 = 4.7 uF at the inductor: input current <= 0.5 A (USB), coil peak ~1 A, HV still 400 V after ~10 ms.
In-place text patch.  Run once with KiCad's python:  python -I tools/hv_inrush.py"""
import os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import q, dump
import gen_sch as g
HV = os.path.join(PRJ, "hv_multiplier.kicad_sch")
h = open(HV, encoding="utf-8").read()
if '"R24"' in h:
    print("already done"); sys.exit(0)
hv_uuid = re.search(r'\n\t\(uuid "([0-9a-f-]+)"\)', h).group(1)
root_uuid = re.search(r'\(path "/([0-9a-f-]+)/%s"' % hv_uuid, h).group(1)


def closing(s, k):
    d, i = 0, k
    while True:
        c = s[i]
        if c == '"':
            i = s.index('"', i + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i
        i += 1


def indent(text, n=1):
    return "".join(("\t" * n + l) if l.strip() else l for l in text.splitlines(True))


pat = "(xy 158.75 167.64) (xy 207.01 167.64)"
k = h.index(pat)
a = h.rindex("\t(wire\n", 0, k); b = closing(h, a + 1) + 1
if h[b] == "\n":
    b += 1
h = h[:a] + h[b:]
g.LIBS = {}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/%s/%s" % (root_uuid, hv_uuid)
sh = g.Sheet(); sh.npwr, sh.nflg = 960, 960
sh.add("R24", "Device:R", 181.61, 167.64, rot=90, value="10", fp="Resistor_SMD:R_2512_6332Metric", fields="T", extra={"LCSC": "C171290"})
sh.add("C39", "Device:C", 194.31, 171.45, value="4.7 uF", fp="Capacitor_SMD:C_0805_2012Metric", fields="R", extra={"LCSC": "C1746"})
sh.power("GND", (194.31, 175.26))
sh.wire((158.75, 167.64), (177.8, 167.64))
sh.wire((185.42, 167.64), (194.31, 167.64), (207.01, 167.64))
sh.text("R24 + C39: inrush limit (input current <= 0.5 A); without them the coil current runs up to several amps at start-up.", 160.0, 153.0, 1.27)
g.finish(sh)
body = []
for (x, y) in sh.junctions:
    body.append(dump(["junction", ["at", g.fmt(x), g.fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]]))
for w in sh.wires:
    body.append(dump(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]]))
for (s_, x, y, size, bold) in sh.texts:
    body.append(dump(["text", q(s_), ["exclude_from_sim", "no"], ["at", g.fmt(x), g.fmt(y), "0"],
                      ["effects", ["font", ["size", g.fmt(size), g.fmt(size)]], ["justify", "left", "bottom"]], ["uuid", q(g.uid())]]))
for key in sh.order:
    body.append(dump(g.sym_instance(sh, sh.parts[key])))
k = h.rstrip().rindex(")")
h = h[:k] + "".join(indent(b, 1).rstrip("\n") + "\n" for b in body) + h[k:]
open(HV, "w", encoding="utf-8").write(h)
print("inrush limit added")
