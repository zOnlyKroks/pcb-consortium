"""Output filter re-sized for the bridge: 15 uH per leg, 680 nF differential, 220 nF CM + 6.8 ohm / 470 nF damping.
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



want = {"L1": ("33uH", "15uH"), "L3": ("33uH", "15uH"), "C12": ("2.2uF", "220nF"), "C37": ("2.2uF", "220nF"),
        "R47": ("3.9", "6.8"), "R48": ("3.9", "6.8"), "C43": ("4.7uF", "470nF"), "C44": ("4.7uF", "470nF"), "C38": ("1uF", "680nF")}
for ref, (old, new) in want.items():
    s = by_ref(ref); assert unq(prop(s, "Value")[2]) == old, (ref, unq(prop(s, "Value")[2]))
    prop(s, "Value")[2] = q(new)
for t in find_all(root, "text"):
    if unq(t[1]).startswith("Filter:") or unq(t[1]).startswith("4 ohm sim load"): pass
open(SCH, "w", encoding="utf-8").write(dump(tree) + chr(10))
print("filter re-sized")
