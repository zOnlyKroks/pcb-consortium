"""NetworkSwitchV1 design truth: every part's intended pin -> net map.

check_netlist.py compares the exported KiCad netlist with this table (as pin groups, so net names may differ where
the sheet leaves a net unlabelled).  Written from the design intent, not from the generator.
"""

NETS = {}


def part(ref, pins):
    if ref in NETS:
        NETS[ref].update(pins)
    else:
        NETS[ref] = dict(pins)


# ======================================================================= power.kicad_sch (1xx)
# --- PoE input from port 1 magnetics centre taps, Bob Smith (DC-blocked), bridges
for n in range(1, 5):
    part("R15%d" % n, {"1": "POE_CT%d" % n, "2": "BS_%d" % n})            # 75R
    part("C15%d" % n, {"1": "BS_%d" % n, "2": "BS_NODE"})                  # 100nF 100V (DC block)
part("C155", {"1": "BS_NODE", "2": "CHASSIS"})                              # 1nF 2kV
part("BR101", {"3": "POE_CT1", "4": "POE_CT2", "1": "POE_VDD", "2": "POE_VSS"})
part("BR102", {"3": "POE_CT3", "4": "POE_CT4", "1": "POE_VDD", "2": "POE_VSS"})
part("D101", {"1": "POE_VDD", "2": "POE_VSS"})                              # SMAJ58A K/A
part("C101", {"1": "POE_VDD", "2": "POE_VSS"})
part("R101", {"1": "POE_VDD", "2": "DEN"})                                  # 24.9k
part("R102", {"1": "CLS", "2": "POE_VSS"})                                  # 90.9R class 3
part("U101", {"9": "POE_VDD", "8": "POE_VDD", "7": "POE_VSS", "10": "DEN", "11": "CLS", "12": "RTN",
              "13": "RTN", "6": "RTN", "14": "FRS", "2": "VB", "1": "CTL", "4": "VC", "5": "GATE", "3": "CS"})
part("R103", {"1": "FRS", "2": "RTN"})                                      # 56k -> ~270 kHz
part("C102", {"1": "VB", "2": "RTN"})
part("R104", {"1": "VB", "2": "CTL"})
part("C103", {"1": "CTL", "2": "RTN"})
part("C104", {"1": "VC", "2": "RTN"})
part("C105", {"1": "VC", "2": "RTN"})
part("C106", {"1": "POE_VDD", "2": "RTN"})                                  # 2.2uF 100V
part("C107", {"1": "POE_VDD", "2": "RTN"})
part("R106", {"1": "GATE", "2": "GATE_R"})
part("Q101", {"1": "GATE_R", "2": "DRAIN", "3": "CS"})                      # IRFR220N G/D/S
part("R107", {"1": "CS", "2": "RTN"})                                       # 0.43R current sense
part("T101", {"3": "POE_VDD", "4": "DRAIN", "2": "RTN", "1": "AUX_A", "7": "GND", "8": "GND",
              "9": "SEC_A", "10": "SEC_A"})
part("D102", {"2": "DRAIN", "1": "CLAMP"})                                  # US1M A/K
part("D103", {"1": "CLAMP", "2": "POE_VDD"})                                # SMAJ58A K/A
part("D104", {"2": "AUX_A", "1": "AUX_K"})                                  # 1N4148W
part("R105", {"1": "AUX_K", "2": "VC"})
part("D105", {"2": "SEC_A", "1": "+12V"})                                   # SS210
for c in ("C108", "C109", "C110"):
    part(c, {"1": "+12V", "2": "GND"})
# --- secondary feedback
part("U103", {"4": "CTL", "3": "RTN", "1": "OPTO_A", "2": "OPTO_K"})        # LTV-817S
part("R110", {"1": "+12V", "2": "OPTO_A"})
part("R112", {"1": "+12V", "2": "OPTO_K"})
part("U102", {"2": "OPTO_K", "3": "GND", "1": "FB_REF"})                    # CJ431
part("R113", {"1": "OPTO_K", "2": "COMP"})
part("C111", {"1": "COMP", "2": "FB_REF"})
part("R108", {"1": "+12V", "2": "FB_REF"})                                  # 39k
part("R109", {"1": "FB_REF", "2": "GND"})                                   # 10k  -> 12.2 V
# --- DC jack
part("J101", {"4": "DCJ", "2": "GND"})
part("F101", {"1": "DCJ", "2": "DC_F"})
part("D106", {"1": "DC_F", "2": "GND"})                                     # SMAJ13A
part("D107", {"2": "DC_F", "1": "+12V"})                                    # SS34
# --- 3.3 V buck
part("U104", {"3": "+12V", "5": "EN33", "1": "GND", "2": "SW33", "6": "BST33", "4": "FB33"})
part("C112", {"1": "+12V", "2": "GND"})
part("C113", {"1": "+12V", "2": "GND"})
part("R114", {"1": "+12V", "2": "EN33"})
part("C114", {"1": "SW33", "2": "BST33"})
part("L101", {"1": "SW33", "2": "+3V3"})
part("C115", {"1": "+3V3", "2": "GND"})
part("C116", {"1": "+3V3", "2": "GND"})
part("R115", {"1": "+3V3", "2": "FB33"})                                    # 33k
part("R116", {"1": "FB33", "2": "GND"})                                     # 10k
# --- 1.1 V buck (enabled by 3.3 V)
part("U105", {"3": "+12V", "5": "EN11", "1": "GND", "2": "SW11", "6": "BST11", "4": "FB11"})
part("C117", {"1": "+12V", "2": "GND"})
part("C118", {"1": "+12V", "2": "GND"})
part("R117", {"1": "+3V3", "2": "EN11"})
part("C119", {"1": "SW11", "2": "BST11"})
part("L102", {"1": "SW11", "2": "+1V1"})
part("C120", {"1": "+1V1", "2": "GND"})
part("C121", {"1": "+1V1", "2": "GND"})
part("R118", {"1": "+1V1", "2": "FB11"})                                    # 4.3k
part("R119", {"1": "FB11", "2": "GND"})                                     # 10k -> 1.098 V
# --- power LED
part("R120", {"1": "+3V3", "2": "PWR_LED"})
part("D108", {"2": "PWR_LED", "1": "GND"})

# ======================================================================= switch.kicad_sch (3xx)
PWR = {"DVDDL": ["20", "21", "22", "23", "76", "78", "92", "95"],
       "AVDDL": ["10", "18", "29", "39", "49", "59", "107", "117", "128"],
       "AVDDH": ["5", "15", "19", "24", "34", "54", "64", "96", "102", "112"]}
u = {}
u.update({n: "+1V1" for n in PWR["DVDDL"]})
u.update({n: "+1V1A" for n in PWR["AVDDL"]})
u.update({n: "+3V3A" for n in PWR["AVDDH"]})
u.update({"122": "+1V1P", "44": "+1V1P", "77": "+3V3", "16": "GND", "129": "GND"})
u.update({"98": "XTALI", "97": "XTALO", "99": "SW_NRST", "100": "SW_SCL", "101": "SW_SDA", "17": "MDIREF"})
u.update({"94": "P1_LNK", "93": "P1_SPD", "91": "STRAP_EN_PHY", "89": "P2_LNK", "90": "P2_SPD", "88": "STRAP_SMI_SEL1",
          "86": "P3_LNK", "87": "P3_SPD", "85": "STRAP_DIS_8051", "84": "P4_LNK", "82": "P4_SPD",
          "80": "P5_LNK", "81": "P5_SPD", "74": "P6_LNK", "75": "P6_SPD", "71": "SW_GPIO1"})
part("U301", u)
part("FB301", {"1": "+1V1", "2": "+1V1A"})
part("FB302", {"1": "+1V1", "2": "+1V1P"})
part("FB303", {"1": "+3V3", "2": "+3V3A"})
for i in range(301, 310):
    part("C%d" % i, {"1": "+1V1", "2": "GND"})
for i in range(310, 320):
    part("C%d" % i, {"1": "+1V1A", "2": "GND"})
for i in range(320, 331):
    part("C%d" % i, {"1": "+3V3A", "2": "GND"})
for i in range(331, 334):
    part("C%d" % i, {"1": "+1V1P", "2": "GND"})
part("C334", {"1": "+3V3", "2": "GND"})
part("Y301", {"1": "XTALI", "3": "XTALO", "2": "GND", "4": "GND"})
part("C335", {"1": "XTALI", "2": "GND"})
part("C336", {"1": "XTALO", "2": "GND"})
part("R301", {"1": "+3V3", "2": "SW_NRST"})
part("C337", {"1": "SW_NRST", "2": "GND"})
part("R302", {"1": "SW_NRST", "2": "SW_RST_N"})
part("R303", {"1": "+3V3", "2": "SW_SCL"})
part("R304", {"1": "+3V3", "2": "SW_SDA"})
part("R305", {"1": "MDIREF", "2": "GND"})                                   # 2.49k 1%
part("R306", {"1": "P1_LNK", "2": "GND"})                                   # SMI_SEL0 = 0
part("R307", {"1": "STRAP_EN_PHY", "2": "+3V3"})                            # EN_PHY = 1
part("R308", {"1": "P2_LNK", "2": "+3V3"})                                  # MID29 = 1 (unused in I2C mode)
part("R309", {"1": "STRAP_SMI_SEL1", "2": "GND"})                           # SMI_SEL[1:0] = 00 -> I2C, LSB first
part("R310", {"1": "P3_LNK", "2": "GND"})                                   # DISAUTOLOAD = 0 -> EEPROM autoload
part("R311", {"1": "STRAP_DIS_8051", "2": "+3V3"})                          # DIS_8051 = 1: EEPROM = registers
part("R314", {"1": "STRAP_DIS_8051", "2": "GND"})                           # DNP option: run 8051 code from EEPROM
part("R312", {"1": "P4_LNK", "2": "GND"})                                   # EN_FLASH = 0
part("R313", {"1": "P5_LNK", "2": "+3V3"})                                  # EEPROM_MOD = 1 (24C32+, 2-byte address)
# configuration EEPROM (autoload at reset; written by the MCU or through J302)
part("U302", {"8": "+3V3", "4": "GND", "1": "GND", "2": "GND", "3": "GND", "6": "SW_SCL", "5": "SW_SDA", "7": "EE_WP"})
part("C338", {"1": "+3V3", "2": "GND"})
part("R315", {"1": "EE_WP", "2": "GND"})
part("J302", {"1": "+3V3", "2": "SW_SCL", "3": "SW_SDA", "4": "SW_RST_N", "5": "GND"})

# ======================================================================= ports.kicad_sch (4xx)
MDI = {0: [103, 104, 105, 106, 108, 109, 110, 111], 1: [113, 114, 115, 116, 118, 119, 120, 121],
       2: [124, 125, 126, 127, 1, 2, 3, 4], 3: [6, 7, 8, 9, 11, 12, 13, 14], 4: [25, 26, 27, 28, 30, 31, 32, 33],
       5: [35, 36, 37, 38, 40, 41, 42, 43], 6: [45, 46, 47, 48, 50, 51, 52, 53], 7: [55, 56, 57, 58, 60, 61, 62, 63]}
TD = ["2", "3", "5", "6", "8", "9", "11", "12"]          # GST5009 TD1+ .. TD4-
MX = ["23", "22", "20", "19", "17", "16", "14", "13"]    # GST5009 MX1+ .. MX4-
JP = ["1", "2", "3", "6", "4", "5", "7", "8"]            # RJ45 contacts for pairs A, B, C, D
SIG = ["AP", "AN", "BP", "BN", "CP", "CN", "DP", "DN"]
for k in range(1, 7):
    p = k - 1
    tr, j = "TR40%d" % k, "J40%d" % k
    t, jj = {}, {}
    for i in range(8):
        part("U301", {str(MDI[p][i]): "P%d_MDI_%s" % (k, SIG[i])})
        t[TD[i]] = "P%d_MDI_%s" % (k, SIG[i])
        t[MX[i]] = "P%d_LINE_%s" % (k, SIG[i])
        jj[JP[i]] = "P%d_LINE_%s" % (k, SIG[i])
    for n, ct in (("1", 1), ("4", 2), ("7", 3), ("10", 4)):
        t[n] = "P%d_TCT%d" % (k, ct)
        part("C4%d%d" % (k, ct), {"1": "P%d_TCT%d" % (k, ct), "2": "GND"})
    for n, ct in (("24", 1), ("21", 2), ("18", 3), ("15", 4)):
        if k == 1:
            t[n] = "POE_CT%d" % ct
        else:
            t[n] = "P%d_MCT%d" % (k, ct)
            part("R4%d%d" % (k, ct), {"1": "P%d_MCT%d" % (k, ct), "2": "P%d_BS" % k})
    if k != 1:
        part("C4%d5" % k, {"1": "P%d_BS" % k, "2": "CHASSIS"})
    part(tr, t)
    # LEDs: yellow = 1000M (active low), green = link/act (active high on ports 1, 3, 4: strap pull-downs)
    jj.update({"9": "+3V3", "10": "P%d_Y_K" % k, "13": "CHASSIS"})
    part("R4%d5" % k, {"1": "P%d_Y_K" % k, "2": "P%d_SPD" % k})
    if k in (1, 3, 4):
        jj.update({"11": "P%d_G_A" % k, "12": "GND"})
        part("R4%d6" % k, {"1": "P%d_LNK" % k, "2": "P%d_G_A" % k})
    else:
        jj.update({"11": "+3V3", "12": "P%d_G_K" % k})
        part("R4%d6" % k, {"1": "P%d_G_K" % k, "2": "P%d_LNK" % k})
    part(j, jj)
part("U301", {"55": "MG_AP", "56": "MG_AN", "57": "MG_BP", "58": "MG_BN"})
part("C401", {"1": "CHASSIS", "2": "GND"})                                  # 1nF 2kV
part("R401", {"1": "CHASSIS", "2": "GND"})                                  # 1M
for h in ("H401", "H402", "H403", "H404"):
    part(h, {"1": "CHASSIS"})

# ======================================================================= mgmt.kicad_sch (5xx)
part("U501", {"13": "+3V3", "27": "+3V3", "4": "+3V3", "29": "GND", "21": "VINTA", "2": "OSC_IN", "3": "OSC_OUT",
              "26": "BOOT0", "5": "SW_RST_N", "6": "EE_WP", "7": "UART_TX", "8": "UART_RX", "24": "SW_SCL", "25": "SW_SDA",
              "10": "LED_SYS", "11": "BTN_RST", "12": "SW_GPIO1", "20": "SWDIO", "23": "SWCLK",
              "16": "ETH_TXP", "17": "ETH_TXN", "14": "ETH_RXP", "15": "ETH_RXN"})
for c in ("C501", "C502", "C503", "C504"):
    part(c, {"1": "+3V3", "2": "GND"})
part("C505", {"1": "VINTA", "2": "GND"})
part("Y501", {"1": "OSC_IN", "3": "OSC_OUT", "2": "GND", "4": "GND"})
part("R501", {"1": "BOOT0", "2": "GND"})                                    # 510k
part("SW501", {"1": "+3V3", "2": "+3V3", "3": "BOOT0", "4": "BOOT0"})
part("R502", {"1": "LED_SYS", "2": "LED_SYS_A"})
part("D501", {"2": "LED_SYS_A", "1": "GND"})
part("SW502", {"1": "GND", "2": "GND", "3": "BTN_RST", "4": "BTN_RST"})
part("J501", {"1": "+3V3", "2": "UART_TX", "3": "UART_RX", "4": "SWDIO", "5": "SWCLK", "6": "GND"})
part("TR501", {"2": "ETH_TXP", "3": "ETH_TXN", "5": "ETH_RXP", "6": "ETH_RXN", "1": "+3V3", "4": "+3V3",
               "23": "MG_BP", "22": "MG_BN", "20": "MG_AP", "19": "MG_AN", "24": "MG_MCT1", "21": "MG_MCT2"})
part("C506", {"1": "+3V3", "2": "GND"})
part("C507", {"1": "MG_MCT1", "2": "GND"})
part("C508", {"1": "MG_MCT2", "2": "GND"})
