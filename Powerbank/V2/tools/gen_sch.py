"""Generate the PowerbankV2 schematic (root + battery, port A, port B, system) with explicit placement and real wires.

Power symbols: +BATT = VBAT (pack + after the fuse), -BATT = BATN (cell stack bottom, BQ77915 VSS),
GND = PACK- (system ground), +5V, +3V3.  Global labels only for nets that cross sheets (PD_SCL/SDA/IRQ).
Local labels where a net has to jump inside a sheet.  Run check_netlist.py afterwards.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import Project, write_sheet, write_root, report, title_block

PRJ_NAME = "V2"
ROOT_UUID = "8e2b4c61-1a3f-4d5e-9c7b-6a1d2e3f4b5c"
DATE, REV = "2026-10-24", "1"
L = "PowerbankV2:"

R0603, R2512 = "Resistor_SMD:R_0603_1608Metric", "Resistor_SMD:R_2512_6332Metric"
C0603, C0805, C1206 = "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric", "Capacitor_SMD:C_1206_3216Metric"
RES = {"1k": "C21190", "100R": "C22775", "10k": "C25804", "100k": "C25803", "1M": "C22935", "4.7k": "C23162",
       "2.2k": "C4190", "470k": "C23178", "27k": "C22967", "5.23k": "C23068", "30.1k": "C23000", "665k": "C23227",
       "130k": "C22795", "10.5k": "C22855", "1.96k": "C22854", "37.4k": "C23033", "6.8k": "C23212", "51k": "C23196",
       "15k": "C22809", "1.5k": "C22843", "2mR": "C160590"}
CAP = {"100nF": (C0603, "C14663"), "1uF": (C0603, "C15849"), "10uF": (C0603, "C19702"),
       "10uF 50V": (C1206, "C13585"), "22uF 25V": (C0805, "C45783"), "4.7uF 25V": (C0805, "C1779"),
       "330pF": (C0603, "C1664"), "47nF": (C0603, "C1622"), "1nF": (C0603, "C1588"), "10nF": (C0603, "C57112"),
       "2.2nF": (C0603, "C1604"), "22pF": (C0603, "C1653"), "47uF 10V": (C1206, "C96123")}


def R(sh, ref, val, x, y, rot=0, fields="R", **kw):
    fp = R2512 if val == "2mR" else R0603
    return sh.add(ref, "Device:R", x, y, rot, value=val, fp=fp, lcsc=RES[val], fields=fields, **kw)


def C(sh, ref, val, x, y, rot=0, fields="R", **kw):
    fp, lcsc = CAP[val]
    return sh.add(ref, "Device:C", x, y, rot, value=val, fp=fp, lcsc=lcsc, fields=fields, **kw)


def NTC(sh, ref, x, y, rot=0, fields="R"):
    return sh.add(ref, "Device:Thermistor_NTC", x, y, rot, value="10k B3380", fp=R0603, lcsc="C13564",
                  fields=fields)


# vertical two-pin parts have pin 1 at y-3.81 (top) for rot 0, at y+3.81 for rot 180;
# horizontal: rot 90 -> pin 1 left (x-3.81), rot 270 -> pin 1 right.
def vR(sh, ref, val, x, ytop, flip=False, **kw):
    """Vertical resistor whose top pin is at (x, ytop); flip puts pin 2 on top."""
    return R(sh, ref, val, x, ytop + 3.81, 180 if flip else 0, **kw)


def hR(sh, ref, val, xl, y, flip=False, **kw):
    kw.setdefault("fields", "T")
    return R(sh, ref, val, xl + 3.81, y, 270 if flip else 90, **kw)


def vC(sh, ref, val, x, ytop, flip=False, **kw):
    return C(sh, ref, val, x, ytop + 3.81, 180 if flip else 0, **kw)


def hC(sh, ref, val, xl, y, flip=False, **kw):
    kw.setdefault("fields", "T")
    return C(sh, ref, val, xl + 3.81, y, 270 if flip else 90, **kw)


def decap(sh, ref, val, x, yrail, gnd="GND"):
    """Cap hanging down from a rail at (x, yrail) with a ground symbol on pin 2."""
    vC(sh, ref, val, x, yrail)
    sh.power(gnd, "%s.2" % ref)


def flag_bat(sh, at):
    sh.power("-BATT", at, rot=180)


# ============================================================================ battery
def battery_sheet(prj):
    sh = prj.sheet("battery.kicad_sch", "Battery", 2)
    T = sh.text
    T("4S2P 18650 pack + BQ7791501 protection / balancing", 20.32, 20.32, 2, True)
    T("BQ7791501: OV 4.25 V, UV 2.8 V, OCD1 35 mV (17.5 A), OCD2 60 mV, SCD 120 mV (60 A), OCC 20 mV (10 A)",
      20.32, 24.13)
    T("PACK- = GND (system ground).  -BATT = cell stack bottom (BQ77915 VSS).  Charge to 16.6 V (4.15 V/cell).",
      20.32, 27.94)

    # ---- cells: group g (0 = top, CELL4/CELL3) .. 3 (bottom, CELL1/BATN), two in parallel
    XA, XB = 30.48, 45.72
    ys = [63.5 + 25.4 * g for g in range(4)]
    for g, y in enumerate(ys):
        a, b = "BT1%02d" % (7 - 2 * g), "BT1%02d" % (8 - 2 * g)
        for ref, x in ((a, XA), (b, XB)):
            sh.add(ref, "Device:Battery_Cell", x, y, value="18650", fp=L + "BatteryHolder_BH-18650-B1BA002",
                   lcsc="C2988620", fields="L" if x == XA else "R")
        sh.wire(a + ".1", b + ".1")
        sh.wire(a + ".2", b + ".2")
    # series links between groups (vertical at XB) and the cell taps
    TAPS = {"CELL4": 50.8, "CELL3": 76.2, "CELL2": 101.6, "CELL1": 127.0, "BATN": 152.4}
    sh.wire((XB, 30.48), "BT108.1")                      # top + up to the fuse row
    for g in range(3):
        sh.wire("BT1%02d.2" % (8 - 2 * g), "BT1%02d.1" % (6 - 2 * g))
    sh.wire("BT102.2", (XB, 185.42))                     # stack bottom down to the shunt row
    # fuse and VBAT
    sh.add("F101", "Device:Fuse", 54.61, 30.48, rot=90, value="20A", fp=L + "Fuse_10.3x3.2_1032", lcsc="C5220755",
           fields="T")
    sh.wire((XB, 30.48), "F101.1")
    sh.wire("F101.2", (66.04, 30.48))
    sh.power("+BATT", (66.04, 30.48))

    # ---- RVDD and VDD filter
    hR(sh, "R101", "1k", 76.2, 38.1)                     # CELL4 -> BMS_VDD
    sh.wire((XB, 38.1), "R101.1")
    sh.wire("R101.2", (119.38, 38.1))
    decap(sh, "C101", "1uF", 99.06, 38.1, gnd="-BATT")
    sh.label("BMS_VDD", (119.38, 38.1))
    sh.power("FLAG", (109.22, 38.1))

    # ---- sense inputs: RIN, CIN ladder, channels to the IC
    UX, UY = 139.7, 113.03
    sh.add("U101", L + "BQ77915", UX, UY, value="BQ7791501", fp="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
           lcsc="C2876947", fields="IC")
    sh.wire((119.38, 38.1), (119.38, UY - 13.97), "U101.1")          # BMS_VDD -> VDD
    rin = [("R102", "CELL4", 114.3, "U101.4"), ("R103", "CELL3", 109.22, "U101.5"),
           ("R104", "CELL2", 104.14, "U101.6"), ("R105", "CELL1", 109.22, "U101.7"),
           ("R106", "BATN", 114.3, "U101.8")]
    for ref, net, xch, pin in rin:
        y = TAPS[net]
        hR(sh, ref, "100R", 76.2, y)
        sh.wire((XB, y), ref + ".1")
        py = sh.P(pin)[1]
        sh.wire(ref + ".2", (xch, y), (xch, py), pin)
    sh.wire("U101.3", (121.92, UY - 8.89), (121.92, sh.P("U101.4")[1]))   # VC5 = VC4
    XC = 88.9
    for ref, top, bot in (("C103", "CELL4", "CELL3"), ("C104", "CELL3", "CELL2"), ("C105", "CELL2", "CELL1")):
        y1, y2 = TAPS[top], TAPS[bot]
        vC(sh, ref, "100nF", XC, (y1 + y2) / 2 - 3.81)
        sh.wire((XC, y1), ref + ".1")
        sh.wire(ref + ".2", (XC, y2))
    vC(sh, "C106", "100nF", XC, 129.54)
    sh.wire((XC, TAPS["CELL1"]), "C106.1")
    sh.wire("C106.2", (XC, 139.7))
    vC(sh, "C107", "100nF", XC, 142.24)                                   # pin 1 (BATN) on top
    sh.wire((XC, 139.7), "C107.1")
    sh.wire("C107.2", (XC, TAPS["BATN"]))
    sh.wire((XC, 139.7), (93.98, 139.7))
    flag_bat(sh, (93.98, 139.7))

    # ---- left lower pins: VSS, SRP, SRN, DSG
    for pin, name in (("U101.10", "SRP_F"), ("U101.11", "SRN_F"), ("U101.12", "DSG_DRV")):
        sh.label(name, sh.stub(pin, -5.08, 0), 180)
    p = sh.stub("U101.9", -2.54, 0)
    sh.power("-BATT", p, rot=90)
    # AVDD -> label, cap on the right with CCFG
    sh.label("BMS_AVDD", sh.stub("U101.2", -2.54, 0), 180)

    # ---- right side
    RX = UX + 12.7
    sh.wire("U101.24", (RX + 5.08, sh.P("U101.24")[1]), (RX + 5.08, sh.P("U101.23")[1]), "U101.23")
    sh.power("-BATT", (RX + 5.08, sh.P("U101.24")[1]), rot=270)
    hR(sh, "R107", "10k", RX + 2.54, sh.P("U101.22")[1], flip=True)    # PRES pull-up to BMS_VDD
    sh.wire("U101.22", "R107.2")
    sh.label("BMS_VDD", sh.stub("R107.1", 2.54, 0))
    sh.nc("U101.21")
    sh.nc("U101.15")
    p = sh.stub("U101.20", 50.8, 0)                                     # CCFG -> AVDD (4-cell)
    sh.label("BMS_AVDD", p)
    vC(sh, "C102", "1uF", p[0] - 2.54, p[1])
    sh.power("-BATT", "C102.2", rot=180)
    yv, yt = sh.P("U101.19")[1], sh.P("U101.18")[1]
    hR(sh, "R108", "10k", RX + 5.08, yv)                                # VTB -> TS
    sh.wire("U101.19", "R108.1")
    sh.wire("R108.2", (RX + 12.7, yt))
    sh.wire("U101.18", (RX + 38.1, yt))
    NTC(sh, "RT101", RX + 38.1, yt + 3.81)
    sh.power("-BATT", "RT101.2", rot=180)
    for ref, val, pin, xl in (("R109", "100k", "U101.17", RX + 20.32), ("R110", "10k", "U101.16", RX + 5.08)):
        y = sh.P(pin)[1]
        hR(sh, ref, val, xl, y, fields="B")
        sh.wire(pin, ref + ".1")
        sh.power("-BATT", sh.stub(ref + ".2", 2.54, 0), rot=270)
    sh.label("LD", sh.stub("U101.14", 5.08, 0))
    sh.label("CHG_DRV", sh.stub("U101.13", 5.08, 0))

    # ---- shunt, sense filter, FETs (bottom row y = 185.42)
    YB = 185.42
    hR(sh, "R111", "2mR", 101.6, YB)
    sh.wire((XB, YB), "R111.1")
    T("Kelvin-route SRP/SRN to the shunt pads", 96.52, 180.34)
    sh.add("Q101", L + "NMOS_DFN8", 132.08, YB + 2.54, rot=90, mirror="y", value="AON6512",
           fp=L + "PDFN-8_5x6_AON6512", lcsc="C485679", fields=((128.27, 176.53, None), (128.27, 179.07, None)))
    sh.add("Q102", L + "NMOS_DFN8", 152.4, YB + 2.54, rot=90, value="AON6512",
           fp=L + "PDFN-8_5x6_AON6512", lcsc="C485679", fields=((156.21, 176.53, None), (156.21, 179.07, None)))
    sh.wire("R111.2", "Q101.1")
    sh.wire("Q101.5", "Q102.5")
    sh.wire("Q102.1", (175.26, YB))
    sh.power("GND", (175.26, YB))
    sh.power("FLAG", (167.64, YB))
    T("DSG", 129.54, 182.88)
    T("CHG", 149.86, 182.88)
    # gate networks
    gq1, gq2 = sh.P("Q101.4"), sh.P("Q102.4")
    vR(sh, "R114", "4.7k", gq1[0], gq1[1], flip=True)                   # pin 2 (gate) on top
    sh.label("DSG_DRV", sh.stub("R114.1", 0, 2.54), 270)
    vR(sh, "R115", "1M", gq1[0] - 10.16, YB, flip=True)                 # SNS_N (pin 2) on top
    sh.wire(gq1, "R115.1")
    vR(sh, "R116", "1k", gq2[0], gq2[1], flip=True)
    sh.label("CHG_DRV", sh.stub("R116.1", 0, 2.54), 270)
    vR(sh, "R117", "1M", gq2[0] + 10.16, gq2[1])
    sh.wire(gq2, "R117.1")
    sh.power("GND", "R117.2")
    vR(sh, "R118", "470k", 175.26, YB + 7.62, flip=True)                # LD -> PACK-
    sh.wire((175.26, YB), "R118.2")
    sh.label("LD", sh.stub("R118.1", 0, 2.54), 270)
    # SRP/SRN filter: RS from each shunt pad, caps
    xs = 101.6
    vR(sh, "R112", "100R", xs, YB + 7.62)                               # BATN (pin 1) on top
    sh.wire((xs, YB), "R112.1")
    vR(sh, "R113", "100R", xs + 10.16, YB + 7.62)
    sh.wire((xs + 10.16, YB), "R113.1")
    yf = YB + 17.78
    sh.wire("R112.2", (xs, yf))
    sh.wire("R113.2", (xs + 10.16, yf))
    hC(sh, "C108", "100nF", xs + 1.27, yf + 7.62)
    sh.wire((xs, yf), (xs, yf + 7.62), "C108.1")
    sh.wire("C108.2", (xs + 10.16, yf + 7.62), (xs + 10.16, yf))
    sh.label("SRP_F", sh.stub((xs, yf), -5.08, 0), 180)
    sh.label("SRN_F", sh.stub((xs + 10.16, yf), 5.08, 0))
    vC(sh, "C109", "100nF", xs - 10.16, yf + 7.62)
    sh.wire((xs, yf + 7.62), (xs - 10.16, yf + 7.62))
    flag_bat(sh, "C109.2")
    vC(sh, "C110", "100nF", xs + 20.32, yf + 7.62)
    sh.wire((xs + 10.16, yf + 7.62), (xs + 20.32, yf + 7.62))
    flag_bat(sh, "C110.2")
    sh.power("FLAG", (XB, 172.72))
    sh.wire((XB, 165.1), (40.64, 165.1))
    sh.power("-BATT", (40.64, 165.1), rot=180)
    sh.power("FLAG", (66.04, 30.48))
    return sh


# ============================================================================ USB-C port (A = 2xx, B = 3xx)
def port_sheet(prj, n, sfx, addr_hi, page):
    sh = prj.sheet("port_%s.kicad_sch" % sfx.lower(), "Port %s" % sfx, page)
    T = sh.text

    def r(k):
        return "%d%02d" % (n, k)
    L3, SCL, SDA, INT = "LDO3V3_" + sfx, "I2CC_SCL_" + sfx, "I2CC_SDA_" + sfx, "CHG_INT_" + sfx
    REGN = "REGN_" + sfx
    T("USB-C port %s: TPS25751D PD controller + BQ25798 buck-boost charger (DRP, 45 W out / 66 W in)" % sfx,
      20.32, 20.32, 2, True)
    T("TPS25751D I2Ct address %s (ADCIN1 = %s, ADCIN2 = GND: SafeMode dead-battery config, patch from EEPROM)."
      % ("0x20" if addr_hi else "0x21", "LDO_3V3" if addr_hi else "GND"), 20.32, 24.13)
    T("BQ25798: PROG 27k = 4S / 750 kHz (2.2 uH).  The PD controller programs it over I2Cc (no MCU).", 20.32, 27.94)
    J, U, Q, E = "J" + r(1), "U" + r(1), "U" + r(3), "U" + r(2)

    # ---------------------------------------------------------------- connector, VBUS, CC
    sh.add(J, "Connector:USB_C_Receptacle_USB2.0_16P", 38.1, 109.22, value="TYPE-C-31-M-12",
           fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", lcsc="C165948", fields="IC")
    sh.wire(J + ".SH", J + ".A1")
    sh.power("GND", sh.stub(J + ".A1", 0, 2.54))
    sh.nc(J + ".A8")
    sh.nc(J + ".B8")
    sh.wire(J + ".A7", (58.42, 106.68), (58.42, 109.22), J + ".B7")
    sh.label("DM_" + sfx, (58.42, 106.68))
    sh.wire(J + ".A6", (58.42, 111.76), (58.42, 114.3), J + ".B6")
    sh.label("DP_" + sfx, (58.42, 114.3))
    sh.add(U, "Interface_USB:TPS25751D", 139.7, 109.22, value="TPS25751DREF",
           fp=L + "Texas_REF0038A_WQFN-38-2EP_6x4mm_P0.4_Via0.3", lcsc="C30169739", fields="IC")
    sh.add(Q, L + "BQ25798", 248.92, 104.14, value="BQ25798RQM",
           fp="Package_DFN_QFN:Texas_RQM0029A_VQFN-29_4x4mm_P0.4mm", lcsc="C2876593", fields="IC")
    sh.wire(J + ".A4", (55.88, 93.98), (55.88, 76.2), (111.76, 76.2), (111.76, 91.44), U + ".23")
    sh.wire((111.76, 91.44), (111.76, 93.98), U + ".32")
    sh.label("VBUS_" + sfx, (96.52, 76.2))
    sh.add("D" + r(1), "Power_Protection:TVS2200DRV", 68.58, 83.82, value="TVS2200",
           fp="Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm", lcsc="C523793", fields="R")
    sh.power("GND", "D%s.1" % r(1))
    decap(sh, "C" + r(1), "10uF 50V", 81.28, 76.2)
    sh.wire(J + ".A5", U + ".28")
    sh.wire(J + ".B5", U + ".29")
    vC(sh, "C" + r(6), "330pF", 93.98, 91.44, flip=True)              # CC1 (pin 1) at the bottom
    sh.power("GND", "C%s.2" % r(6), rot=180)
    decap(sh, "C" + r(7), "330pF", 101.6, 101.6)
    sh.label("DP_" + sfx, sh.stub(U + ".26", -5.08, 0), 180)
    sh.label("DM_" + sfx, sh.stub(U + ".27", -5.08, 0), 180)
    # VIN_3V3
    sh.wire(U + ".38", (121.92, 86.36), (121.92, 71.12))
    sh.power("+3V3", (121.92, 71.12))
    sh.wire((121.92, 73.66), (116.84, 73.66))
    decap(sh, "C" + r(2), "10uF", 116.84, 73.66)
    # unused GPIOs: 10k arrays to GND
    for rn, cy in (("RN" + r(1), 111.76), ("RN" + r(2), 127.0)):
        sh.add(rn, "Device:R_Pack04", 119.38, cy, rot=270, value="4x10k", fp="Resistor_SMD:R_Array_Convex_4x0603",
               lcsc="C29718", fields="L")
    sh.wire("RN%s.1" % r(1), "RN%s.4" % r(1))
    sh.power("GND", sh.stub("RN%s.4" % r(1), -2.54, 0), rot=270)
    sh.wire("RN%s.1" % r(2), "RN%s.3" % r(2))
    sh.power("GND", sh.stub("RN%s.3" % r(2), -2.54, 0), rot=270)
    sh.nc("RN%s.4" % r(2))
    sh.nc("RN%s.5" % r(2))

    # ---------------------------------------------------------------- PD controller right side
    sh.wire(U + ".20", (160.02, 86.36), (160.02, 68.58), (233.68, 68.58), (233.68, 76.2), Q + ".2")
    sh.wire((233.68, 76.2), (233.68, 81.28), Q + ".9")
    sh.wire((233.68, 81.28), (233.68, 88.9), Q + ".8")
    sh.label("PPHV_" + sfx, (215.9, 68.58))
    for k, x in ((8, 175.26), (9, 182.88), (10, 190.5), (11, 198.12)):
        decap(sh, "C" + r(k), "10uF 50V", x, 68.58)
    decap(sh, "C" + r(12), "100nF", 205.74, 68.58)
    sh.wire(U + ".34", (172.72, 88.9))
    sh.power("+5V", (167.64, 88.9))
    decap(sh, "C" + r(5), "22uF 25V", 172.72, 88.9)
    sh.wire(U + ".[15,30]", (157.48, 93.98), (157.48, 96.52), U + ".40")
    sh.wire(U + ".4", (162.56, 101.6))
    vC(sh, "C" + r(4), "10uF", 162.56, 93.98, flip=True)                # LDO_1V5 (pin 1) at the bottom
    sh.power("GND", "C%s.2" % r(4), rot=180)
    sh.wire(U + ".1", (172.72, 104.14))
    sh.label(L3, (172.72, 104.14))
    decap(sh, "C" + r(3), "10uF", 167.64, 104.14)
    if addr_hi:
        sh.wire(U + ".2", (157.48, 109.22), (157.48, 104.14))
        sh.power("GND", sh.stub(U + ".3", 2.54, 0))
    else:
        sh.wire(U + ".2", (157.48, 109.22), (157.48, 111.76), U + ".3")
        sh.power("GND", (157.48, 111.76))
    sh.label(SCL, sh.stub(U + ".17", 5.08, 0))
    sh.label(SDA, sh.stub(U + ".16", 5.08, 0))
    sh.label(INT, sh.stub(U + ".18", 5.08, 0))
    sh.glabel("PD_SCL", sh.stub(U + ".9", 5.08, 0))
    sh.glabel("PD_SDA", sh.stub(U + ".8", 5.08, 0))
    sh.glabel("PD_IRQ", sh.stub(U + ".10", 5.08, 0))
    sh.power("GND", U + ".[11,12,14,31,39]")

    # ---------------------------------------------------------------- EEPROM, jumper, programming header, pull-ups
    T("Config EEPROM (>= 36 kB).  Program through J%s: TPS25751 idles on I2Cc while the EEPROM is blank."
      % r(2), 160.02, 139.7)
    T("Re-flash: cut JP%s, fit a shunt on J%s 1-2; pull the shunt + press PD RESET to flash." % (r(1), r(2)),
      160.02, 142.24)
    sh.add(E, "Memory_EEPROM:24LC512", 190.5, 167.64, value="CAT24C512WI", fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           lcsc="C79986", fields="L")
    sh.wire(E + ".1", (177.8, 165.1), (177.8, 170.18), E + ".3")
    sh.wire(E + ".2", (177.8, 167.64))
    sh.power("GND", (177.8, 170.18))
    sh.power("GND", sh.stub(E + ".7", 2.54, 0))
    sh.power("GND", E + ".4")
    sh.label(SDA, sh.stub(E + ".5", 5.08, 0))
    sh.label(SCL, sh.stub(E + ".6", 5.08, 0))
    sh.wire(E + ".8", (190.5, 149.86), (220.98, 149.86))
    sh.add("JP" + r(1), "Jumper:SolderJumper_2_Bridged", 182.88, 149.86, value="EE_PWR",
           fp="Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm", fields="T")
    sh.wire("JP%s.2" % r(1), (190.5, 149.86))
    sh.label(L3, sh.stub("JP%s.1" % r(1), -2.54, 0), 180)
    decap(sh, "C" + r(13), "100nF", 198.12, 149.86)
    sh.add("J" + r(2), "Connector_Generic:Conn_01x05", 226.06, 154.94, value="EE_PROG",
           fp="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", fields="R", dnp=True)
    sh.label(L3, sh.stub("J%s.2" % r(2), -2.54, 0), 180)
    sh.label(SCL, sh.stub("J%s.3" % r(2), -2.54, 0), 180)
    sh.label(SDA, sh.stub("J%s.4" % r(2), -2.54, 0), 180)
    sh.power("GND", sh.stub("J%s.5" % r(2), -2.54, 0), rot=270)
    T("1 EE_VCC  2 3V3  3 SCL  4 SDA  5 GND", 233.68, 162.56)
    sh.wire((243.84, 152.4), (259.08, 152.4))
    sh.label(L3, (243.84, 152.4), 180)
    for k, x, net in ((1, 248.92, SCL), (2, 254.0, SDA), (3, 259.08, INT)):
        vR(sh, "R" + r(k), "2.2k" if k < 3 else "10k", x, 152.4, flip=True)    # pin 2 (LDO_3V3) on top
        sh.label(net, sh.stub("R%s.1" % r(k), 0, 2.54), 270)

    # ---------------------------------------------------------------- BQ25798
    sh.power("GND", sh.stub(Q + ".11", -2.54, 0))
    sh.power("GND", sh.stub(Q + ".10", -2.54, 0))
    sh.nc(Q + ".6")
    sh.nc(Q + ".7")
    sh.nc(Q + ".12")
    sh.label(SCL, sh.stub(Q + ".14", -5.08, 0), 180)
    sh.label(SDA, sh.stub(Q + ".15", -5.08, 0), 180)
    sh.label(INT, sh.stub(Q + ".21", -5.08, 0), 180)
    sh.power("GND", sh.stub(Q + ".13", -2.54, 0))
    sh.label(REGN, sh.stub(Q + ".17", -5.08, 0), 180)
    hR(sh, "R" + r(7), "27k", 228.6, 127.0, flip=True)                  # PROG (pin 1) on the right
    sh.wire("R%s.1" % r(7), Q + ".20")
    sh.power("GND", sh.stub("R%s.2" % r(7), -2.54, 0))
    sh.wire(Q + ".16", (213.36, 132.08))
    hR(sh, "R" + r(5), "5.23k", 205.74, 132.08)
    sh.wire("R%s.1" % r(5), (200.66, 132.08))
    sh.label(REGN, (200.66, 132.08), 180)
    decap(sh, "C" + r(29), "4.7uF 25V", 200.66, 132.08)
    vR(sh, "R" + r(6), "30.1k", 233.68, 132.08)
    sh.power("GND", "R%s.2" % r(6))
    NTC(sh, "RT" + r(1), 223.52, 132.08 + 3.81)
    sh.power("GND", "RT%s.2" % r(1))
    sh.power("GND", Q + ".27")
    # right side
    sh.wire(Q + ".29", (320.04, 76.2))
    sh.label("PMID_" + sfx, (320.04, 76.2))
    for k, x in ((14, 289.56), (15, 297.18), (16, 304.8)):
        decap(sh, "C" + r(k), "10uF 50V", x, 76.2)
    decap(sh, "C" + r(17), "100nF", 312.42, 76.2)
    sh.wire(Q + ".4", (264.16, 81.28), (264.16, 78.74), (269.24, 78.74))
    vC(sh, "C" + r(18), "47nF", 269.24, 78.74, fields="L")
    sh.wire(Q + ".28", (274.32, 86.36))
    sh.add("L" + r(1), "Device:L", 274.32, 91.44, value="2.2uH", fp=L + "L_7.0x6.6_MWSA0603S", lcsc="C408445")
    sh.wire((274.32, 86.36), "L%s.1" % r(1))
    sh.wire("L%s.2" % r(1), (274.32, 96.52), Q + ".26")
    sh.wire(Q + ".19", (264.16, 101.6), (264.16, 104.14), (269.24, 104.14))
    vC(sh, "C" + r(19), "47nF", 269.24, 96.52, flip=True, fields="L")    # pin 2 (SW2) on top
    sh.wire(Q + ".1", (266.7, 106.68))
    sh.add("D" + r(2), "Device:LED", 270.51, 106.68, value="CHG", fp="LED_SMD:LED_0603_1608Metric", lcsc="C2286",
           fields="B")
    hR(sh, "R" + r(8), "1k", 276.86, 106.68, flip=True, fields="B")
    sh.wire("D%s.2" % r(2), "R%s.2" % r(8))
    sh.power("+3V3", "R%s.1" % r(8))
    sh.label(REGN, sh.stub(Q + ".5", 5.08, 0))
    sh.wire(Q + ".25", (340.36, 116.84))
    sh.label("SYS_" + sfx, (340.36, 116.84))
    for k, x in ((20, 294.64), (21, 302.26), (22, 309.88), (23, 317.5), (24, 325.12)):
        decap(sh, "C" + r(k), "10uF 50V", x, 116.84)
    decap(sh, "C" + r(25), "100nF", 332.74, 116.84)
    sh.wire(Q + ".22", (279.4, 121.92), (279.4, 144.78), (302.26, 144.78))
    sh.power("+BATT", (279.4, 121.92))
    for k, x, v in ((26, 287.02, "10uF 50V"), (27, 294.64, "10uF 50V"), (28, 302.26, "100nF")):
        decap(sh, "C" + r(k), v, x, 144.78)
    hC(sh, "C" + r(30), "1nF", 261.62, 127.0, fields="B")
    sh.wire(Q + ".24", "C%s.1" % r(30))
    sh.power("GND", "C%s.2" % r(30))
    hR(sh, "R" + r(4), "100R", 271.78, 132.08, fields="B")
    sh.wire(Q + ".18", "R%s.1" % r(4))
    sh.power("FLAG", (233.68, 68.58))
    sh.power("FLAG", "JP%s.2" % r(1))
    return sh


# ============================================================================ system: 5 V, 3.3 V, host header, fuel gauge
def system_sheet(prj):
    sh = prj.sheet("system.kicad_sch", "System", 5)
    T = sh.text
    T("5 V PP5V rail (both PD controllers, 5 V source + VCONN), 3.3 V VIN_3V3, PD host header, fuel gauge",
      20.32, 20.32, 2, True)
    T("TPS54531 from TIDA-050047 fig 2-6 (feedback 10.5k/1.96k -> 5.09 V), all-ceramic output.", 20.32, 24.13)

    # ---------------------------------------------------------------- 5 V buck
    sh.add("U401", L + "TPS54531", 101.6, 101.6, value="TPS54531DDA", fp="Package_SO:TI_SO-PowerPAD-8_ThermalVias",
           lcsc="C50605", fields="IC")
    sh.power("+BATT", (55.88, 88.9))
    sh.wire((55.88, 88.9), (86.36, 88.9), (86.36, 96.52), "U401.2")
    decap(sh, "C401", "10uF 50V", 60.96, 88.9)
    decap(sh, "C402", "10uF 50V", 68.58, 88.9)
    decap(sh, "C403", "10nF", 76.2, 88.9)
    vR(sh, "R401", "665k", 81.28, 88.9)
    sh.wire("R401.2", (81.28, 101.6), "U401.3")
    vR(sh, "R402", "130k", 81.28, 101.6)
    sh.power("GND", "R402.2")
    sh.wire("U401.4", (86.36, 104.14))
    decap(sh, "C404", "10nF", 86.36, 104.14)
    sh.power("GND", "U401.7")
    sh.wire("U401.1", (116.84, 96.52), (116.84, 91.44), (119.38, 91.44))
    vC(sh, "C405", "100nF", 119.38, 91.44, fields="L")
    sh.wire("U401.8", (127.0, 99.06))
    sh.add("D401", "Device:D_Schottky", 124.46, 102.87, rot=270, value="SS54", fp="Diode_SMD:D_SMA", lcsc="C22452",
           fields="L")
    sh.power("GND", "D401.2")
    sh.add("L401", "Device:L", 130.81, 99.06, rot=90, value="4.7uH", fp=L + "L_11x10_TMPA1004S", lcsc="C357112",
           fields="T")
    sh.wire("L401.2", (175.26, 99.06))
    sh.power("+5V", (137.16, 99.06))
    sh.power("FLAG", (139.7, 99.06))
    for ref, x in (("C408", 144.78), ("C409", 152.4), ("C410", 160.02), ("C411", 167.64)):
        decap(sh, ref, "47uF 10V", x, 99.06)
    vR(sh, "R403", "10.5k", 175.26, 99.06)
    vR(sh, "R404", "1.96k", 175.26, 106.68)
    sh.power("GND", "R404.2")
    sh.label("FB5", sh.stub((175.26, 106.68), 5.08, 0))
    sh.label("FB5", sh.stub("U401.5", 5.08, 0))
    sh.label("COMP5", sh.stub("U401.6", 5.08, 0))
    sh.wire((124.46, 121.92), (137.16, 121.92))
    sh.label("COMP5", (124.46, 121.92), 180)
    vR(sh, "R405", "37.4k", 129.54, 121.92)
    vC(sh, "C406", "2.2nF", 129.54, 129.54)
    sh.power("GND", "C406.2")
    decap(sh, "C407", "22pF", 137.16, 121.92)

    # ---------------------------------------------------------------- 3.3 V LDO + PD reset button
    sh.add("U402", "Regulator_Linear:ME6211C33M5", 210.82, 96.52, value="ME6211C33M5G", fp="Package_TO_SOT_SMD:SOT-23-5",
           lcsc="C82942", fields="IC")
    sh.wire((185.42, 93.98), "U402.1")
    sh.power("+5V", (185.42, 93.98))
    decap(sh, "C412", "1uF", 187.96, 93.98)
    vR(sh, "R406", "100k", 193.04, 93.98)
    sh.wire("R406.2", (200.66, 101.6), (200.66, 96.52), "U402.3")
    sh.add("SW401", L + "SW_Push_14", 200.66, 106.68, rot=270, value="PD_RESET", fp=L + "SW_TS-1187A_5.1x5.1",
           lcsc="C318884", fields="R")
    sh.power("GND", "SW401.4")
    sh.power("GND", "U402.2")
    sh.nc("U402.4")
    sh.wire("U402.5", (226.06, 93.98))
    sh.power("+3V3", (223.52, 93.98))
    decap(sh, "C413", "1uF", 226.06, 93.98)
    T("PD RESET: holds the 3.3 V rail low -> both TPS25751 reboot (reload EEPROM) when no cable is in.",
      185.42, 119.38)

    # ---------------------------------------------------------------- PD host / I2Ct header
    sh.wire((254.0, 86.36), (287.02, 86.36), (287.02, 96.52))
    sh.power("+3V3", (254.0, 86.36))
    sh.add("J401", "Connector_Generic:Conn_01x05", 299.72, 101.6, value="PD_HOST",
           fp="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", fields="R", dnp=True)
    sh.wire((287.02, 96.52), "J401.1")
    for ref, x, pin, net in (("R407", 264.16, "J401.2", "PD_SCL"), ("R408", 259.08, "J401.3", "PD_SDA"),
                             ("R409", 254.0, "J401.4", "PD_IRQ")):
        vR(sh, ref, "10k", x, 86.36, flip=True)                             # pin 2 (+3V3) on top
        y = sh.P(pin)[1]
        sh.wire(ref + ".1", (x, y), pin)
        sh.glabel(net, (x, y), 180)
    sh.power("GND", sh.stub("J401.5", -2.54, 0))
    T("1 3V3  2 SCL  3 SDA  4 IRQ  5 GND (TI tools / host MCU on I2Ct)", 304.8, 109.22)

    # ---------------------------------------------------------------- fuel gauge
    T("Fuel gauge (press SW402): 1-4 LEDs above 3.09 / 3.40 / 3.61 / 3.81 V per cell (no load)", 38.1, 152.4, 1.5,
      True)
    sh.power("+BATT", (50.8, 160.02))
    sh.add("SW402", L + "SW_Push_14", 58.42, 160.02, value="GAUGE", fp=L + "SW_TS-1187A_5.1x5.1", lcsc="C318884",
           fields="T")
    sh.wire((50.8, 160.02), "SW402.1")
    sh.wire("SW402.4", (228.6, 160.02))
    sh.label("GAUGE_V", (68.58, 160.02))
    sh.power("FLAG", (66.04, 160.02))
    decap(sh, "C414", "100nF", 71.12, 160.02)
    vR(sh, "R410", "4.7k", 78.74, 160.02)
    sh.add("U404", "Reference_Voltage:TL431DBZ", 78.74, 170.18, rot=90, value="TL431B", fp="Package_TO_SOT_SMD:SOT-23",
           lcsc="C41283", fields="L")
    sh.wire("U404.2", (76.2, 167.64), "R410.2")
    sh.power("GND", "U404.3")
    sh.wire("R410.2", (88.9, 167.64))
    chain = [("R411", "1k", 88.9), ("R412", "1k", 101.6), ("R413", "1.5k", 114.3), ("R414", "15k", 127.0)]
    for i, (ref, val, xl) in enumerate(chain):
        hR(sh, ref, val, xl, 167.64)
        if i:
            sh.wire(chain[i - 1][0] + ".2", ref + ".1")
    sh.power("GND", sh.stub("R414.2", 2.54, 0), rot=270)
    # comparators: highest ladder node to the top row so the drops never cross
    rows = [("REF1", 124.46, 182.88, 1, "D402", "R417"), ("REF2", 111.76, 203.2, 2, "D403", "R418"),
            ("REF3", 99.06, 223.52, 4, "D404", "R419"), ("VREF", 83.82, 243.84, 3, "D405", "R420")]
    units = {1: ("5", "4", "2"), 2: ("7", "6", "1"), 4: ("9", "8", "14"), 3: ("11", "10", "13")}
    for i, (name, xn, y, unit, led, rl) in enumerate(rows):
        key = "U403" if unit == 1 else "U403.%d" % unit
        sh.add("U403", "Comparator:LM339", 165.1, y, value="LM339", fp="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
               lcsc="C7948", fields="T", unit=unit)
        plus, minus, out = units[unit]
        sh.wire((xn, 167.64), (xn, y - 2.54), "%s.%s" % (key, plus))
        sh.label("VSENSE_G", sh.stub("%s.%s" % (key, minus), -5.08, 0), 180)
        sh.add(led, "Device:LED", 180.34, y, value="%d/4" % (i + 1), fp="LED_SMD:LED_0603_1608Metric", lcsc="C2290",
               fields="T")
        sh.wire("%s.%s" % (key, out), led + ".1")
        hR(sh, rl, "6.8k", 186.69, y, flip=True)
        sh.wire(led + ".2", rl + ".2")
        sh.wire(rl + ".1", (198.12, y))
    sh.wire((198.12, 160.02), (198.12, 243.84))
    sh.add("U403", "Comparator:LM339", 233.68, 177.8, value="LM339", fp="Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
           lcsc="C7948", fields="R", unit=5)
    sh.wire("U403.5.3", (231.14, 160.02), (228.6, 160.02))
    sh.power("GND", "U403.5.12")
    vR(sh, "R415", "51k", 208.28, 160.02)
    vR(sh, "R416", "10k", 208.28, 167.64)
    sh.power("GND", "R416.2")
    sh.wire((208.28, 167.64), (215.9, 167.64))
    decap(sh, "C415", "100nF", 215.9, 167.64)
    sh.label("VSENSE_G", sh.stub((215.9, 167.64), 5.08, 0))
    # mounting holes
    for i in range(4):
        sh.add("H40%d" % (i + 1), "Mechanical:MountingHole", 330.2 + 10.16 * i, 177.8, value="M3",
               fp="MountingHole:MountingHole_3.2mm_M3", fields="B")
    return sh


# ============================================================================ main
def main(only=None):
    prj = Project(PRJ_NAME, ROOT_UUID)
    sheets = [battery_sheet(prj), port_sheet(prj, 2, "A", True, 3), port_sheet(prj, 3, "B", False, 4),
              system_sheet(prj)]
    tb = lambda t: title_block(prj, "PowerbankV2 - " + t, DATE, REV,
                               ["2x USB-C PD DRP (TPS25751D + BQ25798), 45 W out / 66 W in per port",
                                "4S2P 18650, BQ7791501 protection, JLC PCBA"])
    for sh in sheets:
        write_sheet(sh, tb(sh.title))
        report(sh)
    root = Project.sheet(prj, "_root_", "root", 1)
    prj.sheets.pop()
    root.text("PowerbankV2", 25.4, 30.48, 3, True)
    blocks = [(sh, 50.8 + 76.2 * i, 60.96, 63.5, 25.4, sh.title) for i, sh in enumerate(sheets)]
    write_root(prj, "V2.kicad_sch", tb("Overview"), blocks, root)


if __name__ == "__main__":
    main()
