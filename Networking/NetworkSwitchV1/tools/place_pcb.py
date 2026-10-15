"""Place every footprint of NetworkSwitchV1.kicad_pcb (single-sided, all parts on F.Cu) and set up the 4-layer board.

The board must already contain the footprints (KiCad "Update PCB from Schematic"); this script only moves them,
so the schematic links stay intact.  It also sets: 4 copper layers with the JLC04161H-7628 stackup, a 170 x 90 mm
outline, isolation keepouts, In1.Cu GND / RTN planes, and the JLC standard-tier rules + net classes in the .kicad_pro.
No tracks are created.  Re-running it is safe (outline, zones and notes are replaced).

Local coordinates: origin = board top-left corner, x right, y towards the front edge (y = 90 = RJ45 openings).
"""
import json, math, os, re, sys
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import silk

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "NetworkSwitchV1.kicad_pcb")
PRO = os.path.join(PRJ, "NetworkSwitchV1.kicad_pro")
X0, Y0 = 100.0, 50.0           # absolute position of the local origin
W, D = 170.0, 90.0
MARGIN = 0.15                  # extra space kept around every part (mm)
PLANE = {"GND", "RTN", "+3V3", "+1V1", "+3V3A", "+1V1A", "+1V1P", "CHASSIS"}   # reached through vias

B = pcbnew.LoadBoard(PCB)
FM, TM = pcbnew.FromMM, pcbnew.ToMM
placed = {}                    # ref -> (x0, y0, x1, y1) local
padmap = {}                    # net -> [(ref, x, y)] of placed parts
obstacles = []                 # rectangles parts may not use


def fp(ref):
    f = B.FindFootprintByReference(ref)
    if f is None:
        raise KeyError(ref)
    return f


def extent(f):
    """Bounding box (relative to the footprint origin, current orientation) of courtyard + pads."""
    pos = f.GetPosition()
    boxes = [p.GetBoundingBox() for p in f.Pads()]
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    if not cy.IsEmpty():
        boxes.append(cy.BBox())
    return (TM(min(b.GetX() for b in boxes) - pos.x), TM(min(b.GetY() for b in boxes) - pos.y),
            TM(max(b.GetRight() for b in boxes) - pos.x), TM(max(b.GetBottom() for b in boxes) - pos.y))


def setpos(f, x, y, rot):
    if f.IsFlipped():
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetOrientationDegrees(rot)
    f.SetPosition(pcbnew.VECTOR2I(FM(X0 + x), FM(Y0 + y)))


def box_at(f, x, y, rot, margin=MARGIN):
    setpos(f, x, y, rot)
    e = extent(f)
    return (x + e[0] - margin, y + e[1] - margin, x + e[2] + margin, y + e[3] + margin)


def overlaps(b, edge_ok=False):
    for r, o in placed.items():
        if b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]:
            return r
    for o in obstacles:
        if b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3]:
            return "keepout"
    if not edge_ok and (b[0] < 0.3 or b[1] < 0.3 or b[2] > W - 0.3 or b[3] > D - 0.3):
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


def commit(ref, b):
    placed[ref] = b
    for n, x, y in pads_of(fp(ref)):
        padmap.setdefault(n, []).append((ref, x, y))


def put(ref, x, y, rot=0, edge_ok=False):
    """Place exactly here (warns on collisions)."""
    f = fp(ref)
    b = box_at(f, x, y, rot)
    hit = overlaps(b, edge_ok)
    if hit:
        print("  warning: %s at (%.2f, %.2f) overlaps %s" % (ref, x, y, hit))
    commit(ref, b)
    return f


def free_spot(f, x, y, rot, r, region, step=0.25):
    for ring in range(0, int(r / step) + 1):
        cands = [(0, 0)] if ring == 0 else \
            [(i, -ring) for i in range(-ring, ring + 1)] + [(i, ring) for i in range(-ring, ring + 1)] + \
            [(-ring, j) for j in range(-ring + 1, ring)] + [(ring, j) for j in range(-ring + 1, ring)]
        cands.sort(key=lambda c: c[0] * c[0] + c[1] * c[1])
        for dx, dy in cands:
            cx, cy = x + dx * step, y + dy * step
            b = box_at(f, cx, cy, rot)
            if region and (b[0] < region[0] or b[1] < region[1] or b[2] > region[2] or b[3] > region[3]):
                continue
            if not overlaps(b):
                return cx, cy, b
    return None


def wire_cost(f, ref):
    c = 0.0
    for n, px, py in pads_of(f):
        if n in PLANE:
            continue
        t = [(x, y) for r, x, y in padmap.get(n, ()) if r != ref]
        if t:
            c += min(math.hypot(px - x, py - y) for x, y in t)
    return c


def target_of(ref):
    pts = []
    for n, _, _ in pads_of(fp(ref)):
        if n not in PLANE:
            pts += [(x, y) for r, x, y in padmap.get(n, ()) if r != ref]
    if not pts:
        raise ValueError("no placed neighbours for " + ref)
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def auto(ref, x=None, y=None, r=10.0, region=None, rots=(0, 90, 180, 270), dx=0.0, dy=0.0):
    """Nearest free spot to (x, y) (default: centroid of the placed pads it connects to), trying each rotation
    and keeping the one with the shortest connections."""
    f = fp(ref)
    if x is None:
        x, y = target_of(ref)
    x, y = x + dx, y + dy
    best = None
    for rot in rots:
        s = free_spot(f, x, y, rot, r, region)
        if not s:
            continue
        setpos(f, s[0], s[1], rot)
        c = wire_cost(f, ref) + 0.3 * math.hypot(s[0] - x, s[1] - y)
        if best is None or c < best[0]:
            best = (c, s, rot)
    if not best:
        print("  WARNING: no free spot for %s near (%.1f, %.1f)" % (ref, x, y))
        return put(ref, x, y, rots[0])
    s = best[1]
    setpos(f, s[0], s[1], best[2])
    commit(ref, s[2])
    return f


def pad_local(ref, num):
    p = [q for q in fp(ref).Pads() if q.GetNumber() == str(num)][0].GetPosition()
    return (TM(p.x) - X0, TM(p.y) - Y0)


def at_pad(ref, anchor, num, dx=0.0, dy=0.0, **kw):
    px, py = pad_local(anchor, num)
    return auto(ref, px + dx, py + dy, **kw)


def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]



def silk_pass(notes):
    silk.silk_pass(B, notes=notes)


# ================================================================ front: ports 1-6
PORT_X = [50.5 + 19.0 * i for i in range(6)]
YJ, YT = 78.3, 61.3                                                 # jack mouth 0.4 mm inside the edge
for k, xc in enumerate(PORT_X, 1):
    put("J40%d" % k, xc, YJ, 0, edge_ok=True)
    put("TR40%d" % k, xc, YT, 180)
# isolation barrier of the PoE PD (primary = lower left), also kept free of parts
ISO = [(0.0, 44.5, 41.0, 47.5), (38.0, 44.5, 41.0, 61.3)]
SEC = (0.3, 0.3, 41.0, 44.5)
PRI = (0.3, 47.5, 38.0, D - 0.3)
PRI_COL = (25.0, 61.5, 41.6, D - 0.3)            # primary + the strip left of J401 (port-1 Bob Smith)

# ================================================================ switch IC + decoupling
# The bottom supply cluster (pins 15-24) sits between P3 and P4, right above the gap between TR404 and TR405,
# so its capacitors can stack downwards without blocking any MDI pair.
UX, UY = (PORT_X[3] + PORT_X[4]) / 2, 27.5
put("U301", UX, UY, 0)
E = extent(fp("U301"))                         # (x0, y0, x1, y1) incl. pads
TIP = {"B": UY + E[3], "T": UY + E[1], "L": UX + E[0], "R": UX + E[2]}
ROT = {"B": 270, "T": 90, "L": 180, "R": 0}    # pad 1 (rail) towards the IC
ROW = 3.4                                      # radial pitch of a perpendicular 0603


def rel(pin):
    x, y = pad_local("U301", pin)
    return x - UX, y - UY


def side(n):
    return "B" if n <= 38 else "R" if n <= 64 else "T" if n <= 102 else "L"


def decap(ref, pin, along=None, row=0):
    """Capacitor for U301 pin `pin`, on that side, `row` rows out, centred at `along` (default: the pin)."""
    s = side(pin)
    px, py = rel(pin)
    a = (px if s in "TB" else py) if along is None else along
    d = 1.75 + row * ROW
    if s == "B":
        x, y = UX + a, TIP["B"] + d
    elif s == "T":
        x, y = UX + a, TIP["T"] - d
    elif s == "L":
        x, y = TIP["L"] - d, UY + a
    else:
        x, y = TIP["R"] + d, UY + a
    return auto(ref, x, y, r=1.5, rots=(ROT[s],))


for ref, pin in (("C320", 5), ("C310", 10), ("C312", 29), ("C324", 34)):            # bottom, between MDI pairs
    decap(ref, pin)
CLUSTER = [[("R305", 17), ("C301", 20)], [("C302", 21), ("C303", 22)], [("C304", 23), ("C311", 18)],
           [("C321", 15), ("C322", 19)], [("C323", 24), ("C309", 21)]]
for row, pair in enumerate(CLUSTER):
    for (ref, pin), a in zip(pair, (-0.95, 0.95)):
        decap(ref, pin, along=a, row=row)
for ref, pin, a in (("C313", 39, None), ("C332", 44, None), ("C314", 49, None), ("C325", 54, -0.6),
                    ("C315", 59, -4.4), ("C326", 64, None)):                       # right; MG pairs exit 55-58
    decap(ref, pin, along=a)
for ref, pin, a, row in (("C316", 107, None, 0), ("C329", 112, None, 0), ("C317", 117, None, 0),
                         ("C331", 122, None, 0), ("C318", 128, None, 0)):
    decap(ref, pin, along=a, row=row)
for ref, pin, a, row in (("C305", 76, 5.1, 0), ("C334", 77, 3.2, 0), ("C306", 78, 1.3, 0), ("C307", 92, -4.0, 0),
                         ("C308", 95, -5.9, 0), ("C327", 96, -5.9, 1), ("C328", 102, -9.6, 0)):
    decap(ref, pin, along=a, row=row)

# crystal, reset, straps, EEPROM behind the IC
xi, _ = pad_local("U301", 98)
auto("Y301", xi - 1.2, TIP["T"] - 5.6, r=3, rots=(0, 180))
auto("C335", r=4)
auto("C336", r=4)
STRAPS = ["R306", "R307", "R308", "R309", "R310", "R311", "R314", "R312", "R313"]
for ref in STRAPS:
    n = [n for n, _, _ in pads_of(fp(ref)) if n not in PLANE][0]
    sx = [x for r, x, y in padmap[n] if r == "U301"][0]
    auto(ref, sx, TIP["T"] - 7.0, r=10, rots=(90, 270), region=(0, 0, W, TIP["T"] - 4.6))
auto("R301", r=6, region=(0, 0, W, TIP["T"] - 2))
auto("R302", r=6, region=(0, 0, W, TIP["T"] - 2))
auto("C337", r=6, region=(0, 0, W, TIP["T"] - 2))
put("J302", 88.0, 3.5, 90)                                                  # EEPROM programming header (DNP)
auto("U302", UX - 23.0, 10.0, r=5, rots=(0, 90, 180, 270))
for ref in ("R303", "R304", "R315"):
    auto(ref, r=6)
at_pad("C338", "U302", 8, 0.0, -2.2, r=5)
# rail entry: ferrite beads + bulk at the IC's rear-left corner (clear of the P0/P1 pairs leaving the left side)
CORNER = (0, 0, TIP["L"] - 0.5, TIP["T"] - 0.3)
auto("FB301", UX - 15.0, TIP["T"] - 2.0, r=5, region=CORNER, rots=(0, 180))
auto("FB302", UX - 15.0, TIP["T"] - 4.0, r=5, region=CORNER, rots=(0, 180))
auto("FB303", UX - 15.0, TIP["T"] - 6.0, r=5, region=CORNER, rots=(0, 180))
at_pad("C333", "FB302", 2, 0.0, -1.8, r=4, region=CORNER)
at_pad("C319", "FB301", 2, 0.0, 1.8, r=7, region=CORNER)
at_pad("C330", "FB303", 2, 0.0, -1.8, r=4, region=CORNER)

# ================================================================ ports: CT caps, Bob Smith, LED resistors
for k, xc in enumerate(PORT_X, 1):
    col = (xc - 9.5, 0, xc + 9.5, D)
    tr = "TR40%d" % k
    for i, pin in enumerate(("1", "4", "7", "10"), 1):              # chip-side centre taps
        at_pad("C4%d%d" % (k, i), tr, pin, 0, -3.9, r=2, region=col, rots=(90, 270))
    if k > 1:                                                       # Bob Smith on the line side
        for i, pin in enumerate(("24", "21", "18", "15"), 1):
            at_pad("R4%d%d" % (k, i), tr, pin, 0, 3.6, r=2, region=col, rots=(90, 270))
        auto("C4%d5" % k, xc + 7.4, YT + 8.0, r=3, region=col)
    for ref in ("R4%d5" % k, "R4%d6" % k):                           # LED resistors at the jack LED pins
        j = [n for n, _, _ in pads_of(fp(ref)) if n.startswith("Net-(J40")][0]
        px, py = [(x, y) for r, x, y in padmap[j] if r.startswith("J40")][0]
        auto(ref, px, py - 2.9, r=3, region=col, rots=(0, 180))

# ================================================================ power entry + PoE PD (left)
put("H401", 4.0, 4.0, 0)
put("H403", 4.0, 36.0, 0)
put("J101", 13.0, 11.1, 270, edge_ok=True)                           # plug opening at the rear edge
put("T101", 19.0, 46.0, 0)                                           # primary pins 1-4 face the front
put("U103", 33.0, 46.0, 180)                                         # LED side up (secondary)
obstacles.extend(ISO)
# secondary: DC input, rectifier, output caps, TL431 feedback
auto("F101", r=6, region=SEC)
auto("D107", 23.0, 5.0, r=6, region=SEC, rots=(90, 270))
auto("D106", r=6, region=SEC, rots=(90, 270))
px, py = pad_local("T101", 9)
auto("D105", px + 1.25, py - 6.0, r=4, region=SEC, rots=(90, 270))
auto("C108", 31.0, 24.0, r=6, region=SEC)
auto("C109", r=6, region=SEC)
auto("C110", r=6, region=SEC)
for ref in ("R110", "U102", "R112", "R113", "C111", "R108", "R109"):
    auto(ref, r=8, region=SEC)
# primary: flyback switch loop, PD controller, bridges
auto("Q101", 10.5, 62.5, r=4, region=PRI, rots=(270,))              # drain tab up, towards T101 pin 4
auto("D102", 9.5, 51.6, r=3, region=PRI, rots=(90, 270))
auto("D103", 5.3, 51.6, r=3, region=PRI, rots=(90, 270))
auto("C106", 20.3, 57.8, r=2, region=PRI, rots=(0,))
auto("C107", 20.3, 61.3, r=2, region=PRI, rots=(0,))
auto("R107", r=4, region=PRI)
put("U101", 22.0, 70.0, 270)
put("BR101", 33.0, 65.0, 0)                                          # AC (CT) pads face TR401
put("BR102", 33.0, 71.0, 0)
for ref in ("R106", "D104", "R105", "C104", "C105", "C103", "R104", "C102", "R101", "R102", "R103", "D101", "C101"):
    auto(ref, r=10, region=PRI)
for ref in ("R151", "R152", "R153", "R154", "C151", "C152", "C153", "C154", "C155"):
    auto(ref, r=12, region=PRI_COL)

# ================================================================ bucks (rear, between the PoE block and the IC)
for u, x0, y0 in (("U104", 58.0, 9.0), ("U105", 58.0, 22.0)):
    put(u, x0, y0, 0)
for u, parts, l in (("U104", ("C113", "C112", "R114", "L101", "C114", "R115", "R116"), "L101"),
                    ("U105", ("C118", "C117", "R117", "L102", "C119", "R118", "R119"), "L102")):
    at_pad(parts[0], u, 3, -2.0, 0.0, r=4, region=(42.0, 0.3, 82.0, 34.0))
    at_pad(parts[1], u, 3, -4.3, 0.0, r=4, region=(42.0, 0.3, 82.0, 34.0))
    at_pad(parts[2], u, 5, 2.6, 0.0, r=4, region=(42.0, 0.3, 82.0, 34.0))
    for ref in parts[3:]:
        auto(ref, r=8, region=(42.0, 0.3, 82.0, 34.0))
    co = ("C115", "C116") if l == "L101" else ("C120", "C121")
    at_pad(co[0], l, 2, 3.0, 0.0, r=6, region=(42.0, 0.3, 82.0, 34.0))
    at_pad(co[1], l, 2, 5.0, 0.0, r=6, region=(42.0, 0.3, 82.0, 34.0))

# ================================================================ management (right)
TX = UX + 24.5
put("TR501", TX, UY - 5.0, 90)                                       # line side (MG_*) faces the IC
put("U501", TX + 13.5, UY - 5.0, 90)
for ref in ("C507", "C508"):
    auto(ref, r=5)
at_pad("C506", "TR501", 1, 2.5, 0.0, r=5)
auto("Y501", r=5, rots=(0, 90, 180, 270))
for ref, pin in (("C501", 13), ("C502", 27), ("C503", 4)):
    at_pad(ref, "U501", pin, r=6)
auto("C505", r=6)
at_pad("C504", "U501", 13, 0.0, -4.0, r=6)
auto("R501", r=6)
auto("SW501", TX + 14.0, UY + 6.5, r=5, rots=(0,))
put("J501", TX - 6.0, 3.5, 90)
put("H402", 166.0, 4.0, 0)
put("H404", 166.0, 62.0, 0)
auto("C401", 160.0, 62.0, r=5)
auto("R401", 160.0, 58.0, r=5)
# front panel, right of port 6: power LED, SYS LED, factory reset
auto("D108", 159.5, 88.3, r=2, rots=(0, 180))
auto("D501", 165.0, 88.3, r=2, rots=(0, 180))
at_pad("R120", "D108", 2, 0.0, -2.0, r=3)
at_pad("R502", "D501", 2, 0.0, -2.0, r=3)
auto("SW502", 162.5, 79.0, r=4, rots=(0,))

# ================================================================ hand fixes on top of the automatic placement
def swap(a, b):
    fa, fb = fp(a), fp(b)
    pa, ra = fa.GetPosition(), fa.GetOrientationDegrees()
    fa.SetPosition(fb.GetPosition()); fa.SetOrientationDegrees(fb.GetOrientationDegrees())
    fb.SetPosition(pa); fb.SetOrientationDegrees(ra)
    placed[a], placed[b] = placed[b], placed[a]


swap("R153", "R154")                       # BR102's CT4 pad is above CT3: keeps the two CT links from crossing

# ================================================================ sanity: everything placed exactly once, all on top
refs = {f.GetReference() for f in B.GetFootprints()}
missing = sorted(refs - set(placed))
if missing:
    print("NOT PLACED:", missing)
print("placed %d / %d footprints" % (len(placed), len(refs)))
for f in B.GetFootprints():
    if f.IsFlipped():
        print("  on bottom:", f.GetReference())

# ================================================================ board setup
B.SetCopperLayerCount(4)
NOTES = ["NetworkSwitchV1", "PoE PD - HIGH VOLTAGE SIDE", "PoE PD - HV", "1", "2", "3", "4", "5", "6"]
for d in list(B.GetDrawings()):
    if d.GetLayer() == pcbnew.Edge_Cuts or (isinstance(d, pcbnew.PCB_TEXT) and str(d.GetText()) in NOTES):
        B.Remove(d)
for z in list(B.Zones()):
    B.Remove(z)
rect = pcbnew.PCB_SHAPE(B, pcbnew.SHAPE_T_RECTANGLE)
rect.SetStart(pcbnew.VECTOR2I(FM(X0), FM(Y0)))
rect.SetEnd(pcbnew.VECTOR2I(FM(X0 + W), FM(Y0 + D)))
rect.SetLayer(pcbnew.Edge_Cuts)
rect.SetWidth(FM(0.1))
B.Add(rect)


def outline(z, pts):
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(FM(X0 + x), FM(Y0 + y))


def rule_area(name, pts, tracks=True, vias=True, fills=True):
    z = pcbnew.ZONE(B)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowZoneFills(fills)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    outline(z, pts)
    B.Add(z)


def plane(net, layer, pts, prio=0):
    z = pcbnew.ZONE(B)
    z.SetLayer(layer)
    z.SetNet(B.FindNet(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(FM(0.3))
    z.SetMinThickness(FM(0.25))
    outline(z, pts)
    B.Add(z)


rule_area("PoE isolation (T101/U103)", rect_pts(*ISO[0]))
rule_area("PoE isolation (port 1 side)", rect_pts(*ISO[1]))
for k, xc in enumerate(PORT_X, 1):
    rule_area("Magnetics isolation port %d" % k, rect_pts(xc - 7.6, YT - 2.5, xc + 7.6, YT + 2.5))
rule_area("No planes under line side / RJ45", rect_pts(41.0, YT, PORT_X[-1] + 9.5, D), tracks=False, vias=False)
plane("GND", pcbnew.In1_Cu, [(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, D - 0.5), (41.0, D - 0.5), (41.0, 44.5),
                             (0.5, 44.5)])
plane("RTN", pcbnew.In1_Cu, rect_pts(0.5, 47.5, 38.0, D - 0.5))


def note(txt, x, y, size=1.2):
    t = pcbnew.PCB_TEXT(B)
    t.SetText(txt)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(FM(size), FM(size)))
    t.SetTextThickness(FM(0.18))
    t.SetPosition(pcbnew.VECTOR2I(FM(X0 + x), FM(Y0 + y)))
    B.Add(t)
    return t


notes = [note("NetworkSwitchV1", UX, 1.6, 1.5), note("PoE PD - HV", 6.0, D - 1.5, 1.0)]
for k, xc in enumerate(PORT_X, 1):
    notes.append(note(str(k), xc, YJ - 5.6, 1.2))

# RJ45 locating pegs came out of easyeda2kicad as plated pads with no copper; they are NPTH (library fixed too)
for f in B.GetFootprints():
    for p in f.Pads():
        if p.GetNumber() == "" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize().x >= p.GetSize(pcbnew.F_Cu).x:
            p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)

silk_pass(notes)
tb = B.GetTitleBlock()
tb.SetTitle("NetworkSwitchV1 - 6-port managed gigabit switch, PoE powered")
tb.SetRevision("1")
tb.SetComment(0, "4 layers JLC04161H-7628: F.Cu sig / In1 GND (RTN under PoE primary) / In2 power / B.Cu sig")
tb.SetComment(1, "Placement only (tools/place_pcb.py), not routed")
pcbnew.SaveBoard(PCB, B)

# ================================================================ stackup (JLC04161H-7628) - text patch
STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(copper_finish "HAL lead-free")
\t\t\t(dielectric_constraints no)
\t\t)
"""
txt = open(PCB, encoding="utf-8").read()
m = re.search(r"\n\t\t\(stackup\n.*?\n\t\t\)\n", txt, re.S)
if m:
    txt = txt[:m.start() + 1] + STACKUP + txt[m.end():]
else:
    i = txt.index("\n\t(setup\n") + len("\n\t(setup\n")
    txt = txt[:i] + STACKUP + txt[i:]
open(PCB, "w", encoding="utf-8").write(txt)

# ================================================================ rules + net classes in the project file
pro = json.load(open(PRO, encoding="utf-8"))
r = pro["board"]["design_settings"]["rules"]
r.update({"min_clearance": 0.1, "min_track_width": 0.1, "min_via_diameter": 0.7, "min_via_annular_width": 0.2,
          "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.2,
          "min_hole_to_hole": 0.25, "min_text_height": 1.0, "min_text_thickness": 0.15})
ns = pro["net_settings"]
base = dict([c for c in ns["classes"] if c["name"] == "Default"][0])
base.update({"clearance": 0.15, "track_width": 0.2, "via_diameter": 0.7, "via_drill": 0.3,
             "diff_pair_width": 0.22, "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.25})


def cls(name, prio, **kw):
    c = dict(base)
    c.update(kw)
    c["name"] = name
    c["priority"] = prio
    return c


ns["classes"] = [base,
                 cls("MDI_100R", 0, clearance=0.2, track_width=0.22, diff_pair_width=0.22, diff_pair_gap=0.2),
                 cls("PoE_SW", 1, clearance=0.5, track_width=0.8),
                 cls("PoE_HV", 1, clearance=0.2, track_width=0.5),
                 cls("Power", 2, clearance=0.2, track_width=0.5)]


def netof(ref, num):
    return str([p for p in fp(ref).Pads() if p.GetNumber() == str(num)][0].GetNetname())


sw = {netof("Q101", 2), netof("D102", 1)}                            # flyback drain + clamp, up to ~150 V
hv = {netof("BR101", 1), netof("BR101", 2), "POE_CT1", "POE_CT2", "POE_CT3", "POE_CT4"}
power = {"+12V", "+3V3", "+1V1", "+3V3A", "+1V1A", "+1V1P", "GND", "RTN", netof("L101", 1), netof("L102", 1),
         netof("J101", 4), netof("F101", 2), netof("D105", 2), netof("R107", 1)}
ns["netclass_patterns"] = [{"netclass": "MDI_100R", "pattern": "Net-(TR4*-TD*"},
                           {"netclass": "MDI_100R", "pattern": "Net-(TR4*-MX*"},
                           {"netclass": "MDI_100R", "pattern": "MG_*"},
                           {"netclass": "MDI_100R", "pattern": "Net-(TR501-TD*"}] + \
                          [{"netclass": "PoE_SW", "pattern": n} for n in sorted(sw)] + \
                          [{"netclass": "PoE_HV", "pattern": n} for n in sorted(hv)] + \
                          [{"netclass": "Power", "pattern": n} for n in sorted(power)]
json.dump(pro, open(PRO, "w", encoding="utf-8"), indent=2)
print("saved", PCB)
