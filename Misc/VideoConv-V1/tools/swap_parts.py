"""J6 (SCART), J7 (3.5 mm jack) and SW1 (tact switch) of VideoConv-V1: put real, buyable parts and their footprints on the schematic.
  J6  generic 21-pin right-angle PCB SCART socket (Kycon K-SCART-021 geometry), NOT on LCSC -> buy on eBay / Electrokit 41022977 / Console5
  J7  XKB PJ-307N5, LCSC C692542, footprint Jack_3.5mm_PJ-307N5_Horizontal (pad names T / R / S, same symbol as before)
  SW1 XKB TS-1187A-B-A-B, LCSC C318884, footprint SW_TS-1187A-B-A-B (symbol Switch:SW_Push pins 1 / 2 unchanged)
In-place text patch of sheets/Inputs.kicad_sch and sheets/FPGA.kicad_sch (wherever the reference lives); run tools/add_lcsc.py afterwards.
Run with KiCad's python:  python -I tools/swap_parts.py"""
import glob, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))

CHANGES = {
    "J6": {"Footprint": "VideoConv-V1:SCART_Kycon_K-SCART-021",
           "MPN": "21-pin right-angle PCB SCART socket (Kycon K-SCART-021 type)",
           "Note": "not on LCSC: eBay / Electrokit 41022977 / Console5; footprint = Kycon K-SCART-021 drawing, compare with the seller's drawing"},
    "J7": {"Footprint": "VideoConv-V1:Jack_3.5mm_PJ-307N5_Horizontal", "MPN": "PJ-307N5",
           "Note": "SCART audio pass-through (no HDMI audio in v1); T / R order by geometry analogy with CUI SJ1-3525N, check L / R with a plug"},
    "SW1": {"Footprint": "VideoConv-V1:SW_TS-1187A-B-A-B", "MPN": "TS-1187A-B-A-B"},
}


def closing(s, k):
    d, i = 0, k
    while True:
        c = s[i]
        if c == '"':
            i = s.index('"', i + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i
        i += 1


def setprop(s, key, val):
    pat = r'\(property "%s" "[^"]*"' % re.escape(key)
    if re.search(pat, s):
        return re.sub(pat, '(property "%s" "%s"' % (key, val.replace("\\", "\\\\")), s, 1)
    at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", s)
    new = ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)\n'
           '\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n') % (key, val, at.group(1), at.group(2))
    k = s.index("\n\t\t(pin ") + 1
    return s[:k] + new + s[k:]


done = set()
for f in glob.glob(os.path.join(PRJ, "sheets", "*.kicad_sch")):
    t = open(f, encoding="utf-8").read()
    changed = False
    for m in list(re.finditer(r'\n\t\(symbol\n\t\t\(lib_id "[^"]+"\)\n', t))[::-1]:
        a = m.start() + 1
        b = closing(t, a + 1) + 1
        s = t[a:b]
        ref = re.search(r'\(property "Reference" "([^"]*)"', s).group(1)
        if ref in CHANGES:
            for k, v in CHANGES[ref].items():
                s = setprop(s, k, v)
            t = t[:a] + s + t[b:]
            changed = True
            done.add(ref)
    if changed:
        open(f, "w", encoding="utf-8").write(t)
        print("patched", os.path.basename(f))
print("done:", sorted(done), "missing:", sorted(set(CHANGES) - done))
