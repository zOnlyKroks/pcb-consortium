"""PowerbankV2 design truth: every part's intended pin -> net map.

check_netlist.py compares the exported KiCad netlist with this table (as pin groups, so net names may differ where
the sheet leaves a net unlabelled).  Written from the datasheets / TIDA-050047, not from the generator.

Nets: VBAT = pack + after the fuse, GND = PACK- (system ground, low-side protection FETs), BATN = cell stack
bottom (BQ77915 VSS), +5V = PP5V rail of both PD controllers, +3V3 = VIN_3V3 rail.
"""

NETS = {}


def part(ref, pins):
    NETS.setdefault(ref, {}).update(pins)


def two(ref, a, b):
    part(ref, {"1": a, "2": b})


# ======================================================================= battery.kicad_sch (1xx)
# 4S2P: BT101/102 bottom group ... BT107/108 top group. Battery_Cell pin 1 = +, pin 2 = -
for i, (top, bot) in enumerate((("CELL1", "BATN"), ("CELL2", "CELL1"), ("CELL3", "CELL2"), ("CELL4", "CELL3"))):
    two("BT1%02d" % (2 * i + 1), top, bot)
    two("BT1%02d" % (2 * i + 2), top, bot)
two("F101", "CELL4", "VBAT")                                    # 20 A
part("U101", {"1": "BMS_VDD", "2": "BMS_AVDD", "3": "VC4_F", "4": "VC4_F", "5": "VC3_F", "6": "VC2_F",
              "7": "VC1_F", "8": "VC0_F", "9": "BATN", "10": "SRP_F", "11": "SRN_F", "12": "DSG_DRV",
              "13": "CHG_DRV", "14": "LD", "16": "CBI", "17": "OCDP", "18": "BMS_TS", "19": "BMS_VTB",
              "20": "BMS_AVDD", "22": "BMS_PRES", "23": "BATN", "24": "BATN"})   # 15 LPWR, 21 CBO open
two("R101", "CELL4", "BMS_VDD")                                 # RVDD 1k
two("C101", "BMS_VDD", "BATN")                                  # 1uF
two("C102", "BMS_AVDD", "BATN")                                 # 1uF
two("R102", "CELL4", "VC4_F")                                   # RIN 100R (sets ~20 mA balancing)
two("R103", "CELL3", "VC3_F")
two("R104", "CELL2", "VC2_F")
two("R105", "CELL1", "VC1_F")
two("R106", "BATN", "VC0_F")
two("C103", "VC4_F", "VC3_F")                                   # CIN 100nF ladder (bq77915 fig 9-12)
two("C104", "VC3_F", "VC2_F")
two("C105", "VC2_F", "VC1_F")
two("C106", "VC1_F", "BATN")
two("C107", "BATN", "VC0_F")
two("R107", "BMS_VDD", "BMS_PRES")                              # RHIB 10k: PRES high = NORMAL mode
two("R108", "BMS_VTB", "BMS_TS")                                # RTS_PU 10k
two("RT101", "BMS_TS", "BATN")                                  # 10k NTC
two("R109", "OCDP", "BATN")                                     # ROCD 100k
two("R110", "CBI", "BATN")                                      # RCB 10k: balancing on
two("R111", "BATN", "SNS_N")                                    # RSNS 2 mOhm
two("R112", "BATN", "SRP_F")                                    # RS 100R
two("R113", "SNS_N", "SRN_F")
two("C108", "SRP_F", "SRN_F")
two("C109", "SRP_F", "BATN")
two("C110", "SRN_F", "BATN")
part("Q101", {"4": "DSG_G", "1": "SNS_N", "2": "SNS_N", "3": "SNS_N", **{n: "FET_D" for n in "56789"}})
part("Q102", {"4": "CHG_G", "1": "GND", "2": "GND", "3": "GND", **{n: "FET_D" for n in "56789"}})
two("R114", "DSG_DRV", "DSG_G")                                 # RDSG 4.7k
two("R115", "DSG_G", "SNS_N")                                   # RGS 1M
two("R116", "CHG_DRV", "CHG_G")                                 # RCHG 1k
two("R117", "CHG_G", "GND")                                     # RGS 1M (charger connect for UV recovery)
two("R118", "LD", "GND")                                        # RLD 470k


# ======================================================================= port_a / port_b (2xx / 3xx)
def port(n, s, addr_hi):
    """n = ref hundreds (2 or 3), s = net suffix ('A'/'B'); addr_hi -> ADCIN1 to LDO_3V3 (I2Ct 0x20) else GND (0x21)."""
    def r(k):
        return "%d%02d" % (n, k)
    VBUS, PPHV, L3, L15 = "VBUS_" + s, "PPHV_" + s, "LDO3V3_" + s, "LDO1V5_" + s
    SCL, SDA, INT, EE = "I2CC_SCL_" + s, "I2CC_SDA_" + s, "CHG_INT_" + s, "EE_VCC_" + s
    usb = {p: VBUS for p in ("A4", "A9", "B4", "B9")}
    usb.update({p: "GND" for p in ("A1", "A12", "B1", "B12", "SH")})
    usb.update({"A5": "CC1_" + s, "B5": "CC2_" + s, "A6": "DP_" + s, "B6": "DP_" + s, "A7": "DM_" + s,
                "B7": "DM_" + s})
    part("J" + r(1), usb)
    part("D" + r(1), {"4": VBUS, "5": VBUS, "6": VBUS, "1": "GND", "2": "GND", "3": "GND", "7": "GND"})  # TVS2200
    two("C" + r(1), VBUS, "GND")                                # CVBUS 10uF 50V
    gp = {"5": "GP0_" + s, "6": "GP1_" + s, "7": "GP2_" + s, "19": "GP3_" + s, "37": "GP6_" + s, "36": "GP7_" + s,
          "13": "GP11_" + s}
    u = {"23": VBUS, "32": VBUS, "20": PPHV, "34": "+5V", "38": "+3V3", "1": L3, "4": L15,
         "2": L3 if addr_hi else "GND", "3": "GND", "28": "CC1_" + s, "29": "CC2_" + s, "26": "DP_" + s,
         "27": "DM_" + s, "8": "PD_SDA", "9": "PD_SCL", "10": "PD_IRQ", "16": SDA, "17": SCL, "18": INT,
         "15": "DRAIN_" + s, "30": "DRAIN_" + s, "40": "DRAIN_" + s}
    u.update({p: "GND" for p in ("11", "12", "14", "31", "39")})
    u.update(gp)
    part("U" + r(1), u)
    # unused GPIOs pulled down (datasheet: tie to GND; resistors keep it safe if the config drives one)
    # unused GPIOs pulled down (datasheet: tie to GND), one 10k each, at the pin
    for k, g in ((9, "GP0_"), (10, "GP1_"), (11, "GP2_"), (12, "GP3_"), (13, "GP6_"), (14, "GP7_"), (15, "GP11_")):
        two("R" + r(k), "GND", g + s)
    two("C" + r(2), "+3V3", "GND")                              # VIN_3V3 10uF
    two("C" + r(3), L3, "GND")                                  # LDO_3V3 10uF
    two("C" + r(4), L15, "GND")                                 # LDO_1V5 10uF
    two("C" + r(5), "+5V", "GND")                               # PP5V 10uF
    two("C" + r(6), "CC1_" + s, "GND")                          # 330pF
    two("C" + r(7), "CC2_" + s, "GND")
    for k in (8, 9, 10, 11):
        two("C" + r(k), PPHV, "GND")                            # PPHV / charger VBUS 4x10uF 50V
    two("C" + r(12), PPHV, "GND")                               # 100nF
    two("R" + r(1), SCL, L3)                                    # 2.2k
    two("R" + r(2), SDA, L3)
    two("R" + r(3), INT, L3)                                    # 10k
    part("U" + r(2), {"8": EE, "1": "GND", "2": "GND", "3": "GND", "4": "GND", "7": "GND", "5": SDA, "6": SCL})
    two("C" + r(13), EE, "GND")
    two("JP" + r(1), L3, EE)                                    # bridged solder jumper (cut to re-flash)
    part("J" + r(2), {"1": EE, "2": L3, "3": SCL, "4": SDA, "5": "GND"})   # EEPROM programming header (DNP)
    # BQ25798
    q = {"2": PPHV, "3": PPHV, "9": PPHV, "8": PPHV, "11": "GND", "10": "GND", "29": "PMID_" + s,
         "4": "BTST1_" + s, "28": "SW1_" + s, "19": "BTST2_" + s, "26": "SW2_" + s, "25": "SYS_" + s,
         "22": "VBAT", "23": "VBAT", "18": "BATP_" + s, "5": "REGN_" + s, "1": "STAT_" + s, "13": "GND",
         "14": SCL, "15": SDA, "16": "TS_" + s, "17": "REGN_" + s, "20": "PROG_" + s, "21": INT,
         "24": "SDRV_" + s, "27": "GND"}                        # 6 D+, 7 D-, 12 QON open
    part("U" + r(3), q)
    for k in (14, 15, 16):
        two("C" + r(k), "PMID_" + s, "GND")                     # 3x10uF 50V
    two("C" + r(17), "PMID_" + s, "GND")                        # 100nF
    two("C" + r(18), "BTST1_" + s, "SW1_" + s)                  # 47nF
    two("C" + r(19), "BTST2_" + s, "SW2_" + s)
    two("L" + r(1), "SW1_" + s, "SW2_" + s)                     # 2.2uH (750 kHz)
    for k in (20, 21, 22, 23, 24):
        two("C" + r(k), "SYS_" + s, "GND")                      # 5x10uF 50V
    two("C" + r(25), "SYS_" + s, "GND")                         # 100nF
    two("C" + r(26), "VBAT", "GND")                             # 2x10uF 50V
    two("C" + r(27), "VBAT", "GND")
    two("C" + r(28), "VBAT", "GND")                             # 100nF
    two("R" + r(4), "BATP_" + s, "VBAT")                        # 100R
    two("C" + r(29), "REGN_" + s, "GND")                        # 4.7uF 25V
    two("R" + r(5), "REGN_" + s, "TS_" + s)                     # 5.23k
    two("R" + r(6), "TS_" + s, "GND")                           # 30.1k
    two("RT" + r(1), "TS_" + s, "GND")                          # 10k NTC
    two("R" + r(7), "PROG_" + s, "GND")                         # 27k: 4S, 750 kHz
    two("C" + r(30), "SDRV_" + s, "GND")                        # 1nF (no ship FET)
    part("D" + r(2), {"1": "STAT_" + s, "2": "LEDA_" + s})      # charge LED (pin 1 = K) on STAT
    two("R" + r(8), "+3V3", "LEDA_" + s)                        # 1k


port(2, "A", True)
port(3, "B", False)

# ======================================================================= system.kicad_sch (4xx)
part("U401", {"2": "VBAT", "3": "EN5", "4": "SS5", "1": "BOOT5", "8": "SW5", "5": "FB5", "6": "COMP5",
              "7": "GND", "9": "GND"})                          # TPS54531
two("C401", "VBAT", "GND")                                      # 2x10uF 50V
two("C402", "VBAT", "GND")
two("C403", "VBAT", "GND")                                      # 10nF
two("R401", "VBAT", "EN5")                                      # 665k
two("R402", "EN5", "GND")                                       # 130k
two("C404", "SS5", "GND")                                       # 10nF
two("C405", "BOOT5", "SW5")                                     # 100nF
two("L401", "SW5", "+5V")                                       # 4.7uH
part("D401", {"1": "SW5", "2": "GND"})                          # SS54, K = SW
two("R403", "+5V", "FB5")                                       # 10.5k
two("R404", "FB5", "GND")                                       # 1.96k  -> 5.09 V
two("R405", "COMP5", "COMP5_R")                                 # 37.4k
two("C406", "COMP5_R", "GND")                                   # 2.2nF
two("C407", "COMP5", "GND")                                     # 22pF
for k in (408, 409, 410, 411):
    two("C%d" % k, "+5V", "GND")                                # 4x47uF 10V
part("U402", {"1": "+5V", "2": "GND", "3": "EN3V3", "5": "+3V3"})   # ME6211C33, 4 NC
two("C412", "+5V", "GND")                                       # 1uF
two("C413", "+3V3", "GND")                                      # 1uF
two("R406", "+5V", "EN3V3")                                     # 100k
part("SW401", {"1": "EN3V3", "4": "GND"})                       # PD reset
two("R407", "PD_SCL", "+3V3")                                   # 10k
two("R408", "PD_SDA", "+3V3")
two("R409", "PD_IRQ", "+3V3")
part("J401", {"1": "+3V3", "2": "PD_SCL", "3": "PD_SDA", "4": "PD_IRQ", "5": "GND"})   # host header (DNP)
# fuel gauge: button powers an LM339 + TL431 ladder, 4 LEDs at 3.09/3.40/3.61/3.81 V per cell
part("SW402", {"1": "VBAT", "4": "GAUGE_V"})
part("U403", {"3": "GAUGE_V", "12": "GND",
              "5": "REF1_G", "4": "VSENSE_G", "2": "G1_OUT",
              "7": "REF2_G", "6": "VSENSE_G", "1": "G2_OUT",
              "9": "REF3_G", "8": "VSENSE_G", "14": "G3_OUT",
              "11": "VREF_G", "10": "VSENSE_G", "13": "G4_OUT"})
two("C414", "GAUGE_V", "GND")                                   # 100nF
two("R410", "GAUGE_V", "VREF_G")                                # 4.7k
part("U404", {"1": "VREF_G", "2": "VREF_G", "3": "GND"})        # TL431 K, REF, A
two("R411", "VREF_G", "REF3_G")                                 # 1k
two("R412", "REF3_G", "REF2_G")                                 # 1k
two("R413", "REF2_G", "REF1_G")                                 # 1.5k
two("R414", "REF1_G", "GND")                                    # 15k
two("R415", "GAUGE_V", "VSENSE_G")                              # 51k
two("R416", "VSENSE_G", "GND")                                  # 10k
two("C415", "VSENSE_G", "GND")                                  # 100nF
for k in range(4):
    part("D%d" % (402 + k), {"1": "G%d_OUT" % (k + 1), "2": "GLED%d" % (k + 1)})   # K to comparator output
    two("R%d" % (417 + k), "GAUGE_V", "GLED%d" % (k + 1))       # 6.8k
for k in range(1, 5):
    part("H40%d" % k, {})                                       # M3 mounting holes
