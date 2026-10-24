"""Close the connections Freerouting left open with exact-geometry dog-legs (run after route_finish.py).

For each unconnected pair KiCad's DRC reports: a straight F.Cu link if it is clear; else a short straight escape
out of each end (0.15 mm, along the pin's own axis for IC pins), a 0.7/0.3 via, and an L-shaped (or one-bend)
link on B.Cu between the two vias - or straight onto the other end's B.Cu copper.  Every piece is checked against
the real shapes of all foreign copper (shapely, 0.16 mm against the 0.15 mm rule, 0.35 mm to the board edge).
The GND pours are ignored (they refill); the inner planes are cut around new vias by the fill.
"""
import itertools, json, math, os, re, subprocess, tempfile
import pcbnew
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, "..", "V2.kicad_pcb"))
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
FM, TM = pcbnew.FromMM, pcbnew.ToMM
W, CL, VD, VR = 0.15, 0.16, 0.7, 0.35
X0, Y0, X1, Y1 = 50.0, 50.0, 241.0, 180.0
EDGE = box(X0 + 0.35, Y0 + 0.35, X1 - 0.35, Y1 - 0.35)
LAY = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}


def shp(item, layer):
    s = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(s, layer, 0, FM(0.005), pcbnew.ERROR_INSIDE)
    ps = []
    for i in range(s.OutlineCount()):
        ol = s.Outline(i)
        pts = [(TM(ol.CPoint(k).x), TM(ol.CPoint(k).y)) for k in range(ol.PointCount())]
        if len(pts) >= 3:
            ps.append(Polygon(pts).buffer(0))
    return unary_union(ps)


class Copper:
    def __init__(self, B):
        self.g = {"F": [], "B": []}
        self.n = {"F": [], "B": []}
        for f in B.GetFootprints():
            for p in f.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    c = Point(TM(p.GetPosition().x), TM(p.GetPosition().y)).buffer(TM(p.GetDrillSize().x) / 2 + 0.05)
                    for L in "FB":
                        self.add(L, c, "#hole")
                    continue
                for L in "FB":
                    if p.IsOnLayer(LAY[L]):
                        self.add(L, shp(p, LAY[L]), p.GetNetname())
        for t in B.GetTracks():
            for L in "FB":
                if t.IsOnLayer(LAY[L]):
                    self.add(L, shp(t, LAY[L]), t.GetNetname())
        for z in B.Zones():                      # other nets' zones (not the GND pours, which refill)
            if z.GetNetname() == "GND" or z.GetIsRuleArea():
                continue
            for L in "FB":
                if z.IsOnLayer(LAY[L]):
                    self.add(L, shp(z, LAY[L]), z.GetNetname())
        self.build()

    def add(self, L, g, net):
        if not g.is_empty:
            self.g[L].append(g)
            self.n[L].append(net)

    def build(self):
        self.t = {L: STRtree(self.g[L]) for L in "FB"}

    def clear(self, L, g, net):
        if not EDGE.contains(g):
            return False
        for i in self.t[L].query(g.buffer(CL)):
            if self.n[L][i] != net and self.g[L][i].distance(g) < CL:
                return False
        return True


def drc():
    out = os.path.join(tempfile.gettempdir(), "dogleg_drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", out, PCB], capture_output=True)
    return json.load(open(out, encoding="utf-8"))


def find_item(B, desc, pos):
    """The pad / track a DRC item description + position names."""
    net = re.search(r"\[([^\]]*)\]", desc).group(1)
    P = pcbnew.VECTOR2I(FM(pos["x"]), FM(pos["y"]))
    m = re.match(r"Pad (\S+) \[.*\] of (\S+)", desc)
    if m:
        f = B.FindFootprintByReference(m.group(2))
        return net, min((p for p in f.Pads() if p.GetNumber() == m.group(1)),
                        key=lambda p: (p.GetPosition() - P).EuclideanNorm())
    best = None
    for t in B.GetTracks():
        if t.GetNetname() == net:
            d = (t.GetPosition() - P).EuclideanNorm() if t.Type() == pcbnew.PCB_VIA_T else \
                min((t.GetStart() - P).EuclideanNorm(), (t.GetEnd() - P).EuclideanNorm())
            if best is None or d < best[0]:
                best = (d, t)
    return net, best[1]


def anchors(it):
    """(point, layers it is on, escape directions) for a pad or track end."""
    if isinstance(it, pcbnew.PAD):
        c = (TM(it.GetPosition().x), TM(it.GetPosition().y))
        f = it.GetParentFootprint()
        fc = f.GetPosition()
        dx, dy = c[0] - TM(fc.x), c[1] - TM(fc.y)
        sz = it.GetSize(pcbnew.F_Cu)
        big = len(f.Pads()) > 8
        if big:                                 # IC pin: straight out of the package only
            dirs = [((1 if dx > 0 else -1), 0)] if abs(dx) > abs(dy) else [(0, (1 if dy > 0 else -1))]
        else:
            dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        layers = "FB" if it.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else "F"
        return [(c, layers, dirs)]
    if it.Type() == pcbnew.PCB_VIA_T:
        c = (TM(it.GetPosition().x), TM(it.GetPosition().y))
        return [(c, "FB", [])]
    L = "F" if it.GetLayer() == pcbnew.F_Cu else "B"
    out = []
    for P in (it.GetStart(), it.GetEnd()):
        out.append(((TM(P.x), TM(P.y)), L, [(1, 0), (-1, 0), (0, 1), (0, -1)]))
    return out


def seg(a, b):
    return LineString([a, b]).buffer(W / 2)


def plan(C, net, A, Bi):
    """List of (layer, a, b) tracks and via points, or None."""
    for (pa, la, _), (pb, lb, _) in itertools.product(anchors(A), anchors(Bi)):
        for L in "FB":
            if L in la and L in lb and C.clear(L, seg(pa, pb), net):
                return [(L, pa, pb)], []
    best = None
    for (pa, la, da), (pb, lb, db) in itertools.product(anchors(A), anchors(Bi)):
        # escapes to a via (or the anchor itself if it already reaches B.Cu)
        def escapes(p, layers, dirs):
            if "B" in layers:
                yield p, [], []
            for (ux, uy), e in itertools.product(dirs, (0.8, 1.1, 1.4, 1.8, 2.3, 2.9, 3.6)):
                v = (p[0] + ux * e, p[1] + uy * e)
                s = seg(p, v)
                vg = Point(v).buffer(VR)
                if C.clear("F", s, net) and C.clear("F", vg, net) and C.clear("B", vg, net):
                    yield v, [("F", p, v)], [v]
        for (va, ta, via_a), (vb, tb, via_b) in itertools.product(list(escapes(pa, la, da)),
                                                                  list(escapes(pb, lb, db))):
            if va == vb:
                continue
            cand = [[va, vb], [va, (vb[0], va[1]), vb], [va, (va[0], vb[1]), vb]]
            for mx in (0.3, 0.5, 0.7):
                m = (va[0] + (vb[0] - va[0]) * mx, va[1])
                cand.append([va, m, (m[0], vb[1]), vb])
                m = (va[0], va[1] + (vb[1] - va[1]) * mx)
                cand.append([va, m, (vb[0], m[1]), vb])
            for pts in cand:
                if all(C.clear("B", seg(a, b), net) for a, b in zip(pts, pts[1:]) if a != b):
                    length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) + 2.0 * (len(via_a) + len(via_b))
                    tracks = ta + tb + [("B", a, b) for a, b in zip(pts, pts[1:]) if a != b]
                    if best is None or length < best[0]:
                        best = (length, tracks, via_a + via_b)
                    break
    return (best[1], best[2]) if best else None


def commit(B, C, net, tracks, vias):
    ni = B.FindNet(net)
    for L, a, b in tracks:
        t = pcbnew.PCB_TRACK(B)
        t.SetStart(pcbnew.VECTOR2I(FM(a[0]), FM(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(FM(b[0]), FM(b[1])))
        t.SetWidth(FM(W))
        t.SetLayer(LAY[L])
        t.SetNet(ni)
        B.Add(t)
        C.add(L, seg(a, b), net)
    for v in vias:
        vv = pcbnew.PCB_VIA(B)
        vv.SetPosition(pcbnew.VECTOR2I(FM(v[0]), FM(v[1])))
        vv.SetWidth(FM(VD))
        vv.SetDrill(FM(0.3))
        vv.SetNet(ni)
        B.Add(vv)
        for L in "FB":
            C.add(L, Point(v).buffer(VR), net)
    C.build()


def main():
    for rnd in range(4):
        d = drc()
        pairs = d["unconnected_items"]
        print("round %d: %d unconnected" % (rnd, len(pairs)), flush=True)
        if not pairs:
            break
        B = pcbnew.LoadBoard(PCB)
        C = Copper(B)
        done = 0
        for u in pairs:
            a, b = u["items"][:2]
            try:
                net, A = find_item(B, a["description"], a["pos"])
                _, Bi = find_item(B, b["description"], b["pos"])
            except Exception as e:                  # zone items etc.
                print("  skip", a["description"][:40], e)
                continue
            r = plan(C, net, A, Bi)
            if r is None:
                print("  %-24s no dog-leg" % net, flush=True)
                continue
            commit(B, C, net, *r)
            done += 1
            print("  %-24s %d tracks %d vias" % (net, len(r[0]), len(r[1])), flush=True)
        pcbnew.ZONE_FILLER(B).Fill(B.Zones())
        pcbnew.SaveBoard(PCB, B)
        if not done:
            break
    d = drc()
    print("final: clearance %d, unconnected %d" % (sum(v["type"] in ("clearance", "shorting_items", "hole_clearance")
                                                      for v in d["violations"]), len(d["unconnected_items"])))


if __name__ == "__main__":
    main()
