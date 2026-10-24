"""Check the exported KiCad netlist against the design intent.

* every FPGA ball in design.PINS sits on a net together with exactly the peripheral pins listed in PERIPH
* power balls sit on their rail, spare balls are unconnected
* a hand list of the local nets on the sub-sheets (USB, FT2232H, EEPROM, crystal, regulators, DAC, ...)
Usage: check_netlist.py  (exports the netlist with kicad-cli first).
"""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, find, find_all, unq
import design as D

PRJ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

# ---------------------------------------------------------------- peripheral end of every FPGA signal
PERIPH = {}
for k, n in {"CH_TXD": 19, "CH_RXD": 22, "CH_RTS": 18, "CH_CTS": 17, "CH_SCS": 13, "CH_SCK": 14, "CH_MOSI": 16,
             "CH_MISO": 15}.items():
    PERIPH[k] = ["U301.%d" % n]
for k, n in enumerate([n for n in range(3, 39) if n not in (19, 20)]):
    PERIPH["GPIO%d" % k] = ["J606.%d" % n]
for k in range(8):
    PERIPH["LED%d" % k] = ["R%d.1" % (601 + k)]
    PERIPH["SW%d" % k] = ["RN%d.%d" % (601 + k // 4, k % 4 + 1)]
for k, s in enumerate(("A", "B", "C", "D", "E", "F", "G", "DP")):
    PERIPH["SEG_" + s] = ["RN%d.%d" % (603 + k // 4, k % 4 + 1)]
for k in range(4):
    PERIPH["DIG%d" % k] = ["R%d.1" % (613 + k)]
    PERIPH["BTN%d" % k] = ["R%d.2" % (609 + k), "SW%d.2" % (602 + k)]
PERIPH["CLK25"] = ["R109.2"]
ram = {"RAM_BA0": 20, "RAM_BA1": 21, "RAM_CSn": 19, "RAM_CKE": 37, "RAM_CLK": 38, "RAM_DQML": 15, "RAM_DQMH": 39,
       "RAM_WEn": 16, "RAM_CASn": 17, "RAM_RASn": 18}
for i, n in enumerate((23, 24, 25, 26, 29, 30, 31, 32, 33, 34, 22, 35)):
    ram["RAM_A%d" % i] = n
for i, n in enumerate((2, 4, 5, 7, 8, 10, 11, 13, 42, 44, 45, 47, 48, 50, 51, 53)):
    ram["RAM_DQ%d" % i] = n
for k, n in ram.items():
    PERIPH[k] = ["U401.%d" % n]
for k, n in {"SD_D2": 1, "SD_D3": 2, "SD_CMD": 3, "SD_CLK": 5, "SD_D0": 7, "SD_D1": 8, "SD_CD": 9}.items():
    PERIPH[k] = ["J601.%d" % n]
PERIPH["AUDIO_L"], PERIPH["AUDIO_R"] = ["R519.1"], ["R520.1"]
for j, name in enumerate("ABCD"):
    for i, n in enumerate((1, 3, 5, 7, 2, 4, 6, 8)):
        PERIPH["PMOD%s%d" % (name, i)] = ["J%d.%d" % (602 + j, n)]
for k, n in {"HDMI_D2_P": 1, "HDMI_D2_N": 3, "HDMI_D1_P": 4, "HDMI_D1_N": 6, "HDMI_D0_P": 7, "HDMI_D0_N": 9,
             "HDMI_CK_P": 10, "HDMI_CK_N": 12}.items():
    PERIPH[k] = ["J502.%d" % n]
PERIPH["HDMI_SCL"], PERIPH["HDMI_SDA"] = ["J502.15", "R515.2"], ["J502.16", "R516.2"]
PERIPH["HDMI_HPD"] = ["R517.1", "R518.1"]
for c, r0 in (("R", 501), ("G", 505), ("B", 509)):
    for k in range(4):
        PERIPH["VGA_%s%d" % (c, 3 - k)] = ["R%d.1" % (r0 + k)]
PERIPH["VGA_HS"], PERIPH["VGA_VS"] = ["R513.2"], ["R514.2"]
for k, n in {"FLASH_CSn": 1, "FLASH_CLK": 6, "FLASH_IO0": 5, "FLASH_IO1": 2, "FLASH_IO2": 3, "FLASH_IO3": 7}.items():
    PERIPH[k] = ["U101.%d" % n]
PERIPH["FLASH_CSn"].append("R101.2")
PERIPH["PROGRAMN"] = ["R105.2", "SW101.2"]
PERIPH["INITN"] = ["R106.2"]
PERIPH["DONE"] = ["R107.2", "Q101.1"]
PERIPH["CFG0"], PERIPH["CFG1"], PERIPH["CFG2"] = ["R102.1"], ["R103.2"], ["R104.1"]
PERIPH["JTAG_TCK"] = ["U301.23", "J302.2", "R110.1"]
PERIPH["JTAG_TDI"] = ["U301.25", "J302.3", "R112.2"]
PERIPH["JTAG_TDO"] = ["U301.24", "J302.4"]
PERIPH["JTAG_TMS"] = ["U301.26", "J302.5", "R111.2"]

# ---------------------------------------------------------------- local nets on the sub-sheets
SAME = {
    "VBUS": ["J301.A4", "J301.A9", "J301.B4", "J301.B9", "F301.1"],
    "+5V": ["F301.2", "C301.1", "U302.5", "U201.4", "U202.4", "R201.1", "R204.1", "D501.2", "J606.1"],
    "CC1": ["J301.A5", "R302.1"], "CC2": ["J301.B5", "R303.1"],
    # USBLC6-2SC6 is flow-through: pins 1/6 (and 3/4) are joined inside the part, so each line is two nets
    "USB_DN": ["J301.A7", "J301.B7", "U302.1"], "USB_DN_CH": ["U302.6", "U301.27"],
    "USB_DP": ["J301.A6", "J301.B6", "U302.3"], "USB_DP_CH": ["U302.4", "U301.28"],
    "XI": ["U301.1", "Y301.1", "C302.1"], "XO": ["U301.2", "Y301.3", "C303.1"],
    "+3V3": ["L201.2", "R202.1", "C203.1", "C204.1", "C205.1", "U203.1", "C304.1", "C305.1",
             "U101.8", "U401.1", "U401.3", "U301.21", "U301.6", "J302.1", "J601.4", "J606.2", "J602.11", "J605.12", "R609.1",
             "Q601.2", "SW601.16", "U1.F7", "U1.L6", "U1.H6", "X101.4", "X101.1", "R103.1"],
    "+1V1": ["L202.2", "R205.1", "U1.L10", "U1.G6", "C220.1"],
    "+2V5": ["U203.5", "U1.G11", "U1.L7", "C230.1"],
    "SW33": ["U201.3", "L201.1"], "FB33": ["U201.5", "R202.2", "R203.1", "C203.2"], "EN33": ["U201.1", "R201.2"],
    "SW11": ["U202.3", "L202.1"], "FB11": ["U202.5", "R205.2", "R206.1", "C208.2"], "EN11": ["U202.1", "R204.2"],
    "OSC_OUT": ["X101.3", "R109.1"],
    "DONE_LED": ["Q101.3", "D101.1"], "DONE_R": ["D101.2", "R108.2"],
    "VGA_RED": ["R501.2", "R502.2", "R503.2", "R504.2", "J501.1"],
    "VGA_GRN": ["R505.2", "R506.2", "R507.2", "R508.2", "J501.2"],
    "VGA_BLU": ["R509.2", "R510.2", "R511.2", "R512.2", "J501.3"],
    "HS_C": ["R513.1", "J501.13"], "VS_C": ["R514.1", "J501.14"],
    "HPD_5V": ["J502.19", "R517.2"], "HDMI_5V": ["J502.18", "D501.1"],
    "AL1": ["R519.2", "C501.1", "C503.1"], "AL2": ["C503.2", "J503.T"],
    "AR1": ["R520.2", "C502.1", "C504.1"], "AR2": ["C504.2", "J503.R"],
    "GND": ["J301.A1", "J301.SH", "U1.A1", "U1.T16", "U1.N2", "U401.28", "U401.6", "U301.20", "U101.4", "J501.5", "J501.6", "J501.SH", "J502.17", "J502.2", "J503.S", "J601.6", "J602.9",
            "J605.10", "J606.19", "J606.40", "SW602.1", "R102.2", "R110.2", "R302.2", "Y301.2", "U301.29"],
}
for k in range(8):
    SAME["SWC%d" % k] = ["RN%d.%d" % (601 + k // 4, 8 - k % 4), "SW601.%d" % (k + 1)]
    SAME["LEDA%d" % k] = ["R%d.2" % (601 + k), "D%d.2" % (601 + k)]
segpins = (11, 7, 4, 2, 1, 10, 5, 3)
for k in range(8):
    SAME["SEGC%d" % k] = ["RN%d.%d" % (603 + k // 4, 8 - k % 4), "DS601.%d" % segpins[k]]
for i, ca in enumerate((12, 9, 8, 6)):
    SAME["CA%d" % (i + 1)] = ["Q%d.3" % (601 + i), "DS601.%d" % ca]
    SAME["QB%d" % i] = ["Q%d.1" % (601 + i), "R%d.2" % (613 + i)]
OPEN = ["U301.%d" % n for n in (3, 4, 5, 7, 8, 9, 10, 11, 12)]
OPEN += ["J501.%d" % n for n in (4, 9, 11, 12, 15)] + ["J502.13", "J502.14", "J301.A8", "J301.B8"]
OPEN += ["U1.%s" % b for b in D.SPARE]
BIG = ("GND", "+3V3", "+1V1", "+2V5", "+5V")


def main():
    out = os.path.join(tempfile.gettempdir(), "ecp5_board.net")
    subprocess.run([CLI, "sch", "export", "netlist", "-o", out, os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_sch")],
                   check=True, capture_output=True)
    tree = parse(open(out, encoding="utf-8").read())[0]
    netof, members = {}, {}
    for net in find_all(find(tree, "nets"), "net"):
        name = unq(find(net, "name")[1])
        for nd in find_all(net, "node"):
            key = "%s.%s" % (unq(find(nd, "ref")[1]), unq(find(nd, "pin")[1]))
            netof[key] = name
            members.setdefault(name, set()).add(key)
    bad = 0

    def group(label, pins, exact=True):
        nonlocal bad
        nets = {netof.get(p, "<missing %s>" % p) for p in pins}
        if len(nets) != 1:
            bad += 1
            print("MISMATCH %-12s %s" % (label, {p: netof.get(p) for p in pins}))
            return
        n = nets.pop()
        extra = members[n] - set(pins)
        if exact and extra:
            bad += 1
            print("EXTRA    %-12s %s has also %s" % (label, n, sorted(extra)))

    assert set(PERIPH) == set(D.PINS.values()), set(PERIPH) ^ set(D.PINS.values())
    for ball, sig in D.PINS.items():
        group(sig, ["U1." + ball] + PERIPH[sig])
    for rail, balls in D.POWER.items():
        group(rail, ["U1." + b for b in balls], exact=False)
    for label, pins in SAME.items():
        group(label, pins, exact=label not in BIG)
    for p in OPEN:
        n = netof.get(p)
        if n and len(members[n]) > 1:
            bad += 1
            print("NOT OPEN %s on %s with %s" % (p, n, sorted(members[n])))
    single = sorted(n for n, m in members.items() if len(m) == 1 and not n.startswith("unconnected-"))
    if single:
        print("single-pin nets:", single)
        bad += len(single)
    parts = {k.split(".")[0] for k in netof}
    print("nets %d, parts with pins %d, FPGA signals %d, local groups %d, problems %d" % (
        len(members), len(parts), len(D.PINS), len(SAME), bad))
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
