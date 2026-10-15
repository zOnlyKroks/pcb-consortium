"""Generate the NetworkSwitchV1 schematic (root + 4 sheets) with explicit placement and real wires.

Global labels are used only for nets that cross sheets (port LEDs, SMI, management link, PoE centre taps).
Run check_netlist.py afterwards; it compares the KiCad netlist against design.py.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schlib import Project, write_sheet, write_root, report, title_block

PRJ_NAME = "NetworkSwitchV1"
ROOT_UUID = "3c5e8b1a-2f4d-4e6a-9b7c-1d2e3f4a5b6c"
DATE, REV = "2026-10-14", "1"
L = "NetworkSwitchV1:"

R0603, R1206 = "Resistor_SMD:R_0603_1608Metric", "Resistor_SMD:R_1206_3216Metric"
C0603, C0805, C1206, C1210 = ("Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric",
                              "Capacitor_SMD:C_1206_3216Metric", "Capacitor_SMD:C_1210_3225Metric")
RES = {"10k": "C25804", "4.7k": "C23162", "1k": "C21190", "33k": "C4216", "39k": "C23153", "100k": "C25803",
       "75R": "C4275", "510R": "C23193", "10R": "C22859", "1M": "C22935", "4.3k": "C23159", "56k": "C23206",
       "510k": "C23192", "2.49k": "C22908", "24.9k": "C25962", "90.9R": "C23130", "0.43R": "C24965"}
CAP = {"100nF": (C0603, "C14663"), "1uF": (C0603, "C15849"), "10uF": (C0603, "C19702"), "10uF 25V": (C0805, "C15850"),
       "22uF 25V": (C0805, "C45783"), "1nF": (C0603, "C1588"), "10nF": (C0603, "C57112"), "18pF": (C0603, "C1647"),
       "100nF 100V": (C0805, "C28233"), "10nF 100V": (C0603, "C107059"), "2.2uF 100V": (C1210, "C55151"),
       "1nF 2kV": (C1206, "C9196")}


def R(sh, ref, val, x, y, rot=0, fields="R", **kw):
    fp = R1206 if val == "0.43R" else R0603
    return sh.add(ref, "Device:R", x, y, rot, value=val, fp=fp, lcsc=RES[val], fields=fields, **kw)


def C(sh, ref, val, x, y, rot=0, fields="R", **kw):
    fp, lcsc = CAP[val]
    return sh.add(ref, "Device:C", x, y, rot, value=val, fp=fp, lcsc=lcsc, fields=fields, **kw)


def vline(x, y1, y2):
    return (x, y1), (x, y2)


# ============================================================================ power
def power_sheet(prj):
    sh = prj.sheet("power.kicad_sch", "Power", 2)
    T = sh.text

    # ---------------------------------------------------------------- port 1 Bob Smith (DC blocked for PoE)
    T("Port 1 Bob Smith termination", 15.24, 40.64, 2, True)
    T("(100 nF blocks the PoE DC between centre taps)", 15.24, 44.45)
    ys = [53.34, 63.5, 73.66, 83.82]
    for n, y in enumerate(ys, 1):
        sh.glabel("POE_CT%d" % n, (20.32, y), 180)
        R(sh, "R15%d" % n, "75R", 29.21, y, rot=90, fields="T")
        sh.wire((20.32, y), "R15%d.1" % n)
        C(sh, "C15%d" % n, "100nF 100V", 41.91, y, rot=90, fields=((41.91, y - 4.445, None), (41.91, y + 3.81, None)))
        sh.wire("R15%d.2" % n, "C15%d.1" % n)
        sh.wire("C15%d.2" % n, (50.8, y))
    sh.wire((50.8, ys[0]), (50.8, 88.9))
    C(sh, "C155", "1nF 2kV", 50.8, 92.71)
    sh.power("CHASSIS", "C155.2")

    # ---------------------------------------------------------------- bridges, TVS, PD controller
    T("802.3af PoE PD (class 3), isolated 12 V flyback", 76.2, 40.64, 2, True)
    T("any polarity, data pairs (A/B) or spare pairs (C/D)", 76.2, 44.45)
    for ref, x, a, b in (("BR101", 88.9, "POE_CT1", "POE_CT2"), ("BR102", 144.78, "POE_CT3", "POE_CT4")):
        sh.add(ref, "Device:D_Bridge_+-AA", x, 83.82, rot=90, value="MB10S", fp=L + "MBS_L4.7-W3.8-P2.40-LS7.0-TL",
               lcsc="C2488", fields=((x - 6.35, 71.12, "right"), (x - 6.35, 73.66, "right")))
        sh.glabel(a, sh.stub(ref + ".3", -5.08, 0), 180)
        sh.glabel(b, sh.stub(ref + ".4", 5.08, 0), 0)
        sh.wire(ref + ".1", (x, 60.96))
        sh.wire(ref + ".2", (x, 106.68))
    VDD_Y, VSS_Y = 60.96, 106.68
    sh.wire((88.9, VDD_Y), (309.88, VDD_Y))             # POE_VDD bus
    sh.wire((88.9, VSS_Y), (223.52, VSS_Y))             # POE_VSS bus
    sh.power("FLAG", (165.1, VDD_Y))
    sh.power("FLAG", (165.1, VSS_Y))
    T("POE_VDD", 167.64, 59.69)
    T("POE_VSS", 167.64, 105.41)
    sh.add("D101", "Device:D_Zener", 180.34, 83.82, rot=270, value="SMAJ58A", fp="Diode_SMD:D_SMA", lcsc="C123816",
           fields="L")
    sh.wire("D101.1", (180.34, VDD_Y))
    sh.wire("D101.2", (180.34, VSS_Y))
    C(sh, "C101", "100nF 100V", 190.5, 83.82)
    sh.wire("C101.1", (190.5, VDD_Y))
    sh.wire("C101.2", (190.5, VSS_Y))

    sh.add("U101", L + "TPS23753A", 241.3, 96.52, value="TPS23753APWR", fp=L + "TSSOP-14_L5.0-W4.4-P0.65-LS6.4-BL",
           lcsc="C92115", fields=((241.3, 81.28, None), (241.3, 83.82, None)))
    sh.wire("U101.9", (218.44, 88.9), (218.44, VDD_Y))
    sh.wire("U101.8", (218.44, 91.44), (218.44, 88.9))
    R(sh, "R101", "24.9k", 208.28, 64.77, fields="L")
    sh.wire("R101.1", (208.28, VDD_Y))
    sh.wire("R101.2", (208.28, 96.52), "U101.10")
    R(sh, "R102", "90.9R", 213.36, 102.87, fields="L")
    sh.wire("U101.11", "R102.1")
    sh.wire("R102.2", (213.36, VSS_Y))
    sh.wire("U101.12", (220.98, 101.6))
    sh.power("RTN", (220.98, 101.6))
    T("class 3 (12.95 W max)", 186.69, 113.03)
    sh.power("FLAG", (203.2, 124.46))
    sh.wire((203.2, 124.46), (213.36, 124.46))
    sh.power("RTN", (213.36, 124.46))

    # ---------------------------------------------------------------- flyback power stage
    R(sh, "R106", "10R", 266.7, 88.9, rot=90, fields="T")
    sh.wire("U101.5", "R106.1")
    sh.add("Q101", "Transistor_FET:Q_NMOS_GDS", 297.18, 88.9, value="IRFR220N", fp=L + "TO-252-2_L6.6-W6.1-P4.57-LS9.9-BR-CW",
           lcsc="C22365390", fields=((289.56, 81.28, "right"), (289.56, 83.82, "right")), extra={"Rating": "200 V 8 A"})
    sh.wire("R106.2", "Q101.1")
    sh.wire("Q101.3", (299.72, 96.52))
    R(sh, "R107", "0.43R", 299.72, 100.33, fields="R")
    sh.power("RTN", "R107.2")
    sh.wire("U101.3", (289.56, 93.98), (289.56, 96.52), (299.72, 96.52))
    sh.add("T101", L + "EP1322S-10", 320.04, 86.36, value="EP1322S-10", fp=L + "XFMR-SMD_EP1322S-10", lcsc="C37328796",
           fields=((320.04, 72.39, None), (320.04, 100.33, None)))
    sh.wire("Q101.2", "T101.4")
    sh.wire("T101.3", (309.88, VDD_Y))
    # primary clamp: drain -> US1M -> SMAJ58A -> POE_VDD
    sh.add("D103", "Device:D_Zener", 304.8, 66.04, rot=90, value="SMAJ58A", fp="Diode_SMD:D_SMA", lcsc="C123816",
           fields="L")
    sh.wire((304.8, VDD_Y), "D103.2")
    sh.add("D102", "Device:D", 304.8, 73.66, rot=270, value="US1M", fp="Diode_SMD:D_SMA", lcsc="C412437", fields="L")
    sh.wire("D102.2", (304.8, 83.82))
    # input capacitors on the converter side of the hotswap switch
    for ref, x in (("C106", 271.78), ("C107", 276.86)):
        C(sh, ref, "2.2uF 100V", x, 64.77, fields="L" if ref == "C106" else "R")
        sh.wire((x, VDD_Y), ref + ".1")
        sh.power("RTN", ref + ".2")
    # aux winding -> VC
    sh.wire("T101.2", (307.34, 88.9))
    sh.power("RTN", (307.34, 88.9))
    sh.wire("T101.1", (307.34, 93.98), (307.34, 114.3), (304.8, 114.3))
    sh.add("D104", "Device:D", 300.99, 114.3, value="1N4148W", fp="Diode_SMD:D_SOD-123", lcsc="C81598", fields="B")
    sh.wire("D104.2", (304.8, 114.3))
    sh.wire("D104.1", (294.64, 114.3))
    R(sh, "R105", "10R", 294.64, 110.49, fields="L")
    sh.wire("R105.2", (294.64, 114.3))
    sh.wire("R105.1", (294.64, 101.6))
    sh.wire("U101.4", (294.64, 101.6))
    C(sh, "C104", "1uF", 264.16, 105.41, fields="R")
    C(sh, "C105", "22uF 25V", 276.86, 105.41, fields="R")
    for c in ("C104", "C105"):
        sh.power("RTN", c + ".2")
    T("VC bias from the aux winding (~13.9 V)", 256.54, 142.24)
    # secondary
    sh.wire("T101.7", (332.74, 81.28))
    sh.power("GND", (332.74, 81.28))
    sh.add("D105", "Device:D_Schottky", 336.55, 91.44, rot=180, value="SS210", fp="Diode_SMD:D_SMA", lcsc="C14996",
           fields="T")
    sh.wire("T101.9", "D105.2")
    sh.wire("D105.1", (386.08, 91.44))
    sh.add("C108", "Device:C_Polarized", 347.98, 95.25, value="100uF 25V", fp="Capacitor_SMD:CP_Elec_6.3x7.7",
           lcsc="C970685", fields="R")
    C(sh, "C109", "22uF 25V", 363.22, 95.25)
    C(sh, "C110", "22uF 25V", 378.46, 95.25)
    for c in ("C108", "C109", "C110"):
        sh.power("GND", c + ".2")
    sh.power("+12V", (386.08, 91.44))
    sh.wire((386.08, 91.44), (396.24, 91.44))
    sh.power("FLAG", (396.24, 91.44))
    T("12.2 V, 1 A max (isolated)", 347.98, 86.36)
    T("isolation barrier 1500 V: T101, U103", 312.42, 57.15)

    # ---------------------------------------------------------------- control pins + feedback
    R(sh, "R103", "56k", 233.68, 115.57, fields="L")
    sh.power("RTN", "R103.2")
    T("~270 kHz", 215.9, 121.92)
    sh.wire("U101.13", "U101.6")
    sh.power("RTN", "U101.6")
    sh.wire("U101.2", (246.38, 116.84))
    C(sh, "C102", "100nF", 246.38, 120.65, fields="L")
    sh.power("RTN", "C102.2")
    R(sh, "R104", "10k", 250.19, 116.84, rot=90, fields="T")
    sh.wire("U101.1", (254.0, 116.84))
    C(sh, "C103", "1nF", 254.0, 120.65, fields="R")
    sh.power("RTN", "C103.2")
    sh.add("U103", "Isolator:LTV-817S", 271.78, 129.54, mirror="y", value="LTV-817S",
           fp=L + "OPTO-SMD-4_L4.6-W6.5-P2.54-LS10.3-BL", lcsc="C109227",
           fields=((271.78, 122.555, None), (271.78, 137.16, None)))
    sh.wire((254.0, 116.84), (264.16, 116.84), "U103.4")
    sh.wire("U103.3", (261.62, 132.08))
    sh.power("RTN", (261.62, 132.08))
    sh.power("+12V", (314.96, 114.3))
    R(sh, "R110", "1k", 314.96, 118.11, fields="L")
    sh.wire("R110.2", (314.96, 127.0), "U103.1")
    sh.power("+12V", (322.58, 114.3))
    R(sh, "R112", "4.7k", 322.58, 118.11, fields="R")
    sh.wire("R112.2", (322.58, 132.08))
    sh.wire("U103.2", (330.2, 132.08))
    sh.add("U102", L + "CJ431", 330.2, 137.16, rot=90, value="CJ431", fp=L + "SOT-23-3_L2.9-W1.6-P1.90-LS2.8-BR",
           lcsc="C3113", fields=((332.74, 135.89, "left"), (332.74, 138.43, "left")))
    sh.wire((330.2, 132.08), "U102.2")
    sh.power("GND", "U102.3")
    R(sh, "R113", "10k", 320.04, 135.89, fields="L")
    C(sh, "C111", "10nF", 320.04, 143.51, fields="L")
    sh.wire("R113.2", "C111.1")
    sh.wire("C111.2", (327.66, 147.32), "U102.1")
    sh.wire((327.66, 147.32), (345.44, 147.32))
    R(sh, "R108", "39k", 345.44, 143.51, fields="R")
    sh.power("+12V", "R108.1")
    R(sh, "R109", "10k", 345.44, 151.13, fields="R")
    sh.power("GND", "R109.2")
    T("Vout = 2.495 V x (1 + 39k/10k) = 12.2 V", 299.72, 162.56)
    T("Loop: R113/C111 type-2 + CCTL (C103); verify step response on the bench", 299.72, 166.37)

    # ---------------------------------------------------------------- DC jack
    T("12 V DC input (5.5/2.1 mm, centre +)", 15.24, 175.26, 2, True)
    sh.add("J101", L + "DC-005", 35.56, 190.5, value="DC-005", fp=L + "DC-IN-TH_DC-005-5.5-2.0", lcsc="C16214",
           fields=((33.02, 182.88, None), (33.02, 199.39, None)))
    sh.add("F101", "Device:Polyfuse", 50.8, 187.96, rot=90, value="1.1A 16V", fp="Fuse:Fuse_1206_3216Metric",
           lcsc="C7542961", fields="T")
    sh.wire("J101.4", "F101.1")
    sh.wire("F101.2", (66.04, 187.96))
    sh.add("D106", "Device:D_Zener", 60.96, 191.77, rot=270, value="SMAJ13A", fp="Diode_SMD:D_SMA", lcsc="C10764",
           fields="L")
    sh.power("GND", "D106.2")
    sh.add("D107", "Device:D_Schottky", 69.85, 187.96, rot=180, value="SS34", fp="Diode_SMD:D_SMA", lcsc="C8678",
           fields="T")
    sh.wire("D107.1", (78.74, 187.96))
    sh.power("+12V", (78.74, 187.96))
    sh.wire("J101.2", (43.18, 200.66))
    sh.power("GND", (43.18, 200.66))
    sh.wire((43.18, 200.66), (50.8, 200.66))
    sh.power("FLAG", (50.8, 200.66))
    sh.nc("J101.3")
    T("PoE wins when both are present (12.2 V vs 11.6 V after D107)", 15.24, 210.82)

    # ---------------------------------------------------------------- bucks
    def buck(dx, u, cin, cin2, ren, cb, lref, co1, co2, rt, rb, rtv, out, en_src):
        x = 152.4 + dx
        T(("3.3 V, 3 A" if out == "+3V3" else "1.1 V core, 3 A") + " (TPS563201)", 86.36 + dx, 175.26, 2, True)
        sh.power("+12V", (91.44 + dx, 187.96))
        sh.wire((91.44 + dx, 187.96), (142.24 + dx, 187.96))
        C(sh, cin, "10uF 25V", 96.52 + dx, 191.77)
        C(sh, cin2, "100nF", 111.76 + dx, 191.77)
        for c in (cin, cin2):
            sh.power("GND", c + ".2")
        sh.add(u, "Regulator_Switching:TPS563201", x, 190.5, value="TPS563201DDCR", fp="Package_TO_SOT_SMD:TSOT-23-6",
               lcsc="C116592", fields=((x, 179.07, None), (x, 181.61, None)))
        R(sh, ren, "100k" if en_src == "+12V" else "10k", 138.43 + dx, 193.04, rot=90, fields="B")
        sh.wire(ren + ".1", (132.08 + dx, 193.04))
        sh.power(en_src, (132.08 + dx, 193.04), rot=90)
        sh.power("GND", u + ".1")
        sh.wire(u + ".2", (165.1 + dx, 187.96), (165.1 + dx, 182.88))
        C(sh, cb, "100nF", 172.72 + dx, 186.69, fields="R")
        sh.wire(u + ".6", (172.72 + dx, 190.5))
        sh.add(lref, "Device:L", 181.61 + dx, 182.88, rot=90, value="2.2uH", fp=L + "IND-SMD_L4.0-W4.0_FNR40XXS",
               lcsc="C167869", fields="T")
        sh.wire((165.1 + dx, 182.88), lref + ".1")
        sh.wire(lref + ".2", (220.98 + dx, 182.88))
        R(sh, rt, rtv, 190.5 + dx, 186.69, fields="L")
        sh.wire(rt + ".2", (190.5 + dx, 193.04), (167.64 + dx, 193.04))
        sh.wire(u + ".4", (167.64 + dx, 193.04))
        R(sh, rb, "10k", 167.64 + dx, 196.85)
        sh.power("GND", rb + ".2")
        C(sh, co1, "22uF 25V", 195.58 + dx, 186.69)
        C(sh, co2, "22uF 25V", 210.82 + dx, 186.69)
        for c in (co1, co2):
            sh.power("GND", c + ".2")
        sh.power(out, (220.98 + dx, 182.88))
        sh.wire((220.98 + dx, 182.88), (231.14 + dx, 182.88))
        sh.power("FLAG", (231.14 + dx, 182.88))

    buck(0, "U104", "C112", "C113", "R114", "C114", "L101", "C115", "C116", "R115", "R116", "33k", "+3V3", "+12V")
    buck(152.4, "U105", "C117", "C118", "R117", "C119", "L102", "C120", "C121", "R118", "R119", "4.3k", "+1V1", "+3V3")
    T("Vout = 0.768 V x (1 + 33k/10k) = 3.30 V", 86.36, 213.36)
    T("Vout = 0.768 V x (1 + 4.3k/10k) = 1.10 V; starts after 3.3 V (EN from +3V3)", 238.76, 213.36)

    # ---------------------------------------------------------------- power LED
    T("Power LED", 15.24, 226.06, 2, True)
    sh.power("+3V3", (25.4, 233.68))
    R(sh, "R120", "1k", 25.4, 237.49)
    sh.add("D108", "Device:LED", 25.4, 245.11, rot=90, value="RED", fp="LED_SMD:LED_0603_1608Metric", lcsc="C2286",
           fields="R")
    sh.wire("R120.2", "D108.2")
    sh.power("GND", "D108.1")

    tb = title_block(prj, "NetworkSwitchV1 - power: 12 V DC + 802.3af PoE PD, 3.3 V / 1.1 V", DATE, REV,
                     ["PoE PD: TPS23753A + EP1322S-10 isolated flyback, 12.2 V / 1 A, class 3",
                      "DC jack and PoE are ORed on the isolated 12 V rail"])
    return sh, tb


# ============================================================================ switch core
def switch_sheet(prj):
    sh = prj.sheet("switch.kicad_sch", "Switch core", 3)
    T = sh.text
    RTL = dict(value="RTL8370N-VB-CG", fp=L + "LQFP-128_L20.0-W14.0-P0.50-BL-EP7.0", lcsc="C2803243")

    # ---------------------------------------------------------------- supply filtering + decoupling
    def bank(y, rail, caps, title):
        T(title, 20.32, y - 7.62, 1.524, True)
        x0 = 25.4
        sh.power(rail, (x0, y))
        last = x0 + 12.7 * len(caps)
        sh.wire((x0, y), (last, y))
        sh.wire((x0, y + 7.62), (last, y + 7.62))
        sh.power("GND", (x0, y + 7.62))
        for k, (ref, val) in enumerate(caps, 1):
            C(sh, ref, val, x0 + 12.7 * k, y + 3.81)

    bank(45.72, "+1V1", [("C%d" % i, "100nF") for i in range(301, 309)] + [("C309", "10uF")],
         "DVDDL 1.1 V digital core: one 100 nF at each of pins 20 21 22 23 76 78 92 95")
    bank(76.2, "+1V1A", [("C%d" % i, "100nF") for i in range(310, 319)] + [("C319", "10uF")],
         "AVDDL 1.1 V PHY analog: one 100 nF at each of pins 10 18 29 39 49 59 107 117 128")
    bank(106.68, "+3V3A", [("C%d" % i, "100nF") for i in range(320, 330)] + [("C330", "10uF")],
         "AVDDH 3.3 V PHY analog: one 100 nF at each of pins 5 15 19 24 34 54 64 96 102 112")
    bank(137.16, "+1V1P", [("C331", "100nF"), ("C332", "100nF"), ("C333", "1uF")], "PLLVDDL0/1 (pins 122, 44)")
    T("DVDDIO (pin 77)", 76.2, 129.54, 1.524, True)
    sh.power("+3V3", (81.28, 137.16))
    sh.wire((81.28, 137.16), (91.44, 137.16))
    sh.wire((81.28, 144.78), (91.44, 144.78))
    sh.power("GND", (81.28, 144.78))
    C(sh, "C334", "100nF", 91.44, 140.97)

    T("Supply filters (ferrite beads 120R @ 100 MHz, 2 A)", 20.32, 160.02, 1.524, True)
    for k, (ref, src, dst) in enumerate((("FB301", "+1V1", "+1V1A"), ("FB302", "+1V1", "+1V1P"),
                                         ("FB303", "+3V3", "+3V3A"))):
        x = 25.4 + 45.72 * k
        sh.power(src, (x, 172.72))
        sh.add(ref, "Device:FerriteBead_Small", x + 10.16, 172.72, rot=90, value="BLM18PG121SN1D",
               fp="Inductor_SMD:L_0603_1608Metric", lcsc="C14709", fields=((x + 10.16, 168.275, None), (x + 10.16, 176.53, None)))
        sh.wire((x, 172.72), ref + ".1")
        sh.wire(ref + ".2", (x + 20.32, 172.72))
        sh.power(dst, (x + 20.32, 172.72))
        sh.wire((x + 20.32, 172.72), (x + 30.48, 172.72))
        sh.power("FLAG", (x + 30.48, 172.72))

    # ---------------------------------------------------------------- unit 2: supply pins
    sh.add("U301", L + "RTL8370N-VB", 88.9, 233.68, unit=2, fields=((114.3, 231.14, "left"), (114.3, 233.68, "left")), **RTL)
    for num, rail in (("20", "+1V1"), ("10", "+1V1A"), ("122", "+1V1P"), ("44", "+1V1P"), ("5", "+3V3A"), ("77", "+3V3")):
        sh.power(rail, "U301.2." + num)
    sh.power("GND", "U301.2.16")
    sh.power("GND", "U301.2.129")
    T("EPAD (129) = GND: thermal vias under the pad", 101.6, 259.08)

    # ---------------------------------------------------------------- unit 3: SMI, LEDs + straps, clock, reset
    UX, UY = 292.1, 132.08
    sh.add("U301", L + "RTL8370N-VB", UX, UY, unit=3, fields=((UX, UY - 66.04, None), (UX, UY - 63.5, None)), **RTL)
    # SMI bus in I2C mode: RTL8370N reads U302 at reset, then answers the MCU at 0x5C (16-bit regs, low byte first)
    (xs, ysc), (_, ysd) = sh.P("U301.3.100"), sh.P("U301.3.101")
    R(sh, "R303", "4.7k", xs - 7.62, ysc - 6.35, fields="R")
    sh.power("+3V3", "R303.1")
    sh.wire("R303.2", (xs - 7.62, ysc))
    R(sh, "R304", "4.7k", xs - 7.62, ysd - 3.81, fields="R")
    sh.power("+3V3", "R304.1")
    sh.add("U302", L + "AT24C256C", 210.82, 86.36, value="AT24C256C-SSHL-T", fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
           lcsc="C6482", fields=((215.9, 71.12, "left"), (215.9, 73.66, "left")))
    sh.wire("U301.3.100", (231.14, ysc), (231.14, 83.82), "U302.6")
    sh.wire("U301.3.101", (226.06, ysd), (226.06, 86.36), "U302.5")
    sh.wire((xs - 15.24, ysc), (xs - 15.24, ysc - 5.08), (xs - 20.32, ysc - 5.08))
    sh.glabel("SW_SCL", (xs - 20.32, ysc - 5.08), 180)
    sh.wire((xs - 15.24, ysd), (xs - 15.24, ysd + 5.08), (xs - 20.32, ysd + 5.08))
    sh.glabel("SW_SDA", (xs - 20.32, ysd + 5.08), 180)
    sh.power("+3V3", "U302.8")
    sh.wire("U302.8", (193.04, 76.2))
    C(sh, "C338", "100nF", 193.04, 80.01, fields="L")
    sh.power("GND", "C338.2")
    for pin in ("1", "2", "3"):
        sh.wire("U302." + pin, (198.12, sh.P("U302." + pin)[1]))
    sh.wire((198.12, 83.82), (198.12, 88.9))
    sh.power("GND", (198.12, 88.9))
    sh.power("GND", "U302.4")
    sh.wire("U302.7", (223.52, 88.9), (223.52, 104.14), (218.44, 104.14))
    sh.glabel("EE_WP", (218.44, 104.14), 180)
    R(sh, "R315", "10k", 227.33, 96.52, rot=90, fields="B")
    sh.wire((223.52, 96.52), "R315.1")
    sh.power("GND", "R315.2", rot=90)
    T("U302: switch configuration, autoloaded at every reset (A2..A0 = 0, address 0x50)", 165.1, 60.96)
    T("WP low = writable (R315); the MCU drives EE_WP high to protect it", 165.1, 64.77)
    # external programming header (DNP): hold SW_RST_N low, write U302, release -> switch reloads it
    sh.add("J302", "Connector_Generic:Conn_01x05", 205.74, 124.46, value="EEPROM PROG", dnp=True,
           fp="Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical", lcsc="C492404",
           fields=((205.74, 113.03, None), (205.74, 115.57, None)))
    sh.wire("J302.1", (195.58, sh.P("J302.1")[1]))
    sh.power("+3V3", (195.58, sh.P("J302.1")[1]), rot=90)
    for pin, net in (("2", "SW_SCL"), ("3", "SW_SDA"), ("4", "SW_RST_N")):
        sh.glabel(net, sh.stub("J302." + pin, -7.62, 0), 180)
    sh.wire("J302.5", (195.58, sh.P("J302.5")[1]))
    sh.power("GND", (195.58, sh.P("J302.5")[1]), rot=270)
    for k, s_ in enumerate(("1 3V3", "2 SCL", "3 SDA", "4 nRST (hold low)", "5 GND")):
        T(s_, 209.55, sh.P("J302.%d" % (k + 1))[1] + 0.635, 1.016)
    T("External EEPROM programming (DNP): hold pin 4 low, write 0x50, release", 165.1, 137.16)

    # 25 MHz crystal below the chip
    xi, yb = sh.P("U301.3.98")
    sh.add("Y301", "Device:Crystal_GND24", xi + 3.81, yb + 7.62, value="25MHz 12pF", fp="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
           lcsc="C9006", fields=((xi - 2.54, yb + 3.81, "right"), (xi - 2.54, yb + 6.35, "right")), extra={"MPN": "X322525MOB4SI"})
    sh.wire("U301.3.98", "Y301.1")
    sh.wire("U301.3.97", "Y301.3")
    sh.power("GND", "Y301.2")
    C(sh, "C335", "18pF", xi, yb + 11.43, fields="L")
    C(sh, "C336", "18pF", xi + 7.62, yb + 11.43, fields="R")
    for c in ("C335", "C336"):
        sh.power("GND", c + ".2")
    # reset: RC (~100 ms) + MCU open-drain through 1k
    xr = sh.P("U301.3.99")[0]
    jr = yb + 22.86
    sh.wire("U301.3.99", (xr, jr))
    C(sh, "C337", "10uF", xr, jr + 3.81, fields="L")
    sh.power("GND", "C337.2")
    R(sh, "R301", "10k", xr + 3.81, jr, rot=90, fields="T")
    sh.power("+3V3", "R301.2", rot=270)
    R(sh, "R302", "1k", xr - 3.81, jr, rot=90, fields="T")
    sh.wire("R302.1", (xr - 12.7, jr))
    sh.glabel("SW_RST_N", (xr - 12.7, jr), 180)
    # bias resistor
    xm = sh.P("U301.3.17")[0]
    R(sh, "R305", "2.49k", xm, yb + 3.81, fields="R")
    sh.power("GND", "R305.2")
    T("MDIREF 2.49k 1%", xm + 5.08, yb + 10.16)
    for pin in ("123", "65", "66"):
        sh.nc("U301.3." + pin)

    # right side: per port LED0 = link/act, LED1 = 1000M, LED2 = strap / spare
    rows = [("94", "P1_LNK", "GND", "R306"), ("93", "P1_SPD", None, None), ("91", None, "+3V3", "R307"),
            ("89", "P2_LNK", "+3V3", "R308"), ("90", "P2_SPD", None, None), ("88", None, "GND", "R309"),
            ("86", "P3_LNK", "GND", "R310"), ("87", "P3_SPD", None, None), ("85", None, "+3V3", "R311"),
            ("84", "P4_LNK", "GND", "R312"), ("82", "P4_SPD", None, None), ("83", None, None, None),
            ("80", "P5_LNK", "+3V3", "R313"), ("81", "P5_SPD", None, None), ("79", None, None, None),
            ("74", "P6_LNK", None, None), ("75", "P6_SPD", None, None), ("73", None, None, None),
            ("71", "SW_GPIO1", None, None), ("72", None, None, None), ("70", None, None, None),
            ("68", None, None, None), ("69", None, None, None), ("67", None, None, None)]
    for pin, net, pull, ref in rows:
        spec = "U301.3." + pin
        y = sh.P(spec)[1]
        if not net and not pull:
            sh.nc(spec)
            continue
        if net:
            sh.wire(spec, (325.12, y))
            sh.glabel(net, (325.12, y), 0)
        if pull:
            ry = y + 2.54 if net else y
            if net:
                sh.wire((317.5, y), (317.5, ry), (340.36, ry))
            else:
                sh.wire(spec, (340.36, y))
            R(sh, ref, "4.7k", 344.17, ry, rot=270, fields=((343.535, ry - 2.159, "right"), (344.805, ry - 2.159, "left")))
            sh.wire(ref + ".2", (340.36, ry))
            sh.power(pull, ref + ".1", rot=270 if pull == "+3V3" else 90)
        if pin == "85":                   # DNP pull-down: lets U302 hold 8051 code instead of registers
            ry = y + 2.54
            sh.wire((317.5, y), (317.5, ry), (355.6, ry))
            R(sh, "R314", "4.7k", 359.41, ry, rot=270, dnp=True,
              fields=((358.775, ry + 2.794, "right"), (360.045, ry + 2.794, "left")))
            sh.wire("R314.2", (355.6, ry))
            sh.power("GND", "R314.1", rot=90)
    T("Straps (latched at reset, 4.7k):", 322.58, 40.64, 1.524, True)
    for k, s_ in enumerate(["SMI_SEL[1:0] = 00: I2C, slave 0x5C after autoload (16-bit, low byte first)",
                            "DISAUTOLOAD = 0: registers load from U302 at reset (self-boot)",
                            "DIS_8051 = 1 (R311); fit R314, drop R311: U302 holds 8051 code instead",
                            "EEPROM_MOD = 1 (R313): 24C32+ two-byte addressing; EN_FLASH = 0; EN_PHY = 1",
                            "LED pins pulled up = active-low LED,",
                            "pulled down = active-high (ports 1, 3, 4 link LEDs)"]):
        T(s_, 322.58, 44.45 + 3.81 * k)

    tb = title_block(prj, "NetworkSwitchV1 - switch core: RTL8370N-VB power, clock, reset, EEPROM, LEDs, straps", DATE, REV,
                     ["8 integrated GbE PHYs: P0-P5 = front ports 1-6, P6 unused, P7 = management MCU",
                      "Self-boots from the U302 EEPROM; CH32V208 shares the I2C bus to manage it and rewrite U302"])
    return sh, tb


# ============================================================================ ports
MDI = {0: [103, 104, 105, 106, 108, 109, 110, 111], 1: [113, 114, 115, 116, 118, 119, 120, 121],
       2: [124, 125, 126, 127, 1, 2, 3, 4], 3: [6, 7, 8, 9, 11, 12, 13, 14], 4: [25, 26, 27, 28, 30, 31, 32, 33],
       5: [35, 36, 37, 38, 40, 41, 42, 43], 6: [45, 46, 47, 48, 50, 51, 52, 53], 7: [55, 56, 57, 58, 60, 61, 62, 63]}
TD = ["2", "3", "5", "6", "8", "9", "11", "12"]
MX = ["23", "22", "20", "19", "17", "16", "14", "13"]
JP = ["1", "2", "3", "6", "4", "5", "7", "8"]


def ports_sheet(prj):
    sh = prj.sheet("ports.kicad_sch", "Ports", 4)
    T = sh.text
    UX, UY = 210.82, 147.32
    sh.add("U301", L + "RTL8370N-VB", UX, UY, unit=1, value="RTL8370N-VB-CG", fp=L + "LQFP-128_L20.0-W14.0-P0.50-BL-EP7.0",
           lcsc="C2803243", fields="IC")
    # staircase zones (x of the vertical jogs); groups moving up use zones nearer the chip the higher they sit,
    # so no two bundles ever cross
    inner = [193.04 - 2.54 * n for n in range(8)]
    middle = [172.72 - 2.54 * n for n in range(8)]
    outer = [152.4 - 2.54 * n for n in range(8)]
    near = [228.6 + 2.54 * n for n in range(8)]
    far = [248.92 + 2.54 * n for n in range(8)]
    ports = {1: ("L", 40.64, inner), 2: ("L", 93.98, middle), 3: ("L", 147.32, outer),
             4: ("L", 200.66, inner[::-1]), 5: ("R", 40.64, near), 6: ("R", 93.98, far)}
    for k, (side, yT, xs) in ports.items():
        p = k - 1
        left = side == "L"
        d = -1 if left else 1
        tx = 106.68 if left else 294.64
        jx = 58.42 if left else 342.9
        tr, j = "TR40%d" % k, "J40%d" % k
        sh.add(tr, L + "GST5009", tx, yT, mirror="y" if left else None, value="GST5009",
               fp=L + "XFMR-SMD_24P-L15.1-W7.1-P1.00-LS9.7-BL", lcsc="C55213474",
               fields=((tx, yT - 15.24, None), (tx, yT - 12.7, None)))
        sh.add(j, L + "RJ45_LED", jx, yT, mirror=None if left else "y", value="RJ45-202-007-02",
               fp=L + "RJ45-TH_RJ45-202-007-02", lcsc="C7421418", fields=((jx, yT - 15.24, None), (jx, yT - 12.7, None)))
        title = "PORT %d  (P%d)" % (k, p) + ("  PoE PD input" if k == 1 else "")
        tx0 = 25.4 if left else 312.42
        T(title, tx0, yT - 19.05, 1.778, True)
        T("CT caps 4x 100 nF" + ("" if k == 1 else ";  Bob Smith 4x 75R + 1 nF 2 kV"), tx0 if left else 335.28, yT - 22.86, 1.016)
        # MDI pairs: switch -> magnetics (staircase where the rows do not line up)
        for i in range(8):
            a, b = sh.P("U301.%d" % MDI[p][i]), sh.P("%s.%s" % (tr, TD[i]))
            if a[1] == b[1]:
                sh.wire(a, b)
            else:
                sh.wire(a, (xs[i], a[1]), (xs[i], b[1]), b)
            sh.wire("%s.%s" % (tr, MX[i]), "%s.%s" % (j, JP[i]))
        # chip-side centre taps: 100 nF each to GND
        for ct, num in enumerate(("1", "4", "7", "10"), 1):
            ref = "C4%d%d" % (k, ct)
            px, py = sh.P("%s.%s" % (tr, num))
            C(sh, ref, "100nF", px, py + 3.81, fields=((px + 1.905, py + 3.81, None, 90),) * 2, extra={"hide_value": True})
            sh.power("GND", ref + ".2")
        # line-side centre taps
        mct = [sh.P("%s.%s" % (tr, n)) for n in ("24", "21", "18", "15")]
        if k == 1:
            order = sorted(range(4), key=lambda n: mct[n][0] * -d)      # outermost first
            for step, n in enumerate(order):
                px, py = mct[n]
                yy = py + 2.54 * (step + 1)
                sh.wire((px, py), (px, yy), (81.28, yy))
                sh.glabel("POE_CT%d" % (n + 1), (81.28, yy), 180)
            T("to the PoE PD (sheet power)", 63.5, yT + 33.02, 1.016)
        else:
            for n, (px, py) in enumerate(mct, 1):
                R(sh, "R4%d%d" % (k, n), "75R", px, py + 3.81, fields=((px + 1.905, py + 3.81, None, 90),) * 2,
                  extra={"hide_value": True})
            ys = mct[0][1] + 7.62
            xs_ = [m[0] for m in mct]
            outer_x = min(xs_) if left else max(xs_)
            sh.wire((min(xs_), ys), (max(xs_), ys))
            sh.wire((outer_x, ys), (outer_x + d * 2.54, ys))
            hv = "C4%d5" % k
            C(sh, hv, "1nF 2kV", outer_x + d * 6.35, ys, rot=90, fields="T")
            sh.power("CHASSIS", sh.P(hv + (".1" if left else ".2")))
        sh.power("CHASSIS", j + ".13")
        # LEDs: yellow = 1000M (active low); green = link/act (active high on ports 1, 3, 4: strap pull-downs)
        x0 = sh.P(j + ".9")[0]
        y9, y10, y11, y12 = [sh.P("%s.%s" % (j, n))[1] for n in ("9", "10", "11", "12")]
        sh.wire(j + ".9", (x0 + d * 2.54, y9), (x0 + d * 2.54, y9 - 2.54))
        sh.power("+3V3", (x0 + d * 2.54, y9 - 2.54))
        ry = "R4%d5" % k
        R(sh, ry, "510R", x0 + d * 8.89, y10, rot=90, fields="B")
        sh.wire(j + ".10", sh.P(ry + (".2" if left else ".1")))
        lab = (x0 + d * 17.78, y10)
        sh.wire(sh.P(ry + (".1" if left else ".2")), lab)
        sh.glabel("P%d_SPD" % k, lab, 180 if left else 0)
        rg = "R4%d6" % k
        if k in (1, 3, 4):
            R(sh, rg, "510R", x0 + d * 8.89, y11, rot=90, fields="B")
            sh.wire(j + ".11", sh.P(rg + (".2" if left else ".1")))
            lab = (x0 + d * 17.78, y11)
            sh.wire(sh.P(rg + (".1" if left else ".2")), lab)
            sh.glabel("P%d_LNK" % k, lab, 180 if left else 0)
            sh.wire(j + ".12", (x0 + d * 2.54, y12))
            sh.power("GND", (x0 + d * 2.54, y12))
        else:
            sh.wire(j + ".11", (x0 + d * 5.08, y11))
            sh.power("+3V3", (x0 + d * 5.08, y11), rot=90 if left else 270)
            R(sh, rg, "510R", x0 + d * 8.89, y12, rot=90, fields="B")
            sh.wire(j + ".12", sh.P(rg + (".2" if left else ".1")))
            lab = (x0 + d * 17.78, y12)
            sh.wire(sh.P(rg + (".1" if left else ".2")), lab)
            sh.glabel("P%d_LNK" % k, lab, 180 if left else 0)
    # P6 unused, P7 -> management MCU
    for num in MDI[6]:
        sh.nc("U301.%d" % num)
    for num, net in zip(MDI[7][:4], ("MG_AP", "MG_AN", "MG_BP", "MG_BN")):
        sh.wire("U301.%d" % num, (236.22, sh.P("U301.%d" % num)[1]))
        sh.glabel(net, (236.22, sh.P("U301.%d" % num)[1]), 0)
    for num in MDI[7][4:]:
        sh.nc("U301.%d" % num)
    T("P6: not used (PHY powered down by firmware)", 231.14, 160.02)
    T("P7: 10BASE-T link to the CH32V208 (sheet mgmt)", 231.14, 172.72)

    # chassis bond + mounting holes
    T("Chassis: RJ45 shells, Bob Smith, mounting holes", 251.46, 205.74, 1.524, True)
    sh.power("CHASSIS", (256.54, 220.98))
    sh.wire((256.54, 215.9), (256.54, 220.98))
    sh.wire((256.54, 215.9), (264.16, 215.9))
    C(sh, "C401", "1nF 2kV", 267.97, 215.9, rot=90, fields="T")
    sh.wire("C401.2", (275.59, 215.9))
    sh.wire((256.54, 215.9), (256.54, 210.82), (264.16, 210.82))
    sh.wire((256.54, 210.82), (251.46, 210.82))
    sh.power("FLAG", (251.46, 210.82))
    R(sh, "R401", "1M", 267.97, 210.82, rot=90, fields=((267.97, 207.01, None), (267.97, 208.915, None)))
    sh.wire("R401.2", (275.59, 210.82), (275.59, 215.9))
    sh.wire((275.59, 215.9), (280.67, 215.9))
    sh.power("GND", (280.67, 215.9))
    for n in range(4):
        x = 297.18 + 12.7 * n
        sh.add("H40%d" % (n + 1), "Mechanical:MountingHole_Pad", x, 218.44, value="M3",
               fp="MountingHole:MountingHole_3.2mm_M3_Pad_Via", fields=((x + 2.54, 214.63, "left"), (x + 2.54, 217.17, "left")))
        sh.power("CHASSIS", "H40%d.1" % (n + 1))

    tb = title_block(prj, "NetworkSwitchV1 - ports 1-6: GST5009 magnetics, RJ45 + LEDs, management link", DATE, REV,
                     ["MDI pair A = RJ45 1/2, B = 3/6, C = 4/5, D = 7/8; auto-MDIX in the PHY",
                      "Port 1 centre taps feed the PoE PD (sheet power)"])
    return sh, tb


# ============================================================================ management
def mgmt_sheet(prj):
    sh = prj.sheet("mgmt.kicad_sch", "Management", 5)
    T = sh.text
    UX, UY = 182.88, 132.08
    sh.add("U501", L + "CH32V208GBU6", UX, UY, value="CH32V208GBU6", fp=L + "QFN-28_L4.0-W4.0-P0.40-BL-EP2.8",
           lcsc="C7434833", fields=((UX, 99.06, None), (UX, 101.6, None)))
    T("Management MCU: web UI over the internal 10BASE-T link to switch port P7", 116.84, 76.2, 2, True)
    T("I2C master for the RTL8370N (VLAN, QoS, mirroring, LAG, MIB counters, cable test) and its EEPROM", 116.84, 80.01)
    # supplies
    for pin in ("13", "27", "4"):
        sh.wire("U501." + pin, (160.02, sh.P("U501." + pin)[1]))
    sh.wire((160.02, 96.52), (160.02, sh.P("U501.4")[1]))
    sh.wire((109.22, 96.52), (160.02, 96.52))
    sh.power("+3V3", (109.22, 96.52))
    sh.wire((109.22, 104.14), (149.86, 104.14))
    sh.power("GND", (109.22, 104.14))
    for k, (ref, val) in enumerate((("C501", "100nF"), ("C502", "100nF"), ("C503", "100nF"), ("C504", "10uF")), 1):
        C(sh, ref, val, 109.22 + 10.16 * k, 100.33)
    T("one 100 nF at pins 13, 27, 4", 111.76, 91.44)
    yv = sh.P("U501.21")[1]
    sh.wire("U501.21", (123.19, yv))                      # C505 / J501 positions as moved by hand in KiCad
    C(sh, "C505", "1uF", 123.19, yv + 3.81, fields="L")
    sh.power("GND", "C505.2")
    # 32 MHz crystal (load capacitors are built in)
    yi, yo = sh.P("U501.2")[1], sh.P("U501.3")[1]
    sh.add("Y501", "Device:Crystal_GND24", 142.24, yi + 3.81, rot=270, value="32MHz",
           fp="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", lcsc="C9009",
           fields=((142.24, yi + 10.16, None), (142.24, yi + 12.7, None)), extra={"MPN": "X322532MOB4SI"})
    sh.wire("U501.2", "Y501.1")
    sh.wire("U501.3", (147.32, yo), (147.32, yi + 7.62), "Y501.3")
    sh.wire("Y501.2", (134.62, yi + 3.81))
    sh.power("GND", (134.62, yi + 3.81), rot=270)
    for pin in ("28", "1", "22"):
        sh.nc("U501." + pin)
    # BOOT0: 510k pull-down + BOOT button to 3V3 (USB/serial ISP)
    yb = sh.P("U501.26")[1]
    sh.wire("U501.26", (154.94, yb))
    R(sh, "R501", "510k", 154.94, yb + 3.81, fields="R")
    sh.power("GND", "R501.2")
    sh.add("SW501", L + "SW_Tact_4P", 144.78, yb, value="BOOT", fp=L + "SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5",
           lcsc="C318884", fields=((144.78, yb + 3.81, None), (144.78, yb + 5.715, None)))
    sh.wire("SW501.3", (154.94, yb))
    sh.wire("SW501.1", (137.16, yb))
    sh.power("+3V3", (137.16, yb), rot=90)
    sh.power("GND", "U501.29")
    # switch control + I2C bus
    for pin, net in (("5", "SW_RST_N"), ("6", "EE_WP"), ("24", "SW_SCL"), ("25", "SW_SDA"), ("12", "SW_GPIO1")):
        sh.glabel(net, sh.stub("U501." + pin, 10.16, 0), 0)
    # status LED + factory-reset button
    y5, y6 = sh.P("U501.10")[1], sh.P("U501.11")[1]
    R(sh, "R502", "1k", 210.82, y5, rot=270, fields="T")
    sh.wire("U501.10", "R502.2")
    sh.add("D501", "Device:LED", 222.25, y5, rot=180, value="RED", fp="LED_SMD:LED_0603_1608Metric", lcsc="C2286",
           fields="T")
    sh.wire("R502.1", "D501.2")
    sh.wire("D501.1", (231.14, y5))
    sh.power("GND", (231.14, y5), rot=90)
    sh.add("SW502", L + "SW_Tact_4P", 213.36, y6, rot=180, value="RESET (factory)",
           fp=L + "SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5", lcsc="C318884",
           fields=((213.36, y6 + 3.81, None), (213.36, y6 + 5.715, None)))
    sh.wire("U501.11", "SW502.3")
    sh.wire("SW502.1", (233.68, y6))
    sh.power("GND", (233.68, y6), rot=90)
    # debug header: 3V3, TX, RX, SWDIO, SWCLK, GND (straight across from PA2/PA3/PA13/PA14)
    ytx = sh.P("U501.7")[1]
    hx = 250.19
    sh.add("J501", "Connector_Generic:Conn_01x06", hx, ytx + 2.54, value="DEBUG", dnp=True,
           fp="Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", lcsc="C492405",
           fields=((hx + 2.54, ytx - 6.35, "left"), (hx + 2.54, ytx - 4.445, "left")))
    for pin, hp in (("7", "2"), ("8", "3"), ("20", "4"), ("23", "5")):
        sh.wire("U501." + pin, "J501." + hp)
    sh.wire("J501.1", (hx - 10.16, sh.P("J501.1")[1]))
    sh.power("+3V3", (hx - 10.16, sh.P("J501.1")[1]), rot=90)
    sh.wire("J501.6", (hx - 10.16, sh.P("J501.6")[1]))
    sh.power("GND", (hx - 10.16, sh.P("J501.6")[1]), rot=270)
    for k, s_ in enumerate(("1 3V3", "2 TX (PA2)", "3 RX (PA3)", "4 SWDIO", "5 SWCLK", "6 GND")):
        T(s_, hx + 3.81, sh.P("J501.%d" % (k + 1))[1] + 0.635, 1.016)
    for pin in ("9", "18", "19"):
        sh.nc("U501." + pin)
    # 10BASE-T link: CH32V208 PHY -> GST5009 -> RTL8370N P7 (crossed: MCU TX -> P7 pair B)
    ytxp = sh.P("U501.16")[1]
    tx = UX + 17.78 + 30.48 + 25.4
    sh.add("TR501", L + "GST5009", tx, ytxp + 8.89, value="GST5009", fp=L + "XFMR-SMD_24P-L15.1-W7.1-P1.00-LS9.7-BL",
           lcsc="C55213474", fields=((tx, ytxp - 6.35, None), (tx, ytxp - 3.81, None)))
    for pin, tp in (("16", "2"), ("17", "3"), ("14", "5"), ("15", "6")):
        sh.wire("U501." + pin, "TR501." + tp)
    for tp in ("8", "9", "11", "12", "7", "10", "17", "16", "14", "13", "18", "15"):
        sh.nc("TR501." + tp)
    for tp, net in (("23", "MG_BP"), ("22", "MG_BN"), ("20", "MG_AP"), ("19", "MG_AN")):
        sh.glabel(net, sh.stub("TR501." + tp, 7.62, 0), 0)
    # chip-side centre taps to 3V3 (WCH PHY drivers need the bias), line side to GND via 100 nF
    p1, p4 = sh.P("TR501.1"), sh.P("TR501.4")
    yct = p1[1] + 5.08
    sh.wire(p1, (p1[0], yct))
    sh.wire(p4, (p4[0], yct))
    sh.wire((p1[0] - 12.7, yct), (p4[0], yct))
    sh.power("+3V3", (p1[0] - 12.7, yct))
    C(sh, "C506", "100nF", p1[0] - 7.62, yct + 3.81, fields="L")
    sh.power("GND", "C506.2")
    for tp, ref in (("24", "C507"), ("21", "C508")):
        px, py = sh.P("TR501." + tp)
        C(sh, ref, "100nF", px, py + 3.81, fields="L" if ref == "C507" else "R")
        sh.power("GND", ref + ".2")
    # notes
    T("Notes", 116.84, 200.66, 1.524, True)
    for k, s_ in enumerate((
            "Y501 32 MHz: the load capacitors are internal to the CH32V208 (none fitted).",
            "SYS LED on PA5. Factory reset on PA6 (internal pull-up), hold 10 s at power-up to restore defaults.",
            "J501 (DNP): WCH-LinkE on SWDIO/SWCLK, console 115200 8N1 on PA2/PA3. BOOT (SW501) + power cycle = ISP.",
            "I2C1 on PB6/PB7: RTL8370N slave 0x5C (16-bit registers, low byte first) and EEPROM U302 at 0x50.",
            "  Keep PB6/PB7 released until the switch has finished its EEPROM autoload after SW_RST_N goes high.",
            "  To change the boot configuration: EE_WP low, write U302, pulse SW_RST_N -> the switch reloads it.",
            "TR501 is the same GST5009 as the front ports; the MCU TX pair goes to P7 pair B (crossed link).")):
        T(s_, 116.84, 205.74 + 3.81 * k)

    tb = title_block(prj, "NetworkSwitchV1 - management: CH32V208 (10BASE-T to P7, I2C master, EEPROM writer)", DATE, REV,
                     ["CH32V208GBU6: built-in 10M PHY, link via GST5009 to RTL8370N port 7",
                      "Firmware: WCHNET web UI + Realtek I2C-SMI driver + EEPROM writer (not part of this schematic)"])
    return sh, tb


# ============================================================================ root
def main():
    prj = Project(PRJ_NAME, ROOT_UUID)
    sheets = [power_sheet(prj), switch_sheet(prj), ports_sheet(prj), mgmt_sheet(prj)]
    for sh, tb in sheets:
        write_sheet(sh, tb)
        report(sh)
    root = prj.sheet("_root", "root", 1)
    prj.sheets.remove(root)
    T = root.text
    T("NetworkSwitchV1: 6-port gigabit smart-managed switch", 25.4, 35.56, 3.81, True)
    notes = [
        "RTL8370N-VB 8-port GbE switch (P0-P5 = front ports 1-6, P6 unused, P7 = internal management link)",
        "802.3x flow control, 802.3az EEE, auto-MDIX, 9216-byte jumbo, IGMP/MLD snooping, 802.1Q VLAN (4K), QoS 8 queues,",
        "  port mirroring, 2 link-aggregation groups, loop detection, storm control, 802.1X, MIB counters, RTCT cable test",
        "Self-boot: RTL8370N loads its registers from the U302 EEPROM at every reset; works without the MCU",
        "Management: CH32V208 on the I2C/SMI bus (rewrites U302) + 10BASE-T into P7 -> web UI (firmware to be written)",
        "Power: 12 V DC jack or 802.3af PoE on port 1 (class 3, isolated 12.2 V flyback); 3.3 V and 1.1 V bucks",
        "Front panel: link/act (green) + 1000M (yellow) LED per port, power LED, SYS LED, factory-reset button",
    ]
    for k, s in enumerate(notes):
        T(s, 25.4, 45.72 + 5.08 * k, 1.524)
    blocks = [(sheets[0][0], 38.1, 101.6, 63.5, 38.1, "Power: 12 V in, PoE PD, 3.3 V / 1.1 V"),
              (sheets[1][0], 132.08, 101.6, 63.5, 38.1, "Switch core: RTL8370N"),
              (sheets[2][0], 226.06, 101.6, 63.5, 38.1, "Ports 1-6 + magnetics"),
              (sheets[3][0], 320.04, 101.6, 63.5, 38.1, "Management: CH32V208")]
    T("Cross-sheet nets are global labels: P<n>_LNK / P<n>_SPD (LEDs), SW_SCL / SW_SDA / SW_RST_N / EE_WP / SW_GPIO1,",
      25.4, 167.64, 1.524)
    T("MG_AP/AN/BP/BN (management link), POE_CT1..4 (port 1 centre taps)", 25.4, 172.72, 1.524)
    tb = title_block(prj, "NetworkSwitchV1 - 6-port managed gigabit switch, PoE powered", DATE, REV,
                     ["RTL8370N-VB + CH32V208, TPS23753A PoE PD, JLCPCB Basic parts where possible",
                      "Schematic only (board not started)"])
    write_root(prj, "NetworkSwitchV1.kicad_sch", tb, blocks, root)


if __name__ == "__main__":
    main()
