"""Import the Freerouting session (route/V2.ses) into V2.kicad_pcb, fill the zones and save.

route_prep.py handed a few plane pads to the router as "<net>__<n>" nets (GND__3, PBATT__7): they get their real
net back here.  Freerouting echoes the fixed copper back as ordinary wires; those copies are dropped on the file
text (deleting many items through the python API breaks SWIG's object wrapping).
"""
import os, re, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "V2.kicad_pcb")
SES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PRJ, "route", "V2.ses")

ses = open(SES, encoding="utf-8").read()
ses = re.sub(r"\bGND__\d+", "GND", ses)
ses = re.sub(r"\bPBATT__\d+", "+BATT", ses)
SES2 = SES.replace(".ses", ".import.ses")
open(SES2, "w", encoding="utf-8").write(ses)

B = pcbnew.LoadBoard(PCB)
before = len(B.GetTracks())
ok = pcbnew.ImportSpecctraSES(B, SES2)
pcbnew.SaveBoard(PCB, B)
print("SES import:", ok, "items before %d, after %d" % (before, len(B.GetTracks())))

txt = open(PCB, encoding="utf-8").read()
item = re.compile(r"\n\t\((segment|via|arc)\n.*?\n\t\)(?=\n)", re.S)


def key(block):
    kind = block.split("(", 2)[1].split("\n")[0]
    if kind == "via":
        return ("via", re.search(r"\(at ([^)]*)\)", block).group(1))
    s = re.search(r"\(start ([^)]*)\)", block).group(1)
    e = re.search(r"\(end ([^)]*)\)", block).group(1)
    lay = re.search(r'\(layer "([^"]*)"\)', block).group(1)
    return (kind, lay) + tuple(sorted((s, e)))


locked = {key(m.group(0)) for m in item.finditer(txt) if "(locked yes)" in m.group(0)}
dups = [0]


def strip(m):
    b = m.group(0)
    if "(locked yes)" not in b and key(b) in locked:
        dups[0] += 1
        return ""
    return b


txt = item.sub(strip, txt)
open(PCB, "w", encoding="utf-8").write(txt)
print("removed %d copies of fixed items" % dups[0])

B = pcbnew.LoadBoard(PCB)
pcbnew.ZONE_FILLER(B).Fill(B.Zones())
pcbnew.SaveBoard(PCB, B)
tr = list(B.GetTracks())
print("tracks %d, vias %d" % (sum(t.Type() != pcbnew.PCB_VIA_T for t in tr), sum(t.Type() == pcbnew.PCB_VIA_T for t in tr)))
