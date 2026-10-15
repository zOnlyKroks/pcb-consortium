"""Prepare NetworkSwitchV1.kicad_pcb for autorouting and export the Specctra DSN.

- In1.Cu / In2.Cu become plane layers: In1 = GND (secondary) + RTN (PoE primary), In2 = +3V3 with a +1V1 island
  from the 1.1 V buck to the RTL8370N.  Plane outlines avoid the line side (no planes there) and the PoE primary,
  so the router's idea of where a plane exists matches what KiCad will fill.
- Route widths per net class (sized so every class still leaves the 0.5 mm-pitch RTL8370N pins).
- Thermal via arrays in the RTL8370N and CH32V208 exposed pads (locked).
- Writes route/NetworkSwitchV1.dsn for Freerouting (see route_run.py).
"""
import json, os, re, sys
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "NetworkSwitchV1.kicad_pcb")
PRO = os.path.join(PRJ, "NetworkSwitchV1.kicad_pro")
OUT = os.path.join(PRJ, "route")
X0, Y0, W, D = 100.0, 50.0, 170.0, 90.0
FM = pcbnew.FromMM

# ---------------------------------------------------------------- net classes (project file, read by LoadBoard)
pro = json.load(open(PRO, encoding="utf-8"))
ns = pro["net_settings"]
base = dict([c for c in ns["classes"] if c["name"] == "Default"][0])
base.update({"clearance": 0.15, "track_width": 0.2, "via_diameter": 0.7, "via_drill": 0.3})


def cls(name, prio, **kw):
    c = dict(base)
    c.update(kw)
    c["name"] = name
    c["priority"] = prio
    return c


ns["classes"] = [base,
                 cls("MDI_100R", 0, clearance=0.15, track_width=0.22, diff_pair_width=0.22, diff_pair_gap=0.2),
                 cls("MDI_LINE", 1, clearance=0.25, track_width=0.22, diff_pair_width=0.22, diff_pair_gap=0.25),
                 cls("PoE_SW", 2, clearance=0.5, track_width=0.8),
                 cls("PoE_HV", 3, clearance=0.2, track_width=0.4),
                 cls("Power_HC", 4, clearance=0.2, track_width=0.5),
                 cls("Power_IC", 5, clearance=0.15, track_width=0.3),
                 cls("Power", 6, clearance=0.15, track_width=0.25),
                 cls("Chassis", 7, clearance=0.3, track_width=0.5)]
# auto-named nets (the schematic is frozen, so these names are stable)
BR_P, BR_N, DRAIN, CLAMP = "Net-(BR101-+)", "Net-(BR101--)", "Net-(D102-A)", "Net-(D102-K)"
pat = [("MDI_100R", "Net-(TR4*-TD*"), ("MDI_100R", "MG_*"),
       ("MDI_LINE", "Net-(TR4*-MX*")]
pat += [("PoE_SW", n) for n in (DRAIN, CLAMP)]
pat += [("PoE_HV", n) for n in (BR_P, BR_N, "RTN", "POE_CT1", "POE_CT2", "POE_CT3", "POE_CT4")]
pat += [("Power_HC", n) for n in ("+12V", "Net-(U104-SW)", "Net-(U105-SW)", "Net-(F101-Pad1)", "Net-(D106-K)",
                                  "Net-(D105-A)")]
pat += [("Power_IC", n) for n in ("+1V1", "+1V1A", "+3V3A", "+1V1P")]
pat += [("Power", n) for n in ("+3V3", "GND")]
pat += [("Chassis", "CHASSIS")]
ns["netclass_patterns"] = [{"netclass": c, "pattern": p} for c, p in pat]
json.dump(pro, open(PRO, "w", encoding="utf-8"), indent=2)

B = pcbnew.LoadBoard(PCB)                     # first load in this process: picks up the classes above

# ---------------------------------------------------------------- planes
B.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
B.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)


def rect(x0, y0, x1, y1):
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        s.Append(FM(X0 + x), FM(Y0 + y))
    return s


def union(*polys):
    s = pcbnew.SHAPE_POLY_SET()
    for p in polys:
        s.BooleanAdd(p)
    s.Simplify()
    return s


def minus(a, *polys):
    s = pcbnew.SHAPE_POLY_SET(a)
    for p in polys:
        s.BooleanSubtract(p)
    s.Simplify()
    return s


BOARD = rect(0.5, 0.5, W - 0.5, D - 0.5)
PRIMARY_SIDE = rect(0, 44.5, 41.0, D)                     # PoE primary + barrier column
LINE_SIDE = rect(41.0, 61.3, 155.0, D)                    # cable side of the magnetics + jacks: no planes
V11 = union(rect(48.0, 15.0, 104.5, 21.5),                # buck 2 output -> FB301/FB302
            rect(98.8, 9.4, 104.5, 21.5),
            rect(104.5, 15.5, 129.6, 38.6),                # under the RTL8370N and its first capacitor ring
            rect(114.4, 38.6, 120.0, 53.2))                # bottom supply cluster (core pins 20-23)
V11_KEEP = pcbnew.SHAPE_POLY_SET(V11)
V11_KEEP.Inflate(FM(0.5), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, FM(0.01))

for z in list(B.Zones()):
    if not z.GetIsRuleArea():
        B.Remove(z)


def plane(net, layer, poly, prio=0):
    z = pcbnew.ZONE(B)
    z.SetLayer(layer)
    z.SetNet(B.FindNet(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(FM(0.3))
    z.SetMinThickness(FM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(FM(0.3))
    z.SetThermalReliefSpokeWidth(FM(0.35))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.Outline().RemoveAllContours()
    z.Outline().Append(poly)
    B.Add(z)
    return z


GND_POLY = minus(BOARD, PRIMARY_SIDE, LINE_SIDE)
RTN_POLY = rect(0.5, 47.8, 37.7, D - 0.5)
V33_POLY = minus(BOARD, PRIMARY_SIDE, LINE_SIDE, V11_KEEP)
plane("GND", pcbnew.In1_Cu, GND_POLY)
plane("RTN", pcbnew.In1_Cu, RTN_POLY)
plane("+1V1", pcbnew.In2_Cu, V11, prio=1)
plane("+3V3", pcbnew.In2_Cu, V33_POLY)

# ---------------------------------------------------------------- thermal vias in exposed pads (locked)
for t in list(B.GetTracks()):                                 # start from an unrouted board
    B.Delete(t)
have = set()


def via_array(ref, num, n, pitch):
    p = [q for q in B.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
    c = p.GetPosition()
    for i in range(n):
        for j in range(n):
            xy = (c.x + FM((i - (n - 1) / 2) * pitch), c.y + FM((j - (n - 1) / 2) * pitch))
            if xy in have:                                    # re-runs keep the existing array
                continue
            v = pcbnew.PCB_VIA(B)
            v.SetPosition(pcbnew.VECTOR2I(*xy))
            v.SetWidth(FM(0.7))
            v.SetDrill(FM(0.3))
            v.SetNet(p.GetNet())
            v.SetLocked(True)
            B.Add(v)


via_array("U301", "129", 5, 1.3)
via_array("U501", "29", 2, 1.3)

import fanout, dsn_export
PLANES = {"GND": GND_POLY, "RTN": RTN_POLY, "+3V3": V33_POLY, "+1V1": V11}
fo = fanout.Fanout(B, PLANES)
done, left = fo.run()
print("fanout: %d plane pads on their own via" % len(done))
GROUPS = dsn_export.group_leftovers(fo, done, left)
pcbnew.SaveBoard(PCB, B)
dsn_export.export(B, GROUPS, os.path.join(OUT, "NetworkSwitchV1.dsn"))
