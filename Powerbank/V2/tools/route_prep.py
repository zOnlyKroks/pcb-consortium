"""Prepare V2.kicad_pcb for Freerouting and write route/V2.dsn (route_finish.py imports the result).

1. Plane fan-out: GND (In1) and +BATT (In2) are planes.  Freerouting does not connect anything through inner
   planes, so every SMD pad of those nets gets a short locked stub + 0.7/0.3 via here.  Pads with their own thermal
   vias (TPS25751D / TPS54531 exposed pads), through-hole pads and pads inside a same-net F.Cu busbar are skipped.
   A pad that finds no via spot is handed to the router as a small "<net>__<n>" net with the nearest via of its
   net (route_finish.py renames them back).
2. DSN surgery: plane nets and their zones (inner planes, GND pours) leave the router's job; their fixed copper
   becomes a netless obstacle.  The F.Cu busbars (cell links, BATN / shunt / FET path) become fixed copper of their
   nets, so the router connects to them and keeps out of them.
   Widths: Default 0.2 mm, Power 0.3 mm (fits the 0.4 mm-pitch QFN pins; route_pours.py adds the copper area for
   the current afterwards), 0.15 mm clearance, vias 0.7/0.3 only (JLC standard tier).
"""
import math, os, re, sys
import pcbnew
from shapely.geometry import Polygon, Point, LineString, box
from shapely.strtree import STRtree
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "V2.kicad_pcb")
OUT = os.path.join(PRJ, "route")
DSN = os.path.join(OUT, "V2.dsn")
FM, TM = pcbnew.FromMM, pcbnew.ToMM
PLANES = ("GND", "+BATT")
VIA_D, VIA_DRILL, R = 0.7, 0.3, 0.35
CL = 0.15                                   # via / stub clearance to foreign copper during fan-out (net class)
X0, Y0, X1, Y1 = 50.0, 50.0, 241.0, 180.0


def shp(item, layer=pcbnew.F_Cu):
    s = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(s, layer, 0, FM(0.005), pcbnew.ERROR_INSIDE)
    polys = []
    for i in range(s.OutlineCount()):
        ol = s.Outline(i)
        pts = [(TM(ol.CPoint(k).x), TM(ol.CPoint(k).y)) for k in range(ol.PointCount())]
        if len(pts) >= 3:
            polys.append(Polygon(pts).buffer(0))
    return unary_union(polys)


def zone_poly(z):
    ol = z.Outline().Outline(0)
    return Polygon([(TM(ol.CPoint(k).x), TM(ol.CPoint(k).y)) for k in range(ol.PointCount())])


def main():
    B = pcbnew.LoadBoard(PCB)
    B.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    B.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    # drop any earlier fan-out / routing (keep the vias make_pcb.py placed in the busbars)
    assert not [t for t in B.GetTracks() if not t.IsLocked()], "board already has routing"
    busbars = [(z, zone_poly(z)) for z in B.Zones()
               if z.GetLayer() == pcbnew.F_Cu and z.GetAssignedPriority() > 0]
    obst, nets = [], []                      # foreign-copper obstacles on F.Cu (vias go through all layers)
    pads = []
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                obst.append(Point(TM(p.GetPosition().x), TM(p.GetPosition().y)).buffer(TM(p.GetDrillSize().x) / 2 + 0.05))
                nets.append("")
                continue
            if not p.IsOnLayer(pcbnew.F_Cu) or not p.IsOnCopperLayer():
                continue                     # paste-only apertures
            g = shp(p)
            obst.append(g)
            nets.append(p.GetNetname())
            pads.append(p)
    for z, poly in busbars:
        obst.append(poly)
        nets.append(z.GetNetname())
    via_pts = {}                             # net -> via centres (same-net vias keep hole spacing)
    for t in B.GetTracks():                  # make_pcb.py busbars and their vias
        if t.Type() == pcbnew.PCB_VIA_T:
            c = (TM(t.GetPosition().x), TM(t.GetPosition().y))
            obst.append(Point(c).buffer(R))
            via_pts.setdefault(t.GetNetname(), []).append(c)
        else:
            obst.append(LineString([(TM(t.GetStart().x), TM(t.GetStart().y)),
                                    (TM(t.GetEnd().x), TM(t.GetEnd().y))]).buffer(TM(t.GetWidth()) / 2))
        nets.append(t.GetNetname())
    edge = box(X0 + 0.35 + R, Y0 + 0.35 + R, X1 - 0.35 - R, Y1 - 0.35 - R)

    def tree():
        return STRtree(obst)

    T = [tree()]

    def free(geom, net, pad_geom, cl=CL):
        for i in T[0].query(geom.buffer(cl)):
            if nets[i] == net:
                continue
            if obst[i].distance(geom) < cl:
                return False
        return True

    def add(geom, net):
        obst.append(geom)
        nets.append(net)
        T[0] = tree()

    def via_spaced(net, x, y):
        return all(math.hypot(x - a, y - b) >= 1.1 for a, b in via_pts.get(net, []))

    def ep_of(p):
        """The exposed pad (SMD pad with thermal vias) of the same net in p's footprint, if any."""
        f = p.GetParentFootprint()
        for q in f.Pads():
            if (q.GetNetname() == p.GetNetname() and q.GetNumber() != p.GetNumber() and q.GetAttribute() ==
                    pcbnew.PAD_ATTRIB_SMD and own_vias(q)):
                return q
        return None

    def own_vias(p):
        """True if the pad already reaches the planes (thermal vias of an exposed pad, through-hole)."""
        f = p.GetParentFootprint()
        return any(q.GetNumber() == p.GetNumber() and q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for q in f.Pads())

    done, left = [], []
    todo = []
    for p in pads:
        n = p.GetNetname()
        if n not in PLANES or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or own_vias(p):
            continue
        c = Point(TM(p.GetPosition().x), TM(p.GetPosition().y))
        if any(z.GetNetname() == n and poly.contains(c) for z, poly in busbars):
            continue
        todo.append(p)
    todo.sort(key=lambda p: (p.GetParentFootprint().GetReference(), p.GetNumber()))
    seen = set()
    for p in todo:
        n = p.GetNetname()
        key = (p.GetParentFootprint().GetReference(), p.GetPosition().x, p.GetPosition().y)
        if key in seen:                      # stacked pads (USB-C A1/B12 ...): one via is enough
            done.append(p)
            continue
        seen.add(key)
        pg = shp(p)
        ep = ep_of(p)
        if ep is not None:                   # straight stub into the exposed pad
            ex0, ey0, ex1, ey1 = shp(ep).bounds
            pc0 = Point(TM(p.GetPosition().x), TM(p.GetPosition().y))
            q = Point(min(max(pc0.x, ex0 + 0.05), ex1 - 0.05), min(max(pc0.y, ey0 + 0.3), ey1 - 0.3))
            minx, miny, maxx, maxy = pg.bounds
            w = max(0.15, min(0.25, maxx - minx, maxy - miny))
            stub = LineString([(pc0.x, pc0.y), (q.x, q.y)]).buffer(w / 2)
            if free(stub.difference(pg).difference(shp(ep)), n, pg, 0.12):
                t = pcbnew.PCB_TRACK(B)
                t.SetStart(p.GetPosition())
                t.SetEnd(pcbnew.VECTOR2I(FM(q.x), FM(q.y)))
                t.SetWidth(FM(w))
                t.SetLayer(pcbnew.F_Cu)
                t.SetNet(p.GetNet())
                t.SetLocked(True)
                B.Add(t)
                add(stub, n)
                done.append(p)
                continue
        pc = Point(TM(p.GetPosition().x), TM(p.GetPosition().y))
        fc = p.GetParentFootprint().GetPosition()
        vx, vy = pc.x - TM(fc.x), pc.y - TM(fc.y)
        base = math.atan2(vy, vx) if math.hypot(vx, vy) > 0.1 else math.pi / 2
        minx, miny, maxx, maxy = pg.bounds
        w = max(0.15, min(0.4, maxx - minx, maxy - miny))
        big = (maxx - minx) * (maxy - miny) > 2.0
        placed = 0
        cands = []
        for k in range(0, 17):
            a = base + (k + 1) // 2 * (1 if k % 2 else -1) * math.pi / 8
            for d in (0.15, 0.35, 0.6, 0.9, 1.3, 1.8, 2.4, 3.0, 3.8):
                cands.append((d + 0.15 * ((k + 1) // 2), a, d))
        cands.sort()
        used = []
        for _, a, d in cands:
            # leave the pad edge along the ray, then go d further
            ray = LineString([(pc.x, pc.y), (pc.x + 20 * math.cos(a), pc.y + 20 * math.sin(a))])
            ex = ray.intersection(pg.boundary)
            if ex.is_empty:
                continue
            ep = ex if ex.geom_type == "Point" else min(ex.geoms, key=lambda g: g.distance(pc))
            cx, cy = ep.x + (d + R) * math.cos(a), ep.y + (d + R) * math.sin(a)
            v = Point(cx, cy)
            if not edge.contains(v) or not via_spaced(n, cx, cy):
                continue
            via_g = v.buffer(R)
            if via_g.intersects(pg.buffer(-0.01)):
                continue
            stub = LineString([(pc.x, pc.y), (cx, cy)]).buffer(w / 2)
            if not free(via_g, n, pg) or not free(stub.difference(pg), n, pg):
                continue
            t = pcbnew.PCB_TRACK(B)
            t.SetStart(p.GetPosition())
            t.SetEnd(pcbnew.VECTOR2I(FM(cx), FM(cy)))
            t.SetWidth(FM(w))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(p.GetNet())
            t.SetLocked(True)
            B.Add(t)
            vv = pcbnew.PCB_VIA(B)
            vv.SetPosition(pcbnew.VECTOR2I(FM(cx), FM(cy)))
            vv.SetWidth(FM(VIA_D))
            vv.SetDrill(FM(VIA_DRILL))
            vv.SetNet(p.GetNet())
            vv.SetLocked(True)
            B.Add(vv)
            add(via_g, n)
            add(stub, n)
            via_pts.setdefault(n, []).append((cx, cy))
            placed += 1
            if placed >= (2 if big else 1):
                break
        if not placed:                       # last resort: a stub to a connected same-net pad of the same part
            for q in sorted((q for q in p.GetParentFootprint().Pads() if q.GetNetname() == n and q in done),
                            key=lambda q: (q.GetPosition() - p.GetPosition()).EuclideanNorm()):
                qg = shp(q)
                a, b = pg.centroid, qg.centroid
                stub = LineString([(a.x, a.y), (b.x, b.y)]).buffer(0.1)
                if a.distance(b) < 2.0 and free(stub.difference(pg).difference(qg), n, pg, 0.12):
                    t = pcbnew.PCB_TRACK(B)
                    t.SetStart(p.GetPosition())
                    t.SetEnd(q.GetPosition())
                    t.SetWidth(FM(0.2))
                    t.SetLayer(pcbnew.F_Cu)
                    t.SetNet(p.GetNet())
                    t.SetLocked(True)
                    B.Add(t)
                    add(stub, n)
                    placed = 1
                    break
        (done if placed else left).append(p)
    print("fan-out: %d pads, %d without a via: %s" % (len(done), len(left), " ".join(
        "%s-%s" % (p.GetParentFootprint().GetReference(), p.GetNumber()) for p in left)))

    # leftover plane pads: pair each with the nearest via of its net
    vias = {n: [v for v in B.GetTracks() if v.Type() == pcbnew.PCB_VIA_T and v.GetNetname() == n] for n in PLANES}
    groups = []
    for p in left:
        n = p.GetNetname()
        a = min(vias[n], key=lambda v: (v.GetPosition() - p.GetPosition()).EuclideanNorm())
        groups.append(("%s__%d" % (n.replace("+", "P"), len(groups) + 1), n, p, a))
    pcbnew.SaveBoard(PCB, B)
    os.makedirs(OUT, exist_ok=True)
    assert pcbnew.ExportSpecctraDSN(B, DSN)
    dsn_surgery(B, busbars, groups)


def drop_block(text, head):
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


def take_block(text, i):
    depth, j = 0, i
    while True:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1


def qn(n):
    return n if re.fullmatch(r"[^\s()\"]+", n) else '"%s"' % n


def dsn_surgery(B, busbars, groups):
    txt = open(DSN, encoding="utf-8").read()
    # busbar planes -> fixed copper of their net
    fixed = []
    for n in sorted({z.GetNetname() for z, _ in busbars}):
        head = "(plane %s (polygon F.Cu" % qn(n)
        while head in txt:
            i = txt.index(head)
            blk = take_block(txt, i)
            poly = blk[blk.index("(polygon"):-1]
            if n not in PLANES:
                fixed.append("    (wire %s (net %s)(type fix))\n" % (poly, qn(n)))
            k = txt.rfind("\n", 0, i)
            txt = txt[:k] + txt[i + len(blk):]
    for n in PLANES:
        txt = drop_block(txt, "(plane %s " % qn(n))
        txt = drop_block(txt, "(net %s\n" % qn(n))
    assert "(plane" not in txt, "unexpected plane left"
    new_nets = "".join("    (net %s\n      (pins %s-%s)\n    )\n" % (g, p.GetParentFootprint().GetReference(),
                                                                   p.GetNumber()) for g, n, p, a in groups)
    i = txt.index("    (class ")
    txt = txt[:i] + new_nets + txt[i:]
    V = '"Via[0-%d]_700:300_um"' % (B.GetCopperLayerCount() - 1)
    assert "(padstack %s" % V in txt
    rules = {"kicad_default": (200, 150), "Power": (300, 150)}
    extra = {"Power": [g for g, n, p, a in groups]}

    def fix_class(m):
        name, body = m.group(1), m.group(2)
        members = [x for x in re.findall(r'"[^"]*"|\S+', body) if x not in PLANES] + extra.get(name, [])
        w, cl = rules[name]
        return ("(class %s %s\n      (circuit\n        (use_via %s)\n      )\n      (rule\n        (width %d)\n"
                "        (clearance %d)\n      )\n    )" % (name, " ".join(members), V, w, cl))
    txt, k = re.subn(r"\(class (\S+) (.*?)\n\s*\(circuit.*?\n    \)", fix_class, txt, flags=re.S)
    assert k == 2, k
    # plane-net fixed copper: netless obstacle, except the anchor vias of the groups
    anchors = {(round(TM(a.GetPosition().x) * 1000), round(-TM(a.GetPosition().y) * 1000)): g for g, n, p, a in groups}

    def fix_wire(m):
        line, net = m.group(0), m.group(1)
        xy = re.findall(r'"\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\(net', line)
        if line.lstrip().startswith("(via") and xy:
            key = (round(float(xy[0][0])), round(float(xy[0][1])))
            if key in anchors:
                return line.replace("(net %s)" % net, "(net %s)" % anchors.pop(key))
        return line.replace("(net %s)" % net, "")
    txt = re.sub(r"^.*\(net (GND|\+BATT)\).*$", fix_wire, txt, flags=re.M)
    assert not re.search(r"\(net (GND|\+BATT)\)", txt)
    txt = txt.replace("  (wiring\n", "  (wiring\n" + "".join(fixed), 1)
    open(DSN, "w", encoding="utf-8").write(txt)
    print("DSN %s: nets %d, fixed busbars %d, groups %d" % (DSN, txt.count("    (net "), len(fixed), len(groups)))


if __name__ == "__main__":
    main()
