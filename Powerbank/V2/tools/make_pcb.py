"""Build V2.kicad_pcb from the schematic netlist: 4-layer JLC04161H-7628 stack-up, outline, footprints placed, not routed.

Board 191 x 130 mm.  Top: the eight 18650 holders side by side (4S2P, holder orientation alternates so the series
links are short pad-to-pad hops).  Bottom strip (y 141-180): port A on the left, port B mirrored on the right,
protection FETs/shunt under the bottom cell group (BATN), fuse under the top group (CELL4), 5 V buck, 3.3 V LDO,
BQ77915 and the fuel gauge in the middle; USB-C, buttons and LEDs on the front (bottom) edge.

Footprints keep their schematic symbol link (KIID path), so KiCad's "Update PCB from Schematic" works afterwards.
Run from KiCad's python:  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/make_pcb.py
WARNING: rebuilds the board from scratch - do not re-run once the PCB has been edited by hand.
"""
import os, re, subprocess, sys, tempfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
SCH = os.path.join(PRJ, "V2.kicad_sch")
PCB = os.path.join(PRJ, "V2.kicad_pcb")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"
LIBS = {"PowerbankV2": os.path.join(PRJ, "lib", "PowerbankV2.pretty")}

X0, Y0, X1, Y1 = 50.0, 50.0, 241.0, 180.0          # board outline
MIRROR = X0 + X1                                    # port B: x' = MIRROR - x

# ------------------------------------------------------------------------------------------------- placement
PLACE = {}
# holders: group g (BT1(2g+1), BT1(2g+2)); rot 0 = + at the top, rot 180 = + at the bottom
for i in range(8):
    PLACE["BT1%02d" % (i + 1)] = (68.6 + 22.0 * i, 95.5, 0 if (i // 2) % 2 == 0 else 180)
for k, (x, y) in enumerate(((54, 56), (54, 174), (237, 56), (237, 174)), 1):
    PLACE["H40%d" % k] = (x, y, 0)

# port A (refs 2xx); port B = same offsets, mirrored about the board centre line.
# The TPS25751D (U01) is not mirrored: both sit rotated 180 deg so CC / D+- / VBUS face their own USB-C connector,
# 3 mm right of it.  Its decoupling caps and GPIO pull-downs are placed at their pins by place_at_pins().
PORT = {
    "J01": (64.0, 176.35, 0), "D01": (58.4, 167.6, 0), "C01": (55.9, 167.6, 90),
    "C08": (78.4, 166.8, 90), "C09": (81.0, 166.8, 90), "C10": (83.6, 166.8, 90), "C11": (86.2, 166.8, 90),
    "C12": (88.4, 166.8, 90),
    "U03": (95.0, 163.0, 0), "L01": (95.0, 153.0, 0), "C18": (90.6, 164.0, 0), "C19": (99.8, 163.2, 0),
    "C14": (83.8, 158.0, 90), "C15": (86.4, 158.0, 90), "C16": (89.0, 158.0, 90), "C17": (91.6, 158.9, 90),
    "C20": (101.2, 158.0, 90), "C21": (103.8, 158.0, 90), "C22": (106.4, 158.0, 90), "C23": (101.2, 152.6, 90),
    "C24": (103.8, 152.6, 90), "C25": (97.6, 158.9, 90),
    "C26": (102.2, 165.4, 0), "C27": (102.2, 167.8, 0), "C28": (102.2, 170.0, 0),
    "R04": (98.8, 166.0, 90), "C30": (99.0, 171.0, 0), "C29": (91.2, 166.6, 0),
    "R05": (106.4, 163.2, 0), "R06": (106.4, 165.2, 0), "R07": (106.4, 167.2, 0), "RT01": (104.0, 143.0, 0),
    "U02": (59.5, 151.0, 0), "C13": (65.2, 149.4, 0), "JP01": (65.2, 152.2, 0), "J02": (53.2, 144.6, 0),
    "R01": (57.2, 155.8, 0), "R02": (60.2, 155.8, 0), "R03": (63.2, 155.8, 0),
    "D02": (86.0, 178.5, 0), "R08": (89.0, 178.5, 0),
}
TPS_AT = {2: (67.0, 161.6, 180), 3: (230.0, 161.6, 180)}
# part key -> TPS25751D pad it belongs to (decoupling first: they get the closest spots)
AT_PINS = [("C02", "38"), ("C03", "1"), ("C04", "4"), ("C05", "34"), ("C06", "28"), ("C07", "29"),
           ("R09", "5"), ("R10", "6"), ("R11", "7"), ("R12", "19"), ("R13", "37"), ("R14", "36"), ("R15", "13")]


def port_ref(n, key):
    pre = re.match(r"[A-Z]+", key).group(0)
    return "%s%d%s" % (pre, n, key[len(pre):])


for key, (x, y, rot) in PORT.items():
    PLACE[port_ref(2, key)] = (x, y, rot)
    PLACE[port_ref(3, key)] = (MIRROR - x, y, rot)
for key in ("U02", "C13", "JP01", "R01", "R02", "R03"):   # EEPROM block follows the (unmirrored) TPS25751D
    x, y, rot = PORT[key]
    PLACE[port_ref(3, key)] = (x + TPS_AT[3][0] - TPS_AT[2][0], y, rot)
PLACE["J302"] = (236.5, 145.0, 0)
for n, at in TPS_AT.items():
    PLACE["U%d01" % n] = at
for n in (2, 3):                                     # placed by place_at_pins(): park them for now
    for k, (key, _) in enumerate(AT_PINS):
        PLACE[port_ref(n, key)] = (60.0 + 3 * k + 60 * (n - 2), 195.0, 0)

PLACE.update({
    # protection power path under the bottom cell group (BATN pads at x 68.6 / 90.6, y 136.8)
    "R111": (72.0, 145.0, 0), "Q101": (80.5, 145.5, 0), "Q102": (88.5, 145.5, 0),
    "R112": (69.0, 148.6, 0), "R113": (72.0, 148.6, 0),
    "R114": (74.5, 153.0, 0), "R115": (77.5, 153.0, 0), "R116": (80.5, 153.0, 0), "R117": (83.5, 153.0, 0),
    "R118": (86.5, 153.0, 0),
    "F101": (211.6, 144.0, 0),
    # BQ77915 cluster
    "U101": (116.0, 149.0, 0), "RT101": (116.0, 142.6, 0),
    "R101": (110.0, 143.0, 0), "C101": (110.0, 145.0, 0), "C102": (110.0, 147.0, 0),
    "R102": (110.0, 149.0, 0), "R103": (110.0, 151.0, 0), "R104": (110.0, 153.0, 0), "R105": (110.0, 155.0, 0),
    "R106": (113.0, 155.4, 0), "C103": (116.0, 155.4, 0), "C104": (119.0, 155.4, 0), "C105": (122.0, 155.4, 0),
    "C106": (113.0, 157.4, 0), "C107": (116.0, 157.4, 0),
    "R107": (122.0, 145.0, 0), "R108": (122.0, 147.0, 0), "R109": (122.0, 149.0, 0), "R110": (122.0, 151.0, 0),
    "C108": (122.0, 153.0, 0), "C109": (119.0, 157.4, 0), "C110": (122.0, 157.4, 0),
    # 3.3 V LDO, PD host header
    "U402": (130.0, 145.0, 0), "C412": (126.6, 145.0, 90), "C413": (133.4, 145.0, 90), "R406": (130.0, 148.4, 0),
    "J401": (127.0, 152.6, 90), "R407": (130.0, 156.0, 0), "R408": (133.0, 156.0, 0), "R409": (136.0, 156.0, 0),
    # 5 V buck
    "U401": (152.0, 149.0, 0), "C405": (152.0, 144.0, 0), "C401": (141.0, 145.6, 90), "C402": (143.5, 145.6, 90),
    "C403": (145.0, 149.6, 0), "R401": (145.0, 151.6, 0), "R402": (145.0, 153.6, 0), "C404": (148.0, 154.4, 0),
    "L401": (165.0, 147.0, 0), "D401": (157.0, 155.0, 0),
    "C408": (162.0, 159.2, 90), "C409": (164.5, 159.2, 90), "C410": (167.0, 159.2, 90), "C411": (169.5, 159.2, 90),
    "R403": (151.0, 156.6, 0), "R404": (151.0, 158.6, 0), "R405": (154.0, 158.6, 0), "C406": (154.0, 160.6, 0),
    "C407": (151.0, 160.6, 0),
    # fuel gauge
    "U403": (139.0, 167.0, 90), "U404": (125.0, 169.6, 0), "C414": (132.2, 162.6, 0), "C415": (147.0, 166.0, 90),
    "R410": (125.0, 162.6, 0), "R411": (128.6, 162.6, 0), "R412": (125.0, 164.6, 0), "R413": (128.6, 164.6, 0),
    "R414": (128.6, 166.6, 0), "R415": (147.0, 170.6, 90), "R416": (149.4, 170.6, 90),
    "D402": (131.0, 178.5, 0), "D403": (135.0, 178.5, 0), "D404": (139.0, 178.5, 0), "D405": (143.0, 178.5, 0),
    "R417": (131.0, 175.6, 0), "R418": (135.0, 175.6, 0), "R419": (139.0, 175.6, 0), "R420": (143.0, 175.6, 0),
    "SW401": (121.0, 176.4, 0), "SW402": (155.0, 176.4, 0),
})

STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 2" (type "core") (thickness 1.065) (material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "7628") (epsilon_r 4.4) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(copper_finish "HAL lead-free")
			(dielectric_constraints no)
		)
"""


# JLC standard tier (see memory/jlc-standard-tier): 0.3/0.7 vias, 0.3 mm copper-to-edge, 1.0 mm silk text.
# min_clearance 0.1 only for the TPS25751D footprint-local clearance (TI land pattern); net classes stay at 0.15.
RULES = {"min_clearance": 0.1, "min_track_width": 0.15, "min_via_diameter": 0.7, "min_through_hole_diameter": 0.3,
         "min_via_annular_width": 0.2, "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25,
         "min_copper_edge_clearance": 0.3, "min_text_height": 1.0, "min_text_thickness": 0.15}
POWER_NETS = ["+BATT", "-BATT", "Net-(BT1*", "Net-(Q101-*", "GND", "+5V", "*VBUS_*", "*PPHV_*", "*PMID_*",
              "*SYS_*", "Net-(U*03-SW*", "Net-(D401-K)"]


def apply_project_settings():
    """SaveBoard rewrites V2.kicad_pro with the fresh board's defaults; put the project rules back."""
    import json
    pro = os.path.join(PRJ, "V2.kicad_pro")
    d = json.load(open(pro, encoding="utf-8"))
    d["board"]["design_settings"]["rules"].update(RULES)
    ns = d["net_settings"]
    default = dict(ns["classes"][0])
    default.update({"name": "Default", "clearance": 0.15, "track_width": 0.2, "via_diameter": 0.7, "via_drill": 0.3})
    power = dict(default)
    power.update({"name": "Power", "track_width": 1.0, "priority": 0})
    ns["classes"] = [default, power]
    ns["netclass_patterns"] = [{"netclass": "Power", "pattern": p} for p in POWER_NETS]
    json.dump(d, open(pro, "w", encoding="utf-8"), indent=2)


# ------------------------------------------------------------------------------------------------- netlist
def sexp_tokens(text):
    return re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', text)


def parse(text):
    stack = [[]]
    for t in sexp_tokens(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            d = stack.pop()
            stack[-1].append(d)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return stack[0][0]


def child(node, key):
    return next((c for c in node if isinstance(c, list) and c and c[0] == key), None)


def children(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def netlist():
    out = os.path.join(tempfile.gettempdir(), "pbv2_net.net")
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", out, SCH], check=True,
                   capture_output=True)
    root = parse(open(out, encoding="utf-8").read())
    comps = []
    for c in children(child(root, "components"), "comp"):
        ref = child(c, "ref")[1]
        fields = {f[1][1] if isinstance(f[1], list) else "": f[2] if len(f) > 2 else ""
                  for f in children(child(c, "fields") or [], "field")}
        props = {p[1][1]: (p[2][1] if len(p) > 2 else "") for p in children(c, "property")}
        sp = child(c, "sheetpath")
        tstamps = child(sp, "tstamps")[1]
        comps.append(dict(ref=ref, value=child(c, "value")[1], fp=(child(c, "footprint") or [None, ""])[1],
                          datasheet=(child(c, "datasheet") or [None, ""])[1],
                          description=(child(c, "description") or [None, ""])[1],
                          fields=fields, props=props, path=tstamps + child(c, "tstamps")[1]))
    nets = []
    for n in children(child(root, "nets"), "net"):
        name = child(n, "name")[1]
        nodes = [(child(x, "ref")[1], child(x, "pin")[1]) for x in children(n, "node")]
        nets.append((name, nodes))
    return comps, nets


# ------------------------------------------------------------------------------------------------- build
def load_fp(fpid):
    lib, name = fpid.split(":")
    path = LIBS.get(lib) or os.path.join(STOCK, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise RuntimeError("footprint not found: " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def mm(v):
    return pcbnew.FromMM(v)


def courtyard(fp):
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    return (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()), pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def place_at_pins(byref):
    """Put each AT_PINS part next to its TPS25751D pad: pin of the same net toward the pad, long axis radial,
    stepping outward / sideways until the courtyard is free."""
    for n in (2, 3):
        u = byref["U%d01" % n]
        uc = u.GetPosition()
        others = [f for f in byref.values() if not any(f.GetReference() == port_ref(m, k) for m in (2, 3)
                                                         for k, _ in AT_PINS)]
        boxes = [courtyard(f) for f in others]
        for key, padnum in AT_PINS:
            f = byref[port_ref(n, key)]
            pad = [q for q in u.Pads() if q.GetNumber() == padnum][0]
            P = pad.GetPosition()
            dx, dy = P.x - uc.x, P.y - uc.y
            ux, uy = (1 if dx > 0 else -1, 0) if abs(dx) * 1.3 > abs(dy) else (0, 1 if dy > 0 else -1)
            vx, vy = -uy, ux
            px, py = pcbnew.ToMM(P.x), pcbnew.ToMM(P.y)
            mine = [q for q in f.Pads() if q.GetNetCode() == pad.GetNetCode()][0].GetNumber()
            done = False
            for d in [1.3 + 0.35 * k for k in range(22)]:
                for lat in (0, 0.9, -0.9, 1.8, -1.8, 2.7, -2.7, 3.6, -3.6, 4.5, -4.5):
                    cx, cy = px + ux * d + vx * lat, py + uy * d + vy * lat
                    for rot in (0, 90, 180, 270):
                        f.SetPosition(pcbnew.VECTOR2I(mm(cx), mm(cy)))
                        f.SetOrientationDegrees(rot)
                        q = [q for q in f.Pads() if q.GetNumber() == mine][0].GetPosition()
                        o = [q for q in f.Pads() if q.GetNumber() != mine][0].GetPosition()
                        if (q - P).EuclideanNorm() < (o - P).EuclideanNorm() and                                 abs((q.x - o.x) * vx + (q.y - o.y) * vy) < mm(0.1):      # radial, own pin inward
                            break
                    c = courtyard(f)
                    if c[0] < X0 + 0.5 or c[2] > X1 - 0.5 or c[3] > Y1 - 0.5:
                        continue
                    if all(c[2] + 0.05 < b[0] or b[2] + 0.05 < c[0] or c[3] + 0.05 < b[1] or b[3] + 0.05 < c[1]
                           for b in boxes):
                        boxes.append(c)
                        done = True
                        break
                if done:
                    break
            if not done:
                print("WARNING: no spot for", f.GetReference())


def via(b, x, y, net, d=0.7, drill=0.3):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(d))
    v.SetDrill(mm(drill))
    v.SetNet(net)
    v.SetLocked(True)
    b.Add(v)


def main():
    comps, nets = netlist()
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    ds = b.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))
    byref = {}
    missing = []
    for c in comps:
        if not c["fp"]:
            raise RuntimeError("no footprint on " + c["ref"])
        fp = load_fp(c["fp"])
        fp.SetReference(c["ref"])
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        if c["datasheet"] and c["datasheet"] != "~":
            fp.GetField(pcbnew.FIELD_T_DATASHEET).SetText(c["datasheet"])
        if c["description"]:
            fp.GetField(pcbnew.FIELD_T_DESCRIPTION).SetText(c["description"])
        lcsc = c["fields"].get("LCSC Part #") or c["props"].get("LCSC Part #")
        if lcsc:
            fp.SetField("LCSC Part #", lcsc)
            fld = fp.GetField("LCSC Part #")
            if fld:
                fld.SetVisible(False)
        if "dnp" in c["props"]:
            fp.SetDNP(True)
        if "exclude_from_bom" in c["props"]:
            fp.SetExcludedFromBOM(True)
        if c["ref"] not in PLACE:
            missing.append(c["ref"])
            x, y, rot = 60.0 + 3 * len(missing), 190.0, 0
        else:
            x, y, rot = PLACE[c["ref"]]
        b.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(rot)
        byref[c["ref"]] = fp
    place_at_pins(byref)
    # nets
    for name, nodes in nets:
        ni = pcbnew.NETINFO_ITEM(b, name)
        b.Add(ni)
        for ref, pin in nodes:
            fp = byref.get(ref)
            if fp is None:
                continue
            hit = False
            for pad in fp.Pads():
                if pad.GetNumber() == pin:
                    pad.SetNet(ni)
                    hit = True
            if not hit:
                print("WARNING: no pad %s on %s" % (pin, ref))
    # outline
    pts = [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
        s.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        b.Add(s)
    # planes, battery busbars, GND pours
    def net_of(ref, pad):
        return [q for q in byref[ref].Pads() if q.GetNumber() == pad][0].GetNet()

    def zone(layer, net, pts, name, prio=0, clearance=0.3, min_w=0.25):
        z = pcbnew.ZONE(b)
        z.SetLayer(layer)
        z.SetNet(net)
        z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(mm(x), mm(y))
        z.SetMinThickness(mm(min_w))
        z.SetLocalClearance(mm(clearance))
        z.SetAssignedPriority(prio)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        b.Add(z)
        return z

    def rect(x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    board = rect(X0 + 0.3, Y0 + 0.3, X1 - 0.3, Y1 - 0.3)
    gnd, vbat = b.FindNet("GND"), b.FindNet("+BATT")
    zone(pcbnew.In1_Cu, gnd, board, "GND plane")
    zone(pcbnew.In2_Cu, vbat, board, "VBAT plane")
    zone(pcbnew.F_Cu, gnd, board, "GND pour F", prio=0)
    zone(pcbnew.B_Cu, gnd, board, "GND pour B", prio=0)
    # 4S2P links and the BATN -> shunt -> FET path as locked wide tracks on F.Cu (about 10 A).  Tracks, not
    # zones: Freerouting keeps out of fixed tracks but runs straight through fixed polygons.  route_pours.py pours
    # extra copper around them after routing.
    def bar(net, pts, w):
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
            t.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
            t.SetWidth(mm(w))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(net)
            t.SetLocked(True)
            b.Add(t)
    YT, YB = 54.19, 136.81                               # holder pad rows
    bar(net_of("BT101", "1"), [(68.6, YT), (134.6, YT)], 5.0)                 # CELL1
    bar(net_of("BT105", "1"), [(156.6, YT), (222.6, YT)], 5.0)                # CELL3
    bar(net_of("BT103", "1"), [(112.6, YB), (156.6, YB)], 5.0)                # CELL2
    bar(net_of("BT107", "1"), [(200.6, YB), (222.6, YB)], 5.0)                # CELL4
    bar(net_of("BT107", "1"), [(207.1, YB), (207.1, 144.0)], 3.0)             # CELL4 -> fuse
    bar(net_of("BT101", "2"), [(68.6, YB), (90.6, YB)], 5.0)                  # BATN
    bar(net_of("BT101", "2"), [(68.9, YB), (68.9, 145.0)], 2.4)               # BATN -> shunt
    sns = net_of("R111", "2")
    bar(sns, [(74.96, 145.0), (74.96, 148.4), (81.13, 148.4)], 1.4)           # shunt -> DSG FET source
    bar(net_of("Q101", "5"), [(80.5, 144.2), (88.5, 144.2)], 3.0)             # DSG drain <-> CHG drain
    bar(vbat, [(216.1, 144.0), (219.4, 144.0)], 3.0)                          # fuse out -> VBAT vias
    for x in (217.6, 219.2):                        # fuse output into the In2 VBAT plane
        for y in (142.2, 145.8):
            via(b, x, y, vbat)
    for x in (86.59, 87.86, 89.13):                 # charge FET source pins straight into the In1 GND plane
        bar(gnd, [(x, 148.4), (x, 150.3)], 0.58)
        via(b, x, 150.3, gnd)
    # board texts
    t = pcbnew.PCB_TEXT(b)
    t.SetText("PowerbankV2  2x USB-C PD 45 W  4S2P 18650")
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(pcbnew.VECTOR2I(mm(173.0), mm(171.0)))
    t.SetTextSize(pcbnew.VECTOR2I(mm(1.2), mm(1.2)))
    t.SetTextThickness(mm(0.18))
    b.Add(t)
    pcbnew.SaveBoard(PCB, b)
    # JLC04161H-7628 stack-up
    text = open(PCB, encoding="utf-8").read()
    text = re.sub(r"\t\t\(stackup\n.*?\n\t\t\)\n", "", text, flags=re.S)
    text = text.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1)
    open(PCB, "w", encoding="utf-8").write(text)
    apply_project_settings()
    if missing:
        print("not placed:", " ".join(sorted(missing)))
    print("footprints:", len(byref), " nets:", len(nets))


if __name__ == "__main__":
    main()
