"""Place every footprint of VideoConv-V1.kicad_pcb and set up the board (4 copper layers, outline, GND plane on In1.Cu).

The board must already contain the footprints (KiCad "Update PCB from Schematic"); this script only moves them,
so the schematic links stay intact.  No tracks are created.  Re-running is safe (outline and plane are replaced).
Run with KiCad's python:  python -I tools/place_pcb.py

Local coordinates: origin = board top-left corner, x right, y down.
Connectors and ICs sit at fixed spots; every passive is then put next to the pads it connects to (signal nets) or
next to the least-loaded pad of its rail (decoupling), inside the region of its schematic sheet.
"""
import math, os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "VideoConv-V1.kicad_pcb")
X0, Y0 = 100.0, 60.0
W, D = 165.0, 125.0
MARGIN = 0.2
STEP = 0.4

B = pcbnew.LoadBoard(PCB)
FM, TM = pcbnew.ToMM, pcbnew.ToMM
FM = pcbnew.FromMM
placed = {}


FPS = {}      # filled after the outline is rebuilt (B.Remove invalidates earlier wrappers)


def fp(ref):
    if not FPS:
        FPS.update({f.GetReference(): f for f in B.GetFootprints()})
    return FPS[ref]


def is_rail(n):
    return n == "GND" or n.startswith("+") or n.startswith("/+") or "GND" in n.split("/")[-1]


def extent(f):
    pos = f.GetPosition()
    boxes = [p.GetBoundingBox() for p in f.Pads()]
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    if not cy.IsEmpty():
        boxes.append(cy.BBox())
    return (TM(min(b.GetX() for b in boxes) - pos.x), TM(min(b.GetY() for b in boxes) - pos.y),
            TM(max(b.GetRight() for b in boxes) - pos.x), TM(max(b.GetBottom() for b in boxes) - pos.y))


def setpos(f, x, y, rot):
    f.SetOrientationDegrees(rot)
    f.SetPosition(pcbnew.VECTOR2I(FM(X0 + x), FM(Y0 + y)))


def box_at(f, x, y, rot):
    setpos(f, x, y, rot)
    e = extent(f)
    return (x + e[0] - MARGIN, y + e[1] - MARGIN, x + e[2] + MARGIN, y + e[3] + MARGIN)


def overlaps(b, edge_ok=False):
    for r, o in placed.items():
        if b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]:
            return r
    if not edge_ok and (b[0] < 0.5 or b[1] < 0.5 or b[2] > W - 0.5 or b[3] > D - 0.5):
        return "edge"
    return None


def pads_of(f):
    out = []
    for p in f.Pads():
        n = str(p.GetNetname())
        if n and not n.startswith("unconnected"):
            q = p.GetPosition()
            out.append((n, TM(q.x) - X0, TM(q.y) - Y0))
    return out


padmap = {}      # net -> [(ref, x, y)]
load = {}        # (ref, x, y) -> decoupling parts already assigned to this pad


def commit(ref, b):
    placed[ref] = b
    for n, x, y in pads_of(fp(ref)):
        padmap.setdefault(n, []).append((ref, round(x, 3), round(y, 3)))


def put(ref, x, y, rot=0, edge_ok=False):
    f = fp(ref)
    b = box_at(f, x, y, rot)
    hit = overlaps(b, edge_ok)
    if hit:
        print("  warning: %s at (%.1f, %.1f) overlaps %s" % (ref, x, y, hit))
    commit(ref, b)


MOUTH = {"J1": "B", "J10": "B", "J9": "R", "J7": "T", "J2": "B", "J3": "B", "J4": "B", "J5": "B", "J6": "B"}      # side the mating face points to at rotation 0
ORDER = "BRTL"


def put_edge(ref, edge, along):
    f = fp(ref)
    rot = 90 * ((ORDER.index(edge) - ORDER.index(MOUTH[ref])) % 4)
    setpos(f, 0, 0, rot)
    e = extent(f)
    if edge in "BT":
        x, y = along, (D - e[3] if edge == "B" else -e[1])
    else:
        x, y = (W - e[2] if edge == "R" else -e[0]), along
    put(ref, x, y, rot, edge_ok=True)


def free_spot(f, x, y, rot, r, region):
    n = int(r / STEP)
    for ring in range(0, n + 1):
        cands = [(0, 0)] if ring == 0 else \
            [(i, -ring) for i in range(-ring, ring + 1)] + [(i, ring) for i in range(-ring, ring + 1)] + \
            [(-ring, j) for j in range(-ring + 1, ring)] + [(ring, j) for j in range(-ring + 1, ring)]
        cands.sort(key=lambda c: c[0] * c[0] + c[1] * c[1])
        for dx, dy in cands:
            cx, cy = x + dx * STEP, y + dy * STEP
            b = box_at(f, cx, cy, rot)
            if region and (b[0] < region[0] or b[1] < region[1] or b[2] > region[2] or b[3] > region[3]):
                continue
            if not overlaps(b):
                return cx, cy, b
    return None


def sheet_of(ref):
    return str(fp(ref).GetSheetname())


def nearest(net, ref, x, y, sheet=None):
    best = None
    for r, px, py in padmap.get(net, ()):
        if r == ref or (sheet and sheet_of(r) != sheet):
            continue
        d = math.hypot(px - x, py - y)
        if best is None or d < best:
            best = d
    return best


def wire_cost(f, ref):
    c = 0.0
    sh = sheet_of(ref)
    for n, px, py in pads_of(f):
        if n == "GND" or "GND" in n.split("/")[-1]:
            continue
        d = nearest(n, ref, px, py, sh if is_rail(n) else None)
        if d is not None:
            c += d
    return c


def target_signal(ref):
    pts = []
    for n, _, _ in pads_of(fp(ref)):
        if not is_rail(n):
            pts += [(x, y) for r, x, y in padmap.get(n, ()) if r != ref]
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def target_rail(ref, region):
    """Least-loaded pad of one of the part's rails, among the non-passive parts of the same sheet."""
    sh = sheet_of(ref)
    best = None
    for n, _, _ in pads_of(fp(ref)):
        if n == "GND" or not is_rail(n):
            continue
        for r, px, py in padmap.get(n, ()):
            if sheet_of(r) != sh or r[0] in "CR":
                continue
            cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
            score = 4.0 * load.get((r, px, py), 0) + 0.02 * math.hypot(px - cx, py - cy)
            if best is None or score < best[0]:
                best = (score, (r, px, py))
    return best[1] if best else None


def auto(ref, region, r=14.0):
    f = fp(ref)
    t = target_signal(ref)
    key = None
    if t is None:
        key = target_rail(ref, region)
        t = (key[1], key[2]) if key else ((region[0] + region[2]) / 2, (region[1] + region[3]) / 2)
    t = (min(max(t[0], region[0] + 2), region[2] - 2), min(max(t[1], region[1] + 2), region[3] - 2))   # keep the target inside the region
    best = None
    for rot in (0, 90, 180, 270):
        s = free_spot(f, t[0], t[1], rot, r, region) or free_spot(f, t[0], t[1], rot, 40, region)
        if not s:
            continue
        setpos(f, s[0], s[1], rot)
        c = wire_cost(f, ref) + 0.3 * math.hypot(s[0] - t[0], s[1] - t[1])
        if best is None or c < best[0]:
            best = (c, s, rot)
    if not best:
        print("  WARNING: no free spot for %s" % ref)
        put(ref, t[0], t[1], 0)
        return
    setpos(f, best[1][0], best[1][1], best[2])
    commit(ref, best[1][2])
    if key:
        load[key] = load.get(key, 0) + 1


# ================================================================ outline, layers
B.SetCopperLayerCount(4)
# reuse the board-level outline segments of an earlier run (B.Remove invalidates SWIG wrappers)
old_edge = [d for d in B.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
pts = [(0, 0), (W, 0), (W, D), (0, D)]
for i in range(4):
    a, b = pts[i], pts[(i + 1) % 4]
    if i < len(old_edge):
        s = old_edge[i]
    else:
        s = pcbnew.PCB_SHAPE(B)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(FM(0.1))
        B.Add(s)
    s.SetStart(pcbnew.VECTOR2I(FM(X0 + a[0]), FM(Y0 + a[1])))
    s.SetEnd(pcbnew.VECTOR2I(FM(X0 + b[0]), FM(Y0 + b[1])))

# ================================================================ fixed parts
put_edge("J6", "L", 54)                                  # SCART socket, mouth on the left edge
for ref, x in (("J2", 28), ("J3", 45), ("J4", 62), ("J5", 79)):
    put_edge(ref, "B", x)                                # RCA jacks along the bottom edge
put_edge("J7", "B", 104)                                 # line-out jack
put_edge("J1", "T", 14)                                  # USB-C
put_edge("J9", "R", 48)                                  # HDMI
put_edge("J10", "R", 96)                                 # VGA
put("U9", 70, 50, 0)                                     # TVP7002
put("U10", 70, 86, 0)                                    # TVP5150
put("U11", 105, 72, 0)                                   # iCE40
put("U13", 124, 48, 0)                                   # TFP410
put("U14", 143, 48, 90)                                  # TPD12S016
put("U1", 40, 9, 0)
put("U2", 40, 22, 0)
put("U3", 98, 9, 0)
put("U4", 98, 22, 0)
for i in range(6):
    put("FB%d" % (i + 1), 114 + 6.2 * i, 7, 90)

REGION = {"/Power/": (22, 0.5, W - 0.5, 31),
          "/Inputs/": (19, 31, 52, 99),
          "/TVP7002/": (50, 32, 91, 69),
          "/TVP5150/": (52, 72, 91, 99),
          "/FPGA/": (89, 50, 120, 100),
          "/HDMI/": (116, 32, W - 0.5, 69),
          "/VGA/": (118, 70, W - 0.5, D - 0.5)}
for sheet in ("/Inputs/", "/TVP7002/", "/TVP5150/", "/FPGA/", "/HDMI/", "/VGA/", "/Power/"):
    todo = [f.GetReference() for f in FPS.values() if str(f.GetSheetname()) == sheet and f.GetReference() not in placed]
    print(sheet, len(todo), "to place")
    while todo:
        def score(ref):
            sig = [n for n, _, _ in pads_of(fp(ref)) if not is_rail(n)]
            have = sum(1 for n in sig for r, _, _ in padmap.get(n, ()) if r != ref)
            return (0 if have else 1, -have, ref)
        todo.sort(key=score)
        ref = todo.pop(0)
        auto(ref, REGION[sheet])

# ================================================================ GND plane on In1.Cu
zones = [z for z in B.Zones() if z.GetLayer() == pcbnew.In1_Cu]
if zones:
    z = zones[0]
    z.Outline().RemoveAllContours()
else:
    z = pcbnew.ZONE(B)
    z.SetLayer(pcbnew.In1_Cu)
    z.SetNet(B.FindNet("GND"))
    B.Add(z)
ol = z.Outline()
ol.NewOutline()
for x, y in ((0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, D - 0.3), (0.3, D - 0.3)):
    ol.Append(FM(X0 + x), FM(Y0 + y))
try:
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
except Exception as e:
    print("zone fill skipped:", e)

pcbnew.SaveBoard(PCB, B)
print("placed", len(placed), "of", len(list(B.GetFootprints())), "->", PCB)
