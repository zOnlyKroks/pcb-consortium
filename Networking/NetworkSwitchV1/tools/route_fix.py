"""Route the connections KiCad's DRC still reports as unconnected: a small grid A* router on F.Cu/B.Cu with vias.

Usage: route_fix.py drc.json     (kicad-cli pcb drc --format json output for the current board)
Each unconnected pair (pad / track / via) is routed inside a window around it, keeping the net-class clearance
to every other net (exact pad shapes, tracks, vias, keepouts, board edge).  New copper is added unlocked.
"""
import heapq, json, math, os, re, sys
import numpy as np
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rules

PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "NetworkSwitchV1.kicad_pcb")
FM, TM = pcbnew.FromMM, pcbnew.ToMM
G = float(os.environ.get("RF_GRID", "0.05"))   # grid (mm)
VIA_D, VIA_DRILL = 0.7, 0.3
VIA_COST = 1.5 / G                         # a via costs like 1.5 mm of track
VIA_KEEP = float(os.environ.get("RF_VIA_KEEP", "2.5"))   # no new vias this close to RTL8370N pins
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

B = pcbnew.LoadBoard(PCB)
RULES = rules.Rules(B)


# ---------------------------------------------------------------- copper primitives (mm)
def pad_polys(p, layer):
    s = pcbnew.SHAPE_POLY_SET()
    p.TransformShapeToPolygon(s, layer, 0, FM(0.005), pcbnew.ERROR_INSIDE)
    out = []
    for i in range(s.OutlineCount()):
        ol = s.Outline(i)
        out.append(np.array([(TM(ol.CPoint(k).x), TM(ol.CPoint(k).y)) for k in range(ol.PointCount())]))
    return out


def collect():
    items = []                             # (kind, geom, net, layers)
    for f in B.GetFootprints():
        for p in f.Pads():
            net = str(p.GetNetname())
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                c = p.GetPosition()
                items.append(("circ", (TM(c.x), TM(c.y), TM(p.GetDrillSize().x) / 2 + 0.1), "#HOLE", set(LAYERS)))
                continue
            for L in LAYERS:
                if p.IsOnLayer(L):
                    for poly in pad_polys(p, L):
                        items.append(("poly", poly, net, {L}))
    for t in B.GetTracks():
        net = str(t.GetNetname())
        if t.Type() == pcbnew.PCB_VIA_T:
            c = t.GetPosition()
            items.append(("circ", (TM(c.x), TM(c.y), TM(t.GetWidth(pcbnew.F_Cu)) / 2), net, set(LAYERS)))
        elif t.GetLayer() in LAYERS:
            s, e = t.GetStart(), t.GetEnd()
            items.append(("seg", (TM(s.x), TM(s.y), TM(e.x), TM(e.y), TM(t.GetWidth()) / 2), net, {t.GetLayer()}))
    for z in B.Zones():
        if z.GetIsRuleArea() and (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
            ol = z.Outline().Outline(0)
            pts = np.array([(TM(ol.CPoint(k).x), TM(ol.CPoint(k).y)) for k in range(ol.PointCount())])
            items.append(("poly", pts, "#KEEP", set(LAYERS)))
    return items


def bbox(it):
    k, g = it[0], it[1]
    if k == "circ":
        return g[0] - g[2], g[1] - g[2], g[0] + g[2], g[1] + g[2]
    if k == "seg":
        return min(g[0], g[2]) - g[4], min(g[1], g[3]) - g[4], max(g[0], g[2]) + g[4], max(g[1], g[3]) + g[4]
    return g[:, 0].min(), g[:, 1].min(), g[:, 0].max(), g[:, 1].max()


def seg_dist(X, Y, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return np.hypot(X - x1, Y - y1)
    t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1)
    return np.hypot(X - (x1 + t * dx), Y - (y1 + t * dy))


def dist(it, X, Y):
    k, g = it[0], it[1]
    if k == "circ":
        return np.hypot(X - g[0], Y - g[1]) - g[2]
    if k == "seg":
        return seg_dist(X, Y, *g[:4]) - g[4]
    d = np.full(X.shape, np.inf)
    inside = np.zeros(X.shape, bool)
    n = len(g)
    for i in range(n):
        x1, y1 = g[i]
        x2, y2 = g[(i + 1) % n]
        d = np.minimum(d, seg_dist(X, Y, x1, y1, x2, y2))
        cond = ((y1 > Y) != (y2 > Y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xin = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= cond & (X < xin)
    d[inside] = 0
    return d


# ---------------------------------------------------------------- routing one connection
def route(net, start_items, goal_items, items, margin=float(os.environ.get("RF_MARGIN", "7"))):
    w = RULES.width(net)
    if net.startswith(("Net-(TR4", "MG_")):
        w = 0.22
    hw = w / 2
    pts = [bbox(i) for i in start_items + goal_items]
    x0 = min(p[0] for p in pts) - margin
    y0 = min(p[1] for p in pts) - margin
    x1 = max(p[2] for p in pts) + margin
    y1 = max(p[3] for p in pts) + margin
    eb = B.GetBoardEdgesBoundingBox()
    bx0, by0, bx1, by1 = TM(eb.GetX()), TM(eb.GetY()), TM(eb.GetRight()), TM(eb.GetBottom())
    x0, y0, x1, y1 = max(x0, bx0), max(y0, by0), min(x1, bx1), min(y1, by1)
    nx, ny = int((x1 - x0) / G) + 1, int((y1 - y0) / G) + 1
    xs, ys = x0 + np.arange(nx) * G, y0 + np.arange(ny) * G
    trace_bl = {L: np.zeros((ny, nx), bool) for L in LAYERS}
    neck_bl = {L: np.zeros((ny, nx), bool) for L in LAYERS}
    via_bl = np.zeros((ny, nx), bool)
    mdi = net.startswith(("Net-(TR4", "MG_"))
    NW = 0.15                                              # neck-down width
    u = B.FindFootprintByReference("U301").GetCourtyard(pcbnew.F_CrtYd).BBox()
    Xn, Yn = np.meshgrid(xs, ys)
    neck = mdi & (Xn > TM(u.GetX()) - 2.0) & (Xn < TM(u.GetRight()) + 2.0) &         (Yn > TM(u.GetY()) - 2.0) & (Yn < TM(u.GetBottom()) + 2.0)
    edge = 0.3
    for L in LAYERS:
        X, Y = np.meshgrid(xs, ys)
        trace_bl[L] |= (X < bx0 + edge + hw) | (X > bx1 - edge - hw) | (Y < by0 + edge + hw) | (Y > by1 - edge - hw)
    X, Y = np.meshgrid(xs, ys)
    via_bl |= (X < bx0 + edge + VIA_D / 2) | (X > bx1 - edge - VIA_D / 2) | (Y < by0 + edge + VIA_D / 2) | \
              (Y > by1 - edge - VIA_D / 2)
    for it in items:
        k, g, inet, lays = it
        if inet == net:
            continue
        gap = 0.0 if inet == "#KEEP" else (0.25 if inet == "#HOLE" else RULES.gap(net, inet) + float(os.environ.get("RF_CLR_MARGIN", "0.02")))
        reach = gap + max(hw, VIA_D / 2)
        b = bbox(it)
        if b[2] + reach < x0 or b[0] - reach > x1 or b[3] + reach < y0 or b[1] - reach > y1:
            continue
        i0 = max(0, int((b[0] - reach - x0) / G))
        i1 = min(nx, int((b[2] + reach - x0) / G) + 2)
        j0 = max(0, int((b[1] - reach - y0) / G))
        j1 = min(ny, int((b[3] + reach - y0) / G) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1])
        d = dist(it, Xs, Ys)
        for L in lays:
            if L in trace_bl:
                trace_bl[L][j0:j1, i0:i1] |= d < gap + hw
                neck_bl[L][j0:j1, i0:i1] |= d < gap + NW / 2
        via_bl[j0:j1, i0:i1] |= d < gap + VIA_D / 2
    for L in LAYERS:
        trace_bl[L] = np.where(neck, neck_bl[L] & ~((Xn < bx0 + edge + hw) | (Xn > bx1 - edge - hw)), trace_bl[L])
    for q in B.FindFootprintByReference("U301").Pads():
        c = q.GetPosition()
        via_bl |= np.hypot(Xn - TM(c.x), Yn - TM(c.y)) < VIA_KEEP
    # start / goal cells
    def cells(its):
        out = set()
        for it in its:
            b = bbox(it)
            i0, i1 = max(0, int((b[0] - x0) / G)), min(nx, int((b[2] - x0) / G) + 2)
            j0, j1 = max(0, int((b[1] - y0) / G)), min(ny, int((b[3] - y0) / G) + 2)
            Xs, Ys = np.meshgrid(xs[i0:i1], ys[j0:j1])
            d = dist(it, Xs, Ys)
            jj, ii = np.nonzero(d <= -min(hw, 0.05) if it[0] != "seg" else d <= -0.0)
            if len(jj) == 0:
                jj, ii = np.nonzero(d <= 0)
            for L in it[3]:
                if L in trace_bl:
                    for j, i in zip(jj, ii):
                        out.add((j0 + j, i0 + i, L))
        return out

    S, T = cells(start_items), cells(goal_items)
    if not S or not T:
        return None
    for (j, i, L) in S | T:
        trace_bl[L][j, i] = False
    tj = np.mean([c[0] for c in T])
    ti = np.mean([c[1] for c in T])
    Lidx = {L: k for k, L in enumerate(LAYERS)}
    dirs = [(0, 1, 1.0), (1, 0, 1.0), (0, -1, 1.0), (-1, 0, 1.0),
            (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
    gbest = {}
    heap = []
    for s in S:
        gbest[s] = 0.0
        heapq.heappush(heap, (math.hypot(s[0] - tj, s[1] - ti), 0.0, s, None))
    prev = {}
    found = None
    while heap:
        f, g, s, par = heapq.heappop(heap)
        if g > gbest.get(s, 1e18):
            continue
        if s in prev and par is not None:
            continue
        prev[s] = par
        if s in T:
            found = s
            break
        j, i, L = s
        for dj, di, c in dirs:
            jj, ii = j + dj, i + di
            if 0 <= jj < ny and 0 <= ii < nx and not trace_bl[L][jj, ii]:
                n = (jj, ii, L)
                ng = g + c
                if ng < gbest.get(n, 1e18):
                    gbest[n] = ng
                    heapq.heappush(heap, (ng + math.hypot(jj - tj, ii - ti), ng, n, s))
        if not via_bl[j, i]:
            for L2 in LAYERS:
                if L2 != L and not trace_bl[L2][j, i]:
                    n = (j, i, L2)
                    ng = g + VIA_COST
                    if ng < gbest.get(n, 1e18):
                        gbest[n] = ng
                        heapq.heappush(heap, (ng + math.hypot(j - tj, i - ti), ng, n, s))
    if not found:
        if prev:
            near = min(prev, key=lambda c: math.hypot(c[0] - tj, c[1] - ti))
            print("    no path: explored %d cells, closest (%.2f, %.2f) on %s, goal (%.2f, %.2f); start cells %d" % (
                len(prev), x0 + near[1] * G, y0 + near[0] * G, B.GetLayerName(near[2]), x0 + ti * G, y0 + tj * G, len(S)))
        return None
    path = []
    s = found
    while s is not None:
        path.append(s)
        s = prev.get(s)
    path.reverse()

    # string-pull along each layer run (45-degree multiples only), then emit tracks + vias
    def clear_line(a, b, L):
        n = 2 * max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        for k in range(n + 1):
            j = a[0] + round((b[0] - a[0]) * k / max(n, 1))
            i = a[1] + round((b[1] - a[1]) * k / max(n, 1))
            if trace_bl[L][j, i] and (j, i, L) not in S and (j, i, L) not in T:
                return False
        return True

    def ok45(a, b):
        dj, di = b[0] - a[0], b[1] - a[1]
        return dj == 0 or di == 0 or abs(dj) == abs(di)

    def key(c):
        return (c[2], bool(neck[c[0], c[1]]))

    runs, cur = [], [path[0]]
    for s in path[1:]:
        if key(s) != key(cur[-1]):
            if s[2] == cur[-1][2]:
                cur.append(s)                       # same layer: the boundary point belongs to both runs
            runs.append(cur)
            cur = [s]
        else:
            cur.append(s)
    runs.append(cur)
    netobj = B.FindNet(net)
    made = 0

    def P(c):
        return pcbnew.VECTOR2I(FM(float(x0 + c[1] * G)), FM(float(y0 + c[0] * G)))

    for r in runs:
        L = r[0][2]
        rw = NW if any(neck[c[0], c[1]] for c in r) else w
        pts = [r[0]]
        k = 0
        while k < len(r) - 1:
            best = k + 1
            for m in range(len(r) - 1, k, -1):
                if ok45(r[k], r[m]) and clear_line(r[k], r[m], L):
                    best = m
                    break
            if best == k + 1:                        # no 45-degree shortcut: any angle
                for m in range(len(r) - 1, k + 1, -1):
                    if clear_line(r[k], r[m], L):
                        best = m
                        break
            pts.append(r[best])
            k = best
        for a, b2 in zip(pts, pts[1:]):
            if a[:2] == b2[:2]:
                continue
            t = pcbnew.PCB_TRACK(B)
            t.SetStart(P(a))
            t.SetEnd(P(b2))
            t.SetWidth(FM(rw))
            t.SetLayer(L)
            t.SetNet(netobj)
            B.Add(t)
            made += 1
    for a, b2 in zip(path, path[1:]):
        if a[2] != b2[2]:
            v = pcbnew.PCB_VIA(B)
            v.SetPosition(P(a))
            v.SetWidth(FM(VIA_D))
            v.SetDrill(FM(VIA_DRILL))
            v.SetNet(netobj)
            B.Add(v)
            made += 1
    # connect the first/last point to the item centre if the path starts inside a pad off-centre: not needed,
    # the path cells are inside the copper of start/goal.
    return made


# ---------------------------------------------------------------- map DRC items to copper
def find_item(desc, pos, items):
    x, y = pos["x"], pos["y"]
    m = re.match(r"^(?:PTH |NPTH |SMD )?[Pp]ad (\S+) \[(.*?)\] of (\S+)", desc)
    if m:
        num, net, ref = m.group(1), m.group(2), m.group(3)
        p = [q for q in B.FindFootprintByReference(ref).Pads() if q.GetNumber() == num]
        out = []
        for q in p:
            for L in LAYERS:
                if q.IsOnLayer(L):
                    out += [("poly", poly, net, {L}) for poly in pad_polys(q, L)]
        return net, out
    m = re.match(r"^Via \[(.*?)\]", desc)
    if m:
        net = m.group(1)
        return net, [("circ", (x, y, VIA_D / 2), net, set(LAYERS))]
    m = re.match(r"^Track \[(.*?)\] on ([^\s,]+)", desc)
    if m:
        net, lname = m.group(1), m.group(2)
        L = B.GetLayerID(lname)
        best = None
        for t in B.GetTracks():
            if t.Type() != pcbnew.PCB_VIA_T and str(t.GetNetname()) == net and t.GetLayer() == L:
                s, e = t.GetStart(), t.GetEnd()
                d = float(seg_dist(np.array([x]), np.array([y]), TM(s.x), TM(s.y), TM(e.x), TM(e.y))[0])
                if best is None or d < best[0]:
                    best = (d, t)
        if best and best[0] < 0.05:
            t = best[1]
            s, e = t.GetStart(), t.GetEnd()
            return net, [("seg", (TM(s.x), TM(s.y), TM(e.x), TM(e.y), TM(t.GetWidth()) / 2), net, {L})]
    return None, []


def pad_items(q, net):
    out = []
    for L in LAYERS:
        if q.IsOnLayer(L):
            out += [("poly", poly, net, {L}) for poly in pad_polys(q, L)]
    return out


ok = fail = 0
if sys.argv[1] == "--group":
    import itertools
    order = sys.argv[2].split(",")
    saved = []
    for t in list(B.GetTracks()):
        if str(t.GetNetname()) in order:
            B.Delete(t)
    base = list(B.GetTracks())
    best = None
    for k, perm in enumerate(itertools.permutations(order)):
        if k >= int(os.environ.get("RF_TRIES", "24")):
            break
        made = []
        okc = 0
        for net in perm:
            pads = [q for f in B.GetFootprints() for q in f.Pads() if str(q.GetNetname()) == net]
            before = set(id(t) for t in B.GetTracks())
            r = route(net, pad_items(pads[0], net), pad_items(pads[1], net), collect())
            okc += bool(r)
            if not r:
                break
        print("  order %s: %d/%d" % (" ".join(n.split("-")[-1].rstrip(")") for n in perm), okc, len(perm)))
        if okc == len(perm):
            best = perm
            break
        for t in list(B.GetTracks()):                      # undo this attempt
            if str(t.GetNetname()) in order:
                B.Delete(t)
    if best:
        pcbnew.ZONE_FILLER(B).Fill(B.Zones())
        pcbnew.SaveBoard(PCB, B)
        print("route_fix group: all %d routed" % len(order))
    else:
        print("route_fix group: FAILED (board not saved)")
    sys.exit(0)
if sys.argv[1] == "--nets":
    # rip up these nets completely and route them again, in the order given (pad to pad, then the rest)
    order = sys.argv[2].split(",")
    for net in order:
        for t in list(B.GetTracks()):
            if str(t.GetNetname()) == net:
                B.Delete(t)
    for net in order:
        pads = [q for f in B.GetFootprints() for q in f.Pads() if str(q.GetNetname()) == net]
        if len(pads) < 2:
            continue
        r = route(net, pad_items(pads[0], net), pad_items(pads[1], net), collect())
        print("  %s %-22s %s" % ("routed" if r else "FAILED", net, r or ""))
        ok += bool(r)
        fail += not r
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    pcbnew.SaveBoard(PCB, B)
    print("route_fix: %d routed, %d failed" % (ok, fail))
    sys.exit(0)
d = json.load(open(sys.argv[1], encoding="utf-8"))
for x in d["unconnected_items"]:
    a, b = x["items"][0], x["items"][1]
    net, A = find_item(a["description"], a["pos"], None)
    net2, Bi = find_item(b["description"], b["pos"], None)
    if not A or not Bi or net != net2:
        print("  skip (cannot map):", a["description"][:50], "|", b["description"][:50])
        fail += 1
        continue
    r = route(net, A, Bi, collect())
    if r:
        ok += 1
        print("  routed %-22s %d items" % (net, r))
    else:
        fail += 1
        print("  FAILED %s: %s | %s" % (net, a["description"][:45], b["description"][:45]))
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
print("route_fix: %d routed, %d failed" % (ok, fail))
