"""Plane fanout for NetworkSwitchV1: every SMD pad of a plane net gets a short locked stub + via to its plane.

Freerouting does not treat the inner planes as connecting anything (it ties plane pads together with long tracks),
so route_prep.py takes the plane nets out of the router's job:
  - pads with their own fanout via (or a through-hole pad inside the plane) are done here;
  - every other plane pad ("leftover") is paired with one target: its RTL8370N decoupling capacitor, the nearest
    plane pad that already has a via, or a new locked anchor via inside the plane. route_prep.py hands each pair to
    the router as its own small net.
"""
import math
import pcbnew

FM, TM = pcbnew.FromMM, pcbnew.ToMM
VIA_D, VIA_DRILL = 0.7, 0.3
R = VIA_D / 2
WIDTH = {"GND": 0.25, "+3V3": 0.25, "+1V1": 0.3, "RTN": 0.4}
ZONE_CL = 0.3
CELL = FM(2.0)


class Fanout:
    def __init__(self, B, planes):
        self.B, self.planes = B, planes
        self.nets = B.GetNetsByName()
        self.clc, self.grid = {}, {}
        for f in B.GetFootprints():
            for p in f.Pads():
                sps = pcbnew.SHAPE_POLY_SET()
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    item = ["hole", p.GetPosition(), FM(TM(p.GetDrillSize().x) / 2 + 0.25), "", None]
                else:
                    p.TransformShapeToPolygon(sps, pcbnew.F_Cu, 0, FM(0.005), pcbnew.ERROR_INSIDE)
                    item = ["pad", sps, 0, str(p.GetNetname()), p]
                b = p.GetBoundingBox()
                self._add(item, (b.GetX(), b.GetY(), b.GetRight(), b.GetBottom()))
        for t in B.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                c = t.GetPosition()
                self._add(["via", c, t.GetWidth(pcbnew.F_Cu) // 2, str(t.GetNetname()), None],
                          (c.x - FM(R), c.y - FM(R), c.x + FM(R), c.y + FM(R)))
            elif t.GetLayer() == pcbnew.F_Cu or True:      # tracks on any layer block a through via
                s, e = t.GetStart(), t.GetEnd()
                self._add(["stub", pcbnew.SEG(s, e), t.GetWidth() // 2, str(t.GetNetname()), TM(t.GetWidth()),
                           t.GetLayer()],
                          (min(s.x, e.x), min(s.y, e.y), max(s.x, e.x), max(s.y, e.y)))
        self.keep = [z.Outline() for z in B.Zones() if z.GetIsRuleArea() and z.GetDoNotAllowVias()]
        self.allowed = {}
        for n, poly in planes.items():
            a = pcbnew.SHAPE_POLY_SET(poly)
            a.Deflate(FM(R + ZONE_CL + 0.15), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))
            self.allowed[n] = a
        bb = B.GetBoardEdgesBoundingBox()
        self.edge = (bb.GetX() + FM(R + 0.35), bb.GetY() + FM(R + 0.35),
                     bb.GetRight() - FM(R + 0.35), bb.GetBottom() - FM(R + 0.35))
        cy = B.FindFootprintByReference("U301").GetCourtyard(pcbnew.F_CrtYd).BBox()
        self.body = [(cy.GetX(), cy.GetY(), cy.GetRight(), cy.GetBottom())]
        self.anchors = []                     # (VECTOR2I, net) of anchor vias

    # ------------------------------------------------------------ geometry
    def cl(self, n):
        if n not in self.clc:
            import rules
            if not hasattr(self, "rules"):
                self.rules = rules.Rules(self.B)
            self.clc[n] = self.rules.clearance(n)
        return self.clc[n]

    def _add(self, item, bb):
        for i in range(int(bb[0] // CELL) - 1, int(bb[2] // CELL) + 2):
            for j in range(int(bb[1] // CELL) - 1, int(bb[3] // CELL) + 2):
                self.grid.setdefault((i, j), []).append(item)

    def _near(self, x, y, rad):
        seen, out, r = set(), [], FM(rad)
        for i in range(int((x - r) // CELL), int((x + r) // CELL) + 1):
            for j in range(int((y - r) // CELL), int((y + r) // CELL) + 1):
                for it in self.grid.get((i, j), ()):
                    if id(it) not in seen:
                        seen.add(id(it))
                        out.append(it)
        return out

    def ok(self, net, own, pc, c, w):
        """Can a via of `net` sit at c, fed by a stub of width w from pc (pc None: via only)?"""
        e = self.edge
        if not (e[0] < c.x < e[2] and e[1] < c.y < e[3]) or not self.allowed[net].Contains(c):
            return False
        for k in self.keep:
            if k.Contains(c) or math.sqrt(k.SquaredDistance(c)) < FM(R + 0.1):
                return False
        for b in self.body:
            if b[0] < c.x < b[2] and b[1] < c.y < b[3]:
                return False
        seg = pcbnew.SEG(pc, c) if pc is not None else None
        for it in self._near(c.x, c.y, 3.0):
            kind, other = it[0], it[3]
            if kind == "hole":
                if (it[1] - c).EuclideanNorm() < it[2] + FM(R):
                    return False
                if seg and math.sqrt(seg.SquaredDistance(it[1])) < it[2] + FM(w / 2):
                    return False
                continue
            gap = max(self.cl(net), self.cl(other))
            if kind == "stub":
                if other == net:
                    continue
                if math.sqrt(it[1].SquaredDistance(c)) < FM(R + it[4] / 2 + gap):
                    return False
                same_layer = len(it) < 6 or it[5] == pcbnew.F_Cu
                if seg and same_layer and math.sqrt(seg.SquaredDistance(it[1])) < FM(w / 2 + it[4] / 2 + gap):
                    return False
                continue
            if kind == "via":
                g = 0.25 if other == net else gap
                if (it[1] - c).EuclideanNorm() < it[2] + FM(R + g):
                    return False
                if seg and other != net and math.sqrt(seg.SquaredDistance(it[1])) < it[2] + FM(w / 2 + g):
                    return False
                continue
            d = math.sqrt(it[1].SquaredDistance(c))
            if it[4] is own or other == net:
                if d < FM(R + 0.05):                  # never a via in a pad
                    return False
                continue
            if d < FM(R + gap) or (seg and math.sqrt(it[1].SquaredDistanceToSeg(seg)) < FM(w / 2 + gap)):
                return False
        return True

    def _new_via(self, c, netobj, net):
        v = pcbnew.PCB_VIA(self.B)
        v.SetPosition(c)
        v.SetWidth(FM(VIA_D))
        v.SetDrill(FM(VIA_DRILL))
        v.SetNet(netobj)
        v.SetLocked(True)
        self.B.Add(v)
        self._add(["via", c, FM(R), net, None], (c.x - FM(R), c.y - FM(R), c.x + FM(R), c.y + FM(R)))

    def _new_stub(self, pc, c, w, netobj, net):
        t = pcbnew.PCB_TRACK(self.B)
        t.SetStart(pc)
        t.SetEnd(c)
        t.SetWidth(FM(w))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(netobj)
        t.SetLocked(True)
        self.B.Add(t)
        self._add(["stub", pcbnew.SEG(pc, c), FM(w / 2), net, w],
                  (min(pc.x, c.x), min(pc.y, c.y), max(pc.x, c.x), max(pc.y, c.y)))

    # ------------------------------------------------------------ placement
    def place(self, p, net, w, avoid=None):
        pc, fc = p.GetPosition(), p.GetParentFootprint().GetPosition()
        v = pc - fc
        base = math.atan2(v.y, v.x) if v.EuclideanNorm() > FM(0.1) else math.pi / 2
        b = p.GetBoundingBox()
        hx, hy = TM(b.GetWidth()) / 2, TM(b.GetHeight()) / 2
        cands = []
        for k in range(0, 9):
            for sgn in ((1,) if k in (0, 8) else (1, -1)):
                a = base + sgn * k * math.pi / 8
                ca, sa = math.cos(a), math.sin(a)
                t = min(hx / abs(ca) if abs(ca) > 1e-6 else 1e9, hy / abs(sa) if abs(sa) > 1e-6 else 1e9)
                for gap in (0.12, 0.3, 0.5, 0.8, 1.2, 1.7, 2.3):
                    cands.append((gap + 0.22 * k, a, t + R + gap))
        cands.sort()
        for _, a, d in cands:
            c = pcbnew.VECTOR2I(int(pc.x + FM(d * math.cos(a))), int(pc.y + FM(d * math.sin(a))))
            if avoid is not None and (c - avoid).EuclideanNorm() < FM(1.0):
                continue
            if self.ok(net, p, pc, c, w):
                return pc, c
        return None

    def anchor(self, p, net, rmax=12.0, step=0.5):
        """Locked via of `net` inside its plane, as close to pad p as possible (the router links them)."""
        pc = p.GetPosition()
        n = int(rmax / step)
        cands = sorted(((i * i + j * j), i, j) for i in range(-n, n + 1) for j in range(-n, n + 1)
                       if 0 < i * i + j * j <= n * n)
        for _, i, j in cands:
            c = pcbnew.VECTOR2I(pc.x + FM(i * step), pc.y + FM(j * step))
            if self.ok(net, p, None, c, 0) and self.ok(net, p, None, c, 0):
                # keep a routing lane: no other copper within 0.6 mm of the via
                if all(self.ok(net, p, None, pcbnew.VECTOR2I(c.x + FM(dx), c.y + FM(dy)), 0)
                       for dx, dy in ((0.3, 0), (-0.3, 0), (0, 0.3), (0, -0.3))):
                    self._new_via(c, p.GetNet(), net)
                    self.anchors.append((c, net))
                    return c
        return None

    def run(self, skip=(("U301", "129"), ("U501", "29"))):
        """Fan out every plane-net SMD pad. Returns (connected, leftover) lists of pads."""
        B, done, left = self.B, [], []
        u = B.FindFootprintByReference("U301")
        eb = [q for q in u.Pads() if q.GetNumber() == "129"][0].GetBoundingBox()
        todo = []
        for f in B.GetFootprints():
            for p in f.Pads():
                net = str(p.GetNetname())
                if net not in self.planes or (f.GetReference(), p.GetNumber()) in skip:
                    continue
                if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                    (done if self.allowed[net].Contains(p.GetPosition()) else left).append(p)
                    continue
                if f.GetReference() == "U301":
                    if net == "GND":                  # straight stub inward to the exposed pad
                        pc = p.GetPosition()
                        tgt = pcbnew.VECTOR2I(min(max(pc.x, eb.GetX() + FM(0.3)), eb.GetRight() - FM(0.3)),
                                              min(max(pc.y, eb.GetY() + FM(0.3)), eb.GetBottom() - FM(0.3)))
                        t = pcbnew.PCB_TRACK(B)
                        t.SetStart(pc)
                        t.SetEnd(tgt)
                        t.SetWidth(FM(0.25))
                        t.SetLayer(pcbnew.F_Cu)
                        t.SetNet(p.GetNet())
                        t.SetLocked(True)
                        B.Add(t)
                        done.append(p)
                    else:                             # supply pins go to their decoupling cap instead
                        left.append(p)
                    continue
                pri = 0 if f.GetReference().startswith(("C3", "R3")) else 1
                todo.append((pri, f.GetReference(), p.GetNumber(), p))
        todo.sort(key=lambda t: (t[0], t[1], t[2]))
        for _, ref, num, p in todo:
            net = str(p.GetNetname())
            b = p.GetBoundingBox()
            w = min(WIDTH.get(net, 0.25), TM(min(b.GetWidth(), b.GetHeight())))
            r = self.place(p, net, w)
            if not r:
                left.append(p)
                continue
            self._new_stub(r[0], r[1], w, p.GetNet(), net)
            self._new_via(r[1], p.GetNet(), net)
            done.append(p)
            if TM(b.GetWidth()) * TM(b.GetHeight()) > 2.0:          # big pads: a second via
                r2 = self.place(p, net, w, avoid=r[1])
                if r2:
                    self._new_stub(r2[0], r2[1], w, p.GetNet(), net)
                    self._new_via(r2[1], p.GetNet(), net)
        return done, left
