"""Generate the ECP5 emulation board schematic (LFE5U-25F-7BG256I, caBGA-256).

Root sheet = the user's own placement of the 9 units of lcsc_imported:LFE5U-25F-7BG256I (copied verbatim from
tools/user_placement.kicad_sch), with a global label on every used ball, power on unit 9 and the sheet blocks.
Sub-sheets hold the circuits: power, configuration, USB-JTAG, SDRAM, video/audio, user I/O.
Explicit placement, real wires, power symbols; global labels only for nets that leave a sheet.
Ball assignment lives in design.py.  Run check_netlist.py afterwards.
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import Project, Sheet, write_sheet, write_root, report, title_block, RAW_LIBSYM, fmt
from sexp import parse, find, find_all, q, unq
import design as D

PRJ_NAME = "LFE5U-25F-7BG256I"
ROOT_FILE = PRJ_NAME + ".kicad_sch"
ROOT_UUID = "3477bddd-6755-491d-872e-e7d9cabddcfa"
FPGA_LIB = "lcsc_imported:LFE5U-25F-7BG256I"          # symbol + footprint as placed by the user
FPGA_PART, FPGA_LCSC = "LFE5U-25F-6BG256C", "C1521614"   # same die / package / pinout, -6 speed grade, commercial
DATE, REV = "2026-10-18", "1"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "user_placement.kicad_sch")
SHIFT_X = 63.5          # whole FPGA group moved right by this much (arrangement unchanged)

R0603, C0603, C0805 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric"
SOT23, SOT235, SOT236 = ("Package_TO_SOT_SMD:SOT-23", "Package_TO_SOT_SMD:SOT-23-5", "Package_TO_SOT_SMD:SOT-23-6")
LED0603 = "LED_SMD:LED_0603_1608Metric"
RES = {"22R": "C23345", "33R": "C23140", "100R": "C22775", "470R": "C23179", "510R": "C23193", "1k": "C22548",
       "2k": "C22975", "2.2k": "C4190", "3.9k": "C23018", "4.7k": "C23162", "5.1k": "C23186", "10k": "C25804",
       "12k": "C22790", "12k 1%": "C22790", "10k 1%": "C25804", "22k": "C31850", "22k 1%": "C31850",
       "100k": "C25803", "100k 1%": "C25803"}
CAP = {"100nF": (C0603, "C14663"), "10nF": (C0603, "C1589"), "1uF": (C0603, "C14664"), "4.7uF": (C0603, "C19666"),
       "10uF": (C0603, "C19702"), "22uF": (C0805, "C380338"), "22pF": (C0603, "C1653"), "30pF": (C0603, "C1658")}


def R(sh, ref, val, x, y, rot=0, fields="R"):
    return sh.add(ref, "Device:R", x, y, rot, value=val, fp=R0603, lcsc=RES[val], fields=fields)


def C(sh, ref, val, x, y, rot=0, fields="R"):
    fp, lcsc = CAP[val]
    return sh.add(ref, "Device:C", x, y, rot, value=val, fp=fp, lcsc=lcsc, fields=fields)


def LED(sh, ref, color, x, y, rot=0, fields="R"):
    lcsc = {"red": "C2286", "green": "C12624", "yellow": "C2287"}[color]
    return sh.add(ref, "Device:LED", x, y, rot, value="LED " + color, fp=LED0603, lcsc=lcsc, fields=fields)


def hfields(x, y, below=False):
    """Reference left / value right on one line above (or below) a horizontal 2-pin part."""
    dy = 1.905 if below else -1.905
    return ((x - 0.635, y + dy, "right"), (x + 0.635, y + dy, "left"))


def vcap(sh, ref, val, x, ytop, fields="R"):
    """Vertical capacitor whose top pin sits at (x, ytop); GND symbol on the bottom pin."""
    C(sh, ref, val, x, ytop + 3.81, fields=fields)
    sh.power("GND", ref + ".2")


def cap_row(sh, refs_vals, x0, y, rail, pitch=10.16):
    """Decoupling row: rail wire at y from x0 to the last cap, caps hanging down, GND bus underneath."""
    xs = [x0 + pitch * (i + 1) for i in range(len(refs_vals))]
    sh.power(rail, (x0, y))
    sh.wire((x0, y), (xs[-1], y))
    for (ref, val), x in zip(refs_vals, xs):
        C(sh, ref, val, x, y + 3.81, fields=((x + 1.27, y + 2.54, "left"), (x + 1.27, y + 5.08, "left")))
    sh.wire((xs[0], y + 7.62), (xs[-1], y + 7.62))
    sh.power("GND", (xs[0], y + 7.62))
    return xs


def U(unit):
    return "U1" if unit == 1 else "U1.%d" % unit


# ============================================================================ root: FPGA as placed by the user
def root_sheet(prj):
    sh = Sheet(prj, ROOT_FILE, "ECP5 emulation board", 1)
    base = parse(open(BASE, encoding="utf-8").read())[0]
    for s in find_all(find(base, "lib_symbols"), "symbol"):
        if unq(s[1]) == FPGA_LIB:
            RAW_LIBSYM[FPGA_LIB] = s
    units = {}
    lib = RAW_LIBSYM[FPGA_LIB]
    for s in find_all(base, "symbol"):
        if unq(find(s, "lib_id")[1]) != FPGA_LIB:
            continue
        s = copy.deepcopy(s)
        at, unit = find(s, "at"), int(find(s, "unit")[1])
        # the user's arrangement, moved as a whole so units 7/8 (left of x = 0) land inside the A3 frame
        x, y = round(float(at[1]) + SHIFT_X, 3), round(float(at[2]), 3)
        at[1], at[2] = fmt(x), fmt(y)
        # reference above / value below the body instead of on top of the label column
        body = find(next(u for u in find_all(lib, "symbol") if unq(u[1]).endswith("_%d_1" % unit)), "rectangle")
        top, bot = -abs(float(find(body, "start")[2])), abs(float(find(body, "end")[2]))
        for pr in find_all(s, "property"):
            pat = find(pr, "at")
            if unq(pr[1]) == "Reference":
                pat[1], pat[2], pat[3] = fmt(x), fmt(y + top - 1.905), "0"
            elif unq(pr[1]) == "Value":
                pat[1], pat[2], pat[3] = fmt(x), fmt(y + bot + 1.905), "0"
                pr[2] = q(FPGA_PART)
                if unit != 9 and find(pr, "hide") is None:       # part number shown once, on the power unit
                    pr.insert(4, ["hide", "yes"])
            else:
                pat[1], pat[2] = fmt(float(pat[1]) + SHIFT_X), pat[2]
                if unq(pr[1]) == "LCSC":
                    pr[2] = q(FPGA_LCSC)
                elif unq(pr[1]) == "Description":
                    pr[2] = q(FPGA_PART)
            eff = find(pr, "effects")
            if eff is not None:
                j = find(eff, "justify")
                if j is not None:
                    eff.remove(j)
        units[unit] = s
        sh.add("U1", FPGA_LIB, x, y, int(at[3]), unit=unit, raw=s, fields="IC")
    assert sorted(units) == list(range(1, 10)), sorted(units)
    # every ball of the design table must exist on the unit it is listed for
    for ball, unit in D.UNIT.items():
        assert ball in sh.parts[U(unit)]["pins"], (ball, unit)
    for unit in range(1, 9):
        assert set(sh.parts[U(unit)]["pins"]) == {b for b, u in D.UNIT.items() if u == unit}, unit

    # one global label per used ball, on a short stub to the left of the pin
    for ball, unit in D.UNIT.items():
        p = sh.P("%s.%s" % (U(unit), ball))
        if ball in D.PINS:
            sh.glabel(D.PINS[ball], sh.stub(p, -2.54, 0), 180)
        else:
            sh.nc(p)

    # power unit 9: left column = 24 x GND, right column = GND, VCC, VCCAUX, VCCIO
    u9 = U(9)
    def col(balls, dx):
        pts = sorted((sh.P("%s.%s" % (u9, b)) for b in balls), key=lambda p: p[1])
        ends = [sh.stub(p, dx, 0) for p in pts]
        sh.wire(ends[0], ends[-1])
        return ends
    left = [b for b in D.POWER["GND"] if sh.pin(u9, b)[0] < sh.parts[u9]["x"]]
    right_gnd = [b for b in D.POWER["GND"] if b not in left]
    e = col(left, -2.54)
    sh.power("GND", sh.stub(e[-1], 0, 2.54))
    e = col(right_gnd, 2.54)
    sh.power("GND", sh.stub(e[-1], 0, 2.54))
    for rail, dx in (("+3V3", 7.62), ("+2V5", 7.62), ("+1V1", 12.7)):
        e = col(D.POWER[rail], 2.54)
        top = e[0]
        sh.power(rail, sh.wire(top, (top[0] + dx - 2.54, top[1])))
    sh.text("Bank I/O: VCCIO0-3, 6-8 = 3.3 V  |  VCC = 1.1 V  |  VCCAUX = 2.5 V  (decoupling on the power sheet)",
            186.69 + SHIFT_X, 172.72)
    return sh


# ============================================================================ power
def buck(sh, refs, x, y, vin, vout, rtop, rbot, note):
    """SY8089 buck at (x, y).  refs = (U, L, Cin1, Cin2, Ren, Rtop, Rbot, Cff, Cout1, Cout2)."""
    u, l, ci1, ci2, ren, rt, rb, cff, co1, co2 = refs
    sh.add(u, "fpga_board:SY8089", x, y, value="SY8089A1AAC", fp=SOT235, lcsc="C479074",
           fields=((x, y - 7.62, None), (x + 3.81, y + 8.89, "left")))
    sh.power(vin, (x - 38.1, y - 2.54))
    sh.wire((x - 38.1, y - 2.54), u + ".4")
    C(sh, ci1, "10uF", x - 33.02, y + 1.27, fields="L")
    C(sh, ci2, "100nF", x - 27.94, y + 1.27, fields="R")
    sh.power("GND", ci1 + ".2")
    sh.power("GND", ci2 + ".2")
    R(sh, ren, "100k", x - 16.51, y + 2.54, rot=90, fields=hfields(x - 16.51, y + 2.54, below=True))
    sh.wire(ren + ".1", (x - 20.32, y - 2.54))
    sh.wire(ren + ".2", u + ".1")
    sh.power("GND", u + ".2")
    sh.add(l, "Device:L", x + 16.51, y - 2.54, rot=90, value="2.2uH", fp="Inductor_SMD:L_Changjiang_FNR4020S",
           lcsc="C167825", fields=hfields(x + 16.51, y - 2.54))
    sh.wire(u + ".3", l + ".1")
    sh.wire(l + ".2", (x + 58.42, y - 2.54))
    R(sh, rt, rtop, x + 25.4, y + 1.27, fields="L")
    R(sh, rb, rbot, x + 25.4, y + 8.89, fields="L")
    sh.power("GND", rb + ".2")
    C(sh, cff, "22pF", x + 30.48, y + 1.27, fields="R")
    sh.wire(u + ".5", (x + 15.24, y + 2.54), (x + 15.24, y + 5.08), (x + 30.48, y + 5.08))
    C(sh, co1, "22uF", x + 40.64, y + 1.27, fields="R")
    C(sh, co2, "22uF", x + 50.8, y + 1.27, fields="R")
    sh.power("GND", co1 + ".2")
    sh.power("GND", co2 + ".2")
    sh.power(vout, (x + 58.42, y - 2.54))
    sh.wire((x + 58.42, y - 2.54), (x + 68.58, y - 2.54))
    sh.power("FLAG", (x + 68.58, y - 2.54))
    sh.text(note, x - 38.1, y - 15.24)


def power_sheet(prj):
    sh = prj.sheet("power.kicad_sch", "Power", 2)
    T = sh.text
    T("Power: +5 V (USB-C, see USB-JTAG sheet) -> 3.3 V and 1.1 V bucks, 2.5 V LDO", 25.4, 22.86, 2, True)
    buck(sh, ("U201", "L201", "C201", "C202", "R201", "R202", "R203", "C203", "C204", "C205"), 73.66, 66.04,
         "+5V", "+3V3", "100k 1%", "22k 1%",
         "+3.3 V / 2 A  (VCCIO, SDRAM, FT2232H, peripherals):  0.6 V x (1 + 100k / 22k) = 3.33 V")
    buck(sh, ("U202", "L202", "C206", "C207", "R204", "R205", "R206", "C208", "C209", "C210"), 73.66, 109.22,
         "+5V", "+1V1", "10k 1%", "12k 1%",
         "+1.1 V / 2 A  (ECP5 VCC core, 1.045-1.155 V):  0.6 V x (1 + 10k / 12k) = 1.100 V")
    # 2.5 V LDO for VCCAUX
    x, y = 73.66, 152.4
    T("+2.5 V  (ECP5 VCCAUX, < 100 mA) from +3.3 V", x - 38.1, y - 15.24)
    sh.add("U203", "Regulator_Linear:AP2112K-2.5", x, y, value="AP2112K-2.5TRG1", fp=SOT235, lcsc="C176945",
           fields=((x, y - 7.62, None), (x + 3.81, y + 8.89, "left")))
    sh.power("+3V3", (x - 25.4, y - 2.54))
    sh.wire((x - 25.4, y - 2.54), "U203.1")
    C(sh, "C211", "10uF", x - 17.78, y + 1.27, fields="L")
    sh.power("GND", "C211.2")
    sh.wire((x - 12.7, y - 2.54), (x - 12.7, y), "U203.3")
    sh.power("GND", "U203.2")
    sh.wire("U203.5", (x + 17.78, y - 2.54))
    C(sh, "C212", "10uF", x + 12.7, y + 1.27, fields="R")
    sh.power("GND", "C212.2")
    sh.power("+2V5", (x + 17.78, y - 2.54))
    # power LED and the GND flag
    x, y = 45.72, 190.5
    T("Power indicator", x - 10.16, y - 7.62)
    sh.power("+3V3", (x - 5.08, y))
    R(sh, "R207", "1k", x + 3.81, y, rot=90, fields=hfields(x + 3.81, y))
    sh.wire((x - 5.08, y), "R207.1")
    LED(sh, "D201", "red", x + 19.05, y, rot=180, fields=hfields(x + 19.05, y))
    sh.wire("R207.2", "D201.2")
    sh.wire("D201.1", (x + 30.48, y))
    sh.power("GND", (x + 30.48, y))
    sh.wire((x + 30.48, y), (x + 30.48, y - 5.08))
    sh.power("FLAG", (x + 30.48, y - 5.08))

    # ---------------------------------------------------------------- FPGA decoupling
    X = 190.5
    T("ECP5 decoupling - place at the BGA (one 100 nF per supply ball, bulk next to the regulators)", X, 45.72, 1.524, True)
    T("VCC +1.1 V: 6 balls", X, 55.88)
    cap_row(sh, [("C220", "22uF"), ("C221", "10uF")] + [("C%d" % (222 + i), "100nF") for i in range(6)], X, 63.5, "+1V1")
    T("VCCAUX +2.5 V: 2 balls", X, 86.36)
    cap_row(sh, [("C230", "10uF"), ("C231", "100nF"), ("C232", "100nF")], X, 93.98, "+2V5")
    T("VCCIO0/1/2/3/6/7/8 +3.3 V: 13 balls", X, 116.84)
    cap_row(sh, [("C240", "10uF"), ("C241", "10uF")] + [("C%d" % (242 + i), "100nF") for i in range(8)], X, 124.46, "+3V3")
    cap_row(sh, [("C%d" % (250 + i), "100nF") for i in range(5)], X, 147.32, "+3V3")
    return sh


# ============================================================================ configuration, flash, clock
def config_sheet(prj):
    sh = prj.sheet("config.kicad_sch", "Configuration", 3)
    T = sh.text
    T("Configuration: master SPI from 4 MB QSPI flash, PROGRAMN / INITN / DONE, 25 MHz clock", 25.4, 22.86, 2, True)

    # ---------------------------------------------------------------- SPI flash
    x, y = 101.6, 76.2
    T("Bitstream (~0.6 MB) + user flash (W25Q32JV-IQ: QE=1 from the factory, so IO2/IO3 need no pull-ups)", x - 55.88, y - 27.94)
    sh.add("U101", "Memory_Flash:W25Q32JVSS", x, y, value="W25Q32JVSSIQ", fp="Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
           lcsc="C179173", fields=((x + 3.81, y + 12.7, "left"), (x + 3.81, y + 15.24, "left")))
    for pin, net in ((1, "FLASH_CSn"), (6, "FLASH_CLK"), (5, "FLASH_IO0"), (2, "FLASH_IO1"), (3, "FLASH_IO2"),
                     (7, "FLASH_IO3")):
        sh.glabel(net, sh.stub("U101.%d" % pin, -22.86, 0), 180)
    R(sh, "R101", "10k", x - 15.24, y - 11.43, fields="L")
    sh.power("+3V3", "R101.1")
    sh.wire("U101.8", (x, y - 17.78))
    sh.power("+3V3", (x, y - 17.78))
    sh.wire((x, y - 15.24), (x + 15.24, y - 15.24))
    C(sh, "C101", "100nF", x + 15.24, y - 11.43, fields="R")
    sh.power("GND", "C101.2")
    sh.power("GND", "U101.4")

    # ---------------------------------------------------------------- CFG straps: 010 = master SPI
    x, y = 187.96, 55.88
    T("CFG[2:0] = 010 -> master SPI boot", x - 12.7, y - 7.62)
    for i, (ref, net, up) in enumerate((("R102", "CFG0", False), ("R103", "CFG1", True), ("R104", "CFG2", False))):
        rx = x + 20.32 * i
        R(sh, ref, "10k", rx, y + 3.81, fields="R")
        if up:
            sh.power("+3V3", ref + ".1")
            sh.glabel(net, sh.wire(ref + ".2", (rx - 7.62, y + 7.62)), 180)
        else:
            sh.power("GND", ref + ".2")
            sh.glabel(net, sh.wire(ref + ".1", (rx - 7.62, y)), 180)

    # ---------------------------------------------------------------- PROGRAMN / INITN / DONE
    y = 101.6
    T("PROGRAMN: button reloads the bitstream", 172.72, y - 17.78)
    xn = 190.5
    sh.glabel("PROGRAMN", sh.wire((xn, y), (xn - 10.16, y)), 180)
    R(sh, "R105", "10k", xn, y - 3.81, fields="R")
    sh.power("+3V3", "R105.1")
    sh.add("SW101", "Switch:SW_Push", xn, y + 5.08, rot=90, value="PROG", fp="Button_Switch_SMD:SW_SPST_TL3342",
           lcsc="C318884", fields="R")
    sh.power("GND", "SW101.1")
    xn = 223.52
    T("INITN", xn - 7.62, y - 17.78)
    sh.glabel("INITN", sh.wire((xn, y), (xn - 10.16, y)), 180)
    R(sh, "R106", "10k", xn, y - 3.81, fields="R")
    sh.power("+3V3", "R106.1")
    xn = 256.54
    T("DONE: LED on when configured", xn - 7.62, y - 25.4)
    sh.glabel("DONE", sh.wire((xn, y), (xn - 10.16, y)), 180)
    R(sh, "R107", "10k", xn, y - 3.81, fields="L")
    sh.power("+3V3", "R107.1")
    xq = xn + 10.16
    sh.add("Q101", "Transistor_FET:2N7002", xq, y, value="2N7002", fp=SOT23, lcsc="C8545",
           fields=((xq + 6.35, y - 1.27, "left"), (xq + 6.35, y + 1.27, "left")))
    sh.wire((xn, y), "Q101.1")
    sh.power("GND", "Q101.2")
    LED(sh, "D101", "red", xq + 2.54, y - 8.89, rot=90, fields="R")
    R(sh, "R108", "1k", xq + 2.54, y - 16.51, fields="R")
    sh.wire("Q101.3", "D101.1")
    sh.wire("D101.2", "R108.2")
    sh.power("+3V3", "R108.1")

    # ---------------------------------------------------------------- 25 MHz clock
    x, y = 101.6, 139.7
    T("25 MHz system clock -> ball P6 (PLL input LLC_GPLL0T_IN)", x - 38.1, y - 20.32)
    sh.add("X101", "Oscillator:ASE-xxxMHz", x, y, value="25MHz", fp="Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm",
           lcsc="C669088", fields=((x + 2.54, y - 8.89, "left"), (x + 2.54, y + 8.89, "left")),
           extra={"MPN": "OT322525MJBA4SL"})
    sh.wire("X101.4", (x, y - 12.7))
    sh.power("+3V3", (x, y - 12.7))
    sh.wire("X101.1", (x - 10.16, y), (x - 10.16, y - 10.16), (x, y - 10.16))
    sh.power("GND", "X101.2")
    sh.power("+3V3", (x - 17.78, y - 12.7))
    C(sh, "C102", "100nF", x - 17.78, y - 8.89, fields="L")
    sh.power("GND", "C102.2")
    R(sh, "R109", "100R", x + 13.97, y, rot=90, fields=hfields(x + 13.97, y))
    sh.wire("X101.3", "R109.1")
    sh.glabel("CLK25", sh.wire("R109.2", (x + 22.86, y)), 0, "output")

    # ---------------------------------------------------------------- JTAG pulls (CH347F / J302 drive these)
    x, y = 187.96, 152.4
    T("JTAG: TCK pulled low, TMS / TDI pulled high", x - 12.7, y - 7.62)
    for i, (ref, net, up) in enumerate((("R110", "JTAG_TCK", False), ("R111", "JTAG_TMS", True),
                                        ("R112", "JTAG_TDI", True))):
        rx = x + 20.32 * i
        R(sh, ref, "10k" if up else "2.2k", rx, y + 3.81, fields="R")
        if up:
            sh.power("+3V3", ref + ".1")
            sh.glabel(net, sh.wire(ref + ".2", (rx - 7.62, y + 7.62)), 180)
        else:
            sh.power("GND", ref + ".2")
            sh.glabel(net, sh.wire(ref + ".1", (rx - 7.62, y)), 180)
    return sh


# ============================================================================ USB-C, CH347F (JTAG + UART + SPI)
def usb_sheet(prj):
    sh = prj.sheet("usb_jtag.kicad_sch", "USB-JTAG", 4)
    T = sh.text
    T("USB-C: board power + CH347F (USB 2.0 high speed).  JTAG -> ECP5 (openFPGALoader -c ch347, OpenOCD ch347),", 25.4, 22.86, 2, True)
    T("UART0 + SPI -> bank 7 for the emulated core (console / debug bridge).  All interfaces work at the same time.",
      25.4, 30.48, 2, True)

    # ---------------------------------------------------------------- USB-C receptacle, fuse, CC, ESD
    x, y = 40.64, 101.6
    sh.add("J301", "Connector:USB_C_Receptacle_USB2.0_16P", x, y, value="TYPE-C-31-M-12",
           fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", lcsc="C165948",
           fields=((x, y - 25.4, None), (x, y + 30.48, None)))
    sh.wire("J301.A4", (x + 22.86, y - 15.24))
    sh.add("F301", "Device:Polyfuse_Small", x + 25.4, y - 15.24, rot=90, value="1.1A", fp="Fuse:Fuse_1206_3216Metric",
           lcsc="C20801", fields=hfields(x + 25.4, y - 15.24))
    sh.wire("F301.2", (x + 55.88, y - 15.24))
    C(sh, "C301", "10uF", x + 38.1, y - 11.43, fields="R")
    sh.power("GND", "C301.2")
    sh.power("+5V", (x + 48.26, y - 15.24))
    sh.power("FLAG", (x + 55.88, y - 15.24))
    T("+5 V, 1.1 A PTC", x + 20.32, y - 22.86)
    sh.wire("J301.A5", (x + 30.48, y - 10.16))
    R(sh, "R302", "5.1k", x + 30.48, y - 6.35, fields="R")
    sh.power("GND", "R302.2")
    sh.wire("J301.B5", (x + 25.4, y - 7.62))
    R(sh, "R303", "5.1k", x + 25.4, y - 3.81, fields="L")
    sh.power("GND", "R303.2")
    sh.wire("J301.A7", (x + 20.32, y - 2.54))
    sh.wire("J301.B7", (x + 20.32, y))
    sh.wire((x + 20.32, y - 2.54), (x + 20.32, y + 33.02))
    sh.wire("J301.A6", (x + 17.78, y + 2.54))
    sh.wire("J301.B6", (x + 17.78, y + 5.08))
    sh.wire((x + 17.78, y + 2.54), (x + 17.78, y + 35.56))
    sh.nc("J301.A8")
    sh.nc("J301.B8")
    sh.power("GND", "J301.A1")
    sh.power("GND", "J301.SH")
    xe, ye = 76.2, 134.62
    sh.add("U302", "Power_Protection:USBLC6-2SC6", xe, ye, value="USBLC6-2SC6", fp=SOT236, lcsc="C2687116",
           fields=((xe + 2.54, ye - 6.35, "left"), (xe + 2.54, ye + 8.89, "left")))
    sh.wire((x + 20.32, y + 33.02), "U302.1")
    sh.wire((x + 17.78, y + 35.56), "U302.3")
    sh.power("+5V", sh.stub("U302.5", 0, -2.54))
    sh.power("GND", "U302.2")

    # ---------------------------------------------------------------- CH347F
    xf, yf = 160.02, 127.0
    sh.add("U301", "fpga_board:CH347F", xf, yf, value="CH347F", fp="Package_DFN_QFN:QFN-28-1EP_4x4mm_P0.4mm_EP2.4x2.4mm",
           lcsc="C18221627", fields=((xf + 5.08, yf - 33.02, "left"), (xf + 5.08, yf + 33.02, "left")))
    # USB data straight to UD-/UD+ (no series resistors, they are inside the CH347)
    sh.wire("U302.6", (86.36, ye), (86.36, yf - 2.54), "U301.27")
    sh.wire("U302.4", (88.9, ye + 2.54), (88.9, yf), "U301.28")
    T("UD+/UD-: no series resistors", 101.6, yf + 3.81)
    # 8 MHz crystal (+-0.4 %), 22 pF load caps
    sh.add("Y301", "Device:Crystal_GND24_Small", 137.16, yf - 17.78, rot=270, value="8MHz",
           fp="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", lcsc="C2682774",
           fields=((127.0, yf - 25.4, "left"), (127.0, yf - 22.86, "left")), extra={"MPN": "X32258MSB4SI"})
    sh.wire("U301.1", "Y301.1")
    sh.wire("Y301.1", (121.92, yf - 20.32))
    C(sh, "C302", "22pF", 121.92, yf - 16.51, fields="L")
    sh.power("GND", "C302.2")
    sh.wire("U301.2", "Y301.3")
    sh.wire("Y301.3", (129.54, yf - 15.24))
    C(sh, "C303", "22pF", 129.54, yf - 11.43, fields="R")
    sh.power("GND", "C303.2")
    sh.power("GND", sh.wire("Y301.2", (132.08, yf - 17.78)), rot=270)
    for n in (3, 11, 12, 7, 8, 9, 10, 4, 5):
        sh.nc("U301.%d" % n)
    # supplies
    sh.stub("U301.21", 0, -5.08)
    sh.stub("U301.6", 0, -5.08)
    sh.wire((xf - 2.54, yf - 33.02), (xf + 2.54, yf - 33.02))
    sh.power("+3V3", (xf - 2.54, yf - 33.02))
    sh.stub("U301.20", 0, 5.08)
    sh.stub("U301.29", 0, 5.08)
    sh.wire((xf - 2.54, yf + 33.02), (xf + 2.54, yf + 33.02))
    sh.power("GND", (xf - 2.54, yf + 33.02))
    T("VCC + VIO = 3.3 V: 100 nF each at the pins", 147.32, yf + 43.18)
    cap_row(sh, [("C304", "100nF"), ("C305", "100nF")], 147.32, yf + 48.26, "+3V3")
    # JTAG to the FPGA, UART0 + SPI to bank 7
    for n, net in ((23, "JTAG_TCK"), (26, "JTAG_TMS"), (25, "JTAG_TDI"), (24, "JTAG_TDO"),
                   (19, "CH_TXD"), (22, "CH_RXD"), (18, "CH_RTS"), (17, "CH_CTS"),
                   (13, "CH_SCS"), (14, "CH_SCK"), (16, "CH_MOSI"), (15, "CH_MISO")):
        sh.glabel(net, sh.stub("U301.%d" % n, 2.54, 0), 0)
    T("CH_TXD = CH347 TXD0 (FPGA receives), CH_RXD = CH347 RXD0", 177.8, yf + 27.94)

    # ---------------------------------------------------------------- external JTAG header
    xh, yh = 259.08, 96.52
    T("J302: external JTAG (Lattice / FTDI cable)", xh - 22.86, yh - 15.24)
    sh.add("J302", "Connector_Generic:Conn_01x06", xh, yh, value="JTAG",
           fp="Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", lcsc="C492405",
           fields=((xh + 2.54, yh - 8.89, "left"), (xh + 2.54, yh + 10.16, "left")))
    sh.power("+3V3", sh.wire("J302.1", (xh - 7.62, yh - 5.08), (xh - 7.62, yh - 7.62)))
    for n, net in ((2, "JTAG_TCK"), (3, "JTAG_TDI"), (4, "JTAG_TDO"), (5, "JTAG_TMS")):
        sh.glabel(net, sh.stub("J302.%d" % n, -2.54, 0), 180)
    sh.power("GND", sh.wire("J302.6", (xh - 7.62, yh + 7.62), (xh - 7.62, yh + 10.16)))
    T("1 VREF  2 TCK  3 TDI  4 TDO  5 TMS  6 GND", xh - 22.86, yh + 17.78)
    T("Soft-core debug (e.g. VexRiscv / RISC-V debug) goes through the ECP5 JTAGG primitive on this same chain.",
      xh - 22.86, yh + 25.4)
    return sh


# ============================================================================ SDRAM
def sdram_sheet(prj):
    sh = prj.sheet("sdram.kicad_sch", "SDRAM", 5)
    T = sh.text
    T("16 MB SDR SDRAM, 16 bit (W9812G6KH-6, 166 MHz) on banks 3 / 2", 25.4, 22.86, 2, True)
    T("TSOP-II-54, A0-A11.  The 32 MB W9825G6KH-6 fits the same footprint; it needs A12 on pin 36 (spare ball M15).",
      25.4, 30.48)
    T("Keep RAM_CLK short; a series resistor can be added at layout.", 25.4, 35.56)
    x, y = 152.4, 139.7
    sh.add("U401", "Memory_RAM:W9812G6KH-5", x, y, value="W9812G6KH-6", fp="Package_SO:TSOP-II-54_22.2x10.16mm_P0.8mm",
           lcsc="C62379", fields=((x + 5.08, y - 38.1, "left"), (x + 5.08, y + 38.1, "left")))
    left = [(20, "RAM_BA0"), (21, "RAM_BA1")] + [(n, "RAM_A%d" % i) for i, n in enumerate(
        (23, 24, 25, 26, 29, 30, 31, 32, 33, 34, 22, 35))] + [
        (19, "RAM_CSn"), (37, "RAM_CKE"), (38, "RAM_CLK"), (15, "RAM_DQML"), (39, "RAM_DQMH"), (16, "RAM_WEn"),
        (17, "RAM_CASn"), (18, "RAM_RASn")]
    for n, net in left:
        sh.glabel(net, sh.stub("U401.%d" % n, -2.54, 0), 180)
    for i, n in enumerate((2, 4, 5, 7, 8, 10, 11, 13, 42, 44, 45, 47, 48, 50, 51, 53)):
        sh.glabel("RAM_DQ%d" % i, sh.stub("U401.%d" % n, 2.54, 0), 0)
    top, bot = sh.P("U401.1")[1] - 5.08, sh.P("U401.28")[1] + 5.08
    sh.wire("U401.1", (sh.P("U401.1")[0], top), (sh.P("U401.3")[0], top), "U401.3")
    sh.power("+3V3", (sh.P("U401.1")[0], top))
    sh.wire("U401.28", (sh.P("U401.28")[0], bot), (sh.P("U401.6")[0], bot), "U401.6")
    sh.power("GND", (sh.P("U401.28")[0], bot))
    T("Decoupling: one 100 nF per VDD / VDDQ pin (7) + bulk", 203.2, 93.98)
    cap_row(sh, [("C401", "10uF")] + [("C%d" % (402 + i), "100nF") for i in range(7)], 203.2, 101.6, "+3V3")
    return sh


# ============================================================================ VGA, HDMI (DVI), audio
def video_sheet(prj):
    sh = prj.sheet("video_audio.kicad_sch", "Video + audio", 6)
    T = sh.text
    T("Video + audio: 12-bit VGA (4-4-4 resistor DAC), DVI over HDMI, PWM / sigma-delta line out", 25.4, 22.86, 2, True)

    # ---------------------------------------------------------------- VGA
    x, y = 190.5, 88.9
    sh.add("J501", "Connector:DE15_Socket_HighDensity_MountingHoles", x, y, value="VGA",
           fp="Connector_Dsub:DSUB-15-HD_Socket_Horizontal_P2.29x1.90mm_EdgePinOffset3.03mm_Housed_MountingHolesOffset4.94mm",
           lcsc="C379814", fields=((x, y - 17.78, None), (x + 6.35, y + 16.51, "left")), extra={"MPN": "D-DMRH15PF-E006"})
    T("4-bit DAC per colour into 75R: 510R / 1k / 2k / 3.9k -> 0.72 V full scale", 129.54, 38.1)
    vals = ("510R", "1k", "2k", "3.9k")                    # bit 3 .. bit 0
    blocks = (("R", 1, 48.26, 165.1, 501), ("G", 2, 111.76, 160.02, 505), ("B", 3, 137.16, 170.18, 509))
    for col, pin, ytop, xbus, ref0 in blocks:
        for k in range(4):
            ry = ytop + 5.08 * k
            ref = "R%d" % (ref0 + k)
            R(sh, ref, vals[k], xbus - 3.81, ry, rot=90, fields=hfields(xbus - 3.81, ry))
            sh.glabel("VGA_%s%d" % (col, 3 - k), sh.stub(ref + ".1", -2.54, 0), 180)
        prow = sh.P("J501.%d" % pin)[1]
        far = ytop if prow > ytop else ytop + 15.24          # bus runs over all four resistor ends
        sh.wire((xbus, far), (xbus, prow), "J501.%d" % pin)
    for pin in (6, 7, 8, 10, 5):
        sh.power("GND", sh.stub("J501.%d" % pin, -2.54, 0), rot=270)
    for pin in (9, 4, 11, 12, 15):
        sh.nc("J501.%d" % pin)
    sh.power("GND", "J501.SH")
    for i, (pin, net) in enumerate(((13, "VGA_HS"), (14, "VGA_VS"))):
        ref = "R%d" % (513 + i)
        py = sh.P("J501.%d" % pin)[1]
        R(sh, ref, "100R", x + 13.97, py, rot=90, fields=hfields(x + 13.97, py, below=(i == 1)))
        sh.wire("J501.%d" % pin, ref + ".1")
        sh.glabel(net, sh.stub(ref + ".2", 2.54, 0), 0)

    # ---------------------------------------------------------------- HDMI (DVI-D, TMDS as LVCMOS33D pairs)
    x, y = 190.5, 190.5
    T("HDMI connector, DVI-D signalling: TMDS pairs driven as LVCMOS33D straight from bank 1", 205.74, 177.8)
    sh.add("J502", "Connector:HDMI_A", x, y, value="HDMI-A", fp="Connector_Video:HDMI_A_Molex_208658-1001_Horizontal",
           lcsc="C138388", fields=((x + 12.7, y + 25.4, "left"), (x + 12.7, y + 27.94, "left")),
           extra={"MPN": "HDMI-001 19PCBTP"})
    for pin, net in ((1, "HDMI_D2_P"), (3, "HDMI_D2_N"), (4, "HDMI_D1_P"), (6, "HDMI_D1_N"), (7, "HDMI_D0_P"),
                     (9, "HDMI_D0_N"), (10, "HDMI_CK_P"), (12, "HDMI_CK_N")):
        sh.glabel(net, sh.stub("J502.%d" % pin, -2.54, 0), 180)
    sh.nc("J502.13")
    sh.nc("J502.14")
    # DDC with 2.2k pull-ups to 3.3 V (FPGA pins are not 5 V tolerant)
    ys, yd = sh.P("J502.15")[1], sh.P("J502.16")[1]
    sh.wire("J502.15", (149.86, ys))
    R(sh, "R515", "2.2k", 152.4, ys - 3.81, fields="R")
    sh.power("+3V3", "R515.1")
    sh.glabel("HDMI_SCL", (149.86, ys), 180)
    sh.wire("J502.16", (124.46, yd))
    R(sh, "R516", "2.2k", 127.0, yd - 3.81, fields="R")
    sh.power("+3V3", "R516.1")
    sh.glabel("HDMI_SDA", (124.46, yd), 180)
    # hot-plug detect: 5 V from the sink, divided to 3.2 V
    yh = sh.P("J502.19")[1]
    R(sh, "R517", "12k", 173.99, yh, rot=90, fields=hfields(173.99, yh))
    sh.wire("J502.19", "R517.2")
    R(sh, "R518", "22k", 170.18, yh + 3.81, fields="L")
    sh.power("GND", "R518.2")
    sh.glabel("HDMI_HPD", sh.wire("R517.1", (165.1, yh)), 180)
    # shields + ground
    for pin in (2, 5, 8, 11, 17):
        sh.stub("J502.%d" % pin, 0, 2.54)
    sh.stub("J502.SH", 0, 2.54)
    sh.wire((x - 5.08, y + 30.48), (x + 7.62, y + 30.48))
    sh.power("GND", sh.wire((x, y + 30.48), (x, y + 33.02)))
    # +5 V to the sink (EDID EEPROM), through a Schottky so the monitor cannot back-feed the board
    sh.wire("J502.18", (x, y - 33.02), (x + 2.54, y - 33.02))
    sh.power("FLAG", (x, y - 33.02))
    sh.add("D501", "Device:D_Schottky", x + 6.35, y - 33.02, value="B5819W", fp="Diode_SMD:D_SOD-123", lcsc="C64885",
           fields=hfields(x + 6.35, y - 33.02))
    sh.power("+5V", sh.wire("D501.2", (x + 20.32, y - 33.02)))

    # ---------------------------------------------------------------- audio line out
    xj, yj = 101.6, 236.22
    T("Stereo line out: 470R + 10 nF low-pass (34 kHz) behind PWM / sigma-delta pins, 10 uF DC block", 38.1, 223.52)
    sh.add("J503", "Connector_Audio:AudioJack3", xj, yj, rot=270, value="PJ-320A",
           fp="Connector_Audio:Jack_3.5mm_PJ320D_Horizontal", lcsc="C2884926", fields=((xj + 7.62, yj - 5.08, "left"),
                                                                                       (xj + 7.62, yj - 2.54, "left")))
    sh.power("GND", sh.stub("J503.S", 0, 2.54))
    for i, (pin, net, yrow) in enumerate((("T", "AUDIO_L", yj + 10.16), ("R", "AUDIO_R", yj + 25.4))):
        px = sh.P("J503." + pin)[0]
        sh.wire("J503." + pin, (px, yrow), (xj - 7.62, yrow))
        cdc, cf, rs = "C%d" % (503 + i), "C%d" % (501 + i), "R%d" % (519 + i)
        C(sh, cdc, "10uF", xj - 11.43, yrow, rot=90, fields=hfields(xj - 11.43, yrow))
        sh.wire(cdc + ".2", (xj - 7.62, yrow))
        sh.wire(cdc + ".1", (xj - 20.32, yrow))
        C(sh, cf, "10nF", xj - 17.78, yrow + 3.81, fields="R")
        sh.power("GND", cf + ".2")
        R(sh, rs, "470R", xj - 24.13, yrow, rot=90, fields=hfields(xj - 24.13, yrow))
        sh.glabel(net, sh.stub(rs + ".1", -2.54, 0), 180)
    return sh


# ============================================================================ user I/O
def pmod(sh, ref, x, y, name, bank):
    sh.text("PMOD %s (bank %d)" % (name, bank), x - 10.16, y - 12.7)
    sh.add(ref, "Connector_Generic:Conn_02x06_Odd_Even", x, y, value="PMOD " + name,
           fp="Connector_PinSocket_2.54mm:PinSocket_2x06_P2.54mm_Horizontal", lcsc="C2897426",
           fields=((x + 1.27, y - 8.89, None), (x + 1.27, y + 11.43, None)))
    for i, n in enumerate((1, 3, 5, 7)):
        sh.glabel("PMOD%s%d" % (name, i), sh.stub("%s.%d" % (ref, n), -2.54, 0), 180)
    for i, n in enumerate((2, 4, 6, 8)):
        sh.glabel("PMOD%s%d" % (name, i + 4), sh.stub("%s.%d" % (ref, n), 2.54, 0), 0)
    sh.power("GND", sh.stub(ref + ".9", -2.54, 0), rot=270)
    sh.power("GND", sh.stub(ref + ".10", 2.54, 0), rot=90)
    sh.power("+3V3", sh.stub(ref + ".11", -2.54, 0), rot=90)
    sh.power("+3V3", sh.stub(ref + ".12", 2.54, 0), rot=270)


def user_sheet(prj):
    sh = prj.sheet("user_io.kicad_sch", "User I/O", 7)
    T = sh.text
    T("User I/O: 8 LEDs, 8 DIP switches, 4 buttons, 4-digit 7-segment, microSD, 4x PMOD, 40-pin GPIO", 25.4, 22.86, 2, True)

    # ---------------------------------------------------------------- LEDs, active high
    T("LED0-7: active high", 35.56, 43.18)
    for k in range(8):
        y = 50.8 + 5.08 * k
        R(sh, "R%d" % (601 + k), "1k", 46.99, y, rot=90, fields=hfields(46.99, y))
        sh.glabel("LED%d" % k, sh.stub("R%d.1" % (601 + k), -2.54, 0), 180)
        LED(sh, "D%d" % (601 + k), "red", 57.15, y, rot=180, fields=((61.595, y - 1.905, "left"), (68.58, y - 1.905, "left")))
        sh.wire("R%d.2" % (601 + k), "D%d.2" % (601 + k))
        sh.wire("D%d.1" % (601 + k), (71.12, y))
    sh.wire((71.12, 50.8), (71.12, 88.9))
    sh.power("GND", (71.12, 88.9))
    for k in range(8):
        sh.parts["D%d" % (601 + k)]["extra"]["hide_value"] = True
    T("D601-D608: red 0603", 35.56, 96.52)

    # ---------------------------------------------------------------- DIP switches -> +3.3 V, 1k series, FPGA pull-down
    xs, ys = 127.0, 68.58
    T("SW0-7: ON = 1 (PULLMODE=DOWN in the LPF, 1k series protects a pin set as output)", 93.98, 43.18)
    sh.add("SW601", "Switch:SW_DIP_x08", xs, ys, value="DSHP08TSGET",
           fp="Button_Switch_SMD:SW_DIP_SPSTx08_Slide_KingTek_DSHP08TS_W7.62mm_P1.27mm", lcsc="C40738",
           fields=((xs, ys - 15.24, None), (xs, ys + 12.7, None)))
    for j, yr in enumerate((ys - 5.08, ys + 5.08)):
        rn = "RN%d" % (601 + j)
        sh.add(rn, "Device:R_Pack04", 109.22, yr, rot=270, value="1k x4", fp="Resistor_SMD:R_Array_Convex_4x0603",
               lcsc="C20197", fields=((109.22, yr - 10.16, None), (109.22, yr - 7.62, None)) if j == 0 else
               ((109.22, yr + 6.35, None), (109.22, yr + 8.89, None)))
        for i in range(4):
            k = 4 * j + i
            sh.wire("%s.%d" % (rn, 8 - i), "SW601.%d" % (k + 1))
            sh.glabel("SW%d" % k, sh.stub("%s.%d" % (rn, i + 1), -2.54, 0), 180)
    for k in range(8):
        sh.stub("SW601.%d" % (16 - k), 2.54, 0)
    sh.wire((xs + 10.16, ys - 10.16), (xs + 10.16, ys + 7.62))
    sh.power("+3V3", sh.wire((xs + 10.16, ys - 10.16), (xs + 10.16, ys - 12.7)))

    # ---------------------------------------------------------------- push buttons, active low
    T("BTN0-3: active low, 10k pull-up (BTN0 = reset of the emulated core by convention)", 35.56, 109.22)
    for i in range(4):
        xi, yn = 40.64 + 22.86 * i, 127.0
        R(sh, "R%d" % (609 + i), "10k", xi, yn - 3.81, fields="R")
        sh.power("+3V3", "R%d.1" % (609 + i))
        sh.add("SW%d" % (602 + i), "Switch:SW_Push", xi, yn + 5.08, rot=90, value="BTN%d" % i,
               fp="Button_Switch_SMD:SW_SPST_TL3342", lcsc="C318884", fields="R")
        sh.power("GND", "SW%d.1" % (602 + i))
        sh.glabel("BTN%d" % i, sh.wire((xi, yn), (xi + 5.08, yn)), 0)

    # ---------------------------------------------------------------- 4-digit 7-segment, common anode, multiplexed
    xd, yd = 241.3, 76.2
    T("4-digit 7-segment (common anode): segments active low through 100R, digits active low via PNP", 187.96, 43.18)
    sh.add("DS601", "Display_Character:CA56-12EWA", xd, yd, value="FJ5461BH", fp="Display_7Segment:CA56-12EWA",
           lcsc="C38183", fields=((xd, yd - 15.24, None), (xd, yd + 15.24, None)))
    segs = ((11, "SEG_A"), (7, "SEG_B"), (4, "SEG_C"), (2, "SEG_D"), (1, "SEG_E"), (10, "SEG_F"), (5, "SEG_G"),
            (3, "SEG_DP"))
    for j, yr in enumerate((yd - 2.54, yd + 7.62)):
        rn = "RN%d" % (603 + j)
        sh.add(rn, "Device:R_Pack04", 203.2, yr, rot=270, value="100R x4", fp="Resistor_SMD:R_Array_Convex_4x0603",
               lcsc="C25506", fields=((203.2, yr - 10.16, None), (203.2, yr - 7.62, None)) if j == 0 else
               ((203.2, yr + 6.35, None), (203.2, yr + 8.89, None)))
        for i in range(4):
            pin, net = segs[4 * j + i]
            sh.wire("%s.%d" % (rn, 8 - i), "DS601.%d" % pin)
            sh.glabel(net, sh.stub("%s.%d" % (rn, i + 1), -2.54, 0), 180)
    for i, ca in enumerate((12, 9, 8, 6)):
        xq, yq = 284.48 + 25.4 * i, 58.42
        q, rb = "Q%d" % (601 + i), "R%d" % (613 + i)
        sh.add(q, "Transistor_BJT:MMBT3906", xq, yq, mirror="x", value="MMBT3906", fp=SOT23, lcsc="C53444",
               fields=((xq + 5.08, yq - 1.27, "left"), (xq + 5.08, yq + 1.27, "left")))
        sh.parts[q]["extra"]["hide_value"] = True
        cpt = sh.P("DS601.%d" % ca)
        sh.wire("%s.3" % q, (xq + 2.54, cpt[1]), cpt)
        sh.power("+3V3", sh.stub(q + ".2", 0, -2.54))
        R(sh, rb, "1k", xq - 7.62, yq - 3.81, fields="L")
        sh.wire(q + ".1", rb + ".2")
        sh.glabel("DIG%d" % i, sh.stub(rb + ".1", 0, -2.54), 90)
    T("Q601-Q604: MMBT3906", 284.48, 71.12)

    # ---------------------------------------------------------------- microSD
    xm, ym = 76.2, 190.5
    T("microSD (SD 4-bit or SPI): CMD / DAT / CD use the FPGA pull-ups (PULLMODE=UP)", 35.56, 165.1)
    sh.add("J601", "Connector:Micro_SD_Card_Det1", xm, ym, value="TF PUSH", fp="Connector_Card:microSD_HC_Molex_104031-0811",
           lcsc="C393941", fields=((xm, ym - 15.24, None), (xm, ym + 17.78, None)))
    for pin, net in ((1, "SD_D2"), (2, "SD_D3"), (3, "SD_CMD"), (5, "SD_CLK"), (7, "SD_D0"), (8, "SD_D1"), (9, "SD_CD")):
        sh.glabel(net, sh.stub("J601.%d" % pin, -2.54, 0), 180)
    sh.power("+3V3", sh.stub("J601.4", -2.54, 0), rot=90)
    sh.power("GND", sh.stub("J601.6", -2.54, 0), rot=270)
    sh.power("GND", "J601.SH")
    cap_row(sh, [("C601", "10uF"), ("C602", "100nF")], 106.68, 182.88, "+3V3")

    # ---------------------------------------------------------------- PMODs
    for i, (name, bank) in enumerate((("A", 0), ("B", 0), ("C", 2), ("D", 2))):
        pmod(sh, "J%d" % (602 + i), 165.1 + 50.8 * i, 243.84, name, bank)
    T("PMOD pinout (Digilent): top row 1-4 = PMODx0-3, bottom row 7-10 = PMODx4-7, 5/11 GND, 6/12 3.3 V", 154.94, 220.98)

    # ---------------------------------------------------------------- 40-pin GPIO header
    xg, yg = 355.6, 127.0
    T("GPIO header: 34 I/O (banks 7, 6, 0), 3.3 V logic", 335.28, 93.98)
    sh.add("J606", "Connector_Generic:Conn_02x20_Odd_Even", xg, yg, value="GPIO",
           fp="Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical", lcsc="C22465944",
           fields=((xg + 1.27, yg - 27.94, None), (xg + 1.27, yg + 30.48, None)))
    sh.power("+5V", sh.wire("J606.1", (xg - 7.62, yg - 22.86), (xg - 7.62, yg - 25.4)))
    sh.power("+3V3", sh.wire("J606.2", (xg + 10.16, yg - 22.86), (xg + 10.16, yg - 25.4)))
    sh.power("GND", sh.stub("J606.19", -2.54, 0), rot=270)
    sh.power("GND", sh.stub("J606.20", 2.54, 0), rot=90)
    sh.power("GND", sh.wire("J606.39", (xg - 7.62, yg + 25.4), (xg - 7.62, yg + 27.94)))
    sh.power("GND", sh.wire("J606.40", (xg + 10.16, yg + 25.4), (xg + 10.16, yg + 27.94)))
    io = [n for n in range(3, 39) if n not in (19, 20)]
    for k, n in enumerate(io):
        if n % 2:
            sh.glabel("GPIO%d" % k, sh.stub("J606.%d" % n, -2.54, 0), 180)
        else:
            sh.glabel("GPIO%d" % k, sh.stub("J606.%d" % n, 2.54, 0), 0)
    return sh


def main():
    prj = Project(PRJ_NAME, ROOT_UUID)
    root = root_sheet(prj)
    sheets = [power_sheet(prj), config_sheet(prj), usb_sheet(prj), sdram_sheet(prj), video_sheet(prj), user_sheet(prj)]
    for sh in sheets:
        write_sheet(sh, title_block(prj, sh.title, DATE, REV, ["ECP5 emulation board"]))
        report(sh)
    bx, by = 335.28, 30.48
    blocks = []
    for i, sh in enumerate(sheets):
        blocks.append((sh, bx, by + 20.32 * i, 40.64, 12.7, sh.title))
    write_root(prj, ROOT_FILE, title_block(prj, "ECP5 emulation board - FPGA", DATE, REV,
                                           ["LFE5U-25F-7BG256I, units as placed by the user"]),
               blocks, root, paper="A3")
    report(root)


if __name__ == "__main__":
    main()
