"""Local Freerouting re-run of the two port areas (run on a routed board, then route_finish.py).

Every track / via outside the port windows is locked, so Freerouting only re-routes what lies inside them, with
all of it free to move.  The DSN gets the same surgery as route_prep.py (plane nets out, their copper a netless
obstacle).  Writes route/V2.dsn.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import route_prep as RP

WINDOWS = [(54.0, 147.0, 112.0, 180.0), (179.0, 147.0, 237.0, 180.0)]
FM, TM = pcbnew.FromMM, pcbnew.ToMM


def inside(p):
    x, y = TM(p.x), TM(p.y)
    return any(a <= x <= c and b <= y <= d for a, b, c, d in WINDOWS)


B = pcbnew.LoadBoard(RP.PCB)
B.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
B.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
n_lock = n_free = 0
for t in B.GetTracks():
    if t.IsLocked():
        continue
    pts = [t.GetPosition()] if t.Type() == pcbnew.PCB_VIA_T else [t.GetStart(), t.GetEnd()]
    if all(inside(p) for p in pts):
        n_free += 1
    else:
        t.SetLocked(True)
        t.SetFlags(0)
        n_lock += 1
pcbnew.SaveBoard(RP.PCB, B)
os.makedirs(RP.OUT, exist_ok=True)
assert pcbnew.ExportSpecctraDSN(B, RP.DSN)
RP.dsn_surgery(B, [], [])
print("locked %d items outside the port windows, %d free inside" % (n_lock, n_free))
