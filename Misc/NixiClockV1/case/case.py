"""NixiClockV1 enclosure (CadQuery 2.8): base tray + flat lid, tubes standing up through the lid.

Run:  <venv>/python case.py      -> case_base.step/.stl, case_lid.step/.stl, case_assembly.step (with a dummy PCB),
                                    case_lid_lasercut.dxf (2D lid for 3 mm acrylic)

Board data below is in KiCad coordinates (x right, y towards the FRONT edge, back-left corner = 0, 0), copied from
NixiClockV1.kicad_pcb.  The model uses X = x, Y = 60 - y, Z up (right-handed, front edge at Y = 0) - see K().

Stack (z): floor 2.4 | columns 7.0 | PCB 1.6 (bottom 9.4, top 11.0) | 13.0 free above the PCB | lid 2.5 (top 26.5)
One M3 screw per corner, from below: base counterbore -> column -> PCB -> lid boss with an M3 heat-set insert
(print) or an M3 thread (CNC).  M3 x 12 socket head, 4x.
"""
import os
import cadquery as cq

HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ board (from the KiCad file)
BW, BD, BT = 128.0, 60.0, 1.6                      # board width (x), depth (y), thickness
HOLES = [(4.0, 4.0), (76.0, 4.0), (4.0, 56.0), (124.0, 56.0)]
TUBES = [(15.5, 51.0), (32.5, 51.0), (55.5, 51.0), (72.5, 51.0), (95.5, 51.0), (112.5, 51.0)]
USBC = (31.5,)                                     # J101 on the right edge, centre y
J102_PINS = [(16.0, 5.2), (10.92, 5.2)]            # WJ500V screw positions, wire entry on the back edge (y = 0)
J102_X = (7.8, 19.1)                               # terminal body extent in x
BUTTONS = [("RST", 91.5, 18.5), ("BOOT", 91.5, 25.0)]
ANTENNA = (99.5, 0.0, 128.0, 11.0)                 # ESP32-C3 PCB antenna area (x0, y0, x1, y1)

# ------------------------------------------------------------------ case parameters
GAP = 0.8                 # PCB to inner wall
WALL = 2.4
FLOOR = 2.4
COLUMN_H = 7.0            # space under the PCB (THT leads, J102 pins)
ABOVE = 13.0              # PCB top to lid underside (C106 ~11 mm, WJ500V ~10.5 mm)
LID_T = 2.5
LIP_H, LIP_W, LIP_CLR = 2.0, 1.6, 0.25           # locating lip under the lid
R_OUT, R_IN = 4.5, 3.0    # outer / inner vertical corner radii (inner >= 3 mm: CNC end mill friendly)
TUBE_HOLE = 12.6          # IN-16 glass is ~11-12 mm; adjust to your tubes
COL_D = 7.0
SCREW_D = 3.4             # M3 clearance
CBORE_D, CBORE_H = 6.5, 3.0
INSERT = True             # True: heat-set insert hole (3D print); False: 2.5 mm tap drill for M3 (CNC)
INSERT_D, INSERT_H = 4.0, 6.0
METAL = False             # True (aluminium CNC): open the lid above the ESP32 antenna for a plastic window

def K(x, y):
    """KiCad board coordinates -> model XY (keeps the board's handedness: front at Y = 0, back at Y = BD)."""
    return x, BD - y


def kbox(x0, y0, x1, y1):
    """KiCad rectangle -> model (cx, cy, w, d)."""
    (a, b), (c, d) = K(x0, y0), K(x1, y1)
    return (a + c) / 2, (b + d) / 2, abs(c - a), abs(d - b)


def box(cx, cy, cz, sx, sy, sz):
    return cq.Workplane("XY").box(sx, sy, sz).translate((cx, cy, cz))


ZB = FLOOR + COLUMN_H     # PCB bottom
ZT = ZB + BT              # PCB top
ZL = ZT + ABOVE           # lid underside = wall top
IX0, IY0 = -GAP, -GAP     # cavity corner (board coords)
IW, ID = BW + 2 * GAP, BD + 2 * GAP
OX0, OY0 = IX0 - WALL, IY0 - WALL
OW, OD = IW + 2 * WALL, ID + 2 * WALL


def rbox(x0, y0, w, d, h, r, z0=0.0):
    return (cq.Workplane("XY").workplane(offset=z0).center(x0 + w / 2, y0 + d / 2)
            .rect(w, d).extrude(h).edges("|Z").fillet(r))


# ------------------------------------------------------------------ base
def base():
    b = rbox(OX0, OY0, OW, OD, ZL, R_OUT)
    b = b.cut(rbox(IX0, IY0, IW, ID, ZL, R_IN, z0=FLOOR))
    for (x, y) in (K(*h) for h in HOLES):                     # PCB columns, merged into the walls at the corners
        col = cq.Workplane("XY").workplane(offset=FLOOR - 0.01).center(x, y).circle(COL_D / 2).extrude(COLUMN_H + 0.01)
        b = b.union(col)
        b = b.cut(cq.Workplane("XY").center(x, y).circle(SCREW_D / 2).extrude(ZB + 1))
        b = b.cut(cq.Workplane("XY").center(x, y).circle(CBORE_D / 2).extrude(CBORE_H))
    # USB-C window, right wall (plug overmold up to 12.5 x 7 mm)
    _, uy = K(BW, USBC[0])
    usb = box(BW + GAP + WALL / 2, uy, ZT + 1.6, WALL + 2 * GAP + 2, 13.0, 7.5).edges("|X").fillet(2.5)
    b = b.cut(usb)
    # WJ500V window, back wall: wire entries, from the PCB top to 10 mm above it
    cx, _, tw, _ = kbox(J102_X[0], 0, J102_X[1], 1)
    b = b.cut(box(cx, BD + GAP + WALL / 2, ZT + 5.0, tw + 1.0, WALL + 2 * GAP + 2, 10.0))
    # floor vents under the HV converter (KiCad x 12..46, y 8..26): 1.6 mm slots, finger-safe
    for i in range(9):
        x, y = K(14.0 + i * 3.6, 17.0)
        b = b.cut(cq.Workplane("XY").workplane(offset=-0.1).center(x, y).slot2D(18.0, 1.6, angle=90)
                  .extrude(FLOOR + 0.2))
    # rubber-foot recesses (10 mm self-adhesive bumpers)
    for (x, y) in (K(*f) for f in [(60.0, 12.0), (110.0, 12.0), (18.0, 48.0), (110.0, 48.0)]):
        b = b.cut(cq.Workplane("XY").workplane(offset=-0.1).center(x, y).circle(5.3).extrude(1.1))
    return b


# ------------------------------------------------------------------ lid
def lid():
    lt = rbox(OX0, OY0, OW, OD, LID_T, R_OUT, z0=ZL)
    # locating lip that drops into the base
    lip_o = rbox(IX0 + LIP_CLR, IY0 + LIP_CLR, IW - 2 * LIP_CLR, ID - 2 * LIP_CLR, LIP_H, R_IN - LIP_CLR, z0=ZL - LIP_H)
    lip_i = rbox(IX0 + LIP_CLR + LIP_W, IY0 + LIP_CLR + LIP_W, IW - 2 * (LIP_CLR + LIP_W), ID - 2 * (LIP_CLR + LIP_W),
                 LIP_H, max(R_IN - LIP_CLR - LIP_W, 0.5), z0=ZL - LIP_H)
    l = lt.union(lip_o.cut(lip_i))
    # the lip must not run into the WJ500V body (back edge) or the USB-C (right edge)
    cx, _, tw, _ = kbox(J102_X[0], 0, J102_X[1], 1)
    l = l.cut(box(cx, BD + GAP, ZL - LIP_H / 2, tw + 2.0, 4.0, LIP_H + 0.2))
    l = l.cut(box(BW + GAP, K(0, USBC[0])[1], ZL - LIP_H / 2, 4.0, 16.0, LIP_H + 0.2))
    # bosses down to the PCB top, with insert / tap holes
    for (x, y) in (K(*h) for h in HOLES):
        boss = cq.Workplane("XY").workplane(offset=ZT).center(x, y).circle(COL_D / 2).extrude(ABOVE + 0.01)
        l = l.union(boss)
        hd, hh = (INSERT_D, INSERT_H) if INSERT else (2.5, 8.0)
        l = l.cut(cq.Workplane("XY").workplane(offset=ZT - 0.01).center(x, y).circle(hd / 2).extrude(hh))
    # tubes
    for (x, y) in (K(*t) for t in TUBES):
        l = l.cut(cq.Workplane("XY").workplane(offset=ZT).center(x, y).circle(TUBE_HOLE / 2).extrude(ABOVE + LID_T + 1))
    # screwdriver access to the WJ500V clamps, pin holes for RESET / BOOT
    for (x, y) in (K(*j) for j in J102_PINS):
        l = l.cut(cq.Workplane("XY").workplane(offset=ZL - LIP_H - 1).center(x, y).circle(2.4).extrude(LID_T + LIP_H + 2))
    for (name, bx, by) in BUTTONS:
        x, y = K(bx, by)
        l = l.cut(cq.Workplane("XY").workplane(offset=ZL - 1).center(x, y).circle(1.25).extrude(LID_T + 2))
        txt = (cq.Workplane("XY").workplane(offset=ZL + LID_T - 0.5).center(x - 3.0, y)
               .text(name, 2.5, 0.6, halign="right", valign="center", font="Arial"))
        l = l.cut(txt)
    if METAL:   # antenna window (glue a 2 mm plastic plate on top)
        cx, cy, w, d = kbox(*ANTENNA)
        l = l.cut(box(cx, cy + GAP / 2, ZL + LID_T / 2, w, d + GAP, LID_T + 2))
    return l


def lid_lasercut():
    """Flat 3 mm acrylic lid: same outline and openings, M3 through-holes over 13 mm M3 standoffs (no lip, no bosses)."""
    l = rbox(OX0, OY0, OW, OD, LID_T, R_OUT)                  # flat part at z = 0
    holes = ([(K(*h), SCREW_D) for h in HOLES] + [(K(*t), TUBE_HOLE) for t in TUBES] +
             [(K(*j), 4.8) for j in J102_PINS] + [(K(bx, by), 2.5) for (_, bx, by) in BUTTONS])
    for (x, y), d in holes:
        l = l.cut(cq.Workplane("XY").workplane(offset=-1).center(x, y).circle(d / 2).extrude(LID_T + 2))
    return l


# ------------------------------------------------------------------ dummy board + parts for the fit check
def dummy_pcb():
    p = rbox(0, 0, BW, BD, BT, 2.0, z0=ZB)
    for (x, y) in (K(*h) for h in HOLES):
        p = p.cut(cq.Workplane("XY").workplane(offset=ZB - 1).center(x, y).circle(1.6).extrude(BT + 2))
    parts = [  # KiCad courtyard (x0, y0, x1, y1), height above the PCB top
        (38.95, 6.20, 46.14, 15.89, 11.0),     # C106 2.2 uF 250 V electrolytic
        (7.88, 0.11, 19.13, 11.00, 10.5),      # J102 WJ500V
        (19.70, 1.05, 33.89, 11.64, 4.0),      # L101
        (99.45, 0.05, 128.05, 25.64, 3.2),     # ESP32-C3-WROOM-02 (incl. antenna area)
        (119.04, 26.19, 128.55, 36.92, 3.3),   # USB-C
        (88.95, 15.95, 94.14, 27.64, 1.5),     # buttons
    ]
    for (x0, y0, x1, y1, h) in parts:
        cx, cy, w, d = kbox(x0, y0, x1, y1)
        p = p.union(cq.Workplane("XY").workplane(offset=ZT).center(cx, cy).rect(w, d).extrude(h))
    tubes = None
    for (x, y) in (K(*t) for t in TUBES):   # IN-16: glass from 5 mm above the PCB, ~11.5 mm diameter, 40 mm tall
        t = cq.Workplane("XY").workplane(offset=ZT + 5.0).center(x, y).circle(5.75).extrude(40.0)
        tubes = t if tubes is None else tubes.union(t)
    return p, tubes


def main():
    b, l = base(), lid()
    p, t = dummy_pcb()
    # fit check: nothing of the board / parts / tubes may intersect the case
    for name, body in (("base", b), ("lid", l)):
        for what, other in (("PCB + parts", p), ("tubes", t)):
            v = body.intersect(other).val().Volume() if body.intersect(other).vals() else 0.0
            print("interference %-4s / %-11s %.3f mm3" % (name, what, v))
    out = lambda n: os.path.join(HERE, n)
    cq.exporters.export(b, out("case_base.step"))
    cq.exporters.export(l, out("case_lid.step"))
    cq.exporters.export(b, out("case_base.stl"), tolerance=0.02, angularTolerance=0.1)
    # the lid prints top-down: flip it so the bosses point up
    lp = l.rotate((0, 0, 0), (1, 0, 0), 180)
    cq.exporters.export(lp, out("case_lid.stl"), tolerance=0.02, angularTolerance=0.1)
    asm = (cq.Assembly(name="NixiClockV1_case")
           .add(b, name="base", color=cq.Color(0.15, 0.15, 0.17))
           .add(l, name="lid", color=cq.Color(0.55, 0.36, 0.2))
           .add(p, name="pcb_dummy", color=cq.Color(0.1, 0.45, 0.2))
           .add(t, name="tubes_dummy", color=cq.Color(0.9, 0.6, 0.3, 0.5)))
    asm.export(out("case_assembly.step"))
    # 2D lid outline + holes for laser-cut acrylic (use 13 mm M3 standoffs instead of the printed bosses)
    sec = cq.Workplane("XY").add(lid_lasercut().val()).section(LID_T / 2)
    assert sec.vals(), "empty lid section"
    cq.exporters.export(sec, out("case_lid_lasercut.dxf"))
    bb = b.val().BoundingBox()
    print("outside: %.1f x %.1f x %.1f mm (lid top at z %.1f)" % (bb.xlen, bb.ylen, ZL + LID_T, ZL + LID_T))
    print("volumes: base %.1f cm3, lid %.1f cm3" % (b.val().Volume() / 1000, l.val().Volume() / 1000))


if __name__ == "__main__":
    main()
