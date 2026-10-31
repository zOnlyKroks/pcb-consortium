"""One-off in-place patch of the user-edited D-V1.kicad_sch (do not regenerate: the sheet has hand edits).

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


# ---------------------------------------------------------------- sanity: leg A is where the generator put it
def pos(ref):
    a = find(by_ref(ref), "at"); return (round(float(a[1]) / U, 2), round(float(a[2]) / U, 2))
assert pos("C2") == (28.0, 14.0) and pos("U1") == (28.0, 24.0), "leg A moved, patch needs new coordinates"

# ---------------------------------------------------------------- 1. integrator cap and duty-limit attenuator
prop(by_ref("C2"), "Value")[2] = q("100pF")
remove_wire(34.0, 24.0, 40.0, 24.0)
ra1, ra2 = next_ref("R"), None
clone_sym("R1", ra1, 37.0, 24.0, value="220k")                                  # R1 is a rot-90 10k
ra2 = next_ref("R")
clone_sym("R2", ra2, 38.0, 29.0, value="100k")                                  # R2 is a vertical 15k
wire(34, 24, 35.5, 24); wire(38.5, 24, 40, 24)
wire(38, 27.5, 40, 27.5); junction(40, 27.5)
wire(38, 30.5, 38, 32)
label("VREF", 38, 32, 270)
label("ECMP_A", 40, 21, 90)
# the old E_A label sat at (37,24), now on the new resistor: move it onto the vertical from the integrator cap
for l in find_all(root, "label"):
    if unq(l[1]) == "E_A":
        at = find(l, "at"); at[1], at[2] = fmt(34 * U), fmt(19 * U)
for s in (ra1, ra2):
    prop(by_ref(s), "Footprint")

# ---------------------------------------------------------------- 2. VREF buffer
for l in find_all(root, "label"):
    at = find(l, "at")
    if unq(l[1]) == "VREF" and abs(float(at[1]) / U - 74.5) < .01 and abs(float(at[2]) / U - 70.0) < .01:
        l[1] = q("VREF_RAW")
ub = next_ref("U")
clone_sym("U7", ub, 84.0, 71.0)
wire(74.5, 70, 81, 70)
wire(87, 71, 89, 71); wire(89, 71, 89, 76); wire(89, 76, 79, 76); wire(79, 76, 79, 72); wire(79, 72, 81, 72)
label("VREF", 89, 71, 0)
wire(83, 68, 83, 66.5); pwr("#PWR045", 83, 66.5)
wire(83, 74, 83, 75.5); pwr("#PWR046", 83, 75.5)

# ---------------------------------------------------------------- 3. simulation-only anchors
# R12 (4 ohm sim load): its return goes to a 12 V reference instead of GND (hardware: speaker to GND)
for s in syms():
    if unq(prop(s, "Reference")[2]) == "#PWR027":
        root.remove(s)
label("LOAD_REF", 140, 46.5, 270)
v3 = next_ref("V")
clone_sym("V1", v3, 146.0, 50.0, value="12", simonly=True)
for p in find_all(by_ref(v3), "property"):
    if unq(p[1]) == "Sim.Params":
        p[2] = q("dc=12")
wire(146, 48, 146, 46.5); label("LOAD_REF", 146, 46.5, 90)
wire(146, 52, 146, 53.5); pwr("#PWR046", 146, 53.5)
rop = next_ref("R")
clone_sym("R12", rop, 123.0, 43.5, value="2k", simonly=True)
wire(123, 42, 123, 40); junction(123, 40)
wire(123, 45, 123, 46.5); label("LOAD_REF", 123, 46.5, 270)

# ---------------------------------------------------------------- 4. directives
for t in list(find_all(root, "text")):
    s = unq(t[1])
    if s.startswith(".tran"):
        t[1] = q(".tran 20n 4m")
    elif s.startswith(".ic") or s.startswith("(start the"):
        root.remove(t)
tx = copy.deepcopy(find_all(root, "text")[0]); new_uuids(tx)
tx[1] = q("Sim only: V3 + Rop (2k) anchor the DC operating point at 12 V; R12 returns to LOAD_REF. Plot V(/SPK)-V(/LOAD_REF).")
at = find(tx, "at"); at[1], at[2] = fmt(8.5 * U), fmt(88 * U)
root.insert(len(root) - 2, tx)

open(SCH, "w", encoding="utf-8").write(dump(tree) + "\n")
print("patched; new parts:", ra1, ra2, ub, v3, rop)
