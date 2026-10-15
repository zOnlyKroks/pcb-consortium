"""Build the project symbol library lib/NetworkSwitchV1.kicad_sym.

Custom symbols (pin numbers checked against the LCSC datasheets and the easyeda2kicad footprints):
* RTL8370N-VB   3 units: 1 = MDI (8 ports), 2 = power (same-name supply pins stacked), 3 = clock/reset/SMI/LED+strap
* GST5009       GbE magnetics, chip side left (TDn), line side right (MXn), centre taps on the bottom edge
* RJ45_LED      XUNPU RJ45-202-007-02, contacts ordered 1,2,3,6,4,5,7,8 so wires from GST5009 run straight
* TPS23753A, CH32V208GBU6, EP1322S-10 (PoE flyback transformer)
* CJ431 (TL431DBZ graphic, CJ431 SOT-23 pinout R=1 K=2 A=3), DC-005 (Barrel_Jack_Switch, tip=4 sleeve=2 sw=3)
* SW_Tact_4P (TS-1187A, pads 1-2 and 3-4 internally connected)
* power symbols CHASSIS, RTN (PoE primary return), +3V3A, +1V1A, +1V1P
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib", "NetworkSwitchV1.kicad_sym")
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
FP = "NetworkSwitchV1:"


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


def rect(x1, y1, x2, y2, fill="background"):
    return ["rectangle", ["start", fmt(x1), fmt(y1)], ["end", fmt(x2), fmt(y2)],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", fill]]]


def poly(pts, width=0.254, fill="none"):
    return ["polyline", ["pts"] + [["xy", fmt(x), fmt(y)] for x, y in pts],
            ["stroke", ["width", fmt(width)], ["type", "default"]], ["fill", ["type", fill]]]


def circle(x, y, r, fill="outline"):
    return ["circle", ["center", fmt(x), fmt(y)], ["radius", fmt(r)],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", fill]]]


def arc(sx, sy, mx, my, ex, ey):
    return ["arc", ["start", fmt(sx), fmt(sy)], ["mid", fmt(mx), fmt(my)], ["end", fmt(ex), fmt(ey)],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "none"]]]


def text(s, x, y, ang=0, size=1.27):
    return ["text", q(s), ["at", fmt(x), fmt(y), str(ang * 10 if ang else 0)], font(size)]


def symbol(name, ref, value, fp, ds, desc, units, ref_at, val_at, pin_names_offset=0.508, hide_pin_numbers=False,
           kw="", power=False, hide_pin_names=False):
    """units: list of (graphics, pins); graphics of a single-unit symbol go to unit 1."""
    s = ["symbol", q(name)]
    if power:
        s.append(["power", "global"])
    if hide_pin_numbers:
        s.append(["pin_numbers", ["hide", "yes"]])
    s.append(["pin_names", ["offset", fmt(pin_names_offset)]] + ([["hide", "yes"]] if power or hide_pin_names else []))
    s += [["exclude_from_sim", "no"], ["in_bom", "no" if power else "yes"], ["on_board", "no" if power else "yes"],
          ["in_pos_files", "no" if power else "yes"], ["duplicate_pin_numbers_are_jumpers", "no"]]
    s.append(prop("Reference", ref, *ref_at, hide=power))
    s.append(prop("Value", value, *val_at))
    s.append(prop("Footprint", fp, 0, 0, hide=True))
    s.append(prop("Datasheet", ds, 0, 0, hide=True))
    s.append(prop("Description", desc, 0, 0, hide=True))
    if kw:
        s.append(prop("ki_keywords", kw, 0, 0, hide=True))
    for i, (gfx, pins) in enumerate(units, 1):
        s.append(["symbol", q("%s_%d_1" % (name, i))] + gfx + pins)
    s.append(["embedded_fonts", "no"])
    return s


# ------------------------------------------------------------------ stock helpers
_stock = {}


def stock(lib, name):
    if lib not in _stock:
        tree = parse(open(os.path.join(STOCK, lib + ".kicad_sym"), encoding="utf-8").read())[0]
        _stock[lib] = {unq(s[1]): s for s in find_all(tree, "symbol")}
    return copy.deepcopy(_stock[lib][name])


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


def renumber(sym, mapping):
    for sub in find_all(sym, "symbol"):
        for p in find_all(sub, "pin"):
            n = find(p, "number")
            if unq(n[1]) in mapping:
                n[1] = q(mapping[unq(n[1])])


# ------------------------------------------------------------------ RTL8370N-VB
def rtl8370n():
    name = "RTL8370N-VB"
    # unit 1: MDI.  4 ports per side, 8 pins per port, 2-slot gap between ports.  Pins at x = +-15.24.
    mdi = {p: {} for p in range(8)}
    num = {}
    base = {0: 103, 1: 113, 2: 124, 3: 6, 4: 25, 5: 35, 6: 45, 7: 55}
    # datasheet pin numbers per port (A+ A- B+ B- C+ C- D+ D-)
    num[0] = [103, 104, 105, 106, 108, 109, 110, 111]
    num[1] = [113, 114, 115, 116, 118, 119, 120, 121]
    num[2] = [124, 125, 126, 127, 1, 2, 3, 4]
    num[3] = [6, 7, 8, 9, 11, 12, 13, 14]
    num[4] = [25, 26, 27, 28, 30, 31, 32, 33]
    num[5] = [35, 36, 37, 38, 40, 41, 42, 43]
    num[6] = [45, 46, 47, 48, 50, 51, 52, 53]
    num[7] = [55, 56, 57, 58, 60, 61, 62, 63]
    sfx = ["MDIAP", "MDIAN", "MDIBP", "MDIBN", "MDICP", "MDICN", "MDIDP", "MDIDN"]
    pins1 = []
    for p in range(8):
        side = -1 if p < 4 else 1
        g = p % 4
        for i in range(8):
            y = 46.99 - 2.54 * (g * 10 + i)
            pins1.append(pin(str(num[p][i]), "P%d%s" % (p, sfx[i]), "bidirectional", side * 15.24, y, 0 if side < 0 else 180))
    gfx1 = [rect(-12.7, 49.53, 12.7, -49.53), text("MDI", 0, 0, 0, 2.54)]

    # unit 2: power.  Supply pins on top (stacked duplicates hidden), grounds on the bottom.
    sup = [("DVDDL", [20, 21, 22, 23, 76, 78, 92, 95]), ("AVDDL", [10, 18, 29, 39, 49, 59, 107, 117, 128]),
           ("PLLVDDL0", [122]), ("PLLVDDL1", [44]), ("AVDDH", [5, 15, 19, 24, 34, 54, 64, 96, 102, 112]),
           ("DVDDIO", [77])]
    pins2 = []
    for k, (nm, nums) in enumerate(sup):
        x = -20.32 + 7.62 * k
        for j, n in enumerate(nums):
            # stacked duplicates are passive: a hidden power_in pin would create an implicit global net
            pins2.append(pin(str(n), nm, "passive" if j else "power_in", x, 10.16, 270, hide=j > 0))
    pins2.append(pin("16", "AGND", "power_in", -2.54, -15.24, 90))
    pins2.append(pin("129", "EPAD", "power_in", 2.54, -15.24, 90))
    gfx2 = [rect(-22.86, 7.62, 20.32, -12.7)]

    # unit 3: clock / reset / SMI on the left, LED+strap pins on the right (5.08 mm pitch for strap resistors)
    left = [("100", "SCK/MDC", "bidirectional", 55.88), ("101", "SDA/MDIO", "bidirectional", 40.64)]
    bottom = [("98", "XTALI", "input", -12.7), ("97", "XTALO", "output", -5.08), ("123", "ATESTCK0", "passive", 2.54),
              ("65", "RESERVED", "passive", 5.08), ("66", "RESERVED", "passive", 7.62), ("99", "nRESET", "input", 10.16),
              ("17", "MDIREF", "passive", 15.24)]
    right = [("94", "P0LED0/SMI_SEL0"), ("93", "P0LED1"), ("91", "P0LED2/EN_PHY"),
             ("89", "P1LED0/MID29"), ("90", "P1LED1/EN_EEE"), ("88", "P1LED2/SMI_SEL1"),
             ("86", "P2LED0/DISAUTOLD"), ("87", "P2LED1/GPIO4"), ("85", "P2LED2/DIS_8051"),
             ("84", "P3LED0/EN_FLASH"), ("82", "P3LED1/GPIO5"), ("83", "P3LED2/EN_PWRLT"),
             ("80", "P4LED0/EEPROM_MOD"), ("81", "P4LED1/GPIO6"), ("79", "P4LED2/GPIO3"),
             ("74", "P5LED0/RSVD"), ("75", "P5LED1"), ("73", "P5LED2/GPIO0"),
             ("71", "P6LED0/GPIO1"), ("72", "P6LED1/GPIO7"), ("70", "P6LED2/SPIF_CS"),
             ("68", "P7LED0/SPIF_D0"), ("69", "P7LED1/SPIF_D1"), ("67", "P7LED2/SPIF_CLK")]
    pins3 = []
    for n, nm, t, y in left:
        pins3.append(pin(n, nm, t, -20.32, y, 0))
    for n, nm, t, x in bottom:
        pins3.append(pin(n, nm, t, x, -78.74, 90))
    for i, (n, nm) in enumerate(right):
        pins3.append(pin(n, nm, "bidirectional", 20.32, 58.42 - 5.08 * i, 180))
    gfx3 = [rect(-17.78, 60.96, 17.78, -76.2)]

    s = symbol(name, "U", "RTL8370N-VB-CG", FP + "LQFP-128_L20.0-W14.0-P0.50-BL-EP7.0",
               "https://www.lcsc.com/datasheet/C2803243.pdf",
               "Realtek 8-port 10/100/1000 switch, 8 integrated GbE PHYs, LQFP-128-EP 14x20",
               [(gfx1, pins1), (gfx2, pins2), (gfx3, pins3)], (0, 52.07), (0, -52.07), kw="ethernet switch gigabit")
    return s


# ------------------------------------------------------------------ GST5009 GbE magnetics
def gst5009():
    left = [("2", "TD1+"), ("3", "TD1-"), ("5", "TD2+"), ("6", "TD2-"), ("8", "TD3+"), ("9", "TD3-"), ("11", "TD4+"), ("12", "TD4-")]
    right = [("23", "MX1+"), ("22", "MX1-"), ("20", "MX2+"), ("19", "MX2-"), ("17", "MX3+"), ("16", "MX3-"), ("14", "MX4+"), ("13", "MX4-")]
    bottom = [("1", "TCT1", -20.32), ("4", "TCT2", -15.24), ("7", "TCT3", -10.16), ("10", "TCT4", -5.08),
              ("24", "MCT1", 5.08), ("21", "MCT2", 10.16), ("18", "MCT3", 15.24), ("15", "MCT4", 20.32)]
    pins = []
    for i, (n, nm) in enumerate(left):
        pins.append(pin(n, nm, "passive", -25.4, 8.89 - 2.54 * i, 0))
    for i, (n, nm) in enumerate(right):
        pins.append(pin(n, nm, "passive", 25.4, 8.89 - 2.54 * i, 180))
    for n, nm, x in bottom:
        pins.append(pin(n, nm, "passive", x, -19.05, 90))
    gfx = [rect(-22.86, 11.43, 22.86, -16.51), poly([(-0.508, 10.16), (-0.508, -15.24)]), poly([(0.508, 10.16), (0.508, -15.24)])]
    return symbol("GST5009", "TR", "GST5009", FP + "XFMR-SMD_24P-L15.1-W7.1-P1.00-LS9.7-BL",
                  "https://www.lcsc.com/datasheet/C55213474.pdf",
                  "CND-tek GST5009 1000BASE-T single-port magnetics, 1CT:1CT, 802.3af PoE rated (350 mA CT)",
                  [(gfx, pins)], (0, 15.24), (0, -21.59), kw="ethernet transformer magnetics")


# ------------------------------------------------------------------ RJ45 with 2 LEDs
def rj45():
    order = ["1", "2", "3", "6", "4", "5", "7", "8"]
    pins = [pin(n, "~", "passive", 10.16, 8.89 - 2.54 * i, 180) for i, n in enumerate(order)]
    pins += [pin("9", "Y+", "passive", -10.16, 6.35, 0), pin("10", "Y-", "passive", -10.16, 3.81, 0),
             pin("11", "G+", "passive", -10.16, -3.81, 0), pin("12", "G-", "passive", -10.16, -6.35, 0),
             pin("13", "SHELL", "passive", -2.54, -13.97, 90)]
    gfx = [rect(-7.62, 11.43, 7.62, -11.43),
           # plug opening
           poly([(1.27, 6.35), (5.08, 6.35), (5.08, -6.35), (1.27, -6.35), (1.27, -2.54), (0, -2.54), (0, 2.54), (1.27, 2.54), (1.27, 6.35)])]
    return symbol("RJ45_LED", "J", "RJ45-202-007-02", FP + "RJ45-TH_RJ45-202-007-02",
                  "https://www.lcsc.com/datasheet/C7421418.pdf",
                  "RJ45 jack, shielded, no magnetics, LEDs: left yellow (9+/10-), right green (11+/12-)",
                  [(gfx, pins)], (0, 13.97), (0, -16.51), hide_pin_numbers=False, kw="rj45 ethernet")


# ------------------------------------------------------------------ TPS23753A
def tps23753a():
    # PoE side on the left, power stage on the right, RTN-referenced control pins on the bottom edge
    left = [("9", "VDD", "power_in", 7.62), ("8", "VDD1", "passive", 5.08), ("10", "DEN", "passive", 0),
            ("11", "CLS", "passive", -2.54), ("12", "APD", "input", -5.08), ("7", "VSS", "power_in", -10.16)]
    right = [("5", "GATE", "output", 7.62), ("3", "CS", "input", 2.54), ("4", "VC", "passive", -5.08)]
    bottom = [("14", "FRS", "passive", -7.62), ("13", "BLNK", "passive", -2.54), ("6", "RTN", "power_in", 0),
              ("2", "VB", "power_out", 5.08), ("1", "CTL", "input", 12.7)]
    pins = [pin(n, nm, t, -17.78, y, 0) for n, nm, t, y in left]
    pins += [pin(n, nm, t, 17.78, y, 180) for n, nm, t, y in right]
    pins += [pin(n, nm, t, x, -15.24, 90) for n, nm, t, x in bottom]
    gfx = [rect(-15.24, 10.16, 15.24, -12.7)]
    return symbol("TPS23753A", "U", "TPS23753APWR", FP + "TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL",
                  "https://www.ti.com/lit/ds/symlink/tps23753a.pdf",
                  "IEEE 802.3at Type 1 PoE PD interface + current-mode DC-DC controller (isolated flyback), TSSOP-14",
                  [(gfx, pins)], (0, 12.7), (-17.78, -17.78), kw="poe pd")


# ------------------------------------------------------------------ CH32V208GBU6
def ch32v208():
    # pins grouped by function (2.54 mm rows, None = empty row)
    left = [("13", "VDD_VIO_1", "power_in"), ("27", "VDD_VIO_3", "power_in"), ("4", "VDDA", "power_in"), None,
            ("21", "VINTA", "passive"), None, ("2", "OSC_IN", "input"), ("3", "OSC_OUT", "output"), None, None,
            ("28", "PC14/OSC32IN", "bidirectional"), ("1", "PC15/OSC32OUT", "bidirectional"), None, None,
            ("26", "PB8/BOOT0", "input"), None, None, ("22", "ANT", "passive")]
    right = [("5", "PA0", "bidirectional"), ("6", "PA1", "bidirectional"), ("24", "PB6/I2C1_SCL", "bidirectional"),
             ("25", "PB7/I2C1_SDA", "bidirectional"), ("12", "PA7", "bidirectional"), None, None,
             ("10", "PA5", "bidirectional"), ("11", "PA6", "bidirectional"), None, None, None,
             ("7", "PA2/U2TX", "bidirectional"), ("8", "PA3/U2RX", "bidirectional"),
             ("20", "PA13/SWDIO", "bidirectional"), ("23", "PA14/SWCLK", "bidirectional"), None, None,
             ("9", "PA4", "bidirectional"), ("18", "PA11/USBDM", "bidirectional"), ("19", "PA12/USBDP", "bidirectional"),
             None,
             ("16", "PC8/ETH_TXP", "bidirectional"), ("17", "PC9/ETH_TXN", "bidirectional"),
             ("14", "PC6/ETH_RXP", "bidirectional"), ("15", "PC7/ETH_RXN", "bidirectional")]
    pins = []
    for i, e in enumerate(left):
        if e:
            pins.append(pin(e[0], e[1], e[2], -17.78, 25.4 - 2.54 * i, 0))
    for i, e in enumerate(right):
        if e:
            pins.append(pin(e[0], e[1], e[2], 17.78, 25.4 - 2.54 * i, 180))
    pins.append(pin("29", "VSS/EP", "power_in", 0, -43.18, 90))
    gfx = [rect(-15.24, 27.94, 15.24, -40.64)]
    return symbol("CH32V208GBU6", "U", "CH32V208GBU6", FP + "QFN-28_L4.0-W4.0-P0.40-BL-EP2.8",
                  "https://www.lcsc.com/datasheet/C7434833.pdf",
                  "WCH CH32V208 RISC-V MCU, 144 MHz, 128K flash, 10M Ethernet MAC+PHY, BLE 5.3, QFN-28 4x4",
                  [(gfx, pins)], (0, 30.48), (0, -45.72), kw="risc-v mcu ethernet")


# ------------------------------------------------------------------ EP1322S-10 PoE flyback transformer
def ep1322():
    pins = [pin("3", "3", "passive", -10.16, 7.62, 0), pin("4", "4", "passive", -10.16, 2.54, 0),
            pin("2", "2", "passive", -10.16, -2.54, 0), pin("1", "1", "passive", -10.16, -7.62, 0),
            pin("7", "7", "passive", 10.16, 5.08, 180), pin("8", "8", "passive", 10.16, 5.08, 180, hide=True),
            pin("9", "9", "passive", 10.16, -5.08, 180), pin("10", "10", "passive", 10.16, -5.08, 180, hide=True),
            pin("5", "NC", "no_connect", -2.54, -10.16, 90, hide=True), pin("6", "NC", "no_connect", 2.54, -10.16, 90, hide=True)]
    gfx = [rect(-7.62, 10.16, 7.62, -10.16, fill="none")]

    def coil(x, y0, y1, right):
        n = 4
        h = (y0 - y1) / n
        g = []
        for k in range(n):
            a, b = y0 - k * h, y0 - (k + 1) * h
            g.append(arc(x, a, x + (1.27 if right else -1.27), (a + b) / 2, x, b))
        return g
    # primary 3(dot)-4, aux 2(dot)-1, secondary 7/8(dot)-9/10
    gfx += [poly([(-7.62, 7.62), (-3.81, 7.62), (-3.81, 6.35)]), poly([(-3.81, 3.81), (-3.81, 2.54), (-7.62, 2.54)])]
    gfx += coil(-3.81, 6.35, 3.81, True)
    gfx += [poly([(-7.62, -2.54), (-3.81, -2.54), (-3.81, -3.81)]), poly([(-3.81, -6.35), (-3.81, -7.62), (-7.62, -7.62)])]
    gfx += coil(-3.81, -3.81, -6.35, True)
    gfx += [poly([(7.62, 5.08), (3.81, 5.08), (3.81, 3.81)]), poly([(3.81, -3.81), (3.81, -5.08), (7.62, -5.08)])]
    gfx += coil(3.81, 3.81, -3.81, False)
    gfx += [poly([(-0.508, 8.89), (-0.508, -8.89)]), poly([(0.508, 8.89), (0.508, -8.89)])]
    gfx += [circle(-5.334, 6.858, 0.381, "outline"), circle(-5.334, -3.302, 0.381, "outline"), circle(5.334, 4.318, 0.381, "outline")]
    return symbol("EP1322S-10", "T", "EP1322S-10", FP + "XFMR-SMD_EP1322S-10",
                  "https://www.lcsc.com/datasheet/C37328796.pdf",
                  "CND-tek/LinkPower EP13 PoE flyback transformer 36-57 V in, 12 V 1.05 A out, Lp 160 uH, 1:0.33:0.385 (3-4 : 7,8-9,10 : 2-1)",
                  [(gfx, pins)], (0, 12.7), (0, -12.7), kw="flyback transformer poe", hide_pin_names=True)


# ------------------------------------------------------------------ stock-derived
def cj431():
    s = stock("Reference_Voltage", "TL431DBZ")
    rename(s, "TL431DBZ", "CJ431")
    renumber(s, {"1": "K_", "2": "R_", "3": "A_"})
    renumber(s, {"K_": "2", "R_": "1", "A_": "3"})
    set_prop(s, "Value", "CJ431")
    set_prop(s, "Footprint", FP + "SOT-23-3_L2.9-W1.6-P1.90-LS2.8-BR")
    set_prop(s, "Datasheet", "https://www.lcsc.com/datasheet/C3113.pdf")
    set_prop(s, "Description", "Shunt reference 2.495 V, SOT-23, CJ431 pinout (1 = REF, 2 = K, 3 = A)")
    return s


def dc005():
    s = stock("Connector", "Barrel_Jack_Switch")
    rename(s, "Barrel_Jack_Switch", "DC-005")
    renumber(s, {"1": "4"})
    set_prop(s, "Value", "DC-005")
    set_prop(s, "Footprint", FP + "DC-IN-TH_DC-005-5.5-2.0")
    set_prop(s, "Datasheet", "https://www.lcsc.com/datasheet/C16214.pdf")
    set_prop(s, "Description", "DC barrel jack 5.5/2.0 mm, pin 4 = centre (+), 2 = sleeve, 3 = switch")
    return s


def tact():
    sw = stock("Switch", "SW_Push")
    rename(sw, "SW_Push", "SW_Tact_4P")
    set_prop(sw, "Description", "Tactile switch, 4 pads: 1-2 and 3-4 internally connected (TS-1187A)")
    set_prop(sw, "Footprint", FP + "SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5")
    for sub in find_all(sw, "symbol"):
        for p in find_all(sub, "pin"):
            num = find(p, "number")
            if unq(num[1]) == "2":
                num[1] = q("3")
        for p in list(find_all(sub, "pin")):
            twin = copy.deepcopy(p)
            n = unq(find(twin, "number")[1])
            find(twin, "number")[1] = q({"1": "2", "3": "4"}[n])
            twin.insert(5, ["hide", "yes"])
            sub.append(twin)
    return sw


def eeprom():
    pins = [pin("1", "A0", "input", -10.16, 2.54, 0), pin("2", "A1", "input", -10.16, 0, 0),
            pin("3", "A2", "input", -10.16, -2.54, 0), pin("6", "SCL", "input", 10.16, 2.54, 180),
            pin("5", "SDA", "bidirectional", 10.16, 0, 180), pin("7", "WP", "input", 10.16, -2.54, 180),
            pin("8", "VCC", "power_in", 0, 10.16, 270), pin("4", "GND", "power_in", 0, -10.16, 90)]
    return symbol("AT24C256C", "U", "AT24C256C-SSHL-T", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                  "https://www.lcsc.com/datasheet/C6482.pdf",
                  "256 Kbit I2C EEPROM, 1 MHz, WP pin, SOIC-8 (address 1010 A2 A1 A0)",
                  [([rect(-7.62, 7.62, 7.62, -7.62)], pins)], (-7.62, 12.7), (-7.62, -12.7), kw="eeprom i2c")


def power_copy(src, new, desc):
    s = stock("power", src)
    rename(s, src, new)
    set_prop(s, "Value", new)
    set_prop(s, "Description", desc)
    return s


def main():
    out = ["kicad_symbol_lib", ["version", "20251024"], ["generator", q("kicad_symbol_editor")], ["generator_version", q("10.0")]]
    out += [rtl8370n(), gst5009(), rj45(), tps23753a(), ch32v208(), ep1322(), cj431(), dc005(), tact(), eeprom()]
    out += [power_copy("Earth", "CHASSIS", "Chassis / shield net (RJ45 shells, Bob Smith terminations, mounting holes)"),
            power_copy("GNDPWR", "RTN", "PoE primary-side return (TPS23753A RTN), isolated from GND"),
            power_copy("+3V3", "+3V3A", "RTL8370N AVDDH analog 3.3 V (ferrite-isolated from +3V3)"),
            power_copy("+1V1", "+1V1A", "RTL8370N AVDDL analog 1.1 V (ferrite-isolated from +1V1)"),
            power_copy("+1V1", "+1V1P", "RTL8370N PLLVDDL 1.1 V (ferrite-isolated from +1V1)")]
    open(LIB, "w", encoding="utf-8").write(dump(out) + "\n")
    print("library:", [unq(s[1]) for s in find_all(out, "symbol")])


if __name__ == "__main__":
    main()
