"""Place gamma-spectrometer.kicad_pcb (footprints already imported from the schematic; this only moves them, nets/links stay intact).
Board 112 x 68 mm, 2 layers, outline on Edge.Cuts.  No tracks, no zones: the user routes.
Layout (local coordinates, origin = top-left corner, x right, y down):
  top edge      ESP32-C6-MINI antenna end at the top edge (its rule-area keep-out hangs over the edge), USB-C on the left edge, buzzer top right
  left          USB-C / 3.3 V power;   bottom-left: Geiger front-end (comparator, reference, pot) next to the cathode clip J3
  middle        555 boost + regulation (L1, Q1, D10, U6, U7 ...) and the HV divider
  right         12-stage Cockcroft-Walton ladder as a snake, 2 rows x 6 stages (stage 1 next to the boost, stage 12 ends at the left end of row 4)
  bottom strip  SBM-20 tube lies along the bottom edge (nothing else under it): anode clip J2 right, cathode clip J3 left, TUBE_SPACING apart
Run with KiCad's python:  python -I tools/place_pcb.py"""
import math, os, re, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "gamma-spectrometer.kicad_pcb")
X0, Y0 = 100.0, 50.0
W, D = 112.0, 68.0
MARGIN, STEP = 0.2, 0.4
TUBE_SPACING = 100.0        # centre to centre of the two clips; SBM-20 is ~105 mm over all -> check against the real tube / holder
B = pcbnew.LoadBoard(PCB)
FM, TM = pcbnew.FromMM, pcbnew.ToMM
placed, FPS = {}, {}


def fp(ref):
    if not FPS:
        FPS.update({f.GetReference(): f for f in B.GetFootprints()})
    return FPS[ref]


def extent(f):
    pos = f.GetPosition()
    boxes = [p.GetBoundingBox() for p in f.Pads()]
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    if f.GetReference() == "U5":      # the courtyard of the module includes its antenna keep-out: use the body
        return (-6.9, -6.5, 6.9, 6.5)
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
    if not edge_ok and (b[0] < 0.8 or b[1] < 0.8 or b[2] > W - 0.8 or b[3] > D - 0.8):
        return "edge"
    return None


RAILS = {"GND", "VCC", "+5V"}


def pads_of(f):
    out = []
    for p in f.Pads():
        n = str(p.GetNetname())
        if n and not n.startswith("unconnected"):
            q = p.GetPosition()
            out.append((n, TM(q.x) - X0, TM(q.y) - Y0))
    return out


padmap, load = {}, {}


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


def put_edge(ref, edge, along, mouth):
    """Part whose mating face points to `mouth` at rotation 0, put on `edge` (L R T B) so that the face looks outwards."""
    f = fp(ref)
    order = "BRTL"
    rot = 90 * ((order.index(edge) - order.index(mouth)) % 4)
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


def nearest(net, ref, x, y, group=None):
    best = None
    for r, px, py in padmap.get(net, ()):
        if r == ref or (group and GROUP.get(r) != group):
            continue
        d = math.hypot(px - x, py - y)
        if best is None or d < best:
            best = d
    return best


def wire_cost(f, ref):
    c = 0.0
    for n, px, py in pads_of(f):
        if n == "GND":
            continue
        d = nearest(n, ref, px, py, GROUP[ref] if n in RAILS else None)
        if d is not None:
            c += d
    return c


def target_signal(ref):
    pts = []
    for n, _, _ in pads_of(fp(ref)):
        if n not in RAILS:
            pts += [(x, y) for r, x, y in padmap.get(n, ()) if r != ref]
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def target_rail(ref, region):
    best = None
    for n, _, _ in pads_of(fp(ref)):
        if n == "GND" or n not in RAILS:
            continue
        for r, px, py in padmap.get(n, ()):
            if GROUP.get(r) != GROUP[ref] or r[0] in "CR":
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
    t = (min(max(t[0], region[0] + 2), region[2] - 2), min(max(t[1], region[1] + 2), region[3] - 2))
    best = None
    for rot in (0, 90, 180, 270):
        s = free_spot(f, t[0], t[1], rot, r, region) or free_spot(f, t[0], t[1], rot, 50, region)
        if not s:
            continue
        setpos(f, s[0], s[1], rot)
        c = wire_cost(f, ref) + 0.3 * math.hypot(s[0] - t[0], s[1] - t[1])
        if best is None or c < best[0]:
            best = (c, s, rot)
    if not best:
        print("  WARNING: no free spot for %s" % ref)
        put(ref, t[0], t[1], 0, edge_ok=True)
        return
    setpos(f, best[1][0], best[1][1], best[2])
    commit(ref, best[1][2])
    if key:
        load[key] = load.get(key, 0) + 1


# ============================================================ groups / regions
LADDER_C, LADDER_D = [], []
STAGES = []
for k in range(1, 13):
    if k == 1:
        cp, cs, da, db = "C11", "C12", "D9", "D11"
    elif k == 2:
        cp, cs, da, db = "C13", "C14", "D12", "D13"
    else:
        j = k - 3; rr, s = j // 2, j % 2
        cp, cs, da, db = "C%d" % (15 + 4 * rr + s), "C%d" % (17 + 4 * rr + s), "D%d" % (15 + 4 * rr + 2 * s), "D%d" % (16 + 4 * rr + 2 * s)
    STAGES.append((cp, cs, da, db))
G_LADDER = {r for st in STAGES for r in st}
G_BOOST = {"L1", "Q1", "D10", "C10", "D14", "U6", "R13", "R14", "R15", "C35", "C36", "C37", "U7", "C38", "R18", "R19", "R16", "R17", "R21", "R22", "R23", "R24", "C39"}
G_USB = {"J1", "F1", "D1", "U3", "R6", "R8", "U4", "C3", "C4", "C5", "C6", "C8", "C9"}
G_MCU = {"U5", "SW1", "SW2", "R10", "R11", "C7"}
G_BUZ = {"BUZZER1", "Q3", "R12", "R20"}
G_AFE = {"U1", "U2", "VR1", "R1", "R2", "R3", "R4", "C1", "C2", "D2", "D3", "JP1", "J3", "J2"}
G_TUBEL = {"R5"}
G_TUBER = {"R7", "R9"}
GROUP = {}
for name, s in (("ladder", G_LADDER), ("boost", G_BOOST), ("usb", G_USB), ("mcu", G_MCU), ("buz", G_BUZ), ("afe", G_AFE), ("tubel", G_TUBEL), ("tuber", G_TUBER)):
    for r_ in s:
        GROUP[r_] = name
REGION = {"usb": (1, 8, 36, 36),
          "mcu": (38, 3, 90, 16),
          "buz": (92, 1, 111, 17),
          "boost": (36, 14, 74, 37),
          "afe": (72, 14, 111, 37),
          "tubel": (1, 54, 40, 67),
          "tuber": (72, 54, 111, 67)}
missing = [f.GetReference() for f in B.GetFootprints() if f.GetReference() not in GROUP]
print("not in a group:", missing)

# ============================================================ outline
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

# ============================================================ fixed parts
put("U5", 60, 8.0, 0)                                   # antenna end at the top edge
put_edge("J1", "L", 24, "B")                            # USB-C, mating face to the left (mouth points to +y at rotation 0)
put("BUZZER1", 103, 9.5, 0)
ytube = D - 6.5
cx = W / 2
put("J2", cx - TUBE_SPACING / 2, ytube, 90, edge_ok=True)   # anode (left, next to the end of the ladder)
put("J3", cx + TUBE_SPACING / 2, ytube, 90, edge_ok=True)   # cathode (right, next to the front-end)
put("L1", 46, 26, 0)
put("U6", 62, 27, 0)
put("U7", 46.0, 40.0, 0) if False else None
# ladder: snake, 4 rows x 3 stages; a stage = pump cap / diode, smoothing cap / diode in a 2 x 2 grid
LX0, LY0, LPX, LPY = 8.0, 40.0, 15.5, 11.0
for k, (cp, cs, da, db) in enumerate(STAGES):
    row, i = divmod(k, 6)
    col = i if row % 2 == 0 else 5 - i
    x, y = LX0 + col * LPX, LY0 + row * LPY
    put(cp, x, y, 0)
    put(cs, x, y + 4.0, 0)
    put(da, x + 7.3, y, 0)
    put(db, x + 7.3, y + 4.0, 0)
# ============================================================ everything else, group by group
for grp in ("usb", "mcu", "buz", "afe", "boost", "tubel", "tuber"):
    todo = [r_ for r_, g_ in GROUP.items() if g_ == grp and r_ not in placed]
    print(grp, len(todo), "to place")
    while todo:
        def score(ref):
            sig = [n for n, _, _ in pads_of(fp(ref)) if n not in RAILS]
            have = sum(1 for n in sig for r_, _, _ in padmap.get(n, ()) if r_ != ref)
            return (0 if have else 1, -have, ref)
        todo.sort(key=score)
        ref = todo.pop(0)
        auto(ref, REGION[grp])

pcbnew.SaveBoard(PCB, B)
print("placed", len(placed), "of", len(list(B.GetFootprints())), "->", PCB)
