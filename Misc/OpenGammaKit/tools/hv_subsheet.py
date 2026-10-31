"""Move the boost + 12-stage Cockcroft-Walton simulation circuit into its own sub-sheet (hv_multiplier.kicad_sch).
Everything is wired (one long ladder row, no label jumping).  In-place edit of gamma-spectrometer.kicad_sch: the simulation parts,
wires, junctions and labels are removed from the root sheet and a sheet symbol 'HV_multiplier' is added.  References are kept.
Run:  python -I tools/hv_subsheet.py   (KiCad's python)"""
import copy, os, re, sys, uuid
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import parse, q, find, find_all, unq, dump
ROOT = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")
SUB = os.path.join(PRJ, "hv_multiplier.kicad_sch")
t = open(ROOT, encoding="utf-8").read()
if "hv_multiplier.kicad_sch" in t:
    print("already a sub-sheet"); sys.exit(0)
tree = parse(t)[0]
BOXES = [(150, 150, 372, 206), (260, 206, 372, 287)]
inb = lambda x, y: any(a <= x <= c and b <= y <= d for a, b, c, d in BOXES)


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


LADDER = {"C%d" % i for i in range(11, 35)} | {"D9", "Rload1"} | {"D%d" % i for i in range(11, 35) if i != 14}
parts, pwr, boost_wires = {}, [], []
for s in find_all(tree, "symbol"):
    if find(s, "lib_id") is None:
        continue
    at = find(s, "at")
    x, y = float(at[1]), float(at[2])
    if not inb(x, y):
        continue
    pr = {unq(p[1]): unq(p[2]) for p in find_all(s, "property")}
    ref, lib, rot = pr["Reference"], unq(find(s, "lib_id")[1]), int(float(at[3]))
    if ref.startswith("#"):
        if x <= 253.0:
            pwr.append((lib.split(":")[1], x, y, rot))
        continue
    if ref in LADDER:
        continue
    fld = {}
    for p in find_all(s, "property"):
        if unq(p[1]) in ("Reference", "Value"):
            pa = find(p, "at"); ju = find(find(p, "effects"), "justify")
            fld[unq(p[1])] = (float(pa[1]), float(pa[2]), " ".join(str(j) for j in ju[1:]) if ju else None)
    parts[ref] = dict(lib=lib, x=x, y=y, rot=rot, props=pr, fld=fld)
for w in find_all(tree, "wire"):
    p = [(float(a[1]), float(a[2])) for a in find_all(find(w, "pts"), "xy")]
    if all(inb(*c) and c[0] <= 253.0 and c[1] >= 160 for c in p):
        boost_wires.append((p[0], p[1]))
print("boost parts:", sorted(parts), "| gnd symbols:", len(pwr), "| wires:", len(boost_wires))


# ---------------------------------------------------------------- remove from the root sheet
def cut(s, start_pat, hit):
    pos = 0
    while True:
        m = re.compile(start_pat).search(s, pos)
        if not m:
            return s
        a = m.start() + 1
        b = closing(s, a + 1) + 1
        if hit(s[a:b]):
            if b < len(s) and s[b] == "\n":
                b += 1
            s = s[:a] + s[b:]
            pos = a - 1
        else:
            pos = b


def at_of(blk):
    m = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", blk)
    return float(m.group(1)), float(m.group(2))


def wire_hit(blk):
    pts = [(float(u), float(v)) for u, v in re.findall(r"\(xy ([\d.\-]+) ([\d.\-]+)\)", blk)]
    return all(inb(*c) for c in pts)


t = cut(t, r'\n\t\(symbol\n\t\t\(lib_id "[^"]+"\)\n', lambda b: inb(*at_of(b)))
t = cut(t, r"\n\t\(wire\n", wire_hit)
t = cut(t, r"\n\t\(junction\n", lambda b: inb(*at_of(b)))
t = cut(t, r"\n\t\(label ", lambda b: inb(*at_of(b)))

# ---------------------------------------------------------------- the sub-sheet
import gen_sch as g
root_uuid = re.search(r'\(uuid "([0-9a-f-]+)"\)', t).group(1)
sheet_uuid = str(uuid.uuid4())
g.LIBS = {"lcsc_imported": os.path.join(PRJ, "libs", "lcsc", "symbols", "lcsc_imported.kicad_sym")}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/%s/%s" % (root_uuid, sheet_uuid)
sh = g.Sheet()
sh.npwr, sh.nflg = 700, 700
SKIP = {"Reference", "Value", "Footprint", "Datasheet", "Description"}
for ref, p in parts.items():
    extra = {k: v for k, v in p["props"].items() if k not in SKIP and not k.startswith("ki_")}
    mode = (p["fld"]["Reference"], p["fld"]["Value"])
    sh.add(ref, p["lib"], p["x"], p["y"], rot=p["rot"], value=p["props"].get("Value", ""), fp=p["props"].get("Footprint", ""), fields=mode, extra=extra)
for (a, b) in boost_wires:
    sh.wire(a, b)
for kind, x, y, rot in pwr:
    sh.power(kind, (x, y), rot)
sh.wire((223.52, 167.64), (223.52, 157.48), (266.7, 157.48), (266.7, 167.64))      # pump input from the switch node
DIODE = "lcsc_imported:UF4007_C84067"
DX = {"Sim.Library": "uf4007_spice.lib", "Sim.Name": "UF4007", "Sim.Device": "SUBCKT", "Sim.Pins": "1=A 2=K", "LCSC": "C84067", "Manufacturer": "星海"}
DFP, CFP = "lcsc_footprints:C84067_DO-41_BD2_4-L4_7-P8_70-D0_9-FD", "Capacitor_SMD:C_0603_1608Metric"
N, P, YT, YB, YD = 12, 41.91, 167.64, 177.8, 172.72
for k in range(1, N + 1):
    if k == 1:
        cp, cs, da, db = "C11", "C12", "D9", "D11"
    elif k == 2:
        cp, cs, da, db = "C13", "C14", "D12", "D13"
    else:
        j = k - 3; r, s = j // 2, j % 2
        cp, cs, da, db = "C%d" % (15 + 4 * r + s), "C%d" % (17 + 4 * r + s), "D%d" % (15 + 4 * r + 2 * s), "D%d" % (16 + 4 * r + 2 * s)
    o = P * (k - 1)
    xcp, xda, xdb, xcs = round(270.51 + o, 2), round(283.21 + o, 2), round(303.53 + o, 2), round(294.64 + o, 2)
    dx = 3.81 if k == 1 else 0.0       # keep the text clear of the pump wire coming down into C11
    sh.add(cp, "Device:C", xcp, YT, rot=90, value="100 nF", fp=CFP, fields=((xcp + dx, YT - 5.08, None), (xcp + dx, YT - 3.17, None)))
    sh.add(cs, "Device:C", xcs, YB, rot=90, value="100 nF", fp=CFP, fields=((xcs, YB + 3.81, None), (xcs, YB + 5.715, None)))
    sh.add(da, DIODE, xda, YD, rot=270, mirror="x", value="UF4007", fp=DFP, fields="R", extra=dict(DX))
    sh.add(db, DIODE, xdb, YD, rot=270, value="UF4007", fp=DFP, fields="R", extra=dict(DX))
    sh.wire((round(xcp + 3.81, 2), YT), (xda, YT), (xdb, YT))                       # pump chain
    if k < N:
        sh.wire((xdb, YT), (round(270.51 + o + P - 3.81, 2), YT))
    sh.wire((xda, YB), (round(xcs - 3.81, 2), YB))                                  # smoothing chain
    sh.wire((round(xcs + 3.81, 2), YB), (xdb, YB))
    if k < N:
        sh.wire((xdb, YB), (round(283.21 + o + P, 2), YB))
    if k == 1:
        sh.power("GND", (xda, YB))
xend = round(303.53 + P * (N - 1), 2)
xo = round(xend + 15.24, 2)
sh.wire((xend, YB), (xo, YB))
sh.label("OUT", (xo, YB), 0)
sh.add("Rload1", "Device:R", xo, round(YB + 3.81, 2), value="100M", fp="Resistor_SMD:R_0603_1608Metric", fields="R")
sh.wire((xo, YB), (xo, round(YB + 3.81 - 2.54 * 0 - 3.81, 2)))
sh.power("GND", (xo, round(YB + 7.62 + 2.54, 2)))
sh.wire((xo, round(YB + 7.62, 2)), (xo, round(YB + 7.62 + 2.54, 2)))
sh.text("Boost (L1, Q2, D10, C10, gate drive V3) + 12-stage Cockcroft-Walton ladder: ~400 V at OUT after ~20 ms (.tran 10m 60m is enough)", 160.0, 140.0, 1.7, True)
sh.text("D14 (30 V zener) stands in for the regulation a boost IC would do. Each stage = 2 x UF4007 + 2 x 100 nF and adds ~33 V; the pump is the switch node of Q2.", 160.0, 145.0, 1.27)
sh.text("Probe V(/HV_multiplier/OUT) in the simulator.", 160.0, 149.0, 1.27)
g.finish(sh)

lib = ["lib_symbols"]
for lid in sh.lib_ids:
    s = copy.deepcopy(g.flat_symbol(lid)); s[1] = q(lid); lib.append(s)
tbm = re.search(r"\n\t\(title_block\n.*?\n\t\)\n", t, re.S)
tb = re.sub(r'\(title "[^"]*"\)', '(title "HV multiplier (simulation)")', tbm.group(0).strip("\n"))
ver = re.search(r"\(version (\d+)\)", t).group(1)
head = ["kicad_sch", ["version", ver], ["generator", q("eeschema")], ["generator_version", q("10.0")], ["uuid", q(sheet_uuid)], ["paper", q("A1")]]
text = dump(head).rstrip("\n")
assert text.endswith(")")
text = text[:-1].rstrip("\n") + "\n" + tb + "\n"
body = [dump(lib)]
for (x, y) in sh.junctions:
    body.append(dump(["junction", ["at", g.fmt(x), g.fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]]))
for w in sh.wires:
    body.append(dump(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]]))
for (name, x, y, ang) in sh.labels:
    body.append(dump(["label", q(name), ["at", g.fmt(x), g.fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                      ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]], ["uuid", q(g.uid())]]))
for (s_, x, y, size, bold) in sh.texts:
    font = ["font", ["size", g.fmt(size), g.fmt(size)]]
    if bold:
        font += [["thickness", g.fmt(size * 0.2)], ["bold", "yes"]]
    body.append(dump(["text", q(s_), ["exclude_from_sim", "no"], ["at", g.fmt(x), g.fmt(y), "0"], ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(g.uid())]]))
for key in sh.order:
    body.append(dump(g.sym_instance(sh, sh.parts[key])))
text += "".join(indent(b, 1).rstrip("\n") + "\n" for b in body) + "\t(embedded_fonts no)\n)\n"
open(SUB, "w", encoding="utf-8").write(text)

# ---------------------------------------------------------------- sheet symbol on the root
node = ["sheet", ["at", "160.02", "165.1"], ["size", "50.8", "20.32"], ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
        ["fields_autoplaced", "yes"], ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0"]], ["uuid", q(sheet_uuid)],
        ["property", q("Sheetname"), q("HV_multiplier"), ["at", "160.02", "164.39", "0"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
        ["property", q("Sheetfile"), q("hv_multiplier.kicad_sch"), ["at", "160.02", "186.2", "0"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]],
        ["instances", ["project", q("gamma-spectrometer"), ["path", q("/" + root_uuid), ["page", q("2")]]]]]
m = re.search(r"\n\t\(sheet_instances", t)
t = t[:m.start() + 1] + indent(dump(node), 1).rstrip("\n") + "\n" + t[m.start() + 1:]
open(ROOT, "w", encoding="utf-8").write(t)
print("sub-sheet written:", len(sh.order), "parts,", len(sh.wires), "wires")
