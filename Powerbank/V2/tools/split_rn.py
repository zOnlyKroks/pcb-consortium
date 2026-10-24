"""One-off edit of the hand-tidied port_a.kicad_sch: the GPIO pull-down arrays RN201 / RN202 become single 10k
0603 resistors R209-R215 (same rows, same GND rail), so each one can sit right at its TPS25751D pin on the board.

R209 GPIO0, R210 GPIO1, R211 GPIO2, R212 GPIO3 (RN201 rows), R213 GPIO6, R214 GPIO7, R215 GPIO11 (RN202 rows).
Pin 1 = GND (left, joins the old array GND rail), pin 2 = GPIO (right, on the TPS25751D pin).
Then run copy_port_layout.py for port B.
"""
import copy, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq
import schlib
from copy_port_layout import ref_of, set_prop, pin_pos

A = os.path.join(schlib.PRJ, "port_a.kicad_sch")
NS = uuid.UUID("0c1d7e55-2b6a-4f1e-8e43-91d2a7c6b5f0")
ROWS = {"RN201": [("R209", "8"), ("R210", "7"), ("R211", "6"), ("R212", "5")],
        "RN202": [("R213", "8"), ("R214", "7"), ("R215", "6")]}


def main():
    t = parse(open(A, encoding="utf-8").read())[0]
    syms = {ref_of(s): s for s in find_all(t, "symbol")}
    if "RN201" not in syms:
        raise SystemExit("already split")
    tmpl = syms["R201"]
    n = [0]

    def fresh():
        n[0] += 1
        return q(str(uuid.uuid5(NS, "split:%d" % n[0])))
    new_items = []
    for rn, rows in ROWS.items():
        s = syms[rn]
        for ref, pin in rows:
            x2, y = pin_pos(s, pin)                          # GPIO end (TPS pin)
            r = copy.deepcopy(tmpl)
            at = find(r, "at")
            at[1], at[2], at[3] = schlib.fmt(x2 - 3.81), schlib.fmt(y), "90"   # rot 90: pin 1 left, pin 2 right
            r[r.index(find(r, "uuid"))] = ["uuid", fresh()]
            for p in find_all(r, "pin"):
                p[p.index(find(p, "uuid"))] = ["uuid", fresh()]
            set_prop(r, "Reference", ref)
            set_prop(r, "Value", "10k")
            set_prop(r, "Footprint", "Resistor_SMD:R_0603_1608Metric")
            set_prop(r, "LCSC Part #", "C25804")
            for p in find_all(r, "property"):                # fields: ref above, value below, others hidden
                k = unq(p[1])
                pa = find(p, "at")
                if k == "Reference":
                    pa[1], pa[2], pa[3] = schlib.fmt(x2 - 3.81), schlib.fmt(y - 1.27), "0"
                elif k == "Value":
                    pa[1], pa[2], pa[3] = schlib.fmt(x2 - 3.81), schlib.fmt(y + 1.27), "0"
                else:
                    pa[1], pa[2] = schlib.fmt(x2 - 3.81), schlib.fmt(y)
            path = find(find(find(r, "instances"), "project"), "path")
            path[path.index(find(path, "reference"))] = ["reference", q(ref)]
            assert pin_pos(r, "2") == (x2, y), (ref, pin_pos(r, "2"))
            x1 = pin_pos(r, "1")[0]
            new_items.append(r)
            gx = pin_pos(s, {"8": "1", "7": "2", "6": "3", "5": "4"}[pin])[0]      # old GND-side pin column
            new_items.append(["wire", ["pts", ["xy", schlib.fmt(x1), schlib.fmt(y)], ["xy", schlib.fmt(gx), schlib.fmt(y)]],
                              ["stroke", ["width", "0"], ["type", "default"]], ["uuid", fresh()]])
        t.remove(s)
    # the arrays' spare pins (R4 of RN202) had no-connect flags; drop the ones that no longer sit on a pin
    pins = {pin_pos(s, num) for s in find_all(t, "symbol") + [x for x in new_items if x[0] == "symbol"]
            for num in schlib.pins_of(schlib.flat_symbol(unq(find(s, "lib_id")[1])), int(find(s, "unit")[1]))}
    for nc in find_all(t, "no_connect"):
        a = find(nc, "at")
        if (float(a[1]), float(a[2])) not in pins:
            t.remove(nc)
    # junctions where a new wire meets the GND rail between two rail segments
    ends = {}
    for w in find_all(t, "wire") + [x for x in new_items if x[0] == "wire"]:
        pts = find(w, "pts")
        for e in pts[1:3]:
            k = (float(e[1]), float(e[2]))
            ends[k] = ends.get(k, 0) + 1
    have = {(float(find(j, "at")[1]), float(find(j, "at")[2])) for j in find_all(t, "junction")}
    for k, c in ends.items():
        if c >= 3 and k not in have:
            new_items.append(["junction", ["at", schlib.fmt(k[0]), schlib.fmt(k[1])], ["diameter", "0"],
                              ["color", "0", "0", "0", "0"], ["uuid", fresh()]])
    i = t.index(find_all(t, "symbol")[0])
    for it in new_items:
        t.insert(i, it)
    open(A, "w", encoding="utf-8").write(dump(t) + "\n")
    print("port A: RN201/RN202 -> R209..R215")


if __name__ == "__main__":
    main()
