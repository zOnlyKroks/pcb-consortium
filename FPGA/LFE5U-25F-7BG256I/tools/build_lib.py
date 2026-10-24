"""Build the project symbol library libs/fpga_board.kicad_sym (copied from 2.5GPcieV1/tools/build_lib.py).

* SY8089      Silergy SY8089A1AAC buck, SOT-23-5: 1 EN, 2 GND, 3 LX, 4 IN, 5 FB (Vfb 0.6 V)
* CH347F      WCH USB-HS to JTAG + 2x UART + SPI + I2C, QFN-28 (EP = 29)
The FPGA itself uses the LCSC symbol lcsc_imported:LFE5U-25F-7BG256I as placed by the user.
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "libs", "fpga_board.kicad_sym")
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
FP = "lcsc_footprints:"


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


def pin(num, name, typ, x, y, ang, length=2.54):
    return ["pin", typ, "line", ["at", fmt(x), fmt(y), str(ang)], ["length", fmt(length)],
            ["name", q(name), font()], ["number", q(num), font()]]


def rect(x1, y1, x2, y2, fill="background"):
    return ["rectangle", ["start", fmt(x1), fmt(y1)], ["end", fmt(x2), fmt(y2)],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", fill]]]


def poly(pts, width=0.254):
    return ["polyline", ["pts"] + [["xy", fmt(x), fmt(y)] for x, y in pts],
            ["stroke", ["width", fmt(width)], ["type", "default"]], ["fill", ["type", "none"]]]


def symbol(name, ref, value, fp, ds, desc, gfx, pins, ref_at, val_at, kw="", lcsc=""):
    s = ["symbol", q(name), ["pin_names", ["offset", "0.508"]], ["exclude_from_sim", "no"], ["in_bom", "yes"],
         ["on_board", "yes"], ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"]]
    s.append(prop("Reference", ref, *ref_at))
    s.append(prop("Value", value, *val_at))
    s.append(prop("Footprint", fp, 0, 0, hide=True))
    s.append(prop("Datasheet", ds, 0, 0, hide=True))
    s.append(prop("Description", desc, 0, 0, hide=True))
    if lcsc:
        s.append(prop("LCSC Part #", lcsc, 0, 0, hide=True))
    if kw:
        s.append(prop("ki_keywords", kw, 0, 0, hide=True))
    s.append(["symbol", q(name + "_1_1")] + gfx + pins)
    s.append(["embedded_fonts", "no"])
    return s


def stock(lib, name):
    tree = parse(open(os.path.join(STOCK, lib + ".kicad_sym"), encoding="utf-8").read())[0]
    return copy.deepcopy({unq(s[1]): s for s in find_all(tree, "symbol")}[name])


def power_copy(src, new, desc):
    s = stock("power", src)
    s[1] = q(new)
    for sub in find_all(s, "symbol"):
        sub[1] = q(unq(sub[1]).replace(src + "_", new + "_", 1))
    for p in find_all(s, "property"):
        if unq(p[1]) == "Value":
            p[2] = q(new)
        if unq(p[1]) == "Description":
            p[2] = q(desc)
    return s


# ------------------------------------------------------------------ SY8089
def sy8089():
    P = [pin("4", "IN", "power_in", -10.16, 2.54, 0), pin("1", "EN", "input", -10.16, -2.54, 0),
         pin("3", "LX", "power_out", 10.16, 2.54, 180), pin("5", "FB", "input", 10.16, -2.54, 180),
         pin("2", "GND", "power_in", 0, -7.62, 90)]
    return symbol("SY8089", "U", "SY8089A1AAC", "Package_TO_SOT_SMD:SOT-23-5", "https://www.lcsc.com/datasheet/C479074.pdf",
                  "Silergy SY8089A1 2 A 1.5 MHz synchronous buck, 2.5-5.5 V in, Vfb 0.6 V, SOT-23-5",
                  [rect(-7.62, 5.08, 7.62, -5.08)], P, (0, 6.35), (0, -10.16), kw="buck regulator", lcsc="C479074")


# ------------------------------------------------------------------ CH347F
def ch347f():
    """WCH CH347F, QFN-28 4x4 0.4 mm (datasheet V1.4, table 4-1..4-7).  All interfaces run at once, no mode straps.
    EP (LCSC pin 0) is numbered 29 to match KiCad's QFN-28-1EP footprints."""
    left = [("1", "XI", "input", 20.32), ("2", "XO", "output", 15.24), ("3", "~{RST}", "input", 7.62),
            ("27", "UD-", "bidirectional", 2.54), ("28", "UD+", "bidirectional", 0),
            ("11", "SCL/CTS1", "bidirectional", -7.62), ("12", "SDA/RTS1", "bidirectional", -10.16),
            ("7", "SCS1/DTR1", "output", -12.7), ("8", "SRST", "output", -15.24), ("9", "TRST/GPIO3", "bidirectional", -17.78),
            ("10", "DTR0/GPIO2", "bidirectional", -20.32)]
    right = [("23", "TCK", "output", 20.32), ("26", "TMS", "output", 17.78), ("25", "TDI", "output", 15.24),
             ("24", "TDO", "input", 12.7), ("19", "TXD0", "output", 7.62), ("22", "RXD0", "input", 5.08),
             ("18", "~{RTS0}/GPIO1", "bidirectional", 2.54), ("17", "~{CTS0}/GPIO0", "bidirectional", 0),
             ("13", "SCS0", "output", -5.08), ("14", "SCK", "output", -7.62), ("16", "MOSI", "output", -10.16),
             ("15", "MISO", "input", -12.7), ("4", "TXD1", "output", -17.78), ("5", "RXD1", "input", -20.32)]
    P = [pin(n, nm, t, -15.24, y, 0) for n, nm, t, y in left]
    P += [pin(n, nm, t, 15.24, y, 180) for n, nm, t, y in right]
    P += [pin("21", "VCC", "power_in", -2.54, 27.94, 270), pin("6", "VIO", "power_in", 2.54, 27.94, 270),
          pin("20", "GND", "power_in", -2.54, -27.94, 90), pin("29", "EP", "power_in", 2.54, -27.94, 90)]
    return symbol("CH347F", "U", "CH347F", "Package_DFN_QFN:QFN-28-1EP_4x4mm_P0.4mm_EP2.4x2.4mm",
                  "https://www.lcsc.com/datasheet/C18221627.pdf",
                  "WCH CH347F USB 2.0 high-speed to JTAG/SWD + 2x UART + SPI + I2C, 3.3 V, 8 MHz crystal, QFN-28",
                  [rect(-12.7, 25.4, 12.7, -25.4)], P, (0, 30.48), (0, -30.48), kw="usb jtag uart spi wch",
                  lcsc="C18221627")


def main():
    out = ["kicad_symbol_lib", ["version", "20251024"], ["generator", q("kicad_symbol_editor")], ["generator_version", q("10.0")]]
    out += [sy8089(), ch347f()]
    open(LIB, "w", encoding="utf-8").write(dump(out) + "\n")
    print("library:", [unq(s[1]) for s in find_all(out, "symbol")])


if __name__ == "__main__":
    main()
