"""Short-circuit protection: shunts in the low-side sources, latched comparators, pull-downs on HIN/LIN.
One-off in-place patch of the user-edited D-V1.kicad_sch (do not regenerate: the sheet has hand edits).

Adds: duty limit (220k/100k attenuator between the error amp and the PWM comparators, Cint 330p -> 100p),
a unity-gain VREF buffer, simulation-only DC anchors (V3 12 V, Rop 2k, load return), and removes uic / .ic.
Reason: bootstrapped half bridge needs a max duty (low side must refresh the bootstrap cap), and KiCad's GUI
runs a plain .tran so the circuit has to start from the DC operating point.
"""
import copy, os, sys, uuid
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from sexp import parse, dump, find, find_all, q, unq
SCH = os.path.join(HERE, "..", "D-V1.kicad_sch")
U = 2.54
tree = parse(open(SCH, encoding="utf-8").read())[0]
root = tree


def fmt(v):
    s = ("%.4f" % round(v, 4)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def prop(s, k):
    return next((p for p in find_all(s, "property") if unq(p[1]) == k), None)


def syms():
    return [s for s in find_all(root, "symbol") if find(s, "lib_id") is not None]


def by_ref(ref):
    return next(s for s in syms() if unq(prop(s, "Reference")[2]) == ref)


def new_uuids(node):
    for i, c in enumerate(node):
        if isinstance(c, list):
            if c and c[0] == "uuid":
                node[i] = ["uuid", q(str(uuid.uuid4()))]
            else:
                new_uuids(c)


def clone_sym(src_ref, ref, x, y, rot=None, value=None, simonly=False):
    s = copy.deepcopy(by_ref(src_ref))
    new_uuids(s)
    at = find(s, "at"); old = (float(at[1]), float(at[2]))
    at[1], at[2] = fmt(x * U), fmt(y * U)
    if rot is not None:
        at[3] = str(rot)
    for p in find_all(s, "property"):                      # move the (hidden or visible) fields with the part
        pa = find(p, "at")
        pa[1] = fmt(float(pa[1]) + x * U - old[0]); pa[2] = fmt(float(pa[2]) + y * U - old[1])
    prop(s, "Reference")[2] = q(ref)
    if value is not None:
        prop(s, "Value")[2] = q(value)
    for inst in find_all(find(s, "instances"), "project"):
        for pth in find_all(inst, "path"):
            find(pth, "reference")[1] = q(ref)
    if simonly:
        for key in ("in_bom", "on_board"):
            find(s, key)[1] = "no"
    root.insert(len(root) - 2, s)
    return s


def wire(x1, y1, x2, y2):
    w = ["wire", ["pts", ["xy", fmt(x1 * U), fmt(y1 * U)], ["xy", fmt(x2 * U), fmt(y2 * U)]],
         ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(str(uuid.uuid4()))]]
    root.insert(len(root) - 2, w)


def junction(x, y):
    root.insert(len(root) - 2, ["junction", ["at", fmt(x * U), fmt(y * U)], ["diameter", "0"],
                                ["color", "0", "0", "0", "0"], ["uuid", q(str(uuid.uuid4()))]])


def label(name, x, y, ang):
    l = copy.deepcopy(find_all(root, "label")[0]); new_uuids(l)
    l[1] = q(name); at = find(l, "at"); at[1], at[2], at[3] = fmt(x * U), fmt(y * U), str(ang)
    eff = find(l, "effects"); j = find(eff, "justify")
    j[:] = ["justify"] + (["right", "bottom"] if ang in (180, 270) else ["left", "bottom"])
    root.insert(len(root) - 2, l)


def remove_wire(x1, y1, x2, y2):
    for w in find_all(root, "wire"):
        p = find(w, "pts"); a = [round(float(c) / U, 2) for c in (p[1][1], p[1][2], p[2][1], p[2][2])]
        if a == [x1, y1, x2, y2] or a == [x2, y2, x1, y1]:
            root.remove(w); return
    raise SystemExit("wire not found %s" % [x1, y1, x2, y2])


def next_ref(prefix):
    n = max(int(unq(prop(s, "Reference")[2])[len(prefix):]) for s in syms()
            if unq(prop(s, "Reference")[2]).startswith(prefix) and unq(prop(s, "Reference")[2])[len(prefix):].isdigit())
    return "%s%d" % (prefix, n + 1)


def pwr(kind_src, x, y):
    ref = next_ref("#PWR")
    clone_sym(kind_src, ref, x, y)



# ---------------------------------------------------------------- short-circuit protection body
import importlib.util
def pos(ref):
    a = find(by_ref(ref), "at"); return (round(float(a[1]) / U, 2), round(float(a[2]) / U, 2))
assert pos("C2") == (28.0, 14.0) and pos("U1") == (28.0, 24.0), "channel A moved, patch needs new coordinates"


def gnd(x, y, d=1.5):
    wire(x, y, x, y + d); pwr("#PWR046", x, y + d)


def vcc(x, y, d=1.5):
    wire(x, y, x, y - d); pwr("#PWR045", x, y - d)


def setprop(ref, key, val):
    prop(by_ref(ref), key)[2] = q(val)


# ---------------------------------------------------------------- 0. lib symbol for the 2N7002 (G, S, D)
spec = importlib.util.spec_from_file_location("g", os.path.join(HERE, "gen_sch.py"))
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
if not any(unq(s[1]) == "Transistor_FET:Q_NMOS_GSD" for s in find_all(find(root, "lib_symbols"), "symbol")):
    ls = g.flat_symbol("Transistor_FET:Q_NMOS_GSD"); ls[1] = q("Transistor_FET:Q_NMOS_GSD")
    find(root, "lib_symbols").append(ls)

# ---------------------------------------------------------------- 1. shunts in the low-side sources
for X, ny in (("A", 37.0), ("B", 127.0)):
    for s in list(syms()):
        a = find(s, "at")
        if round(float(a[1]) / U, 2) == 84.0 and round(float(a[2]) / U, 2) == ny + 1.5 \
                and unq(prop(s, "Value")[2]) == "GND":
            root.remove(s)
    remove_wire(84.0, ny, 84.0, ny + 1.5)
    rs = next_ref("R")
    clone_sym("R2", rs, 84.0, ny + 2.5, value="25m")
    setprop(rs, "Footprint", "Resistor_SMD:R_2512_6332Metric")
    wire(84, ny, 84, ny + 1); gnd(84, ny + 4)
    wire(84, ny, 86, ny); label("SENSE_" + X, 86, ny, 0)
# driver-input nodes (junctions of the dead-time networks) as labelled nets
label("HIN_A", 60, 18, 0); label("LIN_A", 60, 32, 0); label("HIN_B", 60, 108, 0); label("LIN_B", 60, 122, 0)

# ---------------------------------------------------------------- 2. threshold divider
put = lambda s, x, y, size=1.27: None
ra, rb = next_ref("R"), None
clone_sym("R2", ra, 157.0, 100.0, value="100k")
rb = next_ref("R")
clone_sym("R2", rb, 157.0, 106.0, value="5.1k")
vcc(157, 98.5); wire(157, 101.5, 157, 104.5)
wire(157, 103, 159, 103); label("VTH", 159, 103, 0)
gnd(157, 107.5)

# ---------------------------------------------------------------- 3. one comparator per shunt, latched through FAULT
for X, cy in (("A", 102.0), ("B", 120.0)):
    cx = 180.0
    u = next_ref("U"); clone_sym("U2", u, cx, cy)
    n = (cx - 6, cy - 1)                                        # + input node
    wire(cx - 3, cy - 1, *n)
    rsr = next_ref("R"); clone_sym("R1", rsr, cx - 10.5, cy - 1, value="10k")
    wire(cx - 9, cy - 1, *n)
    wire(cx - 12, cy - 1, cx - 14, cy - 1); label("SENSE_" + X, cx - 14, cy - 1, 180)
    cf = next_ref("C"); clone_sym("C3", cf, cx - 9, cy + 2, value="470pF")
    wire(cx - 9, cy - 1, cx - 9, cy + 0.5); gnd(cx - 9, cy + 3.5)
    wire(*n, n[0], cy - 4)
    rf = next_ref("R"); clone_sym("R1", rf, cx - 7.5, cy - 4, value="100k")
    wire(cx - 6, cy - 4, *n)
    wire(cx - 9, cy - 4, cx - 11, cy - 4); label("FAULT", cx - 11, cy - 4, 180)
    wire(cx - 3, cy + 1, cx - 4.5, cy + 1); wire(cx - 4.5, cy + 1, cx - 4.5, cy + 5); label("VTH", cx - 4.5, cy + 5, 270)
    vcc(cx - 1, cy - 3); gnd(cx - 1, cy + 3)
    wire(cx, cy + 3, cx, cy + 4.5); label("CMP_EN", cx, cy + 4.5, 270)
    d = next_ref("D"); clone_sym("D1", d, cx + 6, cy, rot=180)
    wire(cx + 3, cy, cx + 4.5, cy)
    wire(cx + 7.5, cy, cx + 9, cy); label("FAULT", cx + 9, cy, 0)
    byp = next_ref("C"); clone_sym("C3", byp, cx + 5, cy - 6, value="100nF")
    vcc(cx + 5, cy - 7.5); gnd(cx + 5, cy - 4.5)
    # the diode must have its anode towards the comparator output
    ak = {pin_n: None for pin_n in ("1", "2")}
rpd = next_ref("R"); clone_sym("R2", rpd, 194.0, 108.0, value="100k")
wire(194, 106.5, 194, 105); label("FAULT", 194, 105, 90); gnd(194, 109.5)

# ---------------------------------------------------------------- 4. pull-down FETs on the four driver inputs
for k, net in enumerate(("HIN_A", "LIN_A", "HIN_B", "LIN_B")):
    qx, qy = 204.0 + 9 * k, 108.0
    qr = next_ref("Q"); s = clone_sym("Q1", qr, qx, qy, value="2N7002")
    find(s, "lib_id")[1] = q("Transistor_FET:Q_NMOS_GSD")
    setprop(qr, "Footprint", "Package_TO_SOT_SMD:SOT-23")
    for p in find_all(s, "property"):
        kname = unq(p[1])
        if kname == "Sim.Pins": p[2] = q("1=g 2=s 3=d")
        elif kname == "MPN": p[2] = q("2N7002")
    wire(qx - 2, qy, qx - 3.5, qy); label("FAULT", qx - 3.5, qy, 180)
    wire(qx + 1, qy + 2, qx + 1, qy + 3.5); pwr("#PWR046", qx + 1, qy + 3.5)
    wire(qx + 1, qy - 2, qx + 1, qy - 3.5); label(net, qx + 1, qy - 3.5, 90)

# ---------------------------------------------------------------- 5. texts, short-circuit test
def put_text(s, x, y):
    tx = copy.deepcopy(find_all(root, "text")[0]); new_uuids(tx)
    tx[1] = q(s); at = find(tx, "at"); at[1], at[2] = fmt(x * U), fmt(y * U)
    root.insert(len(root) - 2, tx)
put_text("Short-circuit protection: 25 mohm shunt in each low-side source, trips at ~10 A, latches (power-cycle to reset);", 150, 93)
put_text("FAULT turns on four 2N7002 that pull HIN/LIN of both drivers low: all four FETs off.", 150, 94.5)
put_text(".model SWSHORT SW(Ron=20m Roff=100Meg Vt=0.5 Vh=0.05)\\nVSHORT shortctl 0 PWL(0 0 6m 0 6.01m 1)\\nSSHORT /OUT_A /OUT_B shortctl 0 SWSHORT", 150, 133)
put_text("Sim: shorts the speaker output at t = 6 ms (run 8 ms). Delete this text to remove the test.", 150, 135)
for t in find_all(root, "text"):
    if unq(t[1]).startswith(".tran"):
        t[1] = q(".tran 20n 8m")
open(SCH, "w", encoding="utf-8").write(dump(tree) + chr(10))
print("protection patch written")
