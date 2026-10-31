"""Write gateware/pins.pcf (FPGA pin -> net), bom.csv and report footprints that do not exist in KiCad's libraries.

    python -I tools/make_outputs.py        (after gen_sch.py; reads the generated sheet and tools/intent.json)
"""
import csv, json, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, H)
from sexp import parse, find, find_all, unq

FPDIR = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"
import glob
sheets = [parse(open(f, encoding="utf-8").read())[0] for f in sorted(glob.glob(os.path.join(PRJ, "sheets", "*.kicad_sch")))]


def prop(s, k):
    p = next((p for p in find_all(s, "property") if unq(p[1]) == k), None)
    return unq(p[2]) if p else ""


rows, seen = [], set()
for s in [x for sh in sheets for x in find_all(sh, "symbol")]:
    if find(s, "lib_id") is None:
        continue
    ref = prop(s, "Reference")
    if ref.startswith("#") or ref in seen:
        continue
    seen.add(ref)
    if find(s, "in_bom") and find(s, "in_bom")[1] == "no":
        continue
    rows.append([ref, prop(s, "Value"), prop(s, "Footprint"), prop(s, "LCSC Part #"), prop(s, "MPN"), prop(s, "Note"), unq(find(s, "lib_id")[1])])


def key(r):
    m = re.match(r"([A-Za-z]+)(\d+)", r[0])
    return (m.group(1), int(m.group(2)))


rows.sort(key=key)
with open(os.path.join(PRJ, "bom.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Reference", "Value", "Footprint", "LCSC", "MPN", "Note", "Symbol"])
    w.writerows(rows)
print("bom.csv:", len(rows), "parts")

# footprint existence
missing = {}
for r in rows:
    fp = r[2]
    if not fp:
        missing.setdefault("(none assigned)", []).append(r[0])
        continue
    lib, name = fp.split(":")
    if not os.path.exists(os.path.join(FPDIR, lib + ".pretty", name + ".kicad_mod")):
        missing.setdefault(fp, []).append(r[0])
for fp, refs in missing.items():
    print("footprint not in KiCad stock: %-70s %s" % (fp, " ".join(refs[:8])))

# FPGA constraints: pin number -> net (nets in intent.json for the FPGA reference)
intent = {tuple(k.split("|")): v for k, v in json.load(open(os.path.join(H, "intent.json"))).items() if k != "_groups"}
fpga_ref = next(r[0] for r in rows if "ICE40" in r[6].upper())
pins = sorted(((int(p), net) for (ref, p), net in intent.items() if ref == fpga_ref and net not in ("NC",) and p.isdigit()))
io = [(p, n) for p, n in pins if not n.startswith(("+", "GND", "CDONE", "CRESET", "SPI_")) and n != "FPGA_GND0"]
os.makedirs(os.path.join(PRJ, "gateware"), exist_ok=True)
with open(os.path.join(PRJ, "gateware", "pins.pcf"), "w") as f:
    f.write("# iCE40HX4K-TQ144 pin constraints, generated from VideoConv-V1.kicad_sch (do not edit by hand)\n")
    f.write("# nets: TV* = TVP7002 (pixel clock TVCLK), CY*/CSCLK = TVP5150 BT.656, D* = TFP410, V* = VGA R-2R DAC\n")
    for p, n in io:
        f.write("set_io %-12s %d\n" % (n, p))
print("gateware/pins.pcf:", len(io), "pins")

# TVP7002 H-PLL settings per video format: datasheet Table 4 (SLES206C), plus the 27 MHz oversampled SD modes used by this design
MODES = [  # name, frame Hz, line kHz, pixel MHz (out clock), PLLDIV total, reg01h, reg02h, reg03h, note
    ("480i  (native 13.5 MHz)", 29.97, 15.734, 13.5, 858, 0x35, 0xA0, 0x18, "datasheet Table 4"),
    ("576i  (native 13.5 MHz)", 25, 15.625, 13.5, 864, 0x36, 0x00, 0x18, "datasheet Table 4"),
    ("480p  27 MHz", 59.94, 31.469, 27, 858, 0x35, 0xA0, 0x18, "datasheet Table 4"),
    ("576p  27 MHz", 50, 31.25, 27, 864, 0x36, 0x00, 0x18, "datasheet Table 4"),
    ("720p60", 60, 45, 74.25, 1650, 0x67, 0x20, 0xA0, "datasheet Table 4"),
    ("720p50", 50, 37.5, 74.25, 1980, 0x7B, 0xC0, 0x98, "datasheet Table 4"),
    ("1080i60", 30, 33.75, 74.25, 2200, 0x89, 0x80, 0x98, "datasheet Table 4 (30 frames = 60 fields)"),
    ("1080i50", 25, 28.125, 74.25, 2640, 0xA5, 0x00, 0x90, "datasheet Table 4 (25 frames = 50 fields)"),
    ("1080p60", 60, 67.5, 148.5, 2200, 0x89, 0x80, 0xE0, "datasheet Table 4"),
    ("1080p50", 50, 56.25, 148.5, 2640, 0xA5, 0x00, 0xD8, "datasheet Table 4"),
    ("480i  oversampled 27 MHz", 29.97, 15.734, 27, 1716, 0x6B, 0x40, 0x18, "derived: 2x PLLDIV of the 480i row, VCO/CP of the 480p row"),
    ("576i  oversampled 27 MHz", 25, 15.625, 27, 1728, 0x6C, 0x00, 0x18, "derived: 2x PLLDIV of the 576i row, VCO/CP of the 576p row"),
]
with open(os.path.join(PRJ, "gateware", "tvp7002_modes.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["format", "frame_Hz", "line_kHz", "clock_MHz", "PLLDIV_total", "reg01h", "reg02h(PLLDIV[3:0] in bits 7:4)", "reg03h(VCO[7:6] CP[5:3])", "source"])
    for m in MODES:
        assert (m[5] << 4) | (m[6] >> 4) == m[4], m          # reg 01h / 02h must encode PLLDIV
        w.writerow([m[0], m[1], m[2], m[3], m[4], "0x%02X" % m[5], "0x%02X" % m[6], "0x%02X" % m[7], m[8]])
print("gateware/tvp7002_modes.csv:", len(MODES), "formats")
