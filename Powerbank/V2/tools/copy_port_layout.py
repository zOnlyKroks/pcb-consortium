"""Rebuild port_b.kicad_sch from the (hand-tidied) port_a.kicad_sch layout.

* refs 2xx -> 3xx, net labels *_A -> *_B, note texts Port A / 0x20 / U2xx -> Port B / 0x21 / U3xx
* port B's own symbol UUIDs, pin UUIDs and instance paths are kept (the PCB footprints stay linked)
* power / flag symbols get fresh #PWR / #FLG numbers and UUIDs; wires, labels, junctions get fresh UUIDs
* the one real difference: ADCIN1 (U301 pin 2) goes to GND instead of LDO_3V3 (I2Ct address 0x21).
  The wire chain from that pin to the LDO_3V3 net is removed and a GND symbol is put on the pin.

Run after editing port A in KiCad, then check_netlist.py + ERC:
    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/copy_port_layout.py
"""
import copy, os, re, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq
import schlib

PRJ = schlib.PRJ
A, B = os.path.join(PRJ, "port_a.kicad_sch"), os.path.join(PRJ, "port_b.kicad_sch")
NS = uuid.UUID("5d0b7a7e-3c19-4f0e-9b61-0c2f8e4d1a77")


def ref_of(s):
    return next(unq(p[2]) for p in find_all(s, "property") if unq(p[1]) == "Reference")


def set_prop(s, key, val):
    for p in find_all(s, "property"):
        if unq(p[1]) == key:
            p[2] = q(val)


def pin_pos(s, num):
    at, m = find(s, "at"), find(s, "mirror")
    sym = schlib.flat_symbol(unq(find(s, "lib_id")[1]))
    lx, ly = schlib.pins_of(sym, int(find(s, "unit")[1]))[num]
    p = dict(x=float(at[1]), y=float(at[2]), rot=int(float(at[3])), mirror=m[1] if m else None)
    return schlib.xform(p, lx, -ly)


def wire_pts(w):
    pts = find(w, "pts")
    return (float(pts[1][1]), float(pts[1][2])), (float(pts[2][1]), float(pts[2][2]))


def other_power_refs():
    used = set()
    for f in ("battery.kicad_sch", "port_a.kicad_sch", "system.kicad_sch"):
        t = parse(open(os.path.join(PRJ, f), encoding="utf-8").read())[0]
        used |= {ref_of(s) for s in find_all(t, "symbol") if ref_of(s).startswith("#")}
    return used


def rename_text(s):
    s = re.sub(r"\b([A-Z]+)2(\d\d)\b", r"\g<1>3\2", s)
    return (s.replace("Port A", "Port B").replace("port A", "port B").replace("0x20", "0x21")
             .replace("ADCIN1 = LDO_3V3", "ADCIN1 = GND"))


def main():
    ta = parse(open(A, encoding="utf-8").read())[0]
    tb = parse(open(B, encoding="utf-8").read())[0]
    bsyms = {ref_of(s): s for s in find_all(tb, "symbol")}
    bpath = next(unq(find(find(find(s, "instances"), "project"), "path")[1]) for s in bsyms.values())
    project = unq(find(find(next(iter(bsyms.values())), "instances"), "project")[1])
    out = copy.deepcopy(ta)
    out[out.index(find(out, "uuid"))] = ["uuid", find(tb, "uuid")[1]]
    n = [0]

    def fresh():
        n[0] += 1
        return q(str(uuid.uuid5(NS, "port_b:%d" % n[0])))

    used = other_power_refs()
    counters = {"#PWR": 0, "#FLG": 0}

    def next_power(prefix):
        while True:
            counters[prefix] += 1
            r = "%s%03d" % (prefix, counters[prefix])
            if r not in used:
                used.add(r)
                return r

    for item in out:
        if not isinstance(item, list):
            continue
        kind = item[0]
        if kind == "symbol":
            ra = ref_of(item)
            if ra.startswith("#"):
                rb = next_power(ra[:4])
                item[item.index(find(item, "uuid"))] = ["uuid", fresh()]
                for p in find_all(item, "pin"):
                    p[p.index(find(p, "uuid"))] = ["uuid", fresh()]
            else:
                rb = rename_text(ra)
                src = bsyms.get(rb)
                if src is None:                      # part new on port A: fresh ids for its port-B twin
                    item[item.index(find(item, "uuid"))] = ["uuid", q(str(uuid.uuid5(NS, "sym:" + rb)))]
                    for p in find_all(item, "pin"):
                        p[p.index(find(p, "uuid"))] = ["uuid", q(str(uuid.uuid5(NS, "pin:%s:%s" % (rb, unq(p[1])))))]
                else:
                    item[item.index(find(item, "uuid"))] = copy.deepcopy(find(src, "uuid"))
                    buuid = {unq(p[1]): find(p, "uuid") for p in find_all(src, "pin")}
                    for p in find_all(item, "pin"):
                        p[p.index(find(p, "uuid"))] = copy.deepcopy(buuid[unq(p[1])])
            set_prop(item, "Reference", rb)
            unit = find(item, "unit")[1]
            item[item.index(find(item, "instances"))] = ["instances", ["project", q(project), [
                "path", q(bpath), ["reference", q(rb)], ["unit", unit]]]]
        elif kind in ("label", "global_label"):
            item[1] = q(re.sub(r"_A$", "_B", unq(item[1])))
            item[item.index(find(item, "uuid"))] = ["uuid", fresh()]
        elif kind == "text":
            item[1] = q(rename_text(unq(item[1])))
            item[item.index(find(item, "uuid"))] = ["uuid", fresh()]
        elif kind in ("wire", "junction", "no_connect", "bus", "polyline", "rectangle"):
            if find(item, "uuid"):
                item[item.index(find(item, "uuid"))] = ["uuid", fresh()]
        elif kind == "title_block":
            for c in item:
                if isinstance(c, list) and len(c) > 1 and isinstance(c[-1], str) and c[-1].startswith('"'):
                    c[-1] = q(rename_text(unq(c[-1])))

    # ---- ADCIN1: cut the strap to LDO_3V3, put GND on the pin
    syms = {ref_of(s): s for s in find_all(out, "symbol")}
    u = syms["U301"]
    p_adc1 = pin_pos(u, "2")
    pin_pts = set()
    for s in syms.values():
        for num in schlib.pins_of(schlib.flat_symbol(unq(find(s, "lib_id")[1])), int(find(s, "unit")[1])):
            pin_pts.add(pin_pos(s, num))
    wires = [w for w in out if isinstance(w, list) and w and w[0] == "wire"]

    def degree(pt, ws):
        return sum(1 for w in ws for e in wire_pts(w) if e == pt) + (1 if pt in pin_pts else 0)

    remove, pt = [], p_adc1
    while True:
        nxt = [w for w in wires if w not in remove and pt in wire_pts(w)]
        if len(nxt) != 1:
            break
        w = nxt[0]
        remove.append(w)
        a, b = wire_pts(w)
        pt = b if a == pt else a
        if degree(pt, [x for x in wires if x not in remove]) != 1:   # reached the LDO_3V3 net
            break
    if not remove:
        raise SystemExit("ADCIN1 strap not found on port A sheet")
    for w in remove:
        out.remove(w)
    left = [x for x in out if isinstance(x, list) and x and x[0] == "wire"]
    if degree(pt, left) < 3:                                          # junction no longer needed
        for j in [x for x in out if isinstance(x, list) and x and x[0] == "junction"]:
            if (float(find(j, "at")[1]), float(find(j, "at")[2])) == pt:
                out.remove(j)
    # GND symbol: copy the one sitting on ADCIN2 (pin 3) and move it to pin 2
    p_adc2 = pin_pos(u, "3")
    g = next(s for s in find_all(out, "symbol") if unq(find(s, "lib_id")[1]) == "power:GND"
             and (float(find(s, "at")[1]), float(find(s, "at")[2])) == p_adc2)
    g2 = copy.deepcopy(g)
    dx, dy = p_adc1[0] - p_adc2[0], p_adc1[1] - p_adc2[1]
    for node in [g2] + find_all(g2, "property"):
        at = find(node, "at")
        at[1], at[2] = schlib.fmt(float(at[1]) + dx), schlib.fmt(float(at[2]) + dy)
    rb = next_power("#PWR")
    set_prop(g2, "Reference", rb)
    g2[g2.index(find(g2, "uuid"))] = ["uuid", fresh()]
    for p in find_all(g2, "pin"):
        p[p.index(find(p, "uuid"))] = ["uuid", fresh()]
    path = find(find(find(g2, "instances"), "project"), "path")
    path[path.index(find(path, "reference"))] = ["reference", q(rb)]
    out.insert(out.index(g) + 1, g2)

    open(B, "w", encoding="utf-8").write(dump(out) + "\n")
    print("port_b rebuilt from port_a: %d symbols, removed %d strap wire(s) at ADCIN1" % (
        len(find_all(out, "symbol")), len(remove)))


if __name__ == "__main__":
    main()
