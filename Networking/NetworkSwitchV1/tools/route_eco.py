"""Fix-up pass on the routed board (run after route_finish.py), then export a DSN with only the missing links.

1. CH32V208 (U501) corner: its caps, crystal and BOOT0 resistor move out to the QFN corners so the 0.4 mm-pitch
   pins can escape; all routing in that corner and every track of the MCU's signal nets is ripped up.
2. Dangling vias and the track stubs left on them are removed.
3. RTL8370N core pins 20-23 (+1V1, adjacent) are tied together on the pin row.
4. Plane pads that lost or never had a connection get a fanout via or a router group (fanout.py / dsn_export.py).
5. Everything already routed is locked, so Freerouting only adds the missing connections.
Then: Freerouting on route/NetworkSwitchV1.dsn, route_finish.py, route_cleanup.py.
"""
import os, sys
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fanout, dsn_export

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "NetworkSwitchV1.kicad_pcb")
X0, Y0 = 100.0, 50.0
FM, TM = pcbnew.FromMM, pcbnew.ToMM
B = pcbnew.LoadBoard(PCB)


def P(x, y):
    return pcbnew.VECTOR2I(FM(X0 + x), FM(Y0 + y))


def inside(v, box):
    return box[0] <= TM(v.x) - X0 <= box[2] and box[1] <= TM(v.y) - Y0 <= box[3]


# ---------------------------------------------------------------- 1. MCU corner
BOX = (145.5, 14.0, 163.5, 31.0)
mcu = B.FindFootprintByReference("U501")
mcu_nets = {str(p.GetNetname()) for p in mcu.Pads()} - set(dsn_export.PLANE_NETS) - {""}
mcu_nets = {n for n in mcu_nets if not n.startswith("unconnected")}
ep = [p for p in mcu.Pads() if p.GetNumber() == "29"][0].GetBoundingBox()
ripped = 0
for t in list(B.GetTracks()):
    net = str(t.GetNetname())
    if t.Type() == pcbnew.PCB_VIA_T and ep.Contains(t.GetPosition()):
        continue                                          # exposed-pad thermal vias stay
    if net in mcu_nets or inside(t.GetStart(), BOX) or inside(t.GetEnd(), BOX):
        B.Delete(t)
        ripped += 1
MOVES = {"C503": (160.6, 21.9, 0), "Y501": (160.4, 25.4, 90), "C502": (157.4, 28.7, 270),
         "R501": (155.6, 28.7, 270), "C505": (151.6, 26.9, 270), "C501": (151.4, 18.9, 180),
         "C504": (148.7, 18.9, 90)}
for ref, (x, y, rot) in MOVES.items():
    f = B.FindFootprintByReference(ref)
    f.SetOrientationDegrees(rot)
    f.SetPosition(P(x, y))
crt = {f.GetReference(): f.GetCourtyard(pcbnew.F_CrtYd).BBox() for f in B.GetFootprints()}
for ref in MOVES:
    for other, bb in crt.items():
        if other != ref and crt[ref].Intersects(bb):
            print("  WARNING: %s courtyard overlaps %s" % (ref, other))
print("MCU corner: ripped %d items, moved %s" % (ripped, " ".join(MOVES)))


# ---------------------------------------------------------------- 2. dangling vias / stubs
def connected_end(t, pt, items):
    for o in items:
        if o is t or id(o) in dead:
            continue
        if o.Type() == pcbnew.PCB_VIA_T:
            if str(o.GetNetname()) == str(t.GetNetname()) and (o.GetPosition() - pt).EuclideanNorm() <= o.GetWidth(pcbnew.F_Cu) // 2:
                return True
        elif o.GetLayer() == t.GetLayer() and str(o.GetNetname()) == str(t.GetNetname()):
            if pcbnew.SEG(o.GetStart(), o.GetEnd()).Distance(pt) <= o.GetWidth() // 2:
                return True
    return False


pads_by_net = {}
for f in B.GetFootprints():
    for p in f.Pads():
        pads_by_net.setdefault(str(p.GetNetname()), []).append(p)


def on_pad(net, pt, layer):
    for p in pads_by_net.get(net, ()):
        if p.IsOnLayer(layer) and p.HitTest(pt):
            return True
    return False


removed = 1
total = 0
dead = set()
while removed:
    removed = 0
    items = list(B.GetTracks())
    dead = set()
    by_net = {}
    for t in items:
        by_net.setdefault(str(t.GetNetname()), []).append(t)
    for t in items:
        if id(t) in dead or t.IsLocked():
            continue
        net = str(t.GetNetname())
        if t.Type() == pcbnew.PCB_VIA_T:
            n = sum(1 for o in by_net[net] if id(o) not in dead and o.Type() != pcbnew.PCB_VIA_T and
                    (o.GetStart() == t.GetPosition() or o.GetEnd() == t.GetPosition()))
            if n <= 1 and not on_pad(net, t.GetPosition(), pcbnew.F_Cu):
                dead.add(id(t))
                B.Delete(t)
                removed += 1
            continue
        for pt in (t.GetStart(), t.GetEnd()):
            if not on_pad(net, pt, t.GetLayer()) and not connected_end(t, pt, by_net[net]):
                dead.add(id(t))
                B.Delete(t)
                removed += 1
                break
    total += removed
print("cleanup: removed %d dangling vias/stubs" % total)

# ---------------------------------------------------------------- 3. RTL8370N core pins 20-23
u = B.FindFootprintByReference("U301")
pin = {p.GetNumber(): p for p in u.Pads()}
t = pcbnew.PCB_TRACK(B)
t.SetStart(pin["20"].GetPosition())
t.SetEnd(pin["23"].GetPosition())
t.SetWidth(FM(0.25))
t.SetLayer(pcbnew.F_Cu)
t.SetNet(pin["20"].GetNet())
t.SetLocked(True)
B.Add(t)

# ---------------------------------------------------------------- 4. plane pads without a connection
planes = {}
for z in B.Zones():
    if not z.GetIsRuleArea() and str(z.GetNetname()) in dsn_export.PLANE_NETS:
        planes.setdefault(str(z.GetNetname()), pcbnew.SHAPE_POLY_SET()).Append(z.Outline())
fo = fanout.Fanout(B, planes)
tracks_by_net = {}
for t in B.GetTracks():
    tracks_by_net.setdefault(str(t.GetNetname()), []).append(t)


def pad_connected(p):
    net = str(p.GetNetname())
    for t in tracks_by_net.get(net, ()):
        if t.Type() == pcbnew.PCB_VIA_T:
            if p.HitTest(t.GetPosition()):
                return True
        elif p.IsOnLayer(t.GetLayer()):
            if p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd()):
                return True
            if pcbnew.SEG(t.GetStart(), t.GetEnd()).Distance(p.GetPosition()) <= t.GetWidth() // 2:
                return True
    return False


done, todo = [], []
for f in B.GetFootprints():
    for p in f.Pads():
        net = str(p.GetNetname())
        if net not in planes:
            continue
        if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            if fo.allowed[net].Contains(p.GetPosition()) or pad_connected(p):
                done.append(p)
            else:
                todo.append(p)
        elif pad_connected(p):
            done.append(p)
        else:
            todo.append(p)
left = []
for p in todo:
    net = str(p.GetNetname())
    if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and p.GetParentFootprint().GetReference() not in ("U301", "U501"):
        b = p.GetBoundingBox()
        w = min(fanout.WIDTH.get(net, 0.25), TM(min(b.GetWidth(), b.GetHeight())))
        r = fo.place(p, net, w)
        if r:
            fo._new_stub(r[0], r[1], w, p.GetNet(), net)
            fo._new_via(r[1], p.GetNet(), net)
            done.append(p)
            continue
    left.append(p)
print("plane pads: %d connected, %d new fanouts, %d to route: %s" %
      (len(done) - (len(todo) - len(left)), len(todo) - len(left), len(left),
       " ".join(dsn_export.pname(p) for p in left)))
GROUPS = dsn_export.group_leftovers(fo, done, left)

# ---------------------------------------------------------------- 5. lock what is routed, export
for t in B.GetTracks():
    t.SetLocked(True)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
dsn_export.export(B, GROUPS, os.path.join(PRJ, "route", "NetworkSwitchV1.dsn"))
