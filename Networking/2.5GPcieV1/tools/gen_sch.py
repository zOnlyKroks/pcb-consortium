"""Generate the 2.5GPcieV1 schematic: root + pcie.kicad_sch + nic.kicad_sch (explicit placement, real wires).

Minimal RTL8125BG PCIe x1 2.5GbE card: no EEPROM / SPI flash (the driver configures the chip), 2 LEDs in the
RJ45.  Pin handling follows the RTL8125B datasheet (Rev 1.6) and the Radxa E25 production schematic.
Global labels only for the PCIe signals between the two sheets.  Run check_netlist.py afterwards.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import Project, write_sheet, write_root, report, title_block

PRJ_NAME = "2.5GPcieV1"
ROOT_UUID = "8d0b6a3e-4c21-4f7b-9e5a-2b6c1d7e9f30"
DATE, REV = "2026-10-16", "2"
L = "2.5GPcieV1:"
FPL = "lcsc_footprints:"

R0603, C0603, C0402, C0805, C1206 = ("Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric",
                                     "Capacitor_SMD:C_0402_1005Metric", "Capacitor_SMD:C_0805_2012Metric",
                                     "Capacitor_SMD:C_1206_3216Metric")
RES = {"0R": "C21189", "1k": "C21190", "15k": "C22809", "4.7k": "C23162", "2.49k 1%": "C22908", "75R": "C4275",
       "330R": "C23138", "33k 1%": "C4216", "56k 1%": "C23206", "100k": "C25803"}
CAP = {"100nF": (C0603, "C14663"), "100nF 0402": (C0402, "C1525"), "1uF": (C0603, "C15849"),
       "10uF": (C0603, "C19702"), "22uF": (C0805, "C45783"), "18pF": (C0603, "C1647"), "22pF": (C0603, "C1653"),
       "1nF 2kV": (C1206, "C9196")}


def R(sh, ref, val, x, y, rot=0, fields="R"):
    return sh.add(ref, "Device:R", x, y, rot, value=val, fp=R0603, lcsc=RES[val], fields=fields)


def C(sh, ref, val, x, y, rot=0, fields="R"):
    fp, lcsc = CAP[val]
    return sh.add(ref, "Device:C", x, y, rot, value=val.replace(" 0402", ""), fp=fp, lcsc=lcsc, fields=fields)


def hfields(x, y, below=False):
    """Reference left / value right on one line above (or below) a horizontal 2-pin part."""
    dy = 1.905 if below else -1.905
    return ((x - 0.635, y + dy, "right"), (x + 0.635, y + dy, "left"))


# ============================================================================ PCIe + power
def pcie_sheet(prj):
    sh = prj.sheet("pcie.kicad_sch", "PCIe x1 + power", 2)
    T = sh.text
    T("PCI Express x1 edge connector", 45.72, 30.48, 2, True)
    T("Only +3.3 V (3 A max), REFCLK, PERST# and lane 0 are used.  +12 V, 3.3 Vaux, SMBus, JTAG and WAKE# stay open.",
      45.72, 35.56)
    sh.add("J1", L + "PCIe_x1_Edge", 101.6, 132.08, value="PCIe x1", fp="Connector_PCBEdge:BUS_PCIexpress_x1",
           fields=((93.98, 101.6, None), (93.98, 162.56, None)))
    for n in ("B5", "B6", "B12", "B11", "B9", "A5", "A6", "A7", "A8"):
        sh.nc("J1." + n)
    sh.nc("J1.A2")                                   # +12V (all +12V pins are stacked on one point)
    sh.nc("J1.B10")                                  # 3.3Vaux
    # +3.3 V from the slot
    sh.wire("J1.A9", (104.14, 96.52))
    sh.power("+3V3", (104.14, 96.52))
    sh.wire((104.14, 99.06), (111.76, 99.06))
    sh.power("FLAG", (111.76, 99.06))
    sh.wire("J1.A4", (101.6, 162.56))
    sh.power("GND", (101.6, 162.56))
    sh.wire((101.6, 157.48), (109.22, 157.48))
    sh.power("FLAG", (109.22, 157.48))
    # presence detect: PRSNT1# (A1) must be strapped to PRSNT2# (B17) on an x1 card
    a, b = sh.stub("J1.A1", -5.08, 0), sh.stub("J1.B17", -5.08, 0)
    sh.wire(a, b)
    T("PRSNT1# - PRSNT2# (x1)", 55.88, 131.445)
    # reference clock and the lane: host TX (PETx) goes straight to the chip's receiver
    sh.glabel("REFCLK_P", sh.stub("J1.A13", -12.7, 0), 180, "input")
    sh.glabel("REFCLK_N", sh.stub("J1.A14", -12.7, 0), 180, "input")
    sh.glabel("PCIE_RX_P", sh.stub("J1.B14", -12.7, 0), 180, "input")
    sh.glabel("PCIE_RX_N", sh.stub("J1.B15", -12.7, 0), 180, "input")
    T("host -> card (AC caps are on the host)", 45.72, 154.94)
    sh.glabel("PERST#", sh.stub("J1.A11", 12.7, 0), 0, "input")
    # card TX -> host RX through the AC-coupling capacitors (card side)
    for n, pinname, lab, y, x in ((1, "A16", "PCIE_TX_P", 144.78, 124.46), (2, "A17", "PCIE_TX_N", 147.32, 132.08)):
        C(sh, "C%d" % n, "100nF 0402", x, y, rot=90, fields=hfields(x, y, below=(n == 2)))
        sh.wire("J1." + pinname, "C%d.1" % n)
        sh.wire("C%d.2" % n, (142.24, y))
        sh.glabel(lab, (142.24, y), 0, "output")
    T("card -> host: 100 nF AC coupling", 116.84, 154.94)

    # ---------------------------------------------------------------- 3.3 V bulk at the slot
    T("+3.3 V input", 152.4, 76.2, 2, True)
    for i, (ref, val) in enumerate((("C3", "22uF"), ("C4", "100nF"))):
        x = 157.48 + 10.16 * i
        sh.power("+3V3", (x, 83.82))
        C(sh, ref, val, x, 87.63)
        sh.power("GND", ref + ".2")

    # ---------------------------------------------------------------- 0.95 V core buck
    T("0.95 V core supply (RTL8125B has no built-in regulator)", 200.66, 76.2, 2, True)
    T("0.92-0.98 V, 364 mA typ / 650 mA max", 200.66, 81.28)
    sh.add("U2", L + "SY8089", 241.3, 116.84, value="SY8089A1AAC", fp="Package_TO_SOT_SMD:SOT-23-5", lcsc="C479074",
           fields=((241.3, 106.68, None), (241.3, 109.22, None)))
    sh.power("+3V3", (200.66, 114.3))
    sh.wire((200.66, 114.3), "U2.4")
    for ref, val, x in (("C5", "10uF", 205.74), ("C6", "100nF", 210.82)):
        C(sh, ref, val, x, 118.11, fields="L" if ref == "C5" else "R")
        sh.power("GND", ref + ".2")
    # EN: RC delay so the core rail rises after +3.3 V
    R(sh, "R1", "100k", 223.52, 119.38, rot=90, fields=hfields(223.52, 119.38, below=True))
    sh.wire("R1.1", (219.71, 114.3))
    sh.wire("R1.2", "U2.1")
    C(sh, "C7", "100nF", 228.6, 125.73, fields="R")
    sh.wire((228.6, 119.38), "C7.1")
    sh.power("GND", "C7.2")
    sh.power("GND", "U2.2")
    sh.add("L1", "Device:L", 255.27, 114.3, rot=90, value="2.2uH", fp=FPL + "IND-SMD_L4.0-W4.0_FNR40XXS", lcsc="C167869",
           fields=hfields(255.27, 114.3))
    sh.wire("U2.3", "L1.1")
    sh.wire("L1.2", (294.64, 114.3))
    C(sh, "C8", "22pF", 261.62, 118.11, fields="L")
    R(sh, "R2", "33k 1%", 266.7, 118.11, fields="R")
    R(sh, "R3", "56k 1%", 266.7, 125.73, fields="R")
    sh.power("GND", "R3.2")
    sh.wire("U2.5", (254.0, 119.38), (254.0, 121.92), (266.7, 121.92))
    for ref, val, x in (("C9", "22uF", 279.4), ("C10", "22uF", 287.02)):
        C(sh, ref, val, x, 118.11)
        sh.power("GND", ref + ".2")
    sh.power("+0V95", (294.64, 114.3))
    sh.wire((294.64, 114.3), (302.26, 114.3))
    sh.power("FLAG", (302.26, 114.3))
    T("Vout = 0.6 V x (1 + 33k / 56k) = 0.954 V", 241.3, 137.16)
    T("C8 22 pF: feed-forward across the upper divider resistor", 241.3, 140.97)
    T("R1/C7 delay EN (~10 ms) so 0.95 V comes up after 3.3 V", 200.66, 144.78)
    return sh


# ============================================================================ RTL8125BG + Ethernet
def nic_sheet(prj):
    sh = prj.sheet("nic.kicad_sch", "RTL8125BG + Ethernet", 3)
    T = sh.text
    UX, UY = 152.4, 160.02
    sh.add("U1", L + "RTL8125BG", UX, UY, value="RTL8125BG-CG", fp=FPL + "C3013605_TQFN-48_L6_0-W6_0-P0_40-BL-EP4_5",
           lcsc="C3013605", fields=((UX, UY + 7.62, None), (UX, UY + 10.16, None)))
    T("RTL8125BG 2.5GbE controller", 20.32, 30.48, 2, True)
    T("No EEPROM / SPI flash: the driver configures the chip (MAC from eFuse, or set by the driver).", 20.32, 35.56)

    # ---------------------------------------------------------------- supplies at the pins
    bus = 121.92
    for n in ("46", "29", "43", "15", "19", "33"):
        sh.wire("U1." + n, (sh.P("U1." + n)[0], bus))
    sh.wire((129.54, bus), (142.24, bus))
    sh.power("+3V3", (129.54, bus))
    for n in ("8", "28", "47", "37", "11", "16", "22"):
        sh.wire("U1." + n, (sh.P("U1." + n)[0], bus))
    sh.wire((157.48, bus), (172.72, bus))
    sh.power("+0V95", (172.72, bus))
    # AVDD33_XTAL: ferrite-filtered 3.3 V
    node = (149.86, 101.6)
    sh.wire("U1.34", node)
    sh.add("FB1", "Device:FerriteBead_Small", 149.86, 96.52, value="BLM18PG121SN1D",
           fp="Inductor_SMD:L_0603_1608Metric", lcsc="C14709", fields=((147.32, 93.98, "right"), (147.32, 95.885, "right")))
    sh.wire(node, "FB1.2")
    sh.power("+3V3", "FB1.1")
    sh.wire(node, (170.18, 101.6))
    sh.wire(node, (134.62, 101.6))
    sh.power("FLAG", (134.62, 101.6))
    for ref, val, x in (("C21", "100nF", 160.02), ("C22", "10uF", 170.18)):
        C(sh, ref, val, x, 105.41, fields="R")
        sh.power("GND", ref + ".2")
    T("AVDD33_XTAL", 151.13, 99.695)

    # decoupling, one capacitor per supply pin (place each at its pin)
    T("Decoupling: one 100 nF per supply pin, at the pin", 20.32, 50.8, 1.5, True)
    def caprow(title, rail, refs, x0, y0):
        T(title, x0, y0 - 6.35)
        n = len(refs)
        sh.power(rail, (x0, y0))
        sh.wire((x0, y0), (x0 + 10.16 * (n - 1), y0))
        for i, (ref, val) in enumerate(refs):
            x = x0 + 10.16 * i
            C(sh, ref, val, x, y0 + 3.81, fields="R")
            sh.power("GND", ref + ".2")
    caprow("+3V3: pins 46, 29, 43, 15, 19, 33 + bulk", "+3V3",
           [("C11", "100nF"), ("C12", "100nF"), ("C13", "100nF"), ("C14", "100nF"), ("C15", "100nF"), ("C16", "100nF"),
            ("C17", "10uF")], 25.4, 66.04)
    caprow("+0V95: pins 8, 28, 47, 37, 11, 16, 22 + bulk", "+0V95",
           [("C23", "100nF"), ("C24", "100nF"), ("C25", "100nF"), ("C26", "100nF"), ("C27", "100nF"), ("C28", "100nF"),
            ("C29", "100nF"), ("C30", "10uF")], 116.84, 66.04)

    # ---------------------------------------------------------------- PCIe side
    for n, lab, shape in (("44", "REFCLK_P", "input"), ("45", "REFCLK_N", "input"), ("41", "PCIE_RX_P", "input"),
                          ("42", "PCIE_RX_N", "input"), ("38", "PCIE_TX_P", "output"), ("39", "PCIE_TX_N", "output"),
                          ("36", "PERST#", "input")):
        sh.glabel(lab, sh.stub("U1." + n, -10.16, 0), 180, shape)
    # straps / control pins: one horizontal row each
    def pull(pinnum, ref, val, to):
        y = sh.P("U1." + pinnum)[1]
        R(sh, ref, val, 106.68, y, rot=90, fields=hfields(106.68, y))
        sh.wire("U1." + pinnum, ref + ".2")
        if to == "GND":
            sh.power("GND", ref + ".1", rot=270)
        else:
            sh.power("+3V3", ref + ".1", rot=90)
    pull("48", "R4", "0R", "GND")
    pull("2", "R5", "4.7k", "+3V3")
    pull("3", "R6", "4.7k", "+3V3")
    pull("6", "R7", "4.7k", "+3V3")
    pull("1", "R8", "1k", "+3V3")
    yi = sh.P("U1.1")[1]
    R(sh, "R9", "15k", 116.84, yi + 3.81, fields="R")
    sh.power("GND", "R9.2")
    T("CLKREQB tied low: x1 slots have no CLKREQ#,", 20.32, 165.1)
    T("so the reference clock is always requested", 20.32, 168.91)
    T("LANWAKEB, LED1/EESK: must be high at reset", 20.32, 175.26)
    T("(low = Realtek test mode)", 20.32, 179.07)
    T("GPI high = PHY/LAN enabled", 20.32, 185.42)
    T("ISOLATEB ~3.1 V from main 3.3 V (1k/15k)", 20.32, 191.77)

    # ---------------------------------------------------------------- crystal, RSET, unused pins, ground
    sh.add("Y1", "Device:Crystal_GND24", 144.78, 205.74, value="25MHz 12pF", fp="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
           lcsc="C9006", fields=((144.78, 224.79, None), (144.78, 226.695, None)))
    sh.wire("U1.10", "Y1.1")
    sh.wire("U1.9", "Y1.3")
    sh.power("GND", "Y1.2")
    for ref, x in (("C31", 140.97), ("C32", 148.59)):
        C(sh, ref, "18pF", x, 213.36, fields="L" if ref == "C31" else "R")
        sh.wire((x, 205.74), ref + ".1")
        sh.power("GND", ref + ".2")
    T("18 pF: 12 pF crystal with ~3 pF stray (verify the 25 MHz on the bench)", 101.6, 233.68)
    R(sh, "R10", "2.49k 1%", 152.4, 201.93, fields=((154.94, 207.645, "left"), (154.94, 209.55, "left")))
    sh.wire("U1.12", "R10.1")
    sh.power("GND", "R10.2")
    for n in ("4", "5", "7"):
        sh.nc("U1." + n)
    g40, g49 = sh.P("U1.40"), sh.P("U1.49")
    sh.wire("U1.40", (g40[0], 200.66), (g49[0], 200.66))
    sh.wire("U1.49", (g49[0], 200.66))
    sh.power("GND", (g40[0], 200.66))

    # ---------------------------------------------------------------- magnetics + jack
    TX_, TY = 215.9, 153.67
    sh.add("TR1", L + "H2414QR", TX_, TY, value="H2414QR", fp=FPL + "C4155001_XFMR-SMD_H2414QR", lcsc="C4155001",
           fields=((TX_, TY - 15.24, None), (TX_, TY - 13.335, None)))
    for a, b in (("13", "2"), ("14", "3"), ("17", "5"), ("18", "6"), ("20", "8"), ("21", "9"), ("23", "11"), ("24", "12")):
        sh.wire("U1." + a, "TR1." + b)
    sh.add("J2", L + "RJ45_LED", 264.16, TY, value="RJ45-202-007-02", fp=FPL + "RJ45-TH_RJ45-202-007-02", lcsc="C7421418",
           fields=((264.16, TY - 16.51, None), (264.16, TY - 14.605, None)))
    for a, b in (("23", "1"), ("22", "2"), ("20", "3"), ("19", "6"), ("17", "4"), ("16", "5"), ("14", "7"), ("13", "8")):
        sh.wire("TR1." + a, "J2." + b)
    # chip-side centre taps: 100 nF each to GND (voltage-mode PHY)
    for i, n in enumerate(("1", "4", "7", "10")):
        x = sh.P("TR1." + n)[0]
        sh.add("C%d" % (33 + i), "Device:C", x, 176.53, value="100nF", fp=C0603, lcsc="C14663",
               fields=((x + 1.27, 175.26, "left"), (x, 176.53, None)), extra={"hide_value": True})
        sh.wire("TR1." + n, "C%d.1" % (33 + i))
        sh.power("GND", "C%d.2" % (33 + i))
    # line-side centre taps: Bob Smith, 75R each to 1 nF / 2 kV
    xs = []
    for i, n in enumerate(("24", "21", "18", "15")):
        x = sh.P("TR1." + n)[0]
        xs.append(x)
        sh.add("R%d" % (11 + i), "Device:R", x, 176.53, value="75R", fp=R0603, lcsc="C4275",
               fields=((x + 1.27, 175.26, "left"), (x, 176.53, None)), extra={"hide_value": True})
        sh.wire("TR1." + n, "R%d.1" % (11 + i))
        sh.wire("R%d.2" % (11 + i), (x, 184.15))
    sh.wire((xs[0], 184.15), (243.84, 184.15))
    C(sh, "C37", "1nF 2kV", 243.84, 187.96, fields="R")
    sh.power("GND", "C37.2")
    T("C33-C36 100 nF (chip-side centre taps)", 190.5, 201.93)
    T("R11-R14 75R + C37: Bob Smith termination", 190.5, 205.74)
    sh.wire("J2.13", (266.7, 170.18))
    sh.power("GND", (266.7, 170.18))
    T("shield -> GND (bracket)", 271.78, 171.45)

    # ---------------------------------------------------------------- LEDs (active low, sink into the chip)
    for n, ref in (("9", "R15"), ("11", "R16")):
        y = sh.P("J2." + n)[1]
        R(sh, ref, "330R", 280.67, y, rot=90, fields=hfields(280.67, y))
        sh.wire("J2." + n, ref + ".1")
        sh.power("+3V3", ref + ".2", rot=270)
    for n, lab in (("10", "LED2"), ("12", "LED1")):
        sh.wire("J2." + n, (281.94, sh.P("J2." + n)[1]))
        sh.label(lab, (281.94, sh.P("J2." + n)[1]))
    yg = sh.P("J2.12")[1]
    R(sh, "R17", "4.7k", 289.56, yg, rot=90, fields=hfields(289.56, yg, below=True))
    sh.wire((281.94, yg), "R17.1")
    sh.power("+3V3", "R17.2", rot=270)
    T("Y = LED2, G = LED1 (driver LED settings)", 254.0, 133.35)
    T("R17: LED1/EESK strap pull-up", 279.4, 166.37)
    for n, lab in (("27", "LED1"), ("25", "LED2")):
        p = sh.stub("U1." + n, 5.08, 0)
        sh.label(lab, p)
    for n in ("30", "35", "31", "32", "26"):
        sh.nc("U1." + n)
    T("EEPROM / SPI flash pins unused", 182.88, 196.85)
    return sh


def main():
    prj = Project(PRJ_NAME, ROOT_UUID)
    tb = lambda t, c=(): title_block(prj, t, DATE, REV, list(c))
    p = pcie_sheet(prj)
    n = nic_sheet(prj)
    write_sheet(p, tb("2.5GPcieV1 - PCIe x1 + power",
                      ["RTL8125BG 2.5GbE PCIe x1 card (minimal, driver-configured)", "+3.3 V from the slot, 0.95 V buck"]))
    write_sheet(n, tb("2.5GPcieV1 - RTL8125BG + Ethernet",
                      ["Pin handling per RTL8125B datasheet Rev 1.6 and the Radxa E25 schematic", "H2414QR + RJ45 with 2 LEDs"]))
    root = prj.sheet("2.5GPcieV1.kicad_sch", "root", 1)
    T = root.text
    T("2.5GPcieV1 - minimal RTL8125BG 2.5GbE PCIe x1 card", 30.48, 30.48, 3, True)
    lines = ["- Plugs into any PCIe x1 (or wider) slot; the OS driver (r8125 / r8169 / Windows) configures the chip.",
             "- No EEPROM or SPI flash. The MAC comes from the chip's eFuse if programmed, otherwise the driver assigns one.",
             "- Powered from the slot's +3.3 V only. The 0.95 V core comes from an SY8089 buck.",
             "- 2 LEDs in the RJ45: green = LED1, yellow = LED2. Their function is set by the driver (default: link/activity).",
             "- No Wake-on-LAN (3.3 Vaux and WAKE# unused)."]
    for i, s in enumerate(lines):
        T(s, 30.48, 40.64 + 5.08 * i)
    write_root(prj, "2.5GPcieV1.kicad_sch", tb("2.5GPcieV1 - RTL8125BG 2.5GbE PCIe x1 card", ["Overview"]),
               [(p, 40.64, 88.9, 50.8, 25.4, "PCIe x1 + power"), (n, 121.92, 88.9, 50.8, 25.4, "RTL8125BG + Ethernet")],
               root)
    for sh in (p, n):
        report(sh)


if __name__ == "__main__":
    main()
