"""BGA fan-out + plane fan-out for the ECP5 emulation board.  Run after place_pcb.py.

Re-running is safe as long as nothing is routed yet: it strips all (locked) fan-out copper and starts over, and it
refuses to run once the board has unlocked tracks.

caBGA-256, 0.8 mm pitch, 0.36 mm balls.  Balls sit on (row, col), vias on the interstitials (row +- .5, col +- .5).
Each ball belongs to the side (T/L/R/B) of the ring it sits in; 197 balls need an escape.
  ring 0 signals     F.Cu, straight out
  ring 1 signals     F.Cu, 45 deg into the channel between two ring-0 balls, then straight out
  ring 2, some       F.Cu, straight out through a ring-0 channel that ring 1 left free (no via)
  ring >= 2, rest    dog-bone via + 0.1 mm B.Cu escape, found by a maze router
  GND / +3V3 / +1V1  dog-bone via to the planes; ring-1 ones go into a spare ring-0 channel, ring-0 ones get a via
                     just outside the package, deep core +3V3 balls (F7, H7) link to their neighbour on F.Cu
All escapes end 1.6 mm outside the outer ball row, so routing starts outside the BGA.

Why it is done this way: with straight lanes, the ring of ring-2 vias is a wall.  Between two vias 0.8 mm apart only
one track passes, and between two neighbouring via walls there is only one sideways lane, so rings 3-4 cannot reach
the gaps.  Hence (1) ring 2 goes out on F.Cu wherever a channel is free, which empties its interstitial on B.Cu;
(2) B.Cu escapes use 0.1 mm tracks on a 0.2 mm grid, so an empty interstitial passes 5 tracks instead of 3;
(3) the router picks each signal's via interstitial together with its path (PathFinder negotiated congestion), so
the gaps end up where the deep balls need them.

In4 is +3V3 with a +1V1 island, but the core VCC balls are ringed by VCCIO balls.  The island is the core square
(interstitials 5.5..9.5; +3V3 vias stay on ring 4.5), an arm up the middle of the top side (interstitial column 7.5
kept free of vias) and a bar above the BGA that holds every +1V1 capacitor and C220 from the regulator.
All six 100 nF +1V1 caps sit in the top corners for that (C224/C225 swap places with C242/C243).  The inner planes
use 0.1 mm clearance and 0.1 mm minimum width, so copper still flows between two vias 0.8 mm apart.

Every other SMD pad on GND / +3V3 / +1V1 gets a short stub + via into its plane where one fits (QFN GND pins go
into the exposed pad).  All fan-out copper is locked, so Freerouting keeps it.
"""
import json, math, os, re, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pcb")
PRO = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pro")
X0, Y0 = 160.0, 30.0
FM, TM = pcbnew.FromMM, pcbnew.ToMM
ROWS = "ABCDEFGHJKLMNPRT"
P = 0.8                                   # ball pitch
VIA_D, VIA_DRILL = 0.45, 0.2              # BGA: 0.125 mm ring; JLC charges extra only below a 0.45 mm pad
FAN_VIAS = [(0.7, 0.3), (0.6, 0.3), (VIA_D, VIA_DRILL)]   # cap fan-out: biggest that fits
R = VIA_D / 2
W_SIG, W_PWR, W_FAN = 0.12, 0.2, 0.3
OUT = -2.0                                # escapes end 2 pitches outside the outer ball row
PLANES = ("GND", "+3V3", "+1V1")
PWR = pcbnew.In4_Cu                       # +3V3 plane with the +1V1 island; In1 GND, In2/In3 signals
ZONE_CL, ZONE_MIN = 0.1, 0.1                # inner planes: a 0.15 mm web still fits between two vias 0.8 mm apart
sys.setrecursionlimit(10000)

# ---------------------------------------------------------------- clean previous run (all fan-out copper is locked)
# done on the file text: removing a thousand tracks through the python API breaks SWIG's object wrapping
txt = open(PCB, encoding="utf-8").read()
items_re = re.compile(r"\n\t\((?:segment|via|arc)\n.*?\n\t\)(?=\n)", re.S)
old_cu = items_re.findall(txt)
if any("(locked yes)" not in t for t in old_cu):
    sys.exit("board already has unlocked (routed) tracks - fan-out would have to be redone by hand")
if old_cu:
    open(PCB, "w", encoding="utf-8").write(items_re.sub("", txt))
B = pcbnew.LoadBoard(PCB)
U1 = B.FindFootprintByReference("U1")
nets = B.GetNetsByName()

# ---------------------------------------------------------------- +1V1 caps to the top corners
def swap(a, b):
    """Swap two identical footprints; the reference labels stay where the silk pass put them."""
    fa, fb = B.FindFootprintByReference(a), B.FindFootprintByReference(b)
    pa, pb, ra, rb = fa.GetPosition(), fb.GetPosition(), fa.GetOrientationDegrees(), fb.GetOrientationDegrees()
    la, lb = [(f.Reference().GetPosition(), f.Reference().GetTextAngleDegrees(), f.Reference().IsVisible()) for f in (fa, fb)]
    fa.SetPosition(pb); fa.SetOrientationDegrees(rb)
    fb.SetPosition(pa); fb.SetOrientationDegrees(ra)
    for f, (pos, ang, vis) in ((fa, lb), (fb, la)):
        f.Reference().SetPosition(pos)
        f.Reference().SetTextAngleDegrees(ang)
        f.Reference().SetVisible(vis)


if B.FindFootprintByReference("C224").GetPosition().y > U1.GetPosition().y:
    swap("C224", "C242")
    swap("C225", "C243")

# ---------------------------------------------------------------- ball grid
balls = {}
for p in U1.Pads():
    n = p.GetNumber()
    balls[(ROWS.index(n[0]), int(n[1:]) - 1)] = p
A1 = balls[(0, 0)].GetPosition()
assert abs(TM(balls[(15, 15)].GetPosition().x - A1.x) - 15 * P) < 1e-3


def G(r, c):
    """Grid position (row, col, may be fractional) -> board IU."""
    return pcbnew.VECTOR2I(A1.x + FM(c * P), A1.y + FM(r * P))


def to_rc(s, d, a):
    return {"T": (d, a), "B": (15 - d, a), "L": (a, d), "R": (a, 15 - d)}[s]


def to_da(s, r, c):
    return {"T": (r, c), "B": (15 - r, c), "L": (c, r), "R": (15 - c, r)}[s]


def net_of(p):
    n = str(p.GetNetname())
    return "" if not n or n.startswith("unconnected") else n


def ring(r, c):
    return min(r, c, 15 - r, 15 - c)


def sides(r, c):
    k = ring(r, c)
    return [s for s, v in zip("TLRB", (r, c, 15 - c, 15 - r)) if v == k]


def h(x):                                 # half-grid key
    return int(round(2 * x))


def in_core(sr, sc):                      # interstitial inside the +1V1 island core
    return 5.5 <= sr <= 9.5 and 5.5 <= sc <= 9.5


ARM = {(h(r + 0.5), h(7.5)) for r in range(5)}                      # top side, interstitial column 7.5
LINK_KEEP = {(h(6.5), h(5.5)), (h(7.5), h(5.5)), (h(8.5), h(5.5))}  # next to the F.Cu +3V3 links F7-F6 / H7-H6

# ---------------------------------------------------------------- slot candidates
items, cands, kind = [], {}, {}
outside = []                                                        # (net, ball rc, via rc)
for (r, c), p in sorted(balls.items()):
    n = net_of(p)
    if not n:
        continue
    k = ring(r, c)
    if n in PLANES:
        if k == 0:
            if len(sides(r, c)) == 2:                               # package corner: diagonal
                v = (r + (-0.75 if r == 0 else 0.75), c + (-0.75 if c == 0 else 0.75))
            else:
                s = sides(r, c)[0]
                d, a = to_da(s, r, c)
                v = to_rc(s, -1.0, a)
            outside.append((n, (r, c), v))
            continue
        opts = []
        for dr in (-0.5, 0.5):
            for dc in (-0.5, 0.5):
                sr, sc = r + dr, c + dc
                key = (h(sr), h(sc))
                if key in ARM or key in LINK_KEEP:
                    continue
                if n == "+1V1" and not in_core(sr, sc):
                    continue
                if n == "+3V3" and in_core(sr, sc):
                    continue
                # ring 1: outwards, into a spare ring-0 channel (ring 1.5 is the wall rings 3-5 have to cross);
                # deeper balls: deepest first
                opts.append((ring(sr, sc) if k == 1 else -ring(sr, sc), key))
        kind[(r, c)] = "plane"
        cands[(r, c)] = [(None, key) for _, key in sorted(opts)]
    else:
        lst = []
        for s in sides(r, c):
            d, a = to_da(s, r, c)
            if k == 0:
                continue
            for da in (-0.5, 0.5):
                sr, sc = to_rc(s, d - 0.5, a + da)
                key = (h(sr), h(sc))
                if k >= 2 and (key in ARM or key in LINK_KEEP):
                    continue
                lst.append((s, key))
        kind[(r, c)] = "fcu0" if k == 0 else ("chan" if k == 1 else "via")
        cands[(r, c)] = lst
    items.append((r, c))

owner, assign, blocked = {}, {}, set()


def augment(it, seen):
    for s, key in cands[it]:
        if key in seen or key in blocked:
            continue
        seen.add(key)
        if key not in owner or augment(owner[key], seen):
            owner[key] = it
            assign[it] = (s, key)
            return True
    return False


# stage 1, the ring-0 channels: ring-1 signals and ring-1 plane vias must get one; ring-2 signals take what is left
# and escape straight out on F.Cu.  That leaves their ring-1.5 interstitial empty, which is what the B.Cu escapes of
# rings 3-5 need to get through the ring of ring-2 vias.  Left/right first: their ring 1 has GND balls too.
cands1, k1_of = {}, {}
for it in items:
    if kind[it] == "chan":
        cands1[it] = cands[it]
    elif kind[it] == "plane" and ring(*it) == 1:                     # channel slots only; ring 1.5 is the wall
        cands1[it] = [(s, key) for s, key in cands[it] if ring(key[0] / 2, key[1] / 2) == 0.5]
    elif kind[it] == "via" and ring(*it) == 2:
        cands1[it] = []
        for s in sides(*it):
            d, a = to_da(s, *it)
            for da in (-0.5, 0.5):
                k0 = tuple(h(x) for x in to_rc(s, 0.5, a + da))
                cands1[it].append((s, k0))
                k1_of[(it, k0)] = (tuple(h(x) for x in to_rc(s, 1.5, a + da)), a + da)
stage = cands
cands = cands1
for it in sorted(cands1, key=lambda it: ({"chan": 0, "plane": 1, "via": 2}[kind[it]],
                                         sides(*it)[0] in "TB", len(cands1[it]))):
    if not augment(it, set()) and kind[it] != "via":
        print("no channel for", balls[it].GetNumber(), net_of(balls[it]))
cands = stage
fcu2 = {}
for it in [it for it in assign if kind[it] == "via"]:
    s, k0 = assign.pop(it)
    k1, a = k1_of[(it, k0)]
    if k1 in owner:                                                 # a ring-1 plane via sits there: no F.Cu escape
        del owner[k0]
        continue
    fcu2[it] = (s, k1, a)
    kind[it] = "fcu2"
    blocked |= {k0, k1}
    del owner[k0]
# stage 2: plane vias, deepest free interstitial first.  The signal vias are chosen by the router below.
links = []
for it in sorted((it for it in items if kind[it] == "plane" and it not in assign), key=lambda it: len(cands[it])):
    if not cands[it]:
        links.append(it)
        continue
    if not augment(it, set()):
        print("no interstitial for", balls[it].GetNumber(), net_of(balls[it]))
taken = set(owner) | blocked | ARM | LINK_KEEP

# ---------------------------------------------------------------- B.Cu escapes: negotiated-congestion maze routing
# Nodes on a 0.2 mm grid (quarter pitch), 8-connected, 0.1 mm tracks: neighbouring nodes can both carry one.
# Each ring >= 2 signal also picks its via here, on one of the ball's four free interstitials; a via claims its node
# and the 8 around it (closer than 0.1 mm to a track).  Escapes may not share a node, and a diagonal step also
# claims the other two corners of its cell (0.14 mm away).  An escape may leave the package on any side.
# PathFinder: rip up and reroute the escapes that share something, raising the price of shared nodes each pass.
import heapq, collections

W_ESC = 0.1
U = P / 4                                                              # grid step, mm
CLR = R + W_ESC / 2 + 0.1 - 1e-6
LO, HI = int(4 * OUT), int(4 * (15 - OUT))
fixed = [(2 * k[0], 2 * k[1]) for k, it in owner.items() if kind[it] == "plane"] + \
        [(4 * v[0], 4 * v[1]) for _, _, v in outside]


def seg_d(p, q, v):                                                    # point-segment distance, mm
    (ax, ay), (bx, by), (px, py) = p, q, v
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(ax + t * dx - px, ay + t * dy - py) * U


near_v = collections.defaultdict(list)
for v in fixed:
    for a_ in range(int(math.floor(v[0])) - 4, int(math.ceil(v[0])) + 5):
        for b_ in range(int(math.floor(v[1])) - 4, int(math.ceil(v[1])) + 5):
            near_v[(a_, b_)].append(v)


def clear(p, q):
    return all(seg_d(p, q, v) >= CLR for v in near_v.get(p, []) + near_v.get(q, []))


STEPS = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
nb = {}
for i in range(LO, HI + 1):
    for j in range(LO, HI + 1):
        if clear((i, j), (i, j)):
            nb[(i, j)] = [((i + di, j + dj), di != 0 and dj != 0) for di, dj in STEPS
                          if LO <= i + di <= HI and LO <= j + dj <= HI and clear((i, j), (i + di, j + dj))]

slot_opts = {}
for it in items:
    if kind[it] != "via":
        continue
    r, c = it
    out_ = {(h(r + dr), h(c + dc)) for s in sides(r, c) for dr, dc in ((-0.5, -0.5), (-0.5, 0.5), (0.5, -0.5), (0.5, 0.5))
            if ring(r + dr, c + dc) < ring(r, c)}
    opts = []
    for dr in (-0.5, 0.5):
        for dc in (-0.5, 0.5):
            key = (h(r + dr), h(c + dc))
            q = (2 * key[0], 2 * key[1])
            if key in taken or q not in nb:
                continue
            opts.append((key, 0.0 if key in out_ else 3.0))                # outward interstitials preferred
    slot_opts[it] = opts
    if not opts:
        print("no free interstitial for", balls[it].GetNumber(), net_of(balls[it]))


def block(key):
    ci, cj = 2 * key[0], 2 * key[1]
    return {(ci + di, cj + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)}


def dist_exit(n):
    i, j = n
    return min(i - LO, HI - i, j - LO, HI - j)


def claims(sol):
    key, path = sol
    out = {("v",) + key} | block(key) | set(path)
    for a_, b_ in zip(path, path[1:]):
        if a_[0] != b_[0] and a_[1] != b_[1]:
            out |= {(a_[0], b_[1]), (b_[0], a_[1])}
    return out


occ, hist, sols = collections.Counter(), collections.Counter(), {}


def price(x, pf):
    return (1 + hist[x]) * (1 + pf * occ[x])


def astar(it, pf):
    best, prev, src = {}, {}, {}
    pq = []
    for key, pref in slot_opts[it]:
        q = (2 * key[0], 2 * key[1])
        g = pref + sum(price(x, pf) - 1 for x in block(key) | {("v",) + key})
        if g < best.get(q, math.inf):
            best[q], src[q] = g, key
            heapq.heappush(pq, (g + dist_exit(q), g, q))
    while pq:
        f_, g, n = heapq.heappop(pq)
        if g > best[n] + 1e-9:
            continue
        if dist_exit(n) == 0:
            path = [n]
            while n in prev:
                n = prev[n]
                path.append(n)
            return src[n], path[::-1]
        dn = dist_exit(n)
        for q, diag in nb[n]:
            dq = dist_exit(q)
            step = (1.414 if diag else 1.0) + (0.5 if dq > dn else 0.0)
            c = price(q, pf)
            if diag:
                c += price((n[0], q[1]), pf) + price((q[0], n[1]), pf) - 2
            ng = g + step * c
            if ng < best.get(q, math.inf) - 1e-9:
                best[q], prev[q], src[q] = ng, n, src[n]
                heapq.heappush(pq, (ng + dq, ng, q))
    return None


esc = sorted((it for it in slot_opts if slot_opts[it]), key=lambda it: -ring(*it))
pf, todo_r = 0.5, list(esc)
for it_no in range(300):
    for it in todo_r:
        if it in sols:
            for r_ in claims(sols.pop(it)):
                occ[r_] -= 1
        sol = astar(it, pf)
        if sol is None:
            continue
        sols[it] = sol
        for r_ in claims(sol):
            occ[r_] += 1
    over = {r_ for r_, v in occ.items() if v > 1}
    if not over:
        break
    for r_ in over:
        hist[r_] += 1
    pf = min(pf * 1.15, 50.0)
    todo_r = [it for it in esc if it not in sols or claims(sols[it]) & over]
over = {r_ for r_, v in occ.items() if v > 1}
conflict = {it for it in sols if claims(sols[it]) & over}
paths = {}
for it, (key, path) in sols.items():
    if it in conflict:
        continue
    r, c = it
    assign[it] = (sides(r, c)[0], key)
    owner[key] = it
    paths[it] = path
print("B.Cu escape routing: %d passes, %d/%d clean" % (it_no + 1, len(paths), len([it for it in items if kind[it] == "via"])))
for it in items:
    if kind[it] == "via" and it not in paths:
        print("  no B.Cu escape for", balls[it].GetNumber(), net_of(balls[it]))
vias = {key: it for key, it in owner.items() if kind[it] in ("via", "plane")}   # half-grid key -> ball


def corners(path):
    """Drop the intermediate points of straight runs."""
    out = [path[0]]
    for k in range(1, len(path) - 1):
        a_, b_, c_ = path[k - 1], path[k], path[k + 1]
        if (b_[0] - a_[0], b_[1] - a_[1]) != (c_[0] - b_[0], c_[1] - b_[1]):
            out.append(b_)
    out.append(path[-1])
    return out


# ---------------------------------------------------------------- copper
made = {"track": 0, "via": 0}


def track(a, b, w, net, layer):
    if a == b:
        return None
    t = pcbnew.PCB_TRACK(B)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(FM(w))
    t.SetLayer(layer)
    t.SetNet(nets[net])
    t.SetLocked(True)
    B.Add(t)
    made["track"] += 1
    return t


def via(c, net, d=VIA_D, drill=VIA_DRILL):
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(c)
    v.SetWidth(FM(d))
    v.SetDrill(FM(drill))
    v.SetNet(nets[net])
    v.SetLocked(True)
    B.Add(v)
    made["via"] += 1


F, BC = pcbnew.F_Cu, pcbnew.B_Cu
for it in items:
    r, c = it
    n = net_of(balls[it])
    k = kind[it]
    if k == "fcu0":
        s = sides(r, c)[0]
        d, a = to_da(s, r, c)
        track(G(r, c), G(*to_rc(s, OUT, a)), W_SIG, n, F)
    elif k == "fcu2":
        s, key, a = fcu2[it]
        track(G(r, c), G(key[0] / 2, key[1] / 2), W_SIG, n, F)
        track(G(key[0] / 2, key[1] / 2), G(*to_rc(s, OUT, a)), W_SIG, n, F)
    elif it in assign and k == "chan":
        s, key = assign[it]
        d, a = to_da(s, key[0] / 2, key[1] / 2)
        track(G(r, c), G(key[0] / 2, key[1] / 2), W_SIG, n, F)
        track(G(key[0] / 2, key[1] / 2), G(*to_rc(s, OUT, a)), W_SIG, n, F)
    elif it in assign:
        s, key = assign[it]
        v = G(key[0] / 2, key[1] / 2)
        track(G(r, c), v, W_PWR if k == "plane" else W_SIG, n, F)
        via(v, n)
        if k == "via" and it in paths:
            pts = corners(paths[it])
            for a_, b_ in zip(pts, pts[1:]):
                track(G(a_[0] / 4, a_[1] / 4), G(b_[0] / 4, b_[1] / 4), W_ESC, n, BC)
for n, rc, v in outside:
    track(G(*rc), G(*v), W_PWR, n, F)
    via(G(*v), n)
for r, c in links:                                                   # +3V3 balls deep in the core: to a neighbour
    n = net_of(balls[(r, c)])
    nb = [(r + dr, c + dc) for dr, dc in ((0, -1), (0, 1), (-1, 0), (1, 0))
          if net_of(balls.get((r + dr, c + dc), balls[(r, c)])) == n and (r + dr, c + dc) in assign]
    assert nb, balls[(r, c)].GetNumber()
    track(G(r, c), G(*nb[0]), W_PWR, n, F)
bga = dict(made)
print("BGA: %d tracks, %d vias, %d F.Cu escapes, %d B.Cu escapes, %d links" % (
    made["track"], made["via"], sum(kind[i] in ("fcu0", "chan", "fcu2") for i in items), len(paths), len(links)))

# ---------------------------------------------------------------- planes: In1 GND, In4 +3V3 with the +1V1 island
def rect(x0, y0, x1, y1):
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        s.Append(FM(X0 + x), FM(Y0 + y))
    return s


bx, by = TM(A1.x) - X0, TM(A1.y) - Y0                                # ball A1, local mm
island = pcbnew.SHAPE_POLY_SET()
for x0, y0, x1, y1 in [
        (bx + 5.0 * P, by + 5.0 * P, bx + 10.0 * P, by + 10.0 * P),     # core: interstitials 5.5 .. 9.5
        (bx + 7.0 * P, by - 6.0, bx + 8.0 * P, by + 5.0 * P),             # arm up interstitial column 7.5
        (bx + 4.4, by - 6.0, bx + 7.6, by - 0.6),                       # arm widened outside the package
        (31.3, 23.3, 56.6, 27.0),                                       # bar: C220 (regulator side) .. C221
        (33.1, 26.5, 35.1, 32.7),                                       # top-left +1V1 caps
        (51.4, 26.5, 53.1, 32.7)]:                                      # top-right +1V1 caps
    island.BooleanAdd(rect(x0, y0, x1, y1))
island.Simplify()
assert island.OutlineCount() == 1, island.OutlineCount()

for z in list(B.Zones()):
    if (z.GetNetname() == "+1V1" and z.GetLayer() == PWR) or z.GetZoneName() == "+1V1 arm":
        B.Remove(z)
    elif z.GetLayer() in (pcbnew.In1_Cu, PWR):
        z.SetLocalClearance(FM(ZONE_CL))
        z.SetMinThickness(FM(ZONE_MIN))
z = pcbnew.ZONE(B)
z.SetLayer(PWR)
z.SetNet(nets["+1V1"])
z.SetAssignedPriority(1)
z.SetLocalClearance(FM(ZONE_CL))
z.SetMinThickness(FM(ZONE_MIN))
ol = island.COutline(0)
z.Outline().NewOutline()
for i in range(ol.PointCount()):
    q = ol.CPoint(i)
    z.Outline().Append(q.x, q.y)
B.Add(z)

# the arm is the only feed into the core: no router vias in it
ka = pcbnew.ZONE(B)
ka.SetIsRuleArea(True)
ka.SetZoneName("+1V1 arm")
ka.SetLayer(PWR)
ka.SetDoNotAllowVias(True)
for f in (ka.SetDoNotAllowTracks, ka.SetDoNotAllowPads, ka.SetDoNotAllowFootprints, ka.SetDoNotAllowZoneFills):
    f(False)
arm = pcbnew.SHAPE_POLY_SET()
arm.BooleanAdd(rect(bx + 7.0 * P, by - 6.0, bx + 8.0 * P, by + 5.0 * P))
arm.BooleanAdd(rect(bx + 4.4, by - 6.0, bx + 7.6, by - 0.6))
arm.Simplify()
ol = arm.COutline(0)
ka.Outline().NewOutline()
for i in range(ol.PointCount()):
    q = ol.CPoint(i)
    ka.Outline().Append(q.x, q.y)
B.Add(ka)

# every BGA via must land in its own plane region
ins = pcbnew.SHAPE_POLY_SET(island)
ins.Deflate(FM(R + 0.05), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))
outs = pcbnew.SHAPE_POLY_SET(island)
outs.Inflate(FM(R + ZONE_CL + 0.01), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))
for t in B.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        if t.GetNetname() == "+1V1":
            assert ins.Contains(t.GetPosition()), TM(t.GetPosition().x)
        elif t.GetNetname() == "+3V3":
            assert not outs.Contains(t.GetPosition()), (TM(t.GetPosition().x) - X0, TM(t.GetPosition().y) - Y0)

# ---------------------------------------------------------------- plane fan-out of the other SMD pads
CL = 0.15
CELL = FM(2.0)
grid = {}


def add(item, bb):
    for i in range(int(bb[0] // CELL) - 1, int(bb[2] // CELL) + 2):
        for j in range(int(bb[1] // CELL) - 1, int(bb[3] // CELL) + 2):
            grid.setdefault((i, j), []).append(item)


def near(c, rad=3.0):
    seen, out = set(), []
    rr = FM(rad)
    for i in range(int((c.x - rr) // CELL), int((c.x + rr) // CELL) + 1):
        for j in range(int((c.y - rr) // CELL), int((c.y + rr) // CELL) + 1):
            for it in grid.get((i, j), ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    out.append(it)
    return out


for f in B.GetFootprints():
    for p in f.Pads():
        b = p.GetBoundingBox()
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            add(("hole", p.GetPosition(), FM(TM(p.GetDrillSize().x) / 2 + 0.25), ""),
                (b.GetX(), b.GetY(), b.GetRight(), b.GetBottom()))
            continue
        sps = pcbnew.SHAPE_POLY_SET()
        p.TransformShapeToPolygon(sps, pcbnew.F_Cu, 0, FM(0.005), pcbnew.ERROR_INSIDE)
        add(("pad", sps, p, str(p.GetNetname())), (b.GetX(), b.GetY(), b.GetRight(), b.GetBottom()))


def add_track(t):
    s, e = t.GetStart(), t.GetEnd()
    w = t.GetWidth() // 2
    add(("seg", pcbnew.SEG(s, e), w, str(t.GetNetname()), t.GetLayer()),
        (min(s.x, e.x) - w, min(s.y, e.y) - w, max(s.x, e.x) + w, max(s.y, e.y) + w))


def add_via(c, net):
    add(("via", c, FM(R), net), (c.x - FM(R), c.y - FM(R), c.x + FM(R), c.y + FM(R)))


for t in B.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        add(("via", t.GetPosition(), t.GetWidth(pcbnew.F_Cu) // 2, str(t.GetNetname())),
            (t.GetPosition().x - FM(R), t.GetPosition().y - FM(R), t.GetPosition().x + FM(R), t.GetPosition().y + FM(R)))
    else:
        add_track(t)

_allowed = {}


def allowed(net):
    """Where a via of the current size R may sit for its plane (cached per size)."""
    if (net, R) not in _allowed:
        inset = rect(0.0, 0.0, 100.0, 100.0)
        inset.Deflate(FM(R + 0.35), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))
        if net == "GND":
            a = inset
        elif net == "+1V1":
            a = pcbnew.SHAPE_POLY_SET(island)
            a.Deflate(FM(R + ZONE_CL + 0.05), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))
        else:
            a = pcbnew.SHAPE_POLY_SET(inset)
            grow = pcbnew.SHAPE_POLY_SET(island)
            grow.Inflate(FM(R + ZONE_CL + 0.05), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))
            a.BooleanSubtract(grow)
        _allowed[(net, R)] = a
    return _allowed[(net, R)]

cy = U1.GetCourtyard(pcbnew.F_CrtYd).BBox()
ux0, uy0, ux1, uy1 = TM(cy.GetX()) - X0, TM(cy.GetY()) - Y0, TM(cy.GetRight()) - X0, TM(cy.GetBottom()) - Y0
NOVIA = [(ux0 - 0.3, uy0 - 0.3, ux1 + 0.3, uy1 + 0.3),                    # package + escape ends
         (ux0 + 2.6, uy0 - 6.0, ux1 - 2.6, uy0), (ux0 + 2.6, uy1, ux1 - 2.6, uy1 + 6.0),   # escape fields
         (ux0 - 6.0, uy0 + 2.6, ux0, uy1 - 2.6), (ux1, uy0 + 2.6, ux1 + 6.0, uy1 - 2.6)]


def spot_ok(net, pad, pc, c, w):
    if not allowed(net).Contains(c):
        return False
    x, y = TM(c.x) - X0, TM(c.y) - Y0
    if any(b[0] - R < x < b[2] + R and b[1] - R < y < b[3] + R for b in NOVIA):
        return False
    seg = pcbnew.SEG(pc, c)
    for it in near(c):
        k = it[0]
        if k == "hole":
            if (it[1] - c).EuclideanNorm() < it[2] + FM(R) or math.sqrt(seg.SquaredDistance(it[1])) < it[2] + FM(w / 2):
                return False
        elif k == "via":
            g = 0.25 if it[3] == net else CL
            if (it[1] - c).EuclideanNorm() < it[2] + FM(R + g):
                return False
            if it[3] != net and math.sqrt(seg.SquaredDistance(it[1])) < it[2] + FM(w / 2 + CL):
                return False
        elif k == "seg":
            if it[3] == net:
                continue
            if math.sqrt(it[1].SquaredDistance(c)) < it[2] + FM(R + CL):
                return False
            if it[4] == pcbnew.F_Cu and math.sqrt(seg.SquaredDistance(it[1])) < it[2] + FM(w / 2 + CL):
                return False
        else:
            d = math.sqrt(it[1].SquaredDistance(c))
            if it[2] is pad or it[3] == net:
                if d < FM(R + 0.05):                                        # never a via in a pad
                    return False
                continue
            if d < FM(R + CL) or math.sqrt(it[1].SquaredDistanceToSeg(seg)) < FM(w / 2 + CL):
                return False
    return True


def fan(p, net, w, avoid=None):
    pc, fc = p.GetPosition(), p.GetParentFootprint().GetPosition()
    v = pc - fc
    base = math.atan2(v.y, v.x) if v.EuclideanNorm() > FM(0.1) else math.pi / 2
    b = p.GetBoundingBox()
    hx, hy = TM(b.GetWidth()) / 2, TM(b.GetHeight()) / 2
    cs = []
    for k in range(0, 9):
        for sgn in ((1,) if k in (0, 8) else (1, -1)):
            ang = base + sgn * k * math.pi / 8
            ca, sa = math.cos(ang), math.sin(ang)
            t = min(hx / abs(ca) if abs(ca) > 1e-6 else 1e9, hy / abs(sa) if abs(sa) > 1e-6 else 1e9)
            for gap in (0.1, 0.25, 0.4, 0.6, 0.9, 1.3, 1.8, 2.4, 3.0):
                cs.append((gap + 0.2 * k, ang, t + R + gap))
    for _, ang, d in sorted(cs):
        c = pcbnew.VECTOR2I(int(pc.x + FM(d * math.cos(ang))), int(pc.y + FM(d * math.sin(ang))))
        if avoid is not None and (c - avoid).EuclideanNorm() < FM(1.0):
            continue
        if spot_ok(net, p, pc, c, w):
            return c
    return None


ep_done, left = 0, []
todo = []
for f in B.GetFootprints():
    if f.GetReference() == "U1":
        continue
    for p in f.Pads():
        net = str(p.GetNetname())
        if net in PLANES and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
            d = (p.GetPosition() - U1.GetPosition()).EuclideanNorm()
            todo.append((d, f.GetReference(), p.GetNumber(), p))
for _, ref, num, p in sorted(todo, key=lambda t: t[0]):
    R = VIA_D / 2
    net = str(p.GetNetname())
    b = p.GetBoundingBox()
    bw, bh = TM(b.GetWidth()), TM(b.GetHeight())
    if bw * bh > 4.0 and (p.GetPosition() - p.GetParentFootprint().GetPosition()).EuclideanNorm() < FM(0.2):
        pc = p.GetPosition()                                                # exposed pad: vias in the pad
        for dx, dy in ((-0.6, -0.6), (0.6, -0.6), (-0.6, 0.6), (0.6, 0.6)):
            c = pcbnew.VECTOR2I(pc.x + FM(dx), pc.y + FM(dy))
            via(c, net)
            add_via(c, net)
        ep_done += 1
        continue
    w = min(W_FAN, bw, bh)
    for vd, vdrill in FAN_VIAS:
        R = vd / 2
        c = fan(p, net, w)
        if c is not None:
            break
    fpp = p.GetParentFootprint()
    ep = [q for q in fpp.Pads() if q.GetNetname() == net and q.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
          and TM(q.GetBoundingBox().GetWidth()) * TM(q.GetBoundingBox().GetHeight()) > 4.0
          and (q.GetPosition() - fpp.GetPosition()).EuclideanNorm() < FM(0.2) and q.GetNumber() != p.GetNumber()]
    if c is None and ep:                                                    # QFN GND pin: straight into the exposed pad
        pc, eb = p.GetPosition(), ep[0].GetBoundingBox()
        tgt = pcbnew.VECTOR2I(min(max(pc.x, eb.GetX() + FM(0.3)), eb.GetRight() - FM(0.3)),
                              min(max(pc.y, eb.GetY() + FM(0.3)), eb.GetBottom() - FM(0.3)))
        add_track(track(pc, tgt, min(w, 0.2), net, F))
        continue
    if c is None:
        left.append("%s.%s %s" % (ref, num, net))
        continue
    add_track(track(p.GetPosition(), c, w, net, F))
    via(c, net, vd, vdrill)
    add_via(c, net)
    if bw * bh > 2.0:                                                       # big pads: a second via
        c2 = fan(p, net, w, avoid=c)
        if c2 is not None:
            add_track(track(p.GetPosition(), c2, w, net, F))
            via(c2, net, vd, vdrill)
            add_via(c2, net)
R = VIA_D / 2
print("plane fan-out: %d tracks, %d vias, %d exposed pads; no spot for %d pads:" % (
    made["track"] - bga["track"], made["via"] - bga["via"], ep_done, len(left)), ", ".join(left))

# ---------------------------------------------------------------- fill + save
# JLC: 0.2 mm from any drilled hole to copper (inner layers too); the fill keeps the board's hole clearance
B.GetDesignSettings().m_HoleClearance = FM(0.2)
po = B.GetPlotOptions()                                                 # gerbers: no silk on pads or holes
po.SetSubtractMaskFromSilk(True)
B.SetPlotOptions(po)
for f in B.GetFootprints():                                             # the fill only honours that for plated holes
    for p in f.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            p.SetLocalClearance(FM(0.25))
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
tb = B.GetTitleBlock()
tb.SetComment(1, "Placed (tools/place_pcb.py) + BGA/plane fan-out (tools/fanout_pcb.py), not routed")
pcbnew.SaveBoard(PCB, B)

# BGA rules: 0.1 mm everywhere inside the package (power dog-bones and TMDS escapes pass 0.115 mm from vias)
pro = json.load(open(PRO, encoding="utf-8"))
for c in pro["net_settings"]["classes"]:
    if c["name"] in ("Power", "TMDS"):
        c["clearance"] = 0.1
pro["board"]["design_settings"]["rules"]["min_hole_clearance"] = 0.2
json.dump(pro, open(PRO, "w", encoding="utf-8"), indent=2)
print("saved", PCB)
