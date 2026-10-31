"""Single-ended -> bridge-tied load (BTL): copies channel A to channel B (y +90, sheet A2), rebuilds the output
block (speaker between OUT_A and OUT_B, 1 uF differential cap), adds a sim-only OUT_DIFF probe.
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



# ---------------------------------------------------------------- BTL patch body (appended to the helper head)
def pos(ref):
    a = find(by_ref(ref), "at"); return (round(float(a[1]) / U, 2), round(float(a[2]) / U, 2))
assert pos("C2") == (28.0, 14.0) and pos("U1") == (28.0, 24.0), "channel A moved, patch needs new coordinates"
DY = 90.0
LEG = (4, 2, 113, 43)
OUTR = (118, 36, 162, 60)


def mm(node):
    return float(node) / U


def inr(x, y, r):
    return r[0] <= x <= r[2] and r[1] <= y <= r[3]


def refprefix(ref):
    return ref.rstrip("0123456789")


# paper: A2 gives room for the second channel under the first
find(root, "paper")[1] = q("A2")

# ---------------------------------------------------------------- 1. copy channel A -> channel B
RENAME = {"SW_A": "SW_B", "VB_A": "VB_B", "OUT_A": "OUT_B", "E_A": "E_B", "ECMP_A": "ECMP_B", "INV": "INAC"}
src_syms = []
for s in syms():
    a = find(s, "at"); x, y = mm(a[1]), mm(a[2])
    if inr(x, y, LEG):
        src_syms.append((unq(prop(s, "Reference")[2]), x, y))
src_wires = []
for w in find_all(root, "wire"):
    p = find(w, "pts")
    c = [mm(p[1][1]), mm(p[1][2]), mm(p[2][1]), mm(p[2][2])]
    if inr(c[0], c[1], LEG) and inr(c[2], c[3], LEG):
        src_wires.append(c)
src_labels = []
for l in find_all(root, "label"):
    a = find(l, "at"); x, y = mm(a[1]), mm(a[2])
    if inr(x, y, LEG):
        src_labels.append((unq(l[1]), x, y, int(float(a[3]))))
src_juncs = []
for j in find_all(root, "junction"):
    a = find(j, "at"); x, y = mm(a[1]), mm(a[2])
    if inr(x, y, LEG):
        src_juncs.append((x, y))
src_texts = []
for t in find_all(root, "text"):
    a = find(t, "at"); x, y = mm(a[1]), mm(a[2])
    if inr(x, y, LEG):
        src_texts.append((unq(t[1]), x, y, t))

newref = {}
for ref, x, y in src_syms:
    nr = next_ref(refprefix(ref))
    newref[ref] = nr
    clone_sym(ref, nr, x, y + DY)
for c in src_wires:
    wire(c[0], c[1] + DY, c[2], c[3] + DY)
for (x, y) in src_juncs:
    junction(x, y + DY)
for (name, x, y, ang) in src_labels:
    label(RENAME.get(name, name), x, y + DY, ang)
for (s, x, y, t) in src_texts:
    n = copy.deepcopy(t); new_uuids(n)
    n[1] = q(s.replace("Channel A", "Channel B"))
    at = find(n, "at"); at[2] = fmt((y + DY) * U)
    root.insert(len(root) - 2, n)
print("channel B: %d symbols, %d wires, %d labels" % (len(src_syms), len(src_wires), len(src_labels)))

# ---------------------------------------------------------------- 2. rebuild the output block
keep_j = None
for s in list(syms()):
    a = find(s, "at"); x, y = mm(a[1]), mm(a[2])
    if inr(x, y, OUTR):
        if unq(prop(s, "Value")[2]) == "SPEAKER":
            keep_j = s
        else:
            root.remove(s)
for kind in ("wire", "label", "junction", "text"):
    for n in list(find_all(root, kind)):
        if kind == "wire":
            p = find(n, "pts"); x, y = mm(p[1][1]), mm(p[1][2])
        else:
            a = find(n, "at"); x, y = mm(a[1]), mm(a[2])
        if inr(x, y, OUTR):
            root.remove(n)
assert keep_j is not None
jref = unq(prop(keep_j, "Reference")[2])
find(prop(keep_j, "Pinout"), "at")            # property exists
prop(keep_j, "Pinout")[2] = q("1 = OUT_A, 2 = OUT_B (bridge-tied: neither pin is GND)")
wire(120, 40, 150, 40); wire(150, 40, 150, 46); wire(150, 46, 153, 46); label("OUT_A", 120, 40, 180)
wire(120, 52, 148, 52); wire(148, 52, 148, 47); wire(148, 47, 153, 47); label("OUT_B", 120, 52, 180)
cd = next_ref("C")
clone_sym("C12", cd, 130.0, 46.0, value="1uF")
wire(130, 40, 130, 44.5); wire(130, 52, 130, 47.5); junction(130, 40); junction(130, 52)
rl = next_ref("R")
clone_sym("R2", rl, 140.0, 46.0, value="4", simonly=True)
wire(140, 40, 140, 44.5); wire(140, 52, 140, 47.5); junction(140, 40); junction(140, 52)

# ---------------------------------------------------------------- 3. sim-only differential probe: OUT_DIFF = OUT_A - OUT_B
pr = next_ref("U")
clone_sym("U10", pr, 146.0, 62.0, value="DIFFPROBE", simonly=True)
for p in find_all(by_ref(pr), "property"):
    k = unq(p[1])
    if k == "Sim.Name": p[2] = q("DIFFPROBE")
    elif k == "Sim.Pins": p[2] = q("1=out 3=inp 4=inn")
wire(143, 61, 141.5, 61); label("OUT_A", 141.5, 61, 180)
wire(143, 63, 141.5, 63); label("OUT_B", 141.5, 63, 180)
wire(149, 62, 151, 62); label("OUT_DIFF", 151, 62, 0)
wire(145, 59, 145, 57.5); pwr("#PWR045", 145, 57.5)
wire(145, 65, 145, 66.5); pwr("#PWR046", 145, 66.5)

# ---------------------------------------------------------------- 4. texts, title block
def put_text(s, x, y, size=1.27):
    tx = copy.deepcopy(find_all(root, "text")[0]); new_uuids(tx)
    tx[1] = q(s); at = find(tx, "at"); at[1], at[2] = fmt(x * U), fmt(y * U)
    root.insert(len(root) - 2, tx)
put_text("Speaker output (bridge-tied load)", 120, 36)
put_text("4 ohm sim load; plot V(/OUT_DIFF) = OUT_A - OUT_B (the bridge output seen from GND)", 120, 56)
put_text("Sim probe DIFFPROBE (not on the PCB)", 120, 59)
for t in list(find_all(root, "text")):
    s = unq(t[1])
    if s.startswith("Sim only:"):
        root.remove(t)
tb = find(root, "title_block")
for c in find_all(tb, "comment"):
    if c[1] == "2":
        c[2] = q("24 V, ~45 W into 4 ohm, bridge-tied load, closed loop from the switch nodes")
open(SCH, "w", encoding="utf-8").write(dump(tree) + chr(10))
print("BTL patch written; new refs:", cd, rl, pr, "speaker", jref)
