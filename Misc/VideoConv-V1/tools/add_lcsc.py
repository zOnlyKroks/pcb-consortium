"""Add the hidden property "LCSC Part #" to every part of the VideoConv-V1 schematic (root sheet + sheets/*.kicad_sch) and an LCSC column to
bom.csv.  In-place text patch (nothing is regenerated, the user's edits stay).  Run with KiCad's python:  python -I tools/add_lcsc.py

Numbers were looked up on LCSC (or the JLCPCB mirror, same C-numbers).  Parts without an LCSC equivalent are listed at the end and get no number:
  J6 SCART socket (Tyco 1483465-1), J7 3.5 mm jack (CUI SJ1-3524N), SW1 (C&K RS282G05A3), JP1 (solder jumper, no part)
Substitutes (not the exact MPN of the design, check before ordering): L1/L2 Sunlord SWPA6028 instead of Bourns SRN6028, FB1-6 BLM21AG601SN1D
(600 ohm, 0.6 A), R 576 ohm Yageo instead of UNI-ROYAL (out of stock), TFP410PAP (tray) instead of PAPR, TVP7002PZP (tray) instead of PZPR."""
import csv, glob, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, H)
from sexp import parse, find, find_all, unq

BY_VALUE = {   # (value, footprint name) -> LCSC number
    ("100nF", "C_0603_1608Metric"): "C1591", ("10nF", "C_0603_1608Metric"): "C1589", ("1nF", "C_0603_1608Metric"): "C1588",
    ("1uF", "C_0603_1608Metric"): "C29936", ("2.2uF", "C_0603_1608Metric"): "C23630", ("27pF", "C_0603_1608Metric"): "C1656",
    ("4.7nF", "C_0603_1608Metric"): "C1621", ("820pF", "C_0603_1608Metric"): "C307512",
    ("10uF", "C_0805_2012Metric"): "C15850", ("1uF", "C_0805_2012Metric"): "C116352", ("4.7uF", "C_0805_2012Metric"): "C1746",
    ("22uF", "C_1206_3216Metric"): "C12891",
    ("0", "R_0603_1608Metric"): "C21189", ("1.5k", "R_0603_1608Metric"): "C22843", ("100", "R_0603_1608Metric"): "C22775",
    ("100k", "R_0603_1608Metric"): "C25803", ("10k", "R_0603_1608Metric"): "C25804", ("13.7k", "R_0603_1608Metric"): "C22793",
    ("13k", "R_0603_1608Metric"): "C22797", ("1k", "R_0603_1608Metric"): "C21190", ("2.2k", "R_0603_1608Metric"): "C4190",
    ("24.9", "R_0603_1608Metric"): "C22916", ("27.4k", "R_0603_1608Metric"): "C22964", ("287", "R_0603_1608Metric"): "C22929",
    ("31.6k", "R_0603_1608Metric"): "C25967", ("33", "R_0603_1608Metric"): "C23140", ("33k", "R_0603_1608Metric"): "C4216",
    ("4.7k", "R_0603_1608Metric"): "C23162", ("49.9", "R_0603_1608Metric"): "C23185", ("5.1k", "R_0603_1608Metric"): "C23186",
    ("510", "R_0603_1608Metric"): "C23193", ("576", "R_0603_1608Metric"): "C245982", ("75", "R_0603_1608Metric"): "C4275",
    ("22", "R_Array_Convex_4x0603"): "C12008",
}
BY_REF = {
    "Y1": "C6531315", "X1": "C295526", "D1": "C193402", "D2": "C364279", "D3": "C364279", "F1": "C49318384",
    "J1": "C165948", "J2": "C7527522", "J3": "C7527522", "J4": "C7527522", "J5": "C7527522", "J8": "C2894930", "J9": "C916313", "J10": "C5172168",
    "LED1": "C12624", "LED3": "C12624", "LED2": "C2286", "L1": "C528022", "L2": "C168025",
    "U1": "C1880390", "U2": "C1880390", "U3": "C176944", "U4": "C460310", "U5": "C111212", "U6": "C111212", "U7": "C111212",
    "U8": "C7948", "U9": "C3824085", "U10": "C3824301", "U11": "C1521989", "U12": "C82344", "U13": "C1543847", "U14": "C201665",
}
for i in range(1, 7):
    BY_REF["FB%d" % i] = "C85837"
BY_REF["J7"] = "C692542"       # XKB PJ-307N5 3.5 mm stereo jack
BY_REF["SW1"] = "C318884"       # XKB TS-1187A-B-A-B tactile switch
NONE = {"J6", "JP1"}            # SCART socket is not on LCSC (generic 21-pin right-angle PCB socket from eBay etc.), JP1 is a solder jumper

files = [os.path.join(PRJ, "VideoConv-V1.kicad_sch")] + sorted(glob.glob(os.path.join(PRJ, "sheets", "*.kicad_sch")))


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


numbers, missing = {}, []
for f in files:
    t = open(f, encoding="utf-8").read()
    out, pos, n = [], 0, 0
    for m in re.finditer(r'\n\t\(symbol\n\t\t\(lib_id "[^"]+"\)\n', t):
        a = m.start() + 1
        if a < pos:
            continue
        b = closing(t, a + 1) + 1
        s = t[a:b]
        ref = re.search(r'\(property "Reference" "([^"]*)"', s).group(1)
        if ref.startswith("#"):
            continue
        val = re.search(r'\(property "Value" "([^"]*)"', s).group(1)
        fp = re.search(r'\(property "Footprint" "([^"]*)"', s).group(1).split(":")[-1]
        num = BY_REF.get(ref) or BY_VALUE.get((val, fp))
        if ref in NONE:
            num = None
        if not num:
            missing.append((ref, val, fp))
            continue
        numbers[ref] = num
        if '(property "LCSC Part #"' in s:
            s2 = re.sub(r'\(property "LCSC Part #" "[^"]*"', '(property "LCSC Part #" "%s"' % num, s, 1)
        else:
            at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", s)
            new = ('\t\t(property "LCSC Part #" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)\n'
                   '\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n') % (num, at.group(1), at.group(2))
            k = s.index("\n\t\t(pin ") + 1
            s2 = s[:k] + new + s[k:]
        out.append((a, b, s2))
        n += 1
    for a, b, s2 in reversed(out):
        t = t[:a] + s2 + t[b:]
    open(f, "w", encoding="utf-8").write(t)
    print(os.path.basename(f), n, "parts")
print("without LCSC number:", missing)

# bom.csv: add the LCSC column
p = os.path.join(PRJ, "bom.csv")
rows = list(csv.reader(open(p, encoding="utf-8")))
if "LCSC" not in rows[0]:
    rows[0].insert(3, "LCSC")
    for r in rows[1:]:
        r.insert(3, numbers.get(r[0], ""))
    with open(p, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    print("bom.csv: LCSC column added")
