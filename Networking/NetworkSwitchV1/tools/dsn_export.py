"""Shared by route_prep.py and route_eco.py: group the plane pads the router has to link, and write the DSN.

Freerouting does not treat the inner planes as connecting anything, so the plane nets are taken out of its job:
no planes, no plane nets, and their fixed copper becomes netless (an obstacle).  Plane pads that still need a
connection are handed over as small "<net>__<n>" nets (route_finish.py renames them back on import).
"""
import os, re
import pcbnew

FM = pcbnew.FromMM
X0, Y0 = 100.0, 50.0
PLANE_NETS = ("GND", "RTN", "+3V3", "+1V1")
PLANE_CLASS = {"GND": "Power", "+3V3": "Power", "+1V1": "Power_IC", "RTN": "PoE_HV"}
DECAP = {20: "C301", 21: "C302", 22: "C303", 23: "C304", 76: "C305", 78: "C306", 92: "C307", 95: "C308", 77: "C334"}


def pname(q):
    return "%s-%s" % (q.GetParentFootprint().GetReference(), q.GetNumber())


def group_leftovers(fo, done, left):
    """Pair every leftover plane pad with a target: its RTL8370N decoupling cap, the nearest plane pad that is
    already connected (within 5 mm), or a new anchor via inside the plane.  Returns [(name, net, pins, anchor)]."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x

    def join(a, b):
        parent[find(a)] = find(b)

    netof_pad, anchor_of = {}, {}
    leftover = sorted(left, key=lambda q: pname(q).startswith("U301"))
    for q in leftover:
        n, net = pname(q), str(q.GetNetname())
        netof_pad[n] = net
        find(n)
        ref, num = q.GetParentFootprint().GetReference(), q.GetNumber()
        if ref == "U301" and num.isdigit() and int(num) in DECAP:
            t = "%s-1" % DECAP[int(num)]
            netof_pad[t] = net
            join(n, t)
            continue
        if q.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:            # through-hole: one anchor per footprint/net
            mates = [m for m in netof_pad if m != n and m.split("-")[0] == ref and netof_pad[m] == net]
            if mates:
                join(n, mates[0])
                continue
        best = None
        for d in done:
            if str(d.GetNetname()) == net and d.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                dist = (d.GetPosition() - q.GetPosition()).EuclideanNorm()
                if dist < FM(5.0) and (best is None or dist < best[0]):
                    best = (dist, d)
        if best:
            netof_pad[pname(best[1])] = net
            join(n, pname(best[1]))
            continue
        c = fo.anchor(q, net, rmax=20.0 if q.GetAttribute() != pcbnew.PAD_ATTRIB_SMD else 12.0)
        if c is None:
            print("  WARNING: no plane anchor for", n, net)
            continue
        anchor_of[find(n)] = c
    groups = {}
    for n in netof_pad:
        groups.setdefault(find(n), []).append(n)
    for r, c in list(anchor_of.items()):
        if find(r) != r:
            anchor_of[find(r)] = c
            del anchor_of[r]
    out = []
    for k, (r, pins) in enumerate(sorted(groups.items()), 1):
        net = netof_pad[pins[0]]
        out.append(("%s__%d" % (net, k), net, sorted(pins), anchor_of.get(r)))
    print("router groups: %d leftover plane pads in %d groups (%d anchors)" %
          (len(leftover), len(out), sum(1 for g in out if g[3] is not None)))
    return out


def drop_block(text, head):
    """Remove every balanced (...) block starting with `head`."""
    while True:
        i = text.find(head)
        if i < 0:
            return text
        depth, j = 0, i
        while True:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        k = text.rfind("\n", 0, i)
        text = text[:k] + text[j + 1:]


def export(B, groups, dsn):
    os.makedirs(os.path.dirname(dsn), exist_ok=True)
    ok = pcbnew.ExportSpecctraDSN(B, dsn)
    txt = open(dsn, encoding="utf-8").read()
    txt = re.sub("[ΩµΦ]", "", txt)
    # KiCad exports a rule area that only forbids zone fills as a full keepout; the line side must stay routable
    lx0, ly0 = int(round((X0 + 41.0) * 1000)), -int(round((Y0 + 61.3) * 1000))
    txt, n = re.subn(r'\n\s*\(keepout "" \(polygon \S+ 0\s+%d %d\s[^)]*\)\)' % (lx0, ly0), "", txt)
    assert n == 4, n
    for net in PLANE_NETS:
        txt = drop_block(txt, "(plane %s " % net)
        txt = drop_block(txt, "(net %s\n" % net)
    uses = {}
    for name, net, pins, c in groups:
        uses.setdefault(PLANE_CLASS[net], []).append(name)
    new_nets = "".join("    (net %s\n      (pins %s)\n    )\n" % (name, " ".join(pins)) for name, net, pins, c in groups)
    i = txt.index("    (class ")
    txt = txt[:i] + new_nets + txt[i:]

    def fix_class(m):
        names = [x for x in m.group(2).split() if x not in PLANE_NETS] + uses.get(m.group(1), [])
        return "(class %s %s\n      (circuit" % (m.group(1), " ".join(names))

    txt = re.sub(r"\(class (\S+) ([^()]*?)\n\s*\(circuit", fix_class, txt, flags=re.S)
    anchors = {(round(c.x / 1000), round(-c.y / 1000)): name for name, net, pins, c in groups if c is not None}

    def fix_wire(m):
        line, net = m.group(0), m.group(1)
        if line.lstrip().startswith("(via"):
            nums = re.findall(r"\s(-?[\d.]+)\s+(-?[\d.]+)\s+\(net", line)
            if nums:
                key = (round(float(nums[0][0])), round(float(nums[0][1])))
                if key in anchors:
                    return line.replace("(net %s)" % net, "(net %s)" % anchors[key])
        return line.replace("(net %s)" % net, "")

    txt = re.sub(r"^.*\(net (GND|RTN|\+3V3|\+1V1)\).*$", fix_wire, txt, flags=re.M)
    left_refs = re.findall(r"\(net (GND|RTN|\+3V3|\+1V1)\)", txt)
    assert not left_refs, left_refs[:5]
    open(dsn, "w", encoding="utf-8").write(txt)
    print("DSN export", ok, dsn, "nets:", txt.count("    (net "), "fixed wires:", txt.count("(type fix)"),
          "routed wires:", txt.count("(wire ") - txt.count("(type fix)"))
