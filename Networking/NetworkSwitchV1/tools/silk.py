"""Silkscreen reference placement (shared by place_pcb.py and the routing fix-ups).

silk_pass(B, only=None, notes=()): move each silkscreen reference (all, or just the refs in `only`) to a spot clear
of pads, other silk, other parts' courtyards and the board edge - inside the body for large parts, otherwise next
to the part - and hide it where nothing fits (the F.Fab copy stays for the assembly drawing).
"""
import pcbnew

FM = pcbnew.FromMM


def silk_pass(B, only=None, notes=(), unhide=False):
    def bb(item, grow=0.0):
        b = item.GetBoundingBox()
        g = FM(grow)
        return (b.GetX() - g, b.GetY() - g, b.GetRight() + g, b.GetBottom() + g)

    def hit(a, boxes):
        return any(a[0] < o[2] and o[0] < a[2] and a[1] < o[3] and o[1] < a[3] for o in boxes)

    fps = list(B.GetFootprints())
    pads = [bb(p, 0.2) for f in fps for p in f.Pads()]
    silk = {f.GetReference(): [bb(g, 0.1) for g in f.GraphicalItems() if g.GetLayer() == pcbnew.F_SilkS]
            for f in fps}
    crt = {}
    for f in fps:
        c = f.GetCourtyard(pcbnew.F_CrtYd)
        crt[f.GetReference()] = bb(f) if c.IsEmpty() else \
            (c.BBox().GetX(), c.BBox().GetY(), c.BBox().GetRight(), c.BBox().GetBottom())
    taken = [bb(t, 0.15) for t in notes]
    taken += [bb(d, 0.15) for d in B.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS]
    if only is not None:                                   # references we keep act as obstacles
        for f in fps:
            if f.GetReference() not in only and f.Reference().IsVisible() and f.Reference().GetLayer() == pcbnew.F_SilkS:
                taken.append(bb(f.Reference(), 0.15))
    eb = B.GetBoardEdgesBoundingBox()
    e = FM(0.5)
    inside = (eb.GetX() + e, eb.GetY() + e, eb.GetRight() - e, eb.GetBottom() - e)
    area = lambda r: (crt[r][2] - crt[r][0]) * (crt[r][3] - crt[r][1])
    hidden = []
    for f in sorted(fps, key=lambda f: -area(f.GetReference())):
        ref = f.GetReference()
        if only is not None and ref not in only:
            continue
        t = f.Reference()
        if unhide:
            t.SetVisible(True)
        if not t.IsVisible() or t.GetLayer() != pcbnew.F_SilkS:
            continue
        others_silk = [b for r, l in silk.items() if r != ref for b in l]
        others_crt = [b for r, b in crt.items() if r != ref]
        c = crt[ref]
        cx, cy = (c[0] + c[2]) // 2, (c[1] + c[3]) // 2
        cands = []
        step = FM(0.5)
        for ang in (0, 90):
            t.SetTextAngleDegrees(ang)
            t.SetPosition(pcbnew.VECTOR2I(cx, cy))
            tb = bb(t)
            hw, hh = (tb[2] - tb[0]) // 2, (tb[3] - tb[1]) // 2
            nx, ny = int((c[2] - c[0] - 2 * hw) / step), int((c[3] - c[1] - 2 * hh) / step)
            for i in range(nx + 1):                                  # inside the body (large parts)
                for j in range(ny + 1):
                    x, y = c[0] + hw + i * step, c[1] + hh + j * step
                    cands.append((0, abs(x - cx) + abs(y - cy), ang, x, y))
            for k, ring in ((1, FM(0.15)), (2, FM(1.2))):           # around the courtyard
                for x, y in ((cx, c[1] - hh - ring), (cx, c[3] + hh + ring), (c[0] - hw - ring, cy),
                             (c[2] + hw + ring, cy), (c[0] - hw - ring, c[1] - hh - ring),
                             (c[2] + hw + ring, c[1] - hh - ring), (c[0] - hw - ring, c[3] + hh + ring),
                             (c[2] + hw + ring, c[3] + hh + ring)):
                    cands.append((k, abs(x - cx) + abs(y - cy), ang, x, y))
        cands.sort(key=lambda k: (k[0], k[1], k[2]))
        ok = False
        for kind, _, ang, x, y in cands:
            t.SetTextAngleDegrees(ang)
            t.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            tb = bb(t)
            if tb[0] < inside[0] or tb[1] < inside[1] or tb[2] > inside[2] or tb[3] > inside[3]:
                continue
            if hit(tb, pads) or hit(tb, others_silk) or hit(tb, others_crt) or hit(tb, taken):
                continue
            if kind == 0 and hit(tb, silk[ref]):
                continue
            ok = True
            break
        if ok:
            taken.append(bb(t, 0.15))
        else:
            t.SetVisible(False)
            hidden.append(ref)
    print("silk: %d references hidden (no free spot): %s" % (len(hidden), " ".join(sorted(hidden))))
    return hidden
