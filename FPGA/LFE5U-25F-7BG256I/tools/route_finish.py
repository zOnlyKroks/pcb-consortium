"""Import the Freerouting session (route/LFE5U-25F-7BG256I.ses), fill the planes and save.

route_prep.py routed a few plane pads as "<plane net>__<n>" nets: they get their real net back here.  Freerouting
echoes the fixed fan-out copper back as ordinary wires; those copies are dropped (on the file text: deleting
hundreds of items through the python API breaks SWIG's object wrapping).
"""
import os, re, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pcb")
SES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PRJ, "route", "LFE5U-25F-7BG256I.ses")

ses = open(SES, encoding="utf-8").read()
ses = re.sub(r"(GND|\+3V3|\+1V1)__\d+", lambda m: m.group(1), ses)
SES2 = SES.replace(".ses", ".import.ses")
open(SES2, "w", encoding="utf-8").write(ses)

B = pcbnew.LoadBoard(PCB)
before = len(B.GetTracks())
ok = pcbnew.ImportSpecctraSES(B, SES2)
pcbnew.SaveBoard(PCB, B)
print("SES import:", ok, "items before %d, after %d" % (before, len(B.GetTracks())))

# drop the router's copies of locked items
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
tb = B.GetTitleBlock()
tb.SetComment(1, "Placed, fanned out and routed (tools/place_pcb.py, fanout_pcb.py, route_prep.py + Freerouting)")
pcbnew.SaveBoard(PCB, B)
tr = list(B.GetTracks())
print("tracks %d, vias %d" % (sum(t.Type() != pcbnew.PCB_VIA_T for t in tr), sum(t.Type() == pcbnew.PCB_VIA_T for t in tr)))
print("saved", PCB)
