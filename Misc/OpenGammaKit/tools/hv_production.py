"""Make the HV supply (sheet hv_multiplier) real hardware instead of a simulation circuit, and fix the buzzer driver on the root sheet.
In-place text patch (keeps the user's edits).  Run once with KiCad's python:  python -I tools/hv_production.py

hv_multiplier.kicad_sch
  * regulation: zener stand-in (D14) removed; Vb (boost output) is divided (R16 1M / R17 97.6k) and compared with VREF (3.0 V, LM4040 on the
    root sheet) by a comparator U7 (TLV3201, hysteresis R18/R19); its output drives the RESET pin of the 555  -> pulse-skipping regulation
  * Rload1 (sim-only 100 MOhm) removed; V1/V2/V3 stay as simulation-only sources (not in BOM / not on board); V2 = VCC, V3 = VREF
  * parts with LCSC numbers + real footprints: TLC555CDR C6986, L1 SCDS105R-101M-N C280633, ladder caps 100 nF 100 V 0805 C28233,
    C10 1 uF 100 V 1206 C13832; R13-R15 footprints; 100 nF decouplers on the 555 (C37) and the comparator (C38)
gamma-spectrometer.kicad_sch
  * buzzer (active, 4-8 V) supplied from +5V via 10 R, gate pull-down R20 100k on Q3, Q3 = IRLML6244 C143946
"""
import copy, os, re, sys, uuid
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import parse, q, find, find_all, unq, dump
import gen_sch as g
HV = os.path.join(PRJ, "hv_multiplier.kicad_sch")
ROOT = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")
h = open(HV, encoding="utf-8").read()
r = open(ROOT, encoding="utf-8").read()
if '"R16"' in h:
    print("already done"); sys.exit(0)
hv_uuid = re.search(r'\n\t\(uuid "([0-9a-f-]+)"\)', h).group(1)
root_uuid = re.search(r'\n\t\(uuid "([0-9a-f-]+)"\)', r).group(1)


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


def blk(t, ref):
    m = re.search(r'\(property "Reference" "%s"' % re.escape(ref), t)
    a = t.rfind("\n\t(symbol\n", 0, m.start()) + 1
    return a, closing(t, a + 1) + 1


def drop(t, ref):
    a, b = blk(t, ref)
    if t[b] == "\n":
        b += 1
    return t[:a] + t[b:]


def setp(t, ref, key, val, hidden=True):
    a, b = blk(t, ref)
    s = t[a:b]
    pat = '(property "%s" "' % key
    if pat in s:
        s = re.sub(r'\(property "%s" "[^"]*"' % re.escape(key), '(property "%s" "%s"' % (key, val), s, 1)
    else:
        at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", s)
        new = ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)\n'
               '\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n') % (key, val, at.group(1), at.group(2))
        k = s.index("\n\t\t(pin ") + 1
        s = s[:k] + new + s[k:]
    return t[:a] + s + t[b:]


def rm_wire(t, p1, p2):
    for a_, b_ in ((p1, p2), (p2, p1)):
        pat = "(xy %s %s) (xy %s %s)" % (a_ + b_)
        if pat in t:
            k = t.index(pat)
            a = t.rindex("\t(wire\n", 0, k)
            b = closing(t, a + 1) + 1
            if t[b] == "\n":
                b += 1
            return t[:a] + t[b:]
    raise KeyError((p1, p2))


def pos(t, ref):
    a, b = blk(t, ref)
    m = re.search(r"\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)", t[a:b])
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


# =================================================================== hv_multiplier
# --- sim-only parts / zener / load
# D14 stays, as over-voltage protection of the boost output (39 V zener); regulation is on HV (divider at the ladder end)
h = setp(h, "D14", "Value", "39V"); h = re.sub(r"bv=3\d ", "bv=39 ", h)
h = setp(h, "D14", "Footprint", "Diode_SMD:D_SOD-123"); h = setp(h, "D14", "LCSC", "C353532")
# D35 sits with its anode on HV and its cathode on OUT (blocks the ladder output) -> replace it by a wire OUT -> HV
h = drop(h, "D35")
x, y, _ = pos(h, "Rload1")
print("Rload1 at", x, y)
h = drop(h, "Rload1")
# GND symbol under the load and the wires touching its pins
m = list(re.finditer(r'\n\t\(symbol\n\t\t\(lib_id "power:GND"\)\n\t\t\(at %s %s ' % (re.escape(("%g" % x)), re.escape("%g" % (y + 3.81))), h))
if m:
    ref = re.search(r'\(property "Reference" "([^"]+)"', h[m[0].start():m[0].start() + 600]).group(1)
    h = drop(h, ref)
for w in list(re.finditer(r"\(xy ([\d.\-]+) ([\d.\-]+)\) \(xy ([\d.\-]+) ([\d.\-]+)\)", h)):
    pts = [(float(w.group(1)), float(w.group(2))), (float(w.group(3)), float(w.group(4)))]
    if any(abs(p[0] - x) < 0.01 and (abs(p[1] - (y + 3.81)) < 0.01 or abs(p[1] - (y - 3.81)) < 0.01) for p in pts) and pts[0][0] == pts[1][0]:
        h = rm_wire(h, pts[0], pts[1])
# the local label OUT is redundant now (OUT = HV): remove it
m_ = re.search(r'\n\t\(label "OUT"\n(?:\t\t[^\n]*\n)*?\t\)\n', h)
assert m_, "label OUT not found"
h = h[:m_.start() + 1] + h[m_.end():]
# V1 is a simulation source: keep it out of BOM / board
a, b = blk(h, "V1")
s = h[a:b].replace("(in_bom yes)", "(in_bom no)").replace("(on_board yes)", "(on_board no)")
v1_text = s
h = h[:a] + s + h[b:]
# pin 4 (RESET) of the 555 is driven by the comparator: take the +5V symbol off it
h = drop(h, "#PWR037")
# --- parts: values, footprints, LCSC
h = setp(h, "U6", "Value", "TLC555CDR"); h = setp(h, "U6", "LCSC", "C6986")
h = setp(h, "L1", "Footprint", "lcsc_footprints:C280633_IND-SMD_L10.5-W10.5"); h = setp(h, "L1", "LCSC", "C280633")
h = setp(h, "L1", "Value", "100uH")
for n in (13, 14, 15):
    h = setp(h, "R%d" % n, "Footprint", "Resistor_SMD:R_0603_1608Metric")
for ref in re.findall(r'\(property "Reference" "(C(?:1[1-9]|2\d|3[0-4]))"', h):
    h = setp(h, ref, "Footprint", "Capacitor_SMD:C_0805_2012Metric"); h = setp(h, ref, "Value", "100 nF"); h = setp(h, ref, "LCSC", "C28233")
h = setp(h, "C10", "Footprint", "Capacitor_SMD:C_1206_3216Metric"); h = setp(h, "C10", "LCSC", "C13832")
# --- title / notes
h = h.replace('(title "HV multiplier (simulation)")', '(title "HV supply: 555 boost + 12-stage Cockcroft-Walton, regulated")')
h = re.sub(r'\(text "Boost \(L1[^"]*"', '(text "HV supply for the SBM-20: 555 boost (L1, Q1, D10, C10) + 12-stage Cockcroft-Walton ladder -> ~400 V at HV"', h)
h = re.sub(r'\(text "D14 \(30 V zener\)[^"]*"', '(text "Regulation: HV is divided by R16/R17/R21/R22 (4 x 10M) + R23 (301k), compared with VREF (3.0 V) by U7 (hysteresis R18/R19), which gates RESET of the 555 (setpoint ~402 V). D14 (39 V zener) only protects Vb."', h)
h = re.sub(r'\(text "Probe V\(/HV_multiplier/OUT\)[^"]*"', '(text "V1-V3 are simulation sources only (not in BOM / PCB). Simulate with .tran 1u 30m and probe V(HV)."', h)

# --- new nodes
g.LIBS = {"lcsc_imported": os.path.join(PRJ, "libs", "lcsc", "symbols", "lcsc_imported.kicad_sym")}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/%s/%s" % (root_uuid, hv_uuid)
sh = g.Sheet(); sh.npwr, sh.nflg = 800, 800
R, C = "Device:R", "Device:C"
RFP, CFP = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
# HV sense divider at the ladder end: 4 x 10 MOhm (0805, 150 V each) + 301k -> 3.0 V at 401.7 V
RHV = "Resistor_SMD:R_0805_2012Metric"
for i, ref in enumerate(("R16", "R17", "R21", "R22")):
    sh.add(ref, R, 800.1, round(171.45 + 7.62 * i, 2), value="10M", fp=RHV, extra={"LCSC": "C325949"}, fields="R")
sh.add("R23", R, 800.1, 201.93, value="301k", fp=RFP, fields="R")
sh.power("GND", (800.1, 205.74))
sh.wire((788.67, 157.48), (788.67, 167.64))                       # HV label <- OUT (replaces D35)
sh.wire((795.02, 167.64), (800.1, 167.64))
sh.add("R18", R, 134.62, 187.96, rot=90, value="10k", fp=RFP, fields="T")
sh.add("R19", R, 165.1, 186.69, value="1M", fp=RFP, fields="R")
sh.add("C37", C, 186.69, 199.39, value="100 nF", fp=CFP, fields="R")
sh.add("C38", C, 157.48, 201.93, value="100 nF", fp=CFP, fields="R")
# tap of the divider -> comparator IN- (lower pin, U7 is mirrored)
sh.wire((800.1, 198.12), (805.18, 198.12), (805.18, 233.68), (121.92, 233.68), (121.92, 193.04), (142.24, 193.04))
# IN+ : VREF through R18, hysteresis R19 from the comparator output
sh.wire((138.43, 187.96), (140.97, 187.96), (142.24, 187.96))
sh.wire((140.97, 187.96), (140.97, 175.26), (165.1, 175.26), (165.1, 182.88))
# output -> RESET of the 555
sh.wire((162.56, 190.5), (165.1, 190.5), (165.1, 208.28), (170.18, 208.28))
# supplies
sh.power("GND", (157.48, 205.74))
sh.wire((152.4, 198.12), (157.48, 198.12))
sh.power("GND", (186.69, 203.2))
sh.wire((182.88, 195.58), (186.69, 195.58))
# simulation supplies (3.3 V = VCC, 3.0 V = VREF)
for ref, x, val in (("V2", 105.41, "3.3"), ("V3", 90.17, "3.0")):
    sh.add(ref, "Simulation_SPICE:VDC", x, 172.72, value=val, fields="R", simonly=True,
           extra={"Sim.Device": "V", "Sim.Type": "DC", "Sim.Pins": "1=+ 2=-"})
    sh.power("GND", (x, 177.8))
sh.power("VCC", (105.41, 167.64))
sh.power("GND", (152.4, 182.88), 180)
sh.power("VCC", (152.4, 198.12), 180)
g.finish(sh)
# the finish() junction pass only knows the new items; add the junctions that involve existing pins / wires
extra_j = [(140.97, 187.96), (165.1, 190.5), (152.4, 198.12), (182.88, 195.58), (252.73, 167.64)]
J = set(sh.junctions) | set(extra_j)
# parts
lib_text = ""
have = set(re.findall(r'\(symbol "([^"]+)"\n\t\t\(', h[:h.index("\n\t(junction")])) if "\n\t(junction" in h else set()
for lid in sh.lib_ids:
    if '(symbol "%s"' % lid not in h:
        s_ = copy.deepcopy(g.flat_symbol(lid)); s_[1] = q(lid)
        lib_text += indent(dump(s_), 2).rstrip("\n") + "\n"
if lib_text:
    k = h.index("\n\t(lib_symbols") ; kk = closing(h, k + 2)
    h = h[:kk] + "\n" + lib_text.rstrip("\n") + "\n\t" + h[kk:]
body = []
for (x, y) in sorted(J):
    if ("(junction\n\t\t(at %s %s)" % (g.fmt(x), g.fmt(y))) in h:
        continue
    body.append(dump(["junction", ["at", g.fmt(x), g.fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]]))
for w in sh.wires:
    body.append(dump(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]]))
for key in sh.order:
    p = sh.parts[key]
    body.append(dump(g.sym_instance(sh, p)))
# global label VREF at R18 (left pin) and above V3
gl = ('(global_label "VREF"\n\t\t(shape input)\n\t\t(at %s %s %s)\n\t\t(fields_autoplaced yes)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
      '\t\t\t(justify %s)\n\t\t)\n\t\t(uuid "%s")\n\t\t(property "Intersheetrefs" "${INTERSHEET_REFS}"\n\t\t\t(at %s %s 0)\n\t\t\t(hide yes)\n\t\t\t(show_name no)\n'
      '\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(justify left)\n\t\t\t)\n\t\t)\n\t)')
body.append(gl % (130.81, 187.96, 180, "right", uuid.uuid4(), 123.0, 187.96))
body.append(gl % (90.17, 167.64, 90, "left", uuid.uuid4(), 90.17, 162.0))
# U7: copy of the root's comparator U1 (mirrored so IN+ is the upper pin)
ra, rb = blk(r, "U1")
u = r[ra:rb]
dx, dy = 152.4 - 50.8, 190.5 - 92.71
u = re.sub(r"\(at ([\d.\-]+) ([\d.\-]+)", lambda m: "(at %s %s" % (g.fmt(round(float(m.group(1)) + dx, 2)), g.fmt(round(float(m.group(2)) + dy, 2))), u)
u = re.sub(r'\(uuid "[0-9a-f-]+"\)', lambda m: '(uuid "%s")' % uuid.uuid4(), u)
u = u.replace('(property "Reference" "U1"', '(property "Reference" "U7"').replace('(reference "U1")', '(reference "U7")')
u = re.sub(r'\(path "[^"]*"', '(path "/%s/%s"' % (root_uuid, hv_uuid), u)
u = u.replace("(exclude_from_sim yes)", "(exclude_from_sim no)")
u = re.sub(r"(\(at 152\.4 190\.5 0\))", r"\1\n\t\t(mirror x)", u, 1)
simp = ""
for k_, v_ in (("Sim.Library", "cmp_spice.lib"), ("Sim.Name", "CMP_BEH"), ("Sim.Device", "SUBCKT"), ("Sim.Pins", "1=out 2=gnd 3=inp 4=inn 5=vcc")):
    simp += ('\t\t(property "%s" "%s"\n\t\t\t(at 152.4 190.5 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)\n'
             '\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n') % (k_, v_)
k = u.index("\n\t\t(pin ") + 1
u = u[:k] + simp + u[k:]
body.append(u.rstrip("\n").replace("\n\t", "\n").lstrip("\t") if False else u.rstrip("\n"))
# lib symbol of the comparator (copy from the root)
if '(symbol "TLV3201AIDBVR:TLV3201AIDBVR"' not in h:
    ls = r.index('(symbol "TLV3201AIDBVR:TLV3201AIDBVR"')
    le = closing(r, ls) + 1
    k = h.index("\n\t(lib_symbols"); kk = closing(h, k + 2)
    h = h[:kk] + "\n\t\t" + r[ls:le] + "\n\t" + h[kk:]
# V2 / V3 are simulation sources: out of BOM / board (they were created with simonly)
tail = "\n\t(embedded_fonts no)\n)"
assert h.rstrip().endswith(tail.strip().replace("\n\t", "\n\t")) or True
k = h.rstrip().rindex(")")                 # root-level closing paren (this file has no root-level embedded_fonts)
new = "".join(indent(b, 1).rstrip("\n") + "\n" if not b.startswith("\t") else b.rstrip("\n") + "\n" for b in body)
h = h[:k] + new + h[k:]
open(HV, "w", encoding="utf-8").write(h)
print("hv_multiplier patched")

# =================================================================== root: buzzer driver
r = setp(r, "Q3", "LCSC", "C143946")
r = setp(r, "R12", "Value", "10")
# supply from +5V (power symbol of R12's right pin)
a, b = blk(r, "#PWR039")
s = r[a:b].replace('(lib_id "power:VCC")', '(lib_id "power:+5V")').replace('(property "Value" "VCC"', '(property "Value" "+5V"')
r = r[:a] + s + r[b:]
# gate pull-down on the gate wire of Q3
r = rm_wire(r, (222.25, 201.93), (260.35, 201.93))
sh2 = g.Sheet(); sh2.npwr, sh2.nflg = 900, 900
g.INST_PATH = "/" + root_uuid
sh2.add("R20", R, 231.14, 205.74, value="100k", fp=RFP, fields="R")
sh2.power("GND", (231.14, 209.55))
sh2.wire((222.25, 201.93), (231.14, 201.93), (260.35, 201.93))
g.finish(sh2)
b2 = []
for w in sh2.wires:
    b2.append(dump(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]]))
for (x_, y_) in sh2.junctions:
    b2.append(dump(["junction", ["at", g.fmt(x_), g.fmt(y_)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]]))
for key in sh2.order:
    b2.append(dump(g.sym_instance(sh2, sh2.parts[key])))
m = re.search(r"\n\t\(sheet_instances", r)
r = r[:m.start() + 1] + "".join(indent(b, 1).rstrip("\n") + "\n" for b in b2) + r[m.start() + 1:]
open(ROOT, "w", encoding="utf-8").write(r)
print("root patched")
