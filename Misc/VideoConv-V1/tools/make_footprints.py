"""Write lib/VideoConv-V1.pretty: footprints that are not in KiCad's stock libraries.

SCART_Kycon_K-SCART-021  21-pin SCART socket, geometry from the Kycon K-SCART-021 drawing (1.905 mm staggered pitch, 5.08 mm row spacing,
                       1.3 mm holes, two 3.0 x 4.5 mm mounting pegs 49.8 mm apart)
RCA_XDJK-0271-1650     right-angle RCA jack, LCSC C7527522 (pad geometry from the EasyEDA footprint).
                       pad 1 = centre contact (signal, on the jack axis), pad 2 (two pads) = sleeve / ground

Both have the mating face towards +y (rotation 0).  Check against the manufacturer drawings before ordering boards.
Run:  python -I tools/make_footprints.py
"""
import os

H = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(H, "..", "lib", "VideoConv-V1.pretty")
os.makedirs(OUT, exist_ok=True)


def header(name, descr, tags):
    return ['(footprint "%s"' % name, '\t(version 20240108)', '\t(generator "pcbnew")', '\t(generator_version "8.0")',
            '\t(layer "F.Cu")', '\t(descr "%s")' % descr, '\t(tags "%s")' % tags, '\t(attr through_hole)',
            '\t(property "Reference" "REF**" (at 0 -1) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
            '\t(property "Value" "%s" (at 0 1) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))' % name]


def line(x0, y0, x1, y1, layer, w):
    return '\t(fp_line (start %.3f %.3f) (end %.3f %.3f) (stroke (width %.2f) (type solid)) (layer "%s"))' % (x0, y0, x1, y1, w, layer)


def rect(x0, y0, x1, y1, layer, w):
    return [line(x0, y0, x1, y0, layer, w), line(x1, y0, x1, y1, layer, w), line(x1, y1, x0, y1, layer, w), line(x0, y1, x0, y0, layer, w)]


def pad(num, x, y, size, drill):
    return '\t(pad "%s" thru_hole circle (at %.3f %.3f) (size %.2f %.2f) (drill %.2f) (layers "*.Cu" "*.Mask"))' % (num, x, y, size, size, drill)


# ---------------------------------------------------------------- SCART
# 21-pin right-angle PCB SCART socket, geometry from the Kycon K-SCART-021 drawing (recommended PCB layout): pin pitch 1.905 (3.81 inside each
# row, rows staggered), rows 5.08 apart, holes d1.3, two 3.0 x 4.5 mounting pegs 49.8 apart.  Not on LCSC: buy a generic 21-pin right-angle
# female PCB SCART socket (eBay / Electrokit 41022977 / Console5) and compare its drawing with this layout before ordering boards.
L = header("SCART_Kycon_K-SCART-021", "21-pin right-angle PCB SCART socket, pad geometry from the Kycon K-SCART-021 drawing", "scart jp21 connector")
YA, YB = -7.28, -2.2                        # the two pad rows (odd pins / even pins), mating face towards +y
for n in range(1, 22):
    x = 19.05 - 1.905 * (n - 1)
    L.append(pad(n, x, YA if n % 2 else YB, 2.2, 1.3))
for sx in (-1, 1):
    L.append('	(pad "" np_thru_hole rect (at %.3f 0.0) (size 3.0 4.5) (drill oval 3.0 4.5) (layers "*.Cu" "*.Mask"))' % (sx * 24.9))
L += rect(-29.2, -9.5, 29.2, 8.5, "F.SilkS", 0.15)
L += rect(-29.2, -9.5, 29.2, 8.5, "F.Fab", 0.1)
L += rect(-29.9, -10.2, 29.9, 9.2, "F.CrtYd", 0.05)
L.append('	(fp_text user "1" (at 19.05 -11.0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))')
L.append(")")
open(os.path.join(OUT, "SCART_Kycon_K-SCART-021.kicad_mod"), "w", encoding="utf-8").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- 3.5 mm jack
# XKB PJ-307N5 (LCSC C692542): pad geometry from the EasyEDA footprint; same 5-pad pattern as the CUI SJ1-3525N (S alone, T / R outside, TN / RN
# switch contacts inside).  Pad names follow the KiCad AudioJack3 symbol (T, R, S); TN / RN are the unused switch contacts.
# Mouth towards -x.  T / R order is taken by geometry analogy with the SJ1-3525N and NOT verified against an XKB drawing (datasheet not readable).
L = header("Jack_3.5mm_PJ-307N5_Horizontal", "3.5 mm stereo jack XKB PJ-307N5 (LCSC C692542), pad geometry from EasyEDA", "audio jack 3.5mm pj-307")
L.append('	(pad "S" thru_hole circle (at -2.5 0) (size 2 2) (drill 1.3) (layers "*.Cu" "*.Mask"))')
L.append('	(pad "T" thru_hole circle (at 2.5 5) (size 2 2) (drill 1.3) (layers "*.Cu" "*.Mask"))')
L.append('	(pad "R" thru_hole circle (at 2.5 -5) (size 2 2) (drill 1.3) (layers "*.Cu" "*.Mask"))')
L.append('	(pad "TN" thru_hole circle (at 2.5 2.5) (size 2 2) (drill 1.3) (layers "*.Cu" "*.Mask"))')
L.append('	(pad "RN" thru_hole circle (at 2.5 -2.5) (size 2 2) (drill 1.3) (layers "*.Cu" "*.Mask"))')
for (x, y) in ((2.5, 0), (-2.5, -5), (-2.5, 5), (-5.1, 5), (-5.1, -5)):
    L.append('	(pad "" np_thru_hole circle (at %.2f %.2f) (size 1.2 1.2) (drill 1.2) (layers "*.Cu" "*.Mask"))' % (x, y))
L += rect(-6.1, -6.0, 4.9, 6.0, "F.SilkS", 0.15)
L += rect(-9.1, -3.0, -6.1, 3.0, "F.SilkS", 0.15)
L += rect(-6.1, -6.0, 4.9, 6.0, "F.Fab", 0.1)
L += rect(-9.4, -6.3, 5.2, 6.3, "F.CrtYd", 0.05)
L.append(")")
open(os.path.join(OUT, "Jack_3.5mm_PJ-307N5_Horizontal.kicad_mod"), "w", encoding="utf-8").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- tactile switch
# XKB TS-1187A-B-A-B (LCSC C318884), 5.1 x 5.1 mm SMD.  The two terminals are the diagonal pads 1 and 2; the other two pads are internally
# connected to them (left / right pair) and kept unnamed on purpose (no risk of shorting the terminals).
L = header("SW_TS-1187A-B-A-B", "Tactile switch XKB TS-1187A-B-A-B, 5.1 x 5.1 mm SMD (LCSC C318884), pad geometry from EasyEDA", "tactile switch smd")
L[L.index('	(attr through_hole)')] = '	(attr smd)'
for num, x, y in (("1", -3.0, -1.85), ("", 3.0, -1.85), ("", -3.0, 1.85), ("2", 3.0, 1.85)):
    L.append('	(pad "%s" smd rect (at %.2f %.2f) (size 1.0 0.75) (layers "F.Cu" "F.Paste" "F.Mask"))' % (num, x, y))
L += rect(-2.55, -2.55, 2.55, 2.55, "F.Fab", 0.1)
L += rect(-2.7, -2.7, 2.7, 2.7, "F.SilkS", 0.15)
L += rect(-3.9, -2.9, 3.9, 2.9, "F.CrtYd", 0.05)
L.append(")")
open(os.path.join(OUT, "SW_TS-1187A-B-A-B.kicad_mod"), "w", encoding="utf-8").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- RCA
L = header("RCA_XDJK-0271-1650", "RCA jack, right angle, LCSC C7527522 (pad geometry from EasyEDA)", "rca phono jack")
L.append(pad(1, 0.0, 1.95, 2.5, 1.6))
L.append(pad(2, -4.0, -1.95, 2.5, 1.6))
L.append(pad(2, 4.0, -1.15, 2.5, 1.6))
L += rect(-8.0, -3.95, 8.0, 21.78, "F.SilkS", 0.15)
L += rect(-8.0, -3.95, 8.0, 21.78, "F.Fab", 0.1)
L += rect(-8.25, -4.2, 8.25, 22.03, "F.CrtYd", 0.05)
L.append(")")
open(os.path.join(OUT, "RCA_XDJK-0271-1650.kicad_mod"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("wrote", os.listdir(OUT))
