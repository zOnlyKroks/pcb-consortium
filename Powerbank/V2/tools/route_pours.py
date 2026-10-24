"""Copper pours for the high-current nets, grown around their routed copper (run after route_finish.py).

Freerouting routes the power nets at 0.3 mm so they can reach the 0.4 mm-pitch QFN pins.  Here every heavy net
gets a zone on each outer layer it uses: the outline is its tracks + pads (+ fan-out vias) buffered by a few mm,
so the pour only spreads where the net already runs.  The routed track stays underneath, so a pour that the fill
trims or starves never opens a connection.  Each net gets its own priority (switch nodes highest, so their loops
stay small), all above the GND pours (0) and below the battery busbars (5... raised to 20 here).
Re-running replaces the zones this script made (names start with "pour ").
"""
import os, re
import pcbnew
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "V2.kicad_pcb")
FM, TM = pcbnew.FromMM, pcbnew.ToMM
X0, Y0, X1, Y1 = 50.0, 50.0, 241.0, 180.0
STRIP = box(X0 + 0.3, 140.6, X1 - 0.3, Y1 - 0.3)        # electronics strip under the cells

# (net pattern, grow mm); listed from highest to lowest priority
HEAVY = [(r"Net-\(U[23]03-SW1\)", 1.0), (r"Net-\(U[23]03-SW2\)", 1.0), (r"Net-\(D401-K\)", 1.0),
         (r".*/PMID_[AB]", 1.5), (r".*/SYS_[AB]", 1.5), (r".*/PPHV_[AB]", 1.8), (r".*/VBUS_[AB]", 1.8),
         (r"\+5V", 1.5), (r"\+BATT", 1.8)]


def outline(item, layer):
    s = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(s, layer, 0, FM(0.01), pcbnew.ERROR_INSIDE)
    out = []
    for i in range(s.OutlineCount()):
        ol = s.Outline(i)
        pts = [(TM(ol.CPoint(k).x), TM(ol.CPoint(k).y)) for k in range(ol.PointCount())]
        if len(pts) >= 3:
            out.append(Polygon(pts).buffer(0))
    return out


def main():
    txt = open(PCB, encoding="utf-8").read()
    # drop zones from an earlier run (file text: removing zones through SWIG is fragile)
    zre = re.compile(r"\n\t\(zone\n.*?\n\t\)(?=\n)", re.S)
    txt = zre.sub(lambda m: "" if re.search(r'\(name "pour ', m.group(0)) else m.group(0), txt)
    open(PCB, "w", encoding="utf-8").write(txt)
    B = pcbnew.LoadBoard(PCB)
    for z in B.Zones():                                 # busbars above every pour
        if z.GetAssignedPriority() >= 5:
            z.SetAssignedPriority(20)
    nets = [n for n in B.GetNetsByName().keys()]
    made = 0
    prio = 15
    for pat, grow in HEAVY:
        for name in sorted(str(n) for n in nets if re.fullmatch(pat, str(n))):
            net = B.FindNet(name)
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                geo = []
                for t in B.GetTracks():
                    if t.GetNetname() == name and (t.Type() == pcbnew.PCB_VIA_T or t.GetLayer() == layer):
                        geo += outline(t, layer)
                has_track = any(t.GetNetname() == name and t.Type() != pcbnew.PCB_VIA_T and t.GetLayer() == layer
                                for t in B.GetTracks())
                for f in B.GetFootprints():
                    for p in f.Pads():
                        if p.GetNetname() == name and p.IsOnLayer(layer):
                            geo += outline(p, layer)
                if not geo or (layer == pcbnew.B_Cu and not has_track):
                    continue
                area = unary_union(geo).buffer(grow, join_style=2).intersection(STRIP)
                polys = [area] if area.geom_type == "Polygon" else list(area.geoms)
                for poly in polys:
                    if poly.area < 1.0:
                        continue
                    poly = poly.simplify(0.05)
                    z = pcbnew.ZONE(B)
                    z.SetLayer(layer)
                    z.SetNet(net)
                    z.SetZoneName("pour %s" % name)
                    ol = z.Outline()
                    ol.NewOutline()
                    for x, y in list(poly.exterior.coords)[:-1]:
                        ol.Append(FM(x), FM(y))
                    z.SetAssignedPriority(prio)
                    z.SetLocalClearance(FM(0.2))
                    z.SetMinThickness(FM(0.2))
                    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
                    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
                    B.Add(z)
                    made += 1
            prio -= 1 if prio > 1 else 0
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    pcbnew.SaveBoard(PCB, B)
    print("pours:", made)


if __name__ == "__main__":
    main()
