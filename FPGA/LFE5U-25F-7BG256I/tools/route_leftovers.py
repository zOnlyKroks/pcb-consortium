"""Route the connections Freerouting left open (run after route_finish.py / route_cleanup.py).

A grid router on F.Cu / In2 / In3 / B.Cu with rip-up and reroute, one connection at a time:
  - Copper is rasterised at 0.05 mm and a distance transform gives every grid point its distance to foreign copper.
    A track (0.127 mm) may run where that distance is > clearance + width/2.  A via (0.6/0.3, else 0.45/0.2) may sit
    where it is > clearance + via radius on all four signal layers, outside the "+1V1 arm" rule area.
  - Hard obstacles: pads, the locked fan-out, plane-net copper, NPTH holes (0.1 mm bigger: JLC hole-to-copper 0.2).
    Soft obstacles: other nets' unlocked routing.  A path may cross soft copper at a high price; whatever it crosses
    is ripped up, and those nets go back on the queue and get rerouted around it.
  - The B.Cu GND pour is not an obstacle: it refills.
  - A* from the smallest copper island of a net to any other island.  The grid path is then pulled tight: each
    straight piece is as long as the clearance map allows.
The open connections come from KiCad's DRC (kicad-cli), so only nets that are actually unrouted are touched.
Run tools/route_cleanup.py afterwards for any dead-end stubs a rip-up left behind.
"""
import heapq, json, math, os, re, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pcb")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
FM, TM = pcbnew.FromMM, pcbnew.ToMM
X0, Y0, SIZE = 160.0, 30.0, 100.0           # board outline, mm
RES = 0.05                                  # grid, mm
N = int(SIZE / RES)
W, CL, EDGE = 0.127, 0.1, 0.3
VIAS = [(0.6, 0.3), (0.45, 0.2)]
VIA_COST = 1.5 / RES                        # a via costs like 1.5 mm of track
RIP_COST = 4.0                              # per grid step through soft copper; grows with every attempt
PLANES = ("GND", "+3V3", "+1V1")
LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu]
STEPS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
         (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
THR_T = CL + W / 2 + RES * 1.5               # 1.5 cells: rasterising is only good to about a cell
THR_V = [CL + d / 2 + RES * 1.5 for d, _ in VIAS]


def open_nets():
    out = os.path.join(tempfile.gettempdir(), "route_leftovers_drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", out, PCB], capture_output=True)
    nets = []
    for u in json.load(open(out, encoding="utf-8"))["unconnected_items"]:
        m = re.search(r"\[([^\]]*)\]", u["items"][0]["description"])
        if m and m.group(1) not in nets:
            nets.append(m.group(1))
    return nets


def polys(item, layer):
    s = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(s, layer, 0, FM(0.005), pcbnew.ERROR_INSIDE)
    out = []
    for i in range(s.OutlineCount()):
        ol = s.Outline(i)
        out.append([((TM(ol.CPoint(k).x) - X0) / RES, (TM(ol.CPoint(k).y) - Y0) / RES) for k in range(ol.PointCount())])
    return out


class Raster:
    def __init__(self):
        self.img = [Image.new("1", (N, N), 0) for _ in LAYERS]
        self.draw = [ImageDraw.Draw(i) for i in self.img]

    def poly(self, li, pts):
        if len(pts) >= 3:
            self.draw[li].polygon(pts, fill=1)

    def circle(self, li, x, y, r):
        cx, cy, rr = (x - X0) / RES, (y - Y0) / RES, r / RES
        self.draw[li].ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=1)

    def add(self, item):
        for li, L in enumerate(LAYERS):
            if item.IsOnLayer(L):
                for p in polys(item, L):
                    self.poly(li, p)

    def array(self, li):
        return np.array(self.img[li], dtype=bool).T          # [x, y]


def soft(t):
    return not t.IsLocked() and t.GetNetname() not in PLANES


class Grid:
    """Rasters of one board state, seen from one net."""

    def __init__(self, B, net):
        hard, sft, own, thru = Raster(), Raster(), Raster(), Raster()
        for f in B.GetFootprints():
            for p in f.Pads():
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    d = TM(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2 + 0.1
                    for li in range(len(LAYERS)):
                        hard.circle(li, TM(p.GetPosition().x), TM(p.GetPosition().y), d)
                elif p.GetNetname() == net:
                    own.add(p)
                    if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                        thru.circle(0, TM(p.GetPosition().x), TM(p.GetPosition().y), RES)
                else:
                    hard.add(p)
        for t in B.GetTracks():
            if t.GetNetname() == net:
                own.add(t)
                if t.Type() == pcbnew.PCB_VIA_T:
                    thru.circle(0, TM(t.GetPosition().x), TM(t.GetPosition().y), RES)
            else:
                (sft if soft(t) else hard).add(t)
        self.d_hard, self.d_all = [], []
        for li in range(len(LAYERS)):
            h, s = hard.array(li), sft.array(li)
            self.d_hard.append(ndimage.distance_transform_edt(~h) * RES)
            self.d_all.append(ndimage.distance_transform_edt(~(h | s)) * RES)
        # islands: 8-connected per layer, joined across layers only by vias and plated holes
        labs, off = [], 0
        own_a = [own.array(li) for li in range(len(LAYERS))]
        self.inner = np.stack([ndimage.binary_erosion(a) for a in own_a])   # path ends sit this deep in copper
        for li in range(len(LAYERS)):
            lab, n = ndimage.label(own_a[li], structure=np.ones((3, 3)))
            labs.append(np.where(lab > 0, lab + off, 0))
            off += n
        parent = list(range(off + 1))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        tl, tn = ndimage.label(thru.array(0))
        for k in range(1, tn + 1):
            cells = tl == k
            ids = {int(i) for lab in labs for i in np.unique(lab[cells]) if i}
            ids = sorted(ids)
            for i in ids[1:]:
                parent[find(i)] = find(ids[0])
        root = np.array([find(i) for i in range(off + 1)])
        lab = root[np.stack(labs)]
        uniq = np.unique(lab[lab > 0])
        remap = np.zeros(off + 1, int)
        remap[uniq] = np.arange(1, len(uniq) + 1)
        self.lab, self.n = remap[lab], len(uniq)


def route(B, net, arm, hist, rip_cost):
    G = Grid(B, net)
    if G.n < 2:
        return None
    sizes = ndimage.sum(np.ones_like(G.lab), G.lab, range(1, G.n + 1))
    src = int(np.argmin(sizes)) + 1
    tgt = (G.lab > 0) & (G.lab != src) & G.inner
    t_idx = np.argwhere(tgt)
    tx, ty = t_idx[:, 1].mean(), t_idx[:, 2].mean()

    inside = np.zeros((N, N), bool)
    m = int(round((EDGE + W / 2 + 0.05) / RES))
    inside[m:N - m, m:N - m] = True
    ok = np.stack([d > THR_T for d in G.d_hard]) & inside            # legal, maybe through soft copper
    free = np.stack([d > THR_T for d in G.d_all])                     # legal without ripping anything
    via_ok, via_free = [], []
    for k, (dia, _) in enumerate(VIAS):
        e = int(round((EDGE + dia / 2 + 0.05) / RES))
        edge = np.zeros((N, N), bool)
        edge[e:N - e, e:N - e] = True
        via_ok.append(np.logical_and.reduce([d > THR_V[k] for d in G.d_hard]) & ~arm & edge)
        via_free.append(np.logical_and.reduce([d > THR_V[k] for d in G.d_all]))

    def h(x, y):
        dx, dy = abs(x - tx), abs(y - ty)
        return 1.1 * (max(dx, dy) + 0.414 * min(dx, dy))

    best, prev, pq = {}, {}, []
    for l, x, y in np.argwhere((G.lab == src) & G.inner):
        if ok[l, x, y]:
            s = (int(l), int(x), int(y))
            best[s] = 0.0
            heapq.heappush(pq, (h(x, y), 0.0, s))
    end = None
    while pq:
        _, gc, s = heapq.heappop(pq)
        if gc > best.get(s, math.inf):
            continue
        l, x, y = s
        if tgt[l, x, y]:
            end = s
            break
        for dx, dy, c in STEPS:
            nx, ny = x + dx, y + dy
            if not ok[l, nx, ny]:
                continue
            ns = (l, nx, ny)
            ng = gc + c * (1.0 + 0.5 * hist[l, nx, ny]) * (1.0 if free[l, nx, ny] else rip_cost)
            if ng < best.get(ns, math.inf):
                best[ns], prev[ns] = ng, s
                heapq.heappush(pq, (ng + h(nx, ny), ng, ns))
        for k in range(len(VIAS)):
            if via_ok[k][x, y]:
                vc = VIA_COST * (1.0 + 0.3 * k) * (1.0 if via_free[k][x, y] else rip_cost)
                for nl in range(len(LAYERS)):
                    if nl != l and ok[nl, x, y]:
                        ns = (nl, x, y)
                        if gc + vc < best.get(ns, math.inf):
                            best[ns], prev[ns] = gc + vc, s
                            heapq.heappush(pq, (gc + vc + h(x, y), gc + vc, ns))
                break
    if end is None:
        return "fail"
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    vias = [(a[1], a[2], 0 if via_ok[0][a[1], a[2]] else 1) for a, b in zip(path, path[1:]) if a[0] != b[0]]
    for l, x, y in path:                                     # remember where nets fight
        if not free[l, x, y]:
            hist[l, max(0, x - 4):x + 5, max(0, y - 4):y + 5] += 1
    return path, vias


def mm(x, y):
    return X0 + x * RES, Y0 + y * RES


def seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


def rip(B, net, path, vias):
    """Remove the soft copper the new path runs into; return the nets that lost something."""
    pts = [(LAYERS[l], mm(x, y)) for l, x, y in path]
    vpts = [(mm(x, y), VIAS[k][0] / 2) for x, y, k in vias]
    hit, nets = [], set()
    for t in B.GetTracks():
        if t.GetNetname() == net or not soft(t):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            c, r = (TM(t.GetPosition().x), TM(t.GetPosition().y)), TM(t.GetWidth(pcbnew.F_Cu)) / 2
            near = any(math.hypot(q[0] - c[0], q[1] - c[1]) < CL + r + W / 2 for _, q in pts) or \
                any(math.hypot(q[0] - c[0], q[1] - c[1]) < CL + r + rv for q, rv in vpts)
        else:
            a, b = (TM(t.GetStart().x), TM(t.GetStart().y)), (TM(t.GetEnd().x), TM(t.GetEnd().y))
            w2 = TM(t.GetWidth()) / 2
            lo_x, hi_x = min(a[0], b[0]) - 1.0, max(a[0], b[0]) + 1.0
            lo_y, hi_y = min(a[1], b[1]) - 1.0, max(a[1], b[1]) + 1.0
            near = any(L == t.GetLayer() and lo_x <= q[0] <= hi_x and lo_y <= q[1] <= hi_y and
                       seg_dist(q, a, b) < CL + w2 + W / 2 for L, q in pts) or \
                any(lo_x <= q[0] <= hi_x and lo_y <= q[1] <= hi_y and seg_dist(q, a, b) < CL + w2 + rv for q, rv in vpts)
        if near:
            hit.append(t)
    for t in hit:
        nets.add(t.GetNetname())
        B.Remove(t)
    return hit, nets


def pull(G, run):
    """Shortest straight pieces along a same-layer grid run that stay legal."""
    l = run[0][0]
    d = G.d_all[l]
    own = G.lab[l] > 0

    def clear(a, b):
        n = int(max(abs(b[1] - a[1]), abs(b[2] - a[2])) * 2) + 1
        for k in range(n + 1):
            x = int(round(a[1] + (b[1] - a[1]) * k / n))
            y = int(round(a[2] + (b[2] - a[2]) * k / n))
            if not (d[x, y] > THR_T):
                return False
        return True

    out, i = [run[0]], 0
    while i < len(run) - 1:
        j = len(run) - 1
        while j > i + 1 and not clear(run[i], run[j]):
            j -= 1
        out.append(run[j])
        i = j
    return out


def anchor(B, net, layer, q):
    """If q (mm) lands on the middle of one of the net's tracks, split that track there and return the split point,
    so the junction is a track end (route_cleanup.py may then trim the dead part beyond it without cutting us off)."""
    for t in list(B.GetTracks()):
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetname() != net or t.GetLayer() != layer:
            continue
        a, b = (TM(t.GetStart().x), TM(t.GetStart().y)), (TM(t.GetEnd().x), TM(t.GetEnd().y))
        if seg_dist(q, a, b) > TM(t.GetWidth()) / 2 + W / 2:     # our copper overlaps it: join on its centreline
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
        j = (a[0] + u * dx, a[1] + u * dy)
        if math.hypot(j[0] - a[0], j[1] - a[1]) < 0.01:
            return a
        if math.hypot(j[0] - b[0], j[1] - b[1]) < 0.01:
            return b
        n = pcbnew.PCB_TRACK(B)
        n.SetStart(pcbnew.VECTOR2I(FM(j[0]), FM(j[1])))
        n.SetEnd(t.GetEnd())
        n.SetWidth(t.GetWidth())
        n.SetLayer(layer)
        n.SetNet(t.GetNet())
        n.SetLocked(t.IsLocked())
        B.Add(n)
        t.SetEnd(pcbnew.VECTOR2I(FM(j[0]), FM(j[1])))
        return j
    return q


def commit(B, net, path, vias):
    G = Grid(B, net)                                         # after the rip-up: path is legal now
    nc = B.FindNet(net)
    pt = lambda x, y: pcbnew.VECTOR2I(FM(X0 + x * RES), FM(Y0 + y * RES))
    runs, cur = [], [path[0]]
    for a, b in zip(path, path[1:]):
        if a[0] != b[0]:
            runs.append(cur)
            cur = [b]
        else:
            cur.append(b)
    runs.append(cur)
    n_t = 0
    segs = []
    for run in runs:
        if len(run) < 2:
            continue
        p = pull(G, run)
        segs += [(a[0], mm(a[1], a[2]), mm(b[1], b[2])) for a, b in zip(p, p[1:])]
    # both ends of the path must meet the net at a track end (a path may also start or end on a via)
    if segs and segs[0][0] == path[0][0] and segs[0][1] == mm(path[0][1], path[0][2]):
        l, s0, e0 = segs[0]
        segs[0] = (l, anchor(B, net, LAYERS[l], s0), e0)
    if segs and segs[-1][0] == path[-1][0] and segs[-1][2] == mm(path[-1][1], path[-1][2]):
        l, s1, e1 = segs[-1]
        segs[-1] = (l, s1, anchor(B, net, LAYERS[l], e1))
    for l, a, b in segs:
        t = pcbnew.PCB_TRACK(B)
        t.SetStart(pcbnew.VECTOR2I(FM(a[0]), FM(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(FM(b[0]), FM(b[1])))
        t.SetWidth(FM(W))
        t.SetLayer(LAYERS[l])
        t.SetNet(nc)
        B.Add(t)
        n_t += 1
    for x, y, k in vias:
        v = pcbnew.PCB_VIA(B)
        v.SetPosition(pt(x, y))
        v.SetWidth(FM(VIAS[k][0]))
        v.SetDrill(FM(VIAS[k][1]))
        v.SetNet(nc)
        B.Add(v)
    return n_t


def arm_mask(B):
    r = Raster()
    for z in B.Zones():
        if z.GetIsRuleArea() and z.GetDoNotAllowVias():
            ol = z.Outline().Outline(0)
            r.poly(0, [((TM(ol.CPoint(k).x) - X0) / RES, (TM(ol.CPoint(k).y) - Y0) / RES) for k in range(ol.PointCount())])
    return ndimage.binary_dilation(r.array(0), iterations=int(0.35 / RES))   # the via's radius stays out too


if __name__ == "__main__":
    queue = open_nets()
    print("open:", " ".join(queue))
    B = pcbnew.LoadBoard(PCB)
    arm = arm_mask(B)
    attempts, failed = 0, []
    hist = np.zeros((len(LAYERS), N, N), np.float32)        # PathFinder-style congestion history
    while queue and attempts < 400:
        net = queue.pop(0)
        attempts += 1
        r = route(B, net, arm, hist, RIP_COST * (1.0 + attempts / 8.0))
        if r is None:
            continue                                         # already in one piece
        if r == "fail":
            print("  %-16s no path" % net)
            failed.append(net)
            continue
        path, vias = r
        hit, ripped = rip(B, net, path, vias)
        n_t = commit(B, net, path, vias)
        print("  %-16s %2d tracks %d vias %5.1f mm%s" % (net, n_t, len(vias), len(path) * RES,
              ("   ripped %d items of %s" % (len(hit), " ".join(sorted(ripped)))) if hit else ""))
        for n in [net] + sorted(ripped):                     # the net may still have more pieces
            if n not in queue:
                queue.append(n)
    pcbnew.SaveBoard(PCB, B)

    # On the grid, copper closer than a cell looks joined; KiCad wants it to overlap.  Bridge such near misses.
    out = os.path.join(tempfile.gettempdir(), "route_leftovers_drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", out, PCB], capture_output=True)
    B = pcbnew.LoadBoard(PCB)
    lay = {B.GetLayerName(L): L for L in LAYERS}
    for u in json.load(open(out, encoding="utf-8"))["unconnected_items"]:
        a, b = u["items"][:2]
        la = re.search(r" on (\S+)", a["description"]).group(1).rstrip(",")
        lb = re.search(r" on (\S+)", b["description"]).group(1).rstrip(",")
        pa, pb = (a["pos"]["x"], a["pos"]["y"]), (b["pos"]["x"], b["pos"]["y"])
        if la == lb and la in lay and math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < 0.3:
            net = re.search(r"\[([^\]]*)\]", a["description"]).group(1)
            t = pcbnew.PCB_TRACK(B)
            t.SetStart(pcbnew.VECTOR2I(FM(pa[0]), FM(pa[1])))
            t.SetEnd(pcbnew.VECTOR2I(FM(pb[0]), FM(pb[1])))
            t.SetWidth(FM(W))
            t.SetLayer(lay[la])
            t.SetNet(B.FindNet(net))
            B.Add(t)
            print("  %-16s bridged a %.2f mm gap on %s" % (net, math.hypot(pa[0] - pb[0], pa[1] - pb[1]), la))
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    pcbnew.SaveBoard(PCB, B)
    print("saved", PCB, "| failed:", " ".join(failed) or "none", "| still queued:", " ".join(queue) or "none")
