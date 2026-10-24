"""Build the project symbol library libs/2.5GPcieV1.kicad_sym.

* RTL8125BG   all 49 pins, grouped by function (pin numbers from the RTL8125B datasheet Rev 1.6, figure 2):
              left = PCIe + control, right = MDI / LED / EEPROM-SPI, top = supplies (each pin separate so every
              pin gets its own capacitor), bottom = crystal, RSET, NC, GND
* H2414QR     E-NETTR 2.5G/5G magnetics: chip side 1-12 (TCTn, TDn+/-), line side 13-24 (MCTn, MXn+/-)
* RJ45_LED    XUNPU RJ45-202-007-02 (no magnetics), contacts ordered 1,2,3,6,4,5,7,8; LEDs Y 9+/10-, G 11+/12-
* SY8089      Silergy SY8089A1AAC buck, SOT-23-5: 1 EN, 2 GND, 3 LX, 4 IN, 5 FB (Vfb 0.6 V)
* +0V95       power symbol for the RTL8125B core rail
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "libs", "2.5GPcieV1.kicad_sym")
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


# ------------------------------------------------------------------ RTL8125BG
def rtl8125():
    P = []
    top = [("46", "DVDD33", -22.86), ("29", "DVDD33", -20.32), ("43", "EVDD33", -17.78), ("15", "AVDD33", -15.24),
           ("19", "AVDD33", -12.7), ("33", "AVDD33", -10.16), ("34", "AVDD33_XTAL", -2.54),
           ("8", "DVDD09", 5.08), ("28", "DVDD09", 7.62), ("47", "DVDD09", 10.16), ("37", "EVDD09", 12.7),
           ("11", "AVDD09", 15.24), ("16", "AVDD09", 17.78), ("22", "AVDD09", 20.32)]
    for n, nm, x in top:
        P.append(pin(n, nm, "power_in", x, 33.02, 270))
    left = [("44", "REFCLK_P", "input", 15.24), ("45", "REFCLK_N", "input", 12.7),
            ("41", "HSIP", "input", 7.62), ("42", "HSIN", "input", 5.08),
            ("38", "HSOP", "output", 0), ("39", "HSON", "output", -2.54),
            ("36", "~{PERSTB}", "input", -7.62), ("48", "~{CLKREQB}", "open_collector", -12.7),
            ("2", "~{LANWAKEB}", "open_collector", -17.78), ("3", "GPI", "bidirectional", -22.86),
            ("6", "POW_EXT_SWR", "output", -27.94), ("1", "~{ISOLATEB}", "input", -33.02)]
    for n, nm, t, y in left:
        P.append(pin(n, nm, t, -27.94, y, 0))
    right = [("13", "MDIP0", 15.24), ("14", "MDIN0", 12.7), ("17", "MDIP1", 10.16), ("18", "MDIN1", 7.62),
             ("20", "MDIP2", 5.08), ("21", "MDIN2", 2.54), ("23", "MDIP3", 0), ("24", "MDIN3", -2.54)]
    for n, nm, y in right:
        P.append(pin(n, nm, "bidirectional", 27.94, y, 180))
    right2 = [("30", "LED0/EEDI/SDA", -7.62), ("27", "LED1/EESK", -12.7), ("25", "LED2/EEDO", -17.78),
              ("35", "LED3", -22.86), ("31", "EECS/SCL", -27.94), ("32", "EEPROM_SEL", -30.48),
              ("26", "~{SPICSB}", -33.02)]
    for n, nm, y in right2:
        P.append(pin(n, nm, "bidirectional", 27.94, y, 180))
    bottom = [("10", "CKXTAL1", "input", -11.43), ("9", "CKXTAL2", "output", -3.81), ("12", "RSET", "passive", 0),
              ("4", "NC", "no_connect", 2.54), ("5", "NC", "no_connect", 5.08), ("7", "NC", "no_connect", 7.62),
              ("40", "GND", "power_in", 10.16), ("49", "EP", "power_in", 12.7)]
    for n, nm, t, x in bottom:
        P.append(pin(n, nm, t, x, -38.1, 90))
    gfx = [rect(-25.4, 30.48, 25.4, -35.56)]
    return symbol("RTL8125BG", "U", "RTL8125BG-CG", FP + "C3013605_TQFN-48_L6_0-W6_0-P0_40-BL-EP4_5",
                  "https://atta.szlcsc.com/upload/public/pdf/source/20220830/2E1DB58605ADC2BD893CDFBE192900E6.pdf",
                  "Realtek RTL8125BG 10/100/1000/2500BASE-T PCIe 2.1 x1 Ethernet controller, QFN-48 6x6, "
                  "3.3 V + 0.95 V (external core regulator)", gfx, P, (0, 36.83), (0, -41.91),
                  kw="ethernet 2.5G pcie realtek", lcsc="C3013605")


# ------------------------------------------------------------------ H2414QR (same pinout as GST5009)
def h2414qr():
    left = [("2", "TD1+"), ("3", "TD1-"), ("5", "TD2+"), ("6", "TD2-"), ("8", "TD3+"), ("9", "TD3-"), ("11", "TD4+"), ("12", "TD4-")]
    right = [("23", "MX1+"), ("22", "MX1-"), ("20", "MX2+"), ("19", "MX2-"), ("17", "MX3+"), ("16", "MX3-"), ("14", "MX4+"), ("13", "MX4-")]
    bottom = [("1", "TCT1", -20.32), ("4", "TCT2", -15.24), ("7", "TCT3", -10.16), ("10", "TCT4", -5.08),
              ("24", "MCT1", 5.08), ("21", "MCT2", 10.16), ("18", "MCT3", 15.24), ("15", "MCT4", 20.32)]
    P = [pin(n, nm, "passive", -25.4, 8.89 - 2.54 * i, 0) for i, (n, nm) in enumerate(left)]
    P += [pin(n, nm, "passive", 25.4, 8.89 - 2.54 * i, 180) for i, (n, nm) in enumerate(right)]
    P += [pin(n, nm, "passive", x, -19.05, 90) for n, nm, x in bottom]
    gfx = [rect(-22.86, 11.43, 22.86, -16.51), poly([(-0.508, 10.16), (-0.508, -15.24)]), poly([(0.508, 10.16), (0.508, -15.24)])]
    return symbol("H2414QR", "TR", "H2414QR", FP + "C4155001_XFMR-SMD_H2414QR", "https://www.lcsc.com/datasheet/C4155001.pdf",
                  "E-NETTR H2414QR 2.5G/5GBASE-T single-port magnetics, 1CT:1CT, 1500 Vrms", gfx, P, (0, 15.24),
                  (0, -21.59), kw="ethernet transformer magnetics 2.5G", lcsc="C4155001")


# ------------------------------------------------------------------ RJ45 with 2 LEDs
def rj45():
    order = ["1", "2", "3", "6", "4", "5", "7", "8"]
    P = [pin(n, "~", "passive", -10.16, 8.89 - 2.54 * i, 0) for i, n in enumerate(order)]
    P += [pin("9", "Y+", "passive", 10.16, 6.35, 180), pin("10", "Y-", "passive", 10.16, 3.81, 180),
          pin("11", "G+", "passive", 10.16, -3.81, 180), pin("12", "G-", "passive", 10.16, -6.35, 180),
          pin("13", "SHELL", "passive", 2.54, -13.97, 90)]
    gfx = [rect(-7.62, 11.43, 7.62, -11.43),
           poly([(-1.27, 6.35), (-5.08, 6.35), (-5.08, -6.35), (-1.27, -6.35), (-1.27, -2.54), (0, -2.54), (0, 2.54),
                 (-1.27, 2.54), (-1.27, 6.35)])]
    return symbol("RJ45_LED", "J", "RJ45-202-007-02", FP + "RJ45-TH_RJ45-202-007-02", "https://www.lcsc.com/datasheet/C7421418.pdf",
                  "RJ45 jack, shielded, no magnetics, LEDs: yellow (9+/10-), green (11+/12-)", gfx, P, (0, 13.97),
                  (0, -16.51), kw="rj45 ethernet", lcsc="C7421418")


# ------------------------------------------------------------------ SY8089
def sy8089():
    P = [pin("4", "IN", "power_in", -10.16, 2.54, 0), pin("1", "EN", "input", -10.16, -2.54, 0),
         pin("3", "LX", "power_out", 10.16, 2.54, 180), pin("5", "FB", "input", 10.16, -2.54, 180),
         pin("2", "GND", "power_in", 0, -7.62, 90)]
    return symbol("SY8089", "U", "SY8089A1AAC", "Package_TO_SOT_SMD:SOT-23-5", "https://www.lcsc.com/datasheet/C479074.pdf",
                  "Silergy SY8089A1 2 A 1.5 MHz synchronous buck, 2.5-5.5 V in, Vfb 0.6 V, SOT-23-5",
                  [rect(-7.62, 5.08, 7.62, -5.08)], P, (0, 6.35), (0, -10.16), kw="buck regulator", lcsc="C479074")


def pcie_x1():
    """Stock Connector:Bus_PCI_Express_x1 with every pin passive (it is a card-edge connector: the host drives
    REFCLK / PETx / PERST# and supplies the power, so pin types from the card's side only produce ERC noise)."""
    s = stock("Connector", "Bus_PCI_Express_x1")
    s[1] = q("PCIe_x1_Edge")
    for sub in find_all(s, "symbol"):
        sub[1] = q(unq(sub[1]).replace("Bus_PCI_Express_x1_", "PCIe_x1_Edge_", 1))
        for pn in find_all(sub, "pin"):
            pn[1] = "passive"
    for pr in find_all(s, "property"):
        if unq(pr[1]) == "Description":
            pr[2] = q("PCI Express x1 card edge (stock symbol, all pins passive)")
        if unq(pr[1]) == "Footprint":
            pr[2] = q("Connector_PCBEdge:BUS_PCIexpress_x1")
    return s


def main():
    out = ["kicad_symbol_lib", ["version", "20251024"], ["generator", q("kicad_symbol_editor")], ["generator_version", q("10.0")]]
    out += [rtl8125(), h2414qr(), rj45(), sy8089(), pcie_x1(),
            power_copy("+1V0", "+0V95", "RTL8125B core supply 0.95 V (0.92-0.98 V)")]
    open(LIB, "w", encoding="utf-8").write(dump(out) + "\n")
    print("library:", [unq(s[1]) for s in find_all(out, "symbol")])


if __name__ == "__main__":
    main()
