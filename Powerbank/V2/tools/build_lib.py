"""Build the project libraries lib/PowerbankV2.kicad_sym and lib/PowerbankV2.pretty.

Symbols (pin numbers from the TI datasheets in ../datasheets):
* BQ77915      TSSOP-24, pins laid out like the package (1-12 left, 24-13 right), bq77915.pdf table 7-1
* TPS54531     SO-8 PowerPAD (DDA), pad 9 = exposed GND pad (TIDA-050047 figure 2-6 pinout)
* NMOS_DFN8    Q_NMOS graphic, pins 1-3 S, 4 G, 5-9 D (AON6512 PDFN5x6, pad 9 = drain tab)
* SW_Push_14   SW_Push graphic on pads 1 and 4 (diagonal pads of a 4-pin tact switch are never joined inside)
* BQ25798      stock symbol with BAT (22, 23) typed passive: two chargers share the pack, BAT is bidirectional

Footprints are taken from easyeda2kicad output in lib/lcsc (LCSC parts) with fixes:
* 18650 holder BH-18650-B1BA002: pad 1 = + (the end with the silk "+" and the locating peg), pad 2 = -,
  peg hole non-plated, clean courtyard
* 3D model references removed (models were not downloaded)
* Texas_REF0038A (TPS25751D) = KiCad stock footprint with the exposed-pad thermal vias opened from 0.2 to 0.3 mm
  drill (0.7 mm pad) to stay inside the JLC standard-tier hole size used as the project minimum, and a
  footprint-local 0.1 mm clearance for TI's 0.125 mm pad gaps (JLC multilayer handles 0.1 mm)
"""
import copy, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
LIBDIR = os.path.join(HERE, "..", "lib")
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
STOCK_FP = r"C:\Program Files\KiCad\10.0\share\kicad\footprints"
FP = "PowerbankV2:"


def fmt(v):
    s = ("%.4f" % round(v + 0.0, 4)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def font(size=1.27):
    return ["effects", ["font", ["size", fmt(size), fmt(size)]]]


def prop(key, val, x=0, y=0, hide=False):
    p = ["property", q(key), q(val), ["at", fmt(x), fmt(y), "0"], ["show_name", "no"], ["do_not_autoplace", "no"]]
    if hide:
        p.append(["hide", "yes"])
    p.append(font())
    return p


def pin(num, name, typ, x, y, ang, length=2.54, hide=False):
    p = ["pin", typ, "line", ["at", fmt(x), fmt(y), str(ang)], ["length", fmt(length)]]
    if hide:
        p.append(["hide", "yes"])
    p += [["name", q(name), font()], ["number", q(num), font()]]
    return p


def rect(x1, y1, x2, y2):
    return ["rectangle", ["start", fmt(x1), fmt(y1)], ["end", fmt(x2), fmt(y2)],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]


def symbol(name, ref, value, fp, ds, desc, gfx, pins, ref_at, val_at):
    s = ["symbol", q(name), ["pin_names", ["offset", "1.016"]], ["exclude_from_sim", "no"], ["in_bom", "yes"],
         ["on_board", "yes"], ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"]]
    s += [prop("Reference", ref, *ref_at), prop("Value", value, *val_at), prop("Footprint", fp, hide=True),
          prop("Datasheet", ds, hide=True), prop("Description", desc, hide=True)]
    s.append(["symbol", q(name + "_0_1")] + gfx)
    s.append(["symbol", q(name + "_1_1")] + pins)
    s.append(["embedded_fonts", "no"])
    return s


def stock(lib, name):
    tree = parse(open(os.path.join(STOCK, lib + ".kicad_sym"), encoding="utf-8").read())[0]
    return copy.deepcopy({unq(s[1]): s for s in find_all(tree, "symbol")}[name])


def rename(sym, old, new):
    sym[1] = q(new)
    for sub in find_all(sym, "symbol"):
        sub[1] = q(unq(sub[1]).replace(old + "_", new + "_", 1))


def set_prop(sym, key, val):
    for p in find_all(sym, "property"):
        if unq(p[1]) == key:
            p[2] = q(val)
            return
    raise KeyError(key)


# ---------------------------------------------------------------------------------------------- symbols
def bq77915():
    left = ["VDD", "AVDD", "VC5", "VC4", "VC3", "VC2", "VC1", "VC0", "VSS", "SRP", "SRN", "DSG"]
    right = ["CTRD", "CTRC", "PRES", "CBO", "CCFG", "VTB", "TS", "OCDP", "CBI", "LPWR", "LD", "CHG"]
    types = {"VDD": "power_in", "AVDD": "power_out", "VSS": "power_in", "DSG": "output", "CHG": "output",
             "VTB": "output", "CBO": "output", "LPWR": "output"}
    pins = []
    for i, n in enumerate(left):
        pins.append(pin(str(i + 1), n, types.get(n, "input"), -12.7, 13.97 - 2.54 * i, 0))
    for i, n in enumerate(right):
        pins.append(pin(str(24 - i), n, types.get(n, "input"), 12.7, 13.97 - 2.54 * i, 180))
    return symbol("BQ77915", "U", "BQ77915", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
                  "https://www.ti.com/lit/ds/symlink/bq77915.pdf",
                  "3-5 series Li-ion protector with cell balancing, low-side CHG/DSG FET drivers",
                  [rect(-10.16, 16.51, 10.16, -16.51)], pins, (0, 17.78), (0, -17.78))


def tps54531():
    pins = [pin("2", "VIN", "power_in", -12.7, 5.08, 0), pin("3", "EN", "input", -12.7, 0, 0),
            pin("4", "SS", "passive", -12.7, -2.54, 0),
            pin("1", "BOOT", "passive", 12.7, 5.08, 180), pin("8", "PH", "power_out", 12.7, 2.54, 180),
            pin("5", "VSENSE", "input", 12.7, -2.54, 180), pin("6", "COMP", "passive", 12.7, -5.08, 180),
            pin("7", "GND", "power_in", 0, -10.16, 90), pin("9", "PAD", "passive", 0, -10.16, 90, hide=True)]
    return symbol("TPS54531", "U", "TPS54531", "Package_SO:TI_SO-PowerPAD-8_ThermalVias",
                  "https://www.ti.com/lit/ds/symlink/tps54531.pdf", "28 V 5 A non-synchronous buck, SO-8 PowerPAD",
                  [rect(-10.16, 7.62, 10.16, -7.62)], pins, (0, 8.89), (0, -12.7))


def nmos_dfn8():
    s = stock("Device", "Q_NMOS")
    rename(s, "Q_NMOS", "NMOS_DFN8")
    set_prop(s, "Footprint", FP + "PDFN-8_5x6_AON6512")
    set_prop(s, "Description", "N-MOSFET, PDFN5x6: pads 1-3 source, 4 gate, 5-8 + tab drain")
    for sub in find_all(s, "symbol"):
        for i in range(len(sub) - 1, -1, -1):
            if isinstance(sub[i], list) and sub[i][0] == "pin":
                del sub[i]
    unit = [x for x in find_all(s, "symbol") if unq(x[1]).endswith("_1_1")][0]
    unit.append(pin("4", "G", "input", -5.08, 0, 0))
    for n, h in (("5", False), ("6", True), ("7", True), ("8", True), ("9", True)):
        unit.append(pin(n, "D", "passive", 2.54, 5.08, 270, hide=h))
    for n, h in (("1", False), ("2", True), ("3", True)):
        unit.append(pin(n, "S", "passive", 2.54, -5.08, 90, hide=h))
    s[s.index(find(s, "pin_names"))] = ["pin_names", ["hide", "yes"]]
    return s


def sw_push_14():
    s = stock("Switch", "SW_Push")
    rename(s, "SW_Push", "SW_Push_14")
    set_prop(s, "Footprint", FP + "SW_TS-1187A_5.1x5.1")
    set_prop(s, "Description", "Tact switch on diagonal pads 1 and 4")
    for sub in find_all(s, "symbol"):
        for p in find_all(sub, "pin"):
            num = find(p, "number")
            if unq(num[1]) == "2":
                num[1] = q("4")
    return s


def bq25798():
    s = stock("Battery_Management", "BQ25798")
    for sub in find_all(s, "symbol"):
        for p in find_all(sub, "pin"):
            if unq(find(p, "number")[1]) in ("22", "23"):
                p[1] = "passive"
    return s


def write_symbols():
    lib = ["kicad_symbol_lib", ["version", "20251024"], ["generator", q("build_lib.py")],
           ["generator_version", q("10.0")], bq77915(), tps54531(), nmos_dfn8(), sw_push_14(), bq25798()]
    open(os.path.join(LIBDIR, "PowerbankV2.kicad_sym"), "w", encoding="utf-8").write(dump(lib) + "\n")


# ---------------------------------------------------------------------------------------------- footprints
SRC = os.path.join(LIBDIR, "lcsc", "lcsc.pretty")
FOOTPRINTS = {  # new name: (easyeda file, LCSC part)
    "PDFN-8_5x6_AON6512": ("PDFN-8_L5.6-W5.2-P1.27-LS6.1-BL", "C485679"),
    "Fuse_10.3x3.2_1032": ("FUSE-SMD_L10.3-W3.2", "C5220755"),
    "L_7.0x6.6_MWSA0603S": ("IND-SMD_L7.0-W6.6", "C408445"),
    "L_11x10_TMPA1004S": ("IND-SMD_L11.0-W10.0", "C357112"),
    "SW_TS-1187A_5.1x5.1": ("SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5", "C318884"),
}


def clean(text, name):
    text = re.sub(r"\(module easyeda2kicad:[^\s]+", "(module " + name, text, count=1)
    text = re.sub(r"\n\t\(model .*?\n\t\)", "", text, flags=re.S)
    text = re.sub(r"\(fp_text value [^\s]+", "(fp_text value " + name, text, count=1)
    return text


def holder():
    src = open(os.path.join(SRC, "BATTERY-SMD_18650-1S-L77.1-W20.7-1.kicad_mod"), encoding="utf-8").read()
    src = clean(src, "BatteryHolder_BH-18650-B1BA002")
    # "+" silk and the peg are at -y: that end is the positive contact -> pad 1
    src = src.replace("(pad 1 smd rect (at 0.00 41.31 0.00)", "(pad @2 smd rect (at 0.00 41.31 0.00)")
    src = src.replace("(pad 2 smd rect (at 0.00 -41.31 0.00)", "(pad 1 smd rect (at 0.00 -41.31 0.00)")
    src = src.replace("(pad @2 ", "(pad 2 ")
    src = src.replace('(pad "" thru_hole circle (at 8.00 -35.84) (size 2.40 2.40) (drill 2.40) (layers *.Cu *.Mask))',
                      '(pad "" np_thru_hole circle (at 8.00 -35.84) (size 2.40 2.40) (drill 2.40) (layers *.Cu *.Mask) '
                      '(clearance 0.2))')
    src = re.sub(r"\t\(fp_line [^\n]*F\.CrtYd[^\n]*\n", "", src)
    cy = "".join("\t(fp_line (start %s) (end %s) (layer F.CrtYd) (width 0.05))\n" % (a, b) for a, b in (
        ("-10.6 -44.1", "10.6 -44.1"), ("10.6 -44.1", "10.6 44.1"), ("10.6 44.1", "-10.6 44.1"),
        ("-10.6 44.1", "-10.6 -44.1")))
    src = src.rstrip().rstrip(")") + cy + ")\n"
    assert "np_thru_hole" in src and "(pad 1 smd rect (at 0.00 -41.31" in src
    return src


def tps25751_fp():
    src = os.path.join(STOCK_FP, "Package_DFN_QFN.pretty", "Texas_REF0038A_WQFN-38-2EP_6x4mm_P0.4.kicad_mod")
    t = open(src, encoding="utf-8").read()
    t = t.replace('(footprint "Texas_REF0038A_WQFN-38-2EP_6x4mm_P0.4"',
                  '(footprint "Texas_REF0038A_WQFN-38-2EP_6x4mm_P0.4_Via0.3"', 1)
    via = re.compile(r"\(size 0\.5 0\.5\)(\s*)\(drill 0\.2\)")
    t, n = via.subn(r"(size 0.7 0.7)\1(drill 0.3)", t)
    assert n > 0, "thermal vias not found"
    # TI's land pattern puts the merged PPHV/VBUS_IN pads 0.125 mm apart: footprint-local 0.1 mm clearance
    t = t.replace("\t(attr smd)", "\t(clearance 0.1)\n\t(attr smd)", 1)
    assert "(clearance 0.1)" in t
    return t


def write_footprints():
    out = os.path.join(LIBDIR, "PowerbankV2.pretty")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "Texas_REF0038A_WQFN-38-2EP_6x4mm_P0.4_Via0.3.kicad_mod"), "w",
         encoding="utf-8").write(tps25751_fp())
    for name, (src, lcsc) in FOOTPRINTS.items():
        text = open(os.path.join(SRC, src + ".kicad_mod"), encoding="utf-8").read()
        open(os.path.join(out, name + ".kicad_mod"), "w", encoding="utf-8").write(clean(text, name))
    open(os.path.join(out, "BatteryHolder_BH-18650-B1BA002.kicad_mod"), "w", encoding="utf-8").write(holder())


if __name__ == "__main__":
    write_symbols()
    write_footprints()
    print("ok")
