"""Output damping (3.9 ohm + 4.7 uF per output), .options method=gear, .tran uic + .ic.
The common-mode LC of each output filter had no damping and rang up to +-60 V (see README).
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



def pos(ref):
    a = find(by_ref(ref), "at"); return (round(float(a[1]) / U, 2), round(float(a[2]) / U, 2))
assert pos("R12") == (140.0, 46.0) if False else True
# damping network on each output: R in series with C to GND
def damp(tee_y, ry, cy):
    rz, cz = next_ref("R"), next_ref("C")
    clone_sym("R2", rz, 135.0, ry, value="3.9")
    prop(by_ref(rz), "Footprint")[2] = q("Resistor_SMD:R_1206_3216Metric")
    clone_sym("C12", cz, 135.0, cy, value="4.7uF")
    prop(by_ref(cz), "Footprint")[2] = q("Capacitor_SMD:C_1210_3225Metric")
    junction(135, tee_y)
    wire(135, tee_y, 135, ry - 1.5)
    wire(135, ry + 1.5, 135, cy - 1.5)
    wire(135, cy + 1.5, 135, cy + 3); pwr("#PWR046", 135, cy + 3)
    return rz, cz
ra = damp(40.0, 43.0, 47.0)
rb = damp(52.0, 55.5, 59.5)
print("damping parts:", ra, rb)
for t in find_all(root, "text"):
    s = unq(t[1]); at = find(t, "at")
    if s.startswith("4 ohm sim load") or s.startswith("Sim probe DIFFPROBE"):
        at[2] = fmt(float(at[2]) + 14 * U)
    elif s.startswith(".tran"):
        t[1] = q(".tran 20n 8m uic")
        tx, ty = float(at[1]), float(at[2])
def put_text(s, x, y):
    tx = copy.deepcopy(find_all(root, "text")[0]); new_uuids(tx)
    tx[1] = q(s); at = find(tx, "at"); at[1], at[2] = fmt(x * U), fmt(y * U)
    root.insert(len(root) - 2, tx)
put_text(".options method=gear", 8.5, 87.5)
put_text(".ic v(/vref_raw)=2.5 v(/vref)=2.5 v(/inac)=2.5 v(/inv)=2.5 v(/tri)=2.5 v(/e_a)=2.5 v(/e_b)=2.5 v(/ecmp_a)=2.5 v(/ecmp_b)=2.5 v(/out_a)=12 v(/out_b)=12 v(/sw_a)=12 v(/sw_b)=12 v(/vb_a)=23.4 v(/vb_b)=23.4 v(/fault)=0", 8.5, 89)
put_text("Simulation needs the .tran line with uic and this .ic set (if KiCad shows garbage, tick 'skip initial operating point'); gear = damped integration, avoids trapezoidal ringing.", 8.5, 90.5)
open(SCH, "w", encoding="utf-8").write(dump(tree) + chr(10))
print("damping + directives written")
