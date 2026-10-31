"""Swap the SCART / RCA placeholder footprints on the board for the project's real ones, keeping nets, reference,
value, schematic link (path) and fields.  Pad nets are copied by pad number (pad 2 of the RCA jack exists twice).
Run once per reference (KiCad python cannot load two footprints in one process):
  python -I tools/swap_footprints.py J2   (J2 J3 J4 J5 -> RCA, J6 -> SCART), after make_footprints.py"""
import os
import pcbnew

H = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(H, ".."))
PCB = os.path.join(PRJ, "VideoConv-V1.kicad_pcb")
LIB = os.path.join(PRJ, "lib", "VideoConv-V1.pretty")
B = pcbnew.LoadBoard(PCB)
SWAP = {"J2": "RCA_XDJK-0271-1650", "J3": "RCA_XDJK-0271-1650", "J4": "RCA_XDJK-0271-1650", "J5": "RCA_XDJK-0271-1650",
        "J6": "SCART_Tyco_1483465-1"}
import sys
for ref, name in [(r, SWAP[r]) for r in sys.argv[1:]]:
    old = B.FindFootprintByReference(ref)
    if str(old.GetFPIDAsString()).endswith(name):
        continue
    new = pcbnew.FootprintLoad(LIB, name)
    new.SetParent(B)
    new.SetReference(ref)
    new.SetValue(old.GetValue())
    new.SetPath(old.GetPath())
    new.SetFPID(pcbnew.LIB_ID("VideoConv-V1", name))
    for p in new.Pads():
        op = old.FindPadByNumber(p.GetNumber())
        if op is not None:
            p.SetNet(op.GetNet())
    new.SetPosition(old.GetPosition())
    new.SetSheetname(old.GetSheetname())
    new.SetSheetfile(old.GetSheetfile())
    B.Remove(old)
    B.Add(new)
    print(ref, "->", name)
pcbnew.SaveBoard(PCB, B)
