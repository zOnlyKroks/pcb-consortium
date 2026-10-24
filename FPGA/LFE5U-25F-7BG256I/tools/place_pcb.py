"""Place every footprint of the ECP5 emulation board (single-sided, all parts on F.Cu) and set up the 6-layer board.

The board must already contain the footprints (KiCad "Update PCB from Schematic"); this script only moves them, so the
schematic links stay intact.  It also sets 6 copper layers (JLC 1.6 mm 6-layer stackup), a 100 x 100 mm outline and the
JLC standard-tier rules + net classes in the .kicad_pro.  No tracks: tools/fanout_pcb.py adds the BGA / plane fan-out
and reshapes the +1V1 island afterwards (run it again after re-running this).

Floorplan follows the FPGA banks (BGA unrotated, ball A1 top-left):
  top edge    PMOD A/B (bank 0), HDMI + VGA (bank 1)
  right edge  microSD, audio, PMOD C/D (bank 2); SDRAM just inside (banks 2/3)
  left edge   USB-C, 40-pin GPIO header (banks 7/6); power + CH347 next to the USB connector
  bottom      7-segment, LEDs, DIP switches, buttons (banks 6/8); flash + config right under the BGA
The middle of each BGA side is kept free for the top-layer fan-out; decoupling sits in the four corners.
Local coordinates: origin = board top-left corner, x right, y down.
"""
import json, math, os, re, sys
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import silk

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pcb")
PRO = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pro")
X0, Y0 = 160.0, 30.0
W, D = 100.0, 100.0
MARGIN = 0.15
PLANE = {"GND", "+3V3", "+1V1", "+2V5", "+5V"}

B = pcbnew.LoadBoard(PCB)
FM, TM = pcbnew.FromMM, pcbnew.ToMM
placed, padmap, obstacles = {}, {}, []


def fp(ref):
    f = B.FindFootprintByReference(ref)
    if f is None:
        raise KeyError(ref)
    return f


def extent(f):
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


# supply-only parts (bypass caps) have no signal neighbour: they go next to this part instead
NEAR = {"C201": "U201", "C202": "U201", "C206": "U202", "C207": "U202", "C211": "U203", "C212": "U203",
        "C301": "J301", "C304": "U301", "C305": "U301", "C101": "U101", "C102": "X101", "C601": "Card1",
        "C602": "Card1", "C204": "L201", "C205": "L201", "C209": "L202", "C210": "L202"}


def auto(ref, x=None, y=None, r=10.0, region=None, rots=(0, 90, 180, 270)):
    """Nearest free spot to (x, y) (default: centroid of the placed pads it connects to), trying each rotation
    and keeping the one with the shortest connections."""
    f = fp(ref)
    if x is None:
        if ref in NEAR:
            a = fp(NEAR[ref]).GetPosition()
            x, y = TM(a.x) - X0, TM(a.y) - Y0
        else:
            x, y = target_of(ref)
    if region:                                     # start the search inside the allowed region
        x = min(max(x, region[0] + 1.0), region[2] - 1.0)
        y = min(max(y, region[1] + 1.0), region[3] - 1.0)
        r = max(r, 16.0)
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


# ================================================================ edge connectors
# top edge: PMOD A/B (bank 0), HDMI + VGA (bank 1)
put("J602", 23.5, 9.3, 270, edge_ok=True)                  # PMOD A  (socket bodies overhang the edge by ~3.8 mm)
put("J603", 40.5, 9.3, 270, edge_ok=True)                  # PMOD B
put("J502", 53.5, 8.1, 90, edge_ok=True)                   # HDMI, mouth on the edge
put("J501", 78.1, 13.3, 180, edge_ok=True)                 # VGA, front on the edge
# right edge: microSD, audio, PMOD C/D (bank 2)
put("Card1", 90.5, 25.0, 90, edge_ok=True)                 # card slot opens towards the edge
put("CN1", 91.8, 38.5, 180, edge_ok=True)                  # 3.5 mm jack
put("J604", 90.7, 59.0, 180, edge_ok=True)                 # PMOD C
put("J605", 90.7, 76.0, 180, edge_ok=True)                 # PMOD D
# left edge: USB-C, GPIO header
put("J301", 3.0, 8.5, 270, edge_ok=True)
put("J606", 2.3, 17.5, 0)
# bottom: DIP switches, 7-segment, buttons, PROG on the right edge
put("SW601", 5.5, 92.6, 0)
put("DS601", 31.6, 97.2, 90)
for i, ref in enumerate(("SW602", "SW603", "SW604", "SW605")):
    put(ref, 69.5 + 7.5 * i, 95.2, 90)
put("SW101", 95.4, 82.6, 90)
put("J302", 82.0, 86.0, 270)                                # external JTAG, 1x6 horizontal

# ================================================================ FPGA, SDRAM
FX, FY = 44.0, 39.0
put("U1", FX, FY, 0)
E = extent(fp("U1"))
BX0, BY0, BX1, BY1 = FX + E[0], FY + E[1], FX + E[2], FY + E[3]
put("U401", 69.5, 39.0, 0)
# keep the middle of every BGA side free for the top-layer fan-out (rows 1-2)
FAN, END = 6.0, 2.6
obstacles += [(BX0 + END, BY0 - FAN, BX1 - END, BY0), (BX0 + END, BY1, BX1 - END, BY1 + FAN),
              (BX0 - FAN, BY0 + END, BX0, BY1 - END), (BX1, BY0 + END, BX1 + FAN, BY1 - END)]

# decoupling in the four corners, 100 nF closest, bulk behind
CORNERS = [(BX0, BY0), (BX1, BY0), (BX0, BY1), (BX1, BY1)]
# order = corner TL, TR, BL, BR, ...: all six +1V1 100 nF (C222-C227) end up in the top corners, on the In4 +1V1 bar
small = ["C%d" % n for n in [222, 223, 242, 243, 226, 227, 231, 232, 224, 225] + list(range(244, 255))]
bulk = ["C220", "C221", "C230", "C240", "C241"]
for i, ref in enumerate(small):
    cx, cy = CORNERS[i % 4]
    auto(ref, cx + (-2.0 if cx < FX else 2.0), cy + (-2.0 if cy < FY else 2.0), r=8, rots=(0, 90))
for i, ref in enumerate(bulk):
    cx, cy = CORNERS[i % 4]
    auto(ref, cx + (-5.0 if cx < FX else 5.0), cy + (-5.0 if cy < FY else 5.0), r=8, rots=(0, 90))
for ref in ["C%d" % n for n in range(401, 409)]:                           # SDRAM, along its pin rows
    auto(ref, r=8, rots=(0, 90), x=69.5 + (8.2 if ref in ("C401", "C403", "C405", "C407") else -8.2),
         y=32.0 + 2.2 * (int(ref[1:]) - 401))

# ================================================================ power (top left, next to USB) + USB support
PWR = (12.5, 12.0, 34.0, 29.0)
put("U201", 19.0, 15.5, 0)
put("L201", 24.5, 15.5, 0)
put("U202", 19.0, 22.5, 0)
put("L202", 24.5, 22.5, 0)
for ref in ("C201", "C202", "R201"):
    auto(ref, region=PWR, r=6)
for ref in ("R202", "R203", "C203", "C204", "C205"):
    auto(ref, region=PWR, r=8)
for ref in ("C206", "C207", "R204"):
    auto(ref, region=PWR, r=6)
for ref in ("R205", "R206", "C208", "C209", "C210"):
    auto(ref, region=PWR, r=8)
auto("U203", 30.0, 26.0, r=6, region=PWR)
for ref in ("C211", "C212"):
    auto(ref, region=PWR, r=6)
auto("D201", 16.0, 48.0, r=6, region=(8.0, 46.0, 28.0, 52.0))
auto("R207", region=(8.0, 46.0, 28.0, 52.0), r=6)
USB = (6.8, 11.5, 14.0, 31.0)
for ref in ("U302", "F301", "C301", "R302", "R303"):
    auto(ref, region=USB, r=12)
# CH347F + crystal (bank 7 is right next to it)
CH = (7.0, 31.0, 24.0, 46.0)
put("U301", 15.5, 38.0, 0)
for ref in ("Y301", "C302", "C303", "C304", "C305"):
    auto(ref, region=CH, r=8)

# ================================================================ config, flash, clock under the BGA (bank 8)
CFG = (28.0, 50.0, 60.0, 70.0)
auto("U101", 44.0, 55.5, r=6, region=CFG, rots=(0, 180))
auto("C101", region=CFG, r=6)
auto("R101", region=CFG, r=6)
auto("X101", 35.5, 53.0, r=6, region=CFG)                  # next to ball P6
for ref in ("C102", "R109"):
    auto(ref, region=CFG, r=6)
for ref in ("R102", "R103", "R104", "R105", "R106", "R107", "Q101", "D101", "R108", "R110", "R111", "R112"):
    auto(ref, region=CFG, r=10)

# ================================================================ user I/O
LEDS = (12.5, 70.0, 64.0, 79.0)
for k in range(8):
    x = 15.0 + 5.0 * k
    put("D%d" % (601 + k), x, 77.5, 90)                       # LED row above the display
    auto("R%d" % (601 + k), x, 73.8, r=2, region=LEDS, rots=(90, 270))
for ref in ("RN603", "RN604"):
    auto(ref, region=(28.0, 62.0, 64.0, 79.0), r=12)
for i in range(4):
    auto("Q%d" % (601 + i), region=(28.0, 62.0, 64.0, 79.0), r=12)
    auto("R%d" % (613 + i), region=(28.0, 62.0, 64.0, 79.0), r=12)
for ref in ("RN601", "RN602"):
    auto(ref, region=(0.5, 70.0, 12.4, 86.0), r=12)
for i in range(4):
    auto("R%d" % (609 + i), region=(60.0, 79.0, 99.5, 91.0), r=10)
for ref in ("C601", "C602"):
    auto(ref, region=(76.0, 14.0, 86.0, 34.0), r=10)

# ================================================================ video / audio
VGA = (60.0, 14.5, 86.0, 27.0)
for ref in ["R%d" % n for n in range(501, 515)]:
    auto(ref, region=VGA, r=12)
for ref in ("R515", "R516", "R517", "R518", "D501"):
    auto(ref, region=(42.0, 13.5, 64.0, 27.0), r=10)
AUD = (78.5, 43.5, 88.5, 56.0)
for ref in ("R519", "R520", "C501", "C502", "C503", "C504"):
    auto(ref, region=AUD, r=10)

# ================================================================ sanity
refs = {f.GetReference() for f in B.GetFootprints()}
missing = sorted(refs - set(placed))
if missing:
    print("NOT PLACED:", missing)
print("placed %d / %d footprints" % (len(placed), len(refs)))

# ================================================================ board setup
B.SetCopperLayerCount(6)
PWR_LAYER = pcbnew.In4_Cu                   # +3V3 with the +1V1 island; In1 is GND, In2/In3 are signal layers
B.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
B.SetLayerType(PWR_LAYER, pcbnew.LT_POWER)
NOTES = ["ECP5 emulation board", "PMOD A", "PMOD B", "PMOD C", "PMOD D", "GPIO", "JTAG", "PROG", "BTN0", "BTN1",
         "BTN2", "BTN3", "SW0-7"]
for d in list(B.GetDrawings()):
    if d.GetLayer() == pcbnew.Edge_Cuts or (isinstance(d, pcbnew.PCB_TEXT) and str(d.GetText()) in NOTES):
        B.Remove(d)
for z in list(B.Zones()):
    if z.GetLayer() in (pcbnew.In1_Cu, pcbnew.In2_Cu, PWR_LAYER):   # the B.Cu GND pour is the user's
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


def plane(net, layer, pts, prio=0):
    z = pcbnew.ZONE(B)
    z.SetLayer(layer)
    z.SetNet(B.FindNet(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(FM(0.2))
    z.SetMinThickness(FM(0.2))
    outline(z, pts)
    B.Add(z)


plane("GND", pcbnew.In1_Cu, rect_pts(0.5, 0.5, W - 0.5, D - 0.5))
plane("+3V3", PWR_LAYER, rect_pts(0.5, 0.5, W - 0.5, D - 0.5))
plane("+1V1", PWR_LAYER,rect_pts(BX0 + 3.0, BY0 + 3.0, BX1 - 3.0, BY1 - 3.0), prio=1)   # core island under the BGA


def note(txt, x, y, size=1.2):
    t = pcbnew.PCB_TEXT(B)
    t.SetText(txt)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(FM(size), FM(size)))
    t.SetTextThickness(FM(0.18))
    t.SetPosition(pcbnew.VECTOR2I(FM(X0 + x), FM(Y0 + y)))
    B.Add(t)
    return t


notes = [note("ECP5 emulation board", 72.0, 64.0, 1.2), note("LFE5U-25F", 72.0, 66.5, 1.0)]
# easyeda2kicad imports the plastic locating pegs (microSD, audio jack) as plated holes without copper: make them
# NPTH (libs/lcsc/footprints.pretty is fixed the same way)
for f in B.GetFootprints():
    for p in f.Pads():
        if p.GetNumber() == "" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize().x >= p.GetSize(pcbnew.F_Cu).x:
            p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
silk.silk_pass(B, notes=notes)
tb = B.GetTitleBlock()
tb.SetTitle("ECP5 emulation board - LFE5U-25F caBGA-256")
tb.SetRevision("1")
tb.SetComment(0, "6 layers 1.6 mm: F.Cu sig / In1 GND / In2 sig / In3 sig / In4 +3V3 (+1V1 island under the BGA) / B.Cu sig")
tb.SetComment(1, "Placement only (tools/place_pcb.py), not routed")
pcbnew.SaveBoard(PCB, B)

# ================================================================ stackup (JLC 6-layer 1.6 mm, nominal: no impedance control) - text patch
STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.1) (material "2313") (epsilon_r 4.05) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 2" (type "core") (thickness 0.565) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.127) (material "2116") (epsilon_r 4.16) (loss_tangent 0.02))
\t\t\t(layer "In3.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 4" (type "core") (thickness 0.565) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
\t\t\t(layer "In4.Cu" (type "copper") (thickness 0.0152))
\t\t\t(layer "dielectric 5" (type "prepreg") (thickness 0.1) (material "2313") (epsilon_r 4.05) (loss_tangent 0.02))
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

# ================================================================ rules + net classes (JLC standard tier)
# BGA 0.8 mm: 0.25 / 0.45 mm vias fit between the balls and are still standard price (pad >= 0.45 mm).
pro = json.load(open(PRO, encoding="utf-8"))
r = pro["board"]["design_settings"]["rules"]
r.update({"min_clearance": 0.1, "min_track_width": 0.1, "min_via_diameter": 0.45, "min_via_annular_width": 0.1,
          "min_through_hole_diameter": 0.25, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.2,
          "min_hole_to_hole": 0.25, "min_text_height": 1.0, "min_text_thickness": 0.15})
ns = pro["net_settings"]
base = dict([c for c in ns["classes"] if c["name"] == "Default"][0])
base.update({"clearance": 0.1, "track_width": 0.12, "via_diameter": 0.45, "via_drill": 0.25,
             "diff_pair_width": 0.15, "diff_pair_gap": 0.15, "diff_pair_via_gap": 0.25})


def cls(name, prio, **kw):
    c = dict(base)
    c.update(kw)
    c["name"] = name
    c["priority"] = prio
    return c


ns["classes"] = [base,
                 cls("Power", 1, clearance=0.1, track_width=0.4, via_diameter=0.6, via_drill=0.3),
                 cls("TMDS", 0, clearance=0.1, track_width=0.15, diff_pair_width=0.15, diff_pair_gap=0.15),
                 cls("USB", 0, clearance=0.15, track_width=0.2, diff_pair_width=0.2, diff_pair_gap=0.15)]
ns["netclass_patterns"] = [{"netclass": "Power", "pattern": n} for n in ("+5V", "+3V3", "+1V1", "+2V5", "GND")] + \
                          [{"netclass": "TMDS", "pattern": "HDMI_*_P"}, {"netclass": "TMDS", "pattern": "HDMI_*_N"},
                           {"netclass": "USB", "pattern": "Net-(J301-D*"}, {"netclass": "USB", "pattern": "Net-(U301-UD*"}]
json.dump(pro, open(PRO, "w", encoding="utf-8"), indent=2)
print("saved", PCB)
