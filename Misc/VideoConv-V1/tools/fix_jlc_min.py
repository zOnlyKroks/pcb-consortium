"""Bring VideoConv-V1.kicad_pcb inside JLCPCB's standard (no extra cost) limits:
  * every track segment of 0.0889 mm (3.5 mil) is widened to 0.1 mm (JLC 4-layer minimum is 0.09 mm); a segment that would then break the
    0.1 mm spacing to another net gets 0.094 mm instead
  * vias with a drill below 0.2 mm (one: the GND stub of TFP410 pad 32) are removed when the same pad already has a standard 0.45 / 0.2 mm via;
    the stub tracks touching it go too; the back-side GND chain it fed is re-attached to the standard via (they are cut out of the file text because
    removing items through the pcbnew API invalidates the SWIG wrappers)
Zones are refilled at the end.  Run with KiCad's python:  python -I tools/fix_jlc_min.py   (idempotent)"""
import math, os, re, sys
import pcbnew

H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
PCB = os.path.join(PRJ, "VideoConv-V1.kicad_pcb")
mm, FM = pcbnew.ToMM, pcbnew.FromMM
WIDE, NARROW, CLR = 0.1, 0.094, 0.1


def uid(o):
    return o.m_Uuid.AsString()


def near(q, pt, r):
    return math.hypot(mm(q.x) - mm(pt.x), mm(q.y) - mm(pt.y)) < r


# ------------------------------------------------------------------ 1. read-only analysis: which vias / tracks go
A = pcbnew.LoadBoard(PCB)
tracks = list(A.GetTracks())
vias = [t for t in tracks if t.GetClass() == "PCB_VIA"]
segs = [t for t in tracks if t.GetClass() != "PCB_VIA"]
victims = set()
bridges = []
KEEP_VIA = "--keep-via" in sys.argv        # only widen the tracks, leave the 0.15 mm via alone
for via in ([] if KEEP_VIA else [v for v in vias if mm(v.GetDrillValue()) < 0.19]):
    net = via.GetNetCode()
    vp = via.GetPosition()
    pads = [p for f in A.GetFootprints() for p in f.Pads() if p.GetNetCode() == net]
    twin = [v for v in vias if uid(v) != uid(via) and v.GetNetCode() == net and mm(v.GetDrillValue()) >= 0.19
            and any(p.HitTest(v.GetPosition()) and p.HitTest(vp, FM(0.8)) for p in pads)]
    print("via %.2f mm drill at (%.2f, %.2f) net %s: " % (mm(via.GetDrillValue()), mm(vp.x), mm(vp.y), via.GetNetname()), end="")
    if not twin:
        print("no standard via in the same pad, left alone (needs manual rework)")
        continue
    print("the same pad has a %.2f / %.2f mm via -> removing it" % (mm(twin[0].GetWidth(pcbnew.F_Cu)), mm(twin[0].GetDrillValue())))
    gone = {uid(via)}
    bridge = None
    for t in segs:
        if t.GetNetCode() != net or not (near(t.GetStart(), vp, 0.1) or near(t.GetEnd(), vp, 0.1)):
            continue
        gone.add(uid(t))
        if t.GetLayer() == pcbnew.B_Cu:                           # a back-side stub that led to the rest of the GND chain
            far = [q for q in (t.GetStart(), t.GetEnd()) if not near(q, vp, 0.1)]
            if far:
                bridge = (twin[0].GetPosition().x, twin[0].GetPosition().y, far[0].x, far[0].y, net)
    print("   %d stub track(s) go with it; B.Cu link %s" % (len(gone) - 1, "re-attached to the standard via" if bridge else "none"))
    bridges.append(bridge) if bridge else None
    victims |= gone
del A

# ------------------------------------------------------------------ 2. cut them out of the file text
if victims:
    t = open(PCB, encoding="utf-8").read()
    removed = 0
    for u in victims:
        k = t.find('(uuid "%s")' % u)
        if k < 0:
            continue
        a = max(t.rfind("\n\t(via\n", 0, k), t.rfind("\n\t(segment\n", 0, k), t.rfind("\n\t(arc\n", 0, k)) + 1
        d, i = 0, a
        while True:
            c = t[i]
            if c == '"':
                i = t.index('"', i + 1)
            elif c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            i += 1
        b = i + 1
        if t[b] == "\n":
            b += 1
        t = t[:a] + t[b:]
        removed += 1
    open(PCB, "w", encoding="utf-8").write(t)
    print("cut %d of %d items out of the board file" % (removed, len(victims)))

# ------------------------------------------------------------------ 3. widen the 3.5 mil tracks
B = pcbnew.LoadBoard(PCB)
thin = [t for t in B.GetTracks() if t.GetClass() != "PCB_VIA" and 0.08 < mm(t.GetWidth()) < 0.09]
for t in thin:
    t.SetWidth(FM(WIDE))
narrow = 0
for t in thin:
    sh = t.GetEffectiveShape(t.GetLayer())
    for o in B.GetTracks():
        if uid(o) == uid(t) or o.GetNetCode() == t.GetNetCode():
            continue
        if o.GetClass() != "PCB_VIA" and o.GetLayer() != t.GetLayer():
            continue
        if sh.Collide(o.GetEffectiveShape(t.GetLayer()), FM(CLR)):
            t.SetWidth(FM(NARROW)); narrow += 1
            break
print("segments widened to %.3f mm: %d (%d of them only to %.3f mm, 0.1 mm would break the 0.1 mm spacing)" % (WIDE, len(thin), narrow, NARROW))
for (x0, y0, x1, y1, net) in bridges:
    tr = pcbnew.PCB_TRACK(B)
    tr.SetLayer(pcbnew.B_Cu); tr.SetWidth(FM(0.2)); tr.SetNetCode(net)
    tr.SetStart(pcbnew.VECTOR2I(x0, y0)); tr.SetEnd(pcbnew.VECTOR2I(x1, y1))
    B.Add(tr)
    print("added B.Cu GND link (%.2f, %.2f) -> (%.2f, %.2f)" % (mm(x0), mm(y0), mm(x1), mm(y1)))
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
print("saved", PCB)
