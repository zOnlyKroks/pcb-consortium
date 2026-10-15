"""Import the Freerouting session (route/NetworkSwitchV1.ses) into the board, fill the planes and save.

Run route_prep.py first (planes, classes, DSN), then Freerouting, then this.
"""
import os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "NetworkSwitchV1.kicad_pcb")
SES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PRJ, "route", "NetworkSwitchV1.ses")

import re
# route_prep.py routed leftover plane pads as small "<plane net>__<n>" nets: give them their real net back
ses = open(SES, encoding="utf-8").read()
ses = re.sub(r"(GND|RTN|\+3V3|\+1V1)__\d+", lambda m: m.group(1), ses)
SES2 = SES.replace(".ses", ".import.ses")
open(SES2, "w", encoding="utf-8").write(ses)

B = pcbnew.LoadBoard(PCB)
locked = set()
for t in B.GetTracks():
    if t.IsLocked():
        locked.add((t.Type(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y))
before = len(B.GetTracks())
ok = pcbnew.ImportSpecctraSES(B, SES2)
dups = 0
for t in list(B.GetTracks()):                 # the router echoes our fixed copper back: drop the copies
    if not t.IsLocked() and (t.Type(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y) in locked:
        B.Delete(t)
        dups += 1
print("removed %d duplicate copies of fixed items" % dups)
tracks = [t for t in B.GetTracks()]
vias = [t for t in tracks if t.Type() == pcbnew.PCB_VIA_T]
print("SES import:", ok, "items before %d, after %d (%d vias)" % (before, len(tracks), len(vias)))
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
print("saved", PCB)
