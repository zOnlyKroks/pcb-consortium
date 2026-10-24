"""Merge the router's copies of the locked fan-out / anchor vias (run after route_finish.py).

Freerouting re-emits an anchor via it routed to, sometimes 0.05-0.2 mm off: two holes on top of each other.  Each
unlocked via within 0.5 mm of a locked via of the same net is deleted and the tracks that ended on it are moved
onto the locked via.  Deletion is done on the file text (SWIG breaks after mass B.Remove).
"""
import math, os, re
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, "..", "V2.kicad_pcb"))
FM, TM = pcbnew.FromMM, pcbnew.ToMM

B = pcbnew.LoadBoard(PCB)
vias = [t for t in B.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
locked = [v for v in vias if v.IsLocked()]
drop, moved = set(), 0
for v in vias:
    if v.IsLocked():
        continue
    p = v.GetPosition()
    near = [l for l in locked if l.GetNetCode() == v.GetNetCode() and (l.GetPosition() - p).EuclideanNorm() < FM(0.5)]
    if not near:
        continue
    tgt = min(near, key=lambda l: (l.GetPosition() - p).EuclideanNorm()).GetPosition()
    for t in B.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.IsLocked() or t.GetNetCode() != v.GetNetCode():
            continue
        if (t.GetStart() - p).EuclideanNorm() < FM(0.05):
            t.SetStart(tgt); moved += 1
        if (t.GetEnd() - p).EuclideanNorm() < FM(0.05):
            t.SetEnd(tgt); moved += 1
    drop.add(v.m_Uuid.AsString())
pcbnew.SaveBoard(PCB, B)
txt = open(PCB, encoding="utf-8").read()
item = re.compile(r"\n\t\(via\n.*?\n\t\)(?=\n)", re.S)
txt = item.sub(lambda m: "" if re.search(r'\(uuid "([^"]*)"\)', m.group(0)).group(1) in drop else m.group(0), txt)
open(PCB, "w", encoding="utf-8").write(txt)
print("merged %d duplicate vias, moved %d track ends" % (len(drop), moved))
