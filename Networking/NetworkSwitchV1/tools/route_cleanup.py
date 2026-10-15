"""Final clean-up after importing a Freerouting session (run after route_finish.py).

- removes dangling vias and track stubs (iteratively),
- nudges vias that break a clearance rule (Freerouting gives vias the default clearance whatever their class),
  dragging the ends of the tracks attached to them,
- unlocks everything (the routing scripts lock what they keep), refills the zones and saves.
Usage: route_cleanup.py [drc.json]   (clearance violations from kicad-cli pcb drc --format json)
"""
import json, math, os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "NetworkSwitchV1.kicad_pcb")
FM, TM = pcbnew.FromMM, pcbnew.ToMM
B = pcbnew.LoadBoard(PCB)
nets = B.GetNetsByName()


sys.path.insert(0, HERE)
import rules
RULES = rules.Rules(B)


def cl(n):
    return RULES.clearance(n)


pads_by_net = {}
all_pads = []
for f in B.GetFootprints():
    for p in f.Pads():
        pads_by_net.setdefault(str(p.GetNetname()), []).append(p)
        all_pads.append(p)


def on_pad(net, pt, layer):
    return any(p.IsOnLayer(layer) and p.HitTest(pt) for p in pads_by_net.get(net, ()))


# ---------------------------------------------------------------- dangling vias / stubs
total, removed = 0, 1
while removed:
    removed = 0
    dead = set()
    items = list(B.GetTracks())
    by_net = {}
    for t in items:
        by_net.setdefault(str(t.GetNetname()), []).append(t)
    for t in items:
        if id(t) in dead:
            continue
        net = str(t.GetNetname())
        if t.Type() == pcbnew.PCB_VIA_T:
            n = sum(1 for o in by_net[net] if id(o) not in dead and o.Type() != pcbnew.PCB_VIA_T and
                    (o.GetStart() == t.GetPosition() or o.GetEnd() == t.GetPosition()))
            pad = any(p.HitTest(t.GetPosition()) for p in pads_by_net.get(net, ()))
            limit = 0 if net in ("GND", "RTN", "+3V3", "+1V1") else 1
            if n <= limit and not pad:
                dead.add(id(t))
                B.Delete(t)
                removed += 1
            continue
        for pt in (t.GetStart(), t.GetEnd()):
            if on_pad(net, pt, t.GetLayer()):
                continue
            ok = False
            for o in by_net[net]:
                if o is t or id(o) in dead:
                    continue
                if o.Type() == pcbnew.PCB_VIA_T:
                    if (o.GetPosition() - pt).EuclideanNorm() <= o.GetWidth(pcbnew.F_Cu) // 2:
                        ok = True
                        break
                elif o.GetLayer() == t.GetLayer() and pcbnew.SEG(o.GetStart(), o.GetEnd()).Distance(pt) <= o.GetWidth() // 2:
                    ok = True
                    break
            if not ok:
                dead.add(id(t))
                B.Delete(t)
                removed += 1
                break
    total += removed
print("removed %d dangling vias/stubs" % total)

# ---------------------------------------------------------------- DRC-flagged leftovers
if len(sys.argv) > 1:
    d0 = json.load(open(sys.argv[1], encoding="utf-8"))
    flagged = []
    for x in d0["violations"]:
        if x["type"] in ("via_dangling", "track_dangling"):
            it = x["items"][0]
            flagged.append((x["type"], FM(it["pos"]["x"]), FM(it["pos"]["y"])))
    gone = 0
    for kind, fx, fy in flagged:
        pt = pcbnew.VECTOR2I(fx, fy)
        for t in list(B.GetTracks()):
            if kind == "via_dangling" and t.Type() == pcbnew.PCB_VIA_T and (t.GetPosition() - pt).EuclideanNorm() < FM(0.01):
                net = str(t.GetNetname())
                att = [o for o in B.GetTracks() if o.Type() != pcbnew.PCB_VIA_T and str(o.GetNetname()) == net
                       and (o.GetStart() == t.GetPosition() or o.GetEnd() == t.GetPosition())]
                if net not in ("GND", "RTN", "+3V3", "+1V1") and len({o.GetLayer() for o in att}) <= 1:
                    B.Delete(t)                                # tracks still meet at this point
                    gone += 1
                break
            if kind == "track_dangling" and t.Type() != pcbnew.PCB_VIA_T and t.GetLength() < FM(0.1) and                     pcbnew.SEG(t.GetStart(), t.GetEnd()).Distance(pt) < FM(0.01):
                B.Delete(t)
                gone += 1
                break
    print("removed %d single-layer vias / zero-length stubs flagged by DRC" % gone)

# ---------------------------------------------------------------- nudge vias that violate clearance
pad_poly = {}


def pad_dist(p, c):
    if id(p) not in pad_poly:
        s = pcbnew.SHAPE_POLY_SET()
        p.TransformShapeToPolygon(s, pcbnew.F_Cu, 0, FM(0.005), pcbnew.ERROR_INSIDE)
        if s.OutlineCount() == 0:
            p.TransformShapeToPolygon(s, pcbnew.B_Cu, 0, FM(0.005), pcbnew.ERROR_INSIDE)
        pad_poly[id(p)] = s
    return math.sqrt(pad_poly[id(p)].SquaredDistance(c))


def pad_seg_dist(p, seg):
    pad_dist(p, seg.A)
    return math.sqrt(pad_poly[id(p)].SquaredDistanceToSeg(seg))


def via_ok(v, c, attached):
    net = str(v.GetNetname())
    r = v.GetWidth(pcbnew.F_Cu) / 2
    win = FM(3)
    for p in all_pads:
        if str(p.GetNetname()) == net or (p.GetPosition() - c).EuclideanNorm() > win:
            continue
        g = FM(max(cl(net), cl(str(p.GetNetname()))))
        if pad_dist(p, c) < r + g:
            return False
        for t, end in attached:
            if p.IsOnLayer(t.GetLayer()):
                other = t.GetEnd() if end == "s" else t.GetStart()
                if pad_seg_dist(p, pcbnew.SEG(c, other)) < t.GetWidth() / 2 + g:
                    return False
    for o in B.GetTracks():
        if str(o.GetNetname()) == net or o is v:
            continue
        g = FM(max(cl(net), cl(str(o.GetNetname()))))
        if o.Type() == pcbnew.PCB_VIA_T:
            if (o.GetPosition() - c).EuclideanNorm() < r + o.GetWidth(pcbnew.F_Cu) / 2 + g:
                return False
            continue
        seg = pcbnew.SEG(o.GetStart(), o.GetEnd())
        if seg.Distance(c) < r + o.GetWidth() / 2 + g:
            return False
        for t, end in attached:
            if t.GetLayer() == o.GetLayer():
                other = t.GetEnd() if end == "s" else t.GetStart()
                if seg.SquaredDistance(pcbnew.SEG(c, other)) < (t.GetWidth() / 2 + o.GetWidth() / 2 + g) ** 2:
                    return False
    return True


moved = failed = 0
if len(sys.argv) > 1:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    targets = set()
    for x in d["violations"]:
        if x["type"] != "clearance":
            continue
        for it in x["items"]:
            if it["description"].startswith("Via"):
                targets.add((round(it["pos"]["x"], 3), round(it["pos"]["y"], 3)))
    for v in [t for t in B.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]:
        key = (round(TM(v.GetPosition().x), 3), round(TM(v.GetPosition().y), 3))
        if key not in targets:
            continue
        old = v.GetPosition()
        attached = [(t, "s" if t.GetStart() == old else "e") for t in B.GetTracks()
                    if t.Type() != pcbnew.PCB_VIA_T and str(t.GetNetname()) == str(v.GetNetname())
                    and (t.GetStart() == old or t.GetEnd() == old)]
        done = False
        for step in (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5):
            for k in range(16):
                a = k * math.pi / 8
                c = pcbnew.VECTOR2I(int(old.x + FM(step * math.cos(a))), int(old.y + FM(step * math.sin(a))))
                if via_ok(v, c, attached):
                    v.SetPosition(c)
                    for t, end in attached:
                        (t.SetStart if end == "s" else t.SetEnd)(c)
                    done = True
                    break
            if done:
                break
        moved += done
        failed += not done
print("clearance: nudged %d vias, %d could not be moved" % (moved, failed))

# silkscreen references that DRC flags (parts moved during routing): place them again
if len(sys.argv) > 1:
    import re, silk
    flagged = set()
    for x in d["violations"]:
        if x["type"] in ("silk_over_copper", "silk_overlap"):
            for it in x["items"]:
                m = re.match(r"Reference field of (\S+)", it["description"])
                if m:
                    flagged.add(m.group(1))
    if flagged:
        silk.silk_pass(B, only=flagged)

for t in B.GetTracks():
    t.SetLocked(False)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
print("saved", PCB)
