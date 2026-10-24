"""(Adapted from FPGA/LFE5U-25F-7BG256I/tools.)  Remove dead-end copper after routing (run after route_finish.py and after route_leftovers.py).

With the inner layers free, Freerouting mostly leaves a BGA ball's dog-bone via on In2/In3 directly, so the 0.1 mm
B.Cu escape behind that via ends nowhere.  Rip-up (route_leftovers.py) leaves dead ends too.  KiCad's DRC is the
judge of what dangles (track_dangling / via_dangling); nets that are still unrouted keep theirs.  A dangling track
that another track joins part-way along is trimmed back to that junction; one that nothing joins is deleted.
Rounds repeat until nothing dangles.  A round that would open a connection is undone, and the nets it broke keep
their dangling copper (a harmless stub) from then on.
Deleting is done on the file text: removing items through the python API breaks SWIG's object wrapping.
"""
import json, math, os, re, subprocess, tempfile
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "V2.kicad_pcb")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
item = re.compile(r"\n\t\((segment|via|arc)\n.*?\n\t\)(?=\n)", re.S)


def drc():
    out = os.path.join(tempfile.gettempdir(), "route_cleanup_drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", out, PCB], capture_output=True)
    d = json.load(open(out, encoding="utf-8"))
    open_nets = set()
    for u in d["unconnected_items"]:
        for i in u["items"]:
            m = re.search(r"\[([^\]]*)\]", i["description"])
            if m:
                open_nets.add(m.group(1))
    dead = {}
    for v in d["violations"]:
        if v["type"] in ("track_dangling", "via_dangling"):
            for i in v["items"]:
                m = re.search(r"\[([^\]]*)\]", i["description"])
                if m and m.group(1) not in open_nets:
                    dead[i["uuid"]] = m.group(1)
    return open_nets, dead


def plan(dead):
    """Trim what carries a junction, return the uuids to delete.  Saves the trims."""
    B = pcbnew.LoadBoard(PCB)
    by_net = {}
    for t in B.GetTracks():
        by_net.setdefault(t.GetNetCode(), []).append(t)
    pads = {}
    for f in B.GetFootprints():
        for p in f.Pads():
            pads.setdefault(p.GetNetCode(), []).append(p)
    delete = set()
    for t in B.GetTracks():
        u = t.m_Uuid.AsString()
        if u not in dead:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:                    # "dangling" = one layer only; it may still join two tracks
            hits = sum(1 for o in by_net.get(t.GetNetCode(), []) if o.m_Uuid.AsString() != u and o.Type() != pcbnew.PCB_VIA_T
                       and (t.HitTest(o.GetStart(), 0) or t.HitTest(o.GetEnd(), 0)))
            if not t.IsLocked() and hits <= 1:
                delete.add(u)
            continue
        L, w2 = t.GetLayer(), t.GetWidth() / 2
        others = [o for o in by_net.get(t.GetNetCode(), [])          # by uuid: SWIG wrappers are not identical
                  if o.m_Uuid.AsString() != u and o.m_Uuid.AsString() not in delete]

        def touches(P):
            if any(o.IsOnLayer(L) and o.HitTest(P, 0) for o in others):
                return True
            return any(p.IsOnLayer(L) and p.HitTest(P, 0) for p in pads.get(t.GetNetCode(), []))
        S, E = t.GetStart(), t.GetEnd()
        dx, dy = E.x - S.x, E.y - S.y
        L2 = float(dx * dx + dy * dy) or 1.0
        tol = w2 / math.sqrt(L2)                             # whatever sits at an end is not a junction part-way
        js = []                                              # junctions on the segment, as 0..1 along S -> E
        for o in others + pads.get(t.GetNetCode(), []):          # KiCad joins at track ends, via / pad centres
            if not o.IsOnLayer(L):
                continue
            if o.Type() == pcbnew.PCB_TRACE_T:                 # copper overlap counts, as in KiCad
                ends, reach = [o.GetStart(), o.GetEnd()], w2 + o.GetWidth() / 2
            elif o.Type() == pcbnew.PCB_VIA_T:
                ends, reach = [o.GetPosition()], w2 + o.GetWidth(L) / 2
            else:
                ends, reach = [o.GetPosition()], w2 + min(o.GetSize(L).x, o.GetSize(L).y) / 2
            for P in ends:
                u_ = ((P.x - S.x) * dx + (P.y - S.y) * dy) / L2
                if tol < u_ < 1.0 - tol:
                    qx, qy = S.x + u_ * dx, S.y + u_ * dy
                    if math.hypot(P.x - qx, P.y - qy) <= reach:
                        js.append(u_)
        cs, ce = touches(S), touches(E)
        at = lambda u_: pcbnew.VECTOR2I(int(S.x + u_ * dx), int(S.y + u_ * dy))
        if cs and not ce:
            if js:
                t.SetEnd(at(max(js)))
            else:
                delete.add(u)
        elif ce and not cs:
            if js:
                t.SetStart(at(min(js)))
            else:
                delete.add(u)
        elif not cs and not ce:
            if len(js) >= 2:
                a_, b_ = min(js), max(js)
                t.SetStart(at(a_))
                t.SetEnd(at(b_))
            else:
                delete.add(u)
    pcbnew.SaveBoard(PCB, B)
    return delete


open0, dead = drc()
print("unconnected nets: %s" % (" ".join(sorted(open0)) or "none"))
protect = set()                                              # nets a round broke: their stubs stay
total = rounds = 0
while rounds < 40:
    dead = {u: n for u, n in dead.items() if n not in protect}
    if not dead:
        break
    rounds += 1
    before = open(PCB, encoding="utf-8").read()
    delete = plan(set(dead))
    txt = open(PCB, encoding="utf-8").read()
    txt = item.sub(lambda m: "" if re.search(r'\(uuid "([^"]*)"\)', m.group(0)).group(1) in delete else m.group(0), txt)
    open(PCB, "w", encoding="utf-8").write(txt)
    open1, dead2 = drc()
    broke = open1 - open0
    if broke:
        open(PCB, "w", encoding="utf-8").write(before)
        protect |= broke
        print("round %d undone: it would have opened %s" % (rounds, " ".join(sorted(broke))))
        continue
    total += len(delete)
    if set(dead2) == set(dead):                              # only trimmed items left, still listed
        break
    dead = dead2
print("removed %d dangling items in %d rounds; protected: %s" % (total, rounds, " ".join(sorted(protect)) or "none"))

B = pcbnew.LoadBoard(PCB)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
tr = list(B.GetTracks())
print("tracks %d, vias %d" % (sum(t.Type() != pcbnew.PCB_VIA_T for t in tr), sum(t.Type() == pcbnew.PCB_VIA_T for t in tr)))
