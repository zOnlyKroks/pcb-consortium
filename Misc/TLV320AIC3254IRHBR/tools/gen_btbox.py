"""Finish TLV320AIC3254 board = Bluetooth speaker box: ESP32 (A2DP sink -> I2S) -> codec -> TPA3116D2 mono PBTL (30 W).

In-place splice into TLV320AIC3254IRHBR.kicad_sch (existing codec block, J1-J5, C1-C18 untouched except the input coupling caps).
Uses the sheet/placement helpers of the VideoConv-V1 generator.  Usage: python -I tools/gen_btbox.py
"""
import copy, math, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
GEN = os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools"))
sys.path.insert(0, GEN)
import gen_sch as g
from sexp import parse, dump, find, find_all, q, unq
SCH = os.path.join(PRJ, "TLV320AIC3254IRHBR.kicad_sch")
LCSC_SYM = os.path.join(PRJ, "libs", "lcsc", "symbols", "lcsc_imported.kicad_sym")
t = open(SCH, encoding="utf-8").read()
if "ESP32-WROOM-32E" in t:
    sys.exit("already generated")
ROOT = re.search(r'\(uuid "([0-9a-f-]{36})"\)', t).group(1)
g.PROJECT = "TLV320AIC3254IRHBR"; g.ROOT_UUID = ROOT; g.INST_PATH = "/" + ROOT
g.LIBS["lcsc_imported"] = LCSC_SYM

# ---------------------------------------------------------------- TPA3116D2DADR symbol (LCSC C50144) into the project's lcsc lib
if '(symbol "TPA3116D2DADR"' not in open(LCSC_SYM, encoding="utf-8").read():
    left = ["MODSEL", "SDZ", "FAULTZ", "RINP", "RINN", "PLIMIT", "GVDD", "GAIN/SLV", "GND", "LINP", "LINN", "MUTE", "AM2", "AM1", "AM0", "SYNC"]
    right = ["AVCC", "PVCC", "PVCC", "BSNL", "OUTNL", "GND", "OUTPL", "BSPL", "GND", "BSNR", "OUTNR", "GND", "OUTPR", "BSPR", "PVCC", "PVCC"]
    typ = {"MODSEL": "input", "SDZ": "input", "FAULTZ": "open_collector", "RINP": "input", "RINN": "input", "PLIMIT": "input", "GVDD": "power_out",
           "GAIN/SLV": "input", "GND": "power_in", "LINP": "input", "LINN": "input", "MUTE": "input", "AM2": "input", "AM1": "input", "AM0": "input",
           "SYNC": "bidirectional", "AVCC": "power_in", "PVCC": "power_in", "BSNL": "passive", "OUTNL": "output", "OUTPL": "output", "BSPL": "passive",
           "BSNR": "passive", "OUTNR": "output", "OUTPR": "output", "BSPR": "passive"}

    def pin(n, name, x, y, ang):
        return ('\t\t\t(pin %s line\n\t\t\t\t(at %s %s %s)\n\t\t\t\t(length 2.54)\n\t\t\t\t(name "%s"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n'
                '\t\t\t\t(number "%d"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t)\n') % (typ.get(name, "power_in"), x, y, ang, name, n)
    pins = ""
    for i, nm in enumerate(left):
        pins += pin(i + 1, nm, -15.24, round(19.05 - 2.54 * i, 2), 0)
    for i, nm in enumerate(right):
        pins += pin(17 + i, nm, 15.24, round(-19.05 + 2.54 * i, 2), 180)
    pins += pin(33, "PAD", 0, -27.94, 90)

    def pr(k, v, y, hide=False):
        return '\t\t(property "%s" "%s"\n\t\t\t(at 0 %s 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n%s\t\t\t)\n\t\t)\n' % (k, v, y, "\t\t\t\t(hide yes)\n" if hide else "")
    sym = ('\t(symbol "TPA3116D2DADR"\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n' + pr("Reference", "U", 25.4) + pr("Value", "TPA3116D2DADR", -30.48)
           + pr("Footprint", "lcsc_footprints:HTSSOP-32_L11.0-W6.1-P0.65-LS8.1-BL", -33, True) + pr("Datasheet", "https://www.ti.com/lit/ds/symlink/tpa3116d2.pdf", -33, True)
           + pr("Description", "2x50 W class-D amplifier, PBTL mono up to 100 W, 4.5-26 V, HTSSOP-32 PowerPAD", -33, True) + pr("LCSC Part #", "C50144", -33, True)
           + '\t\t(symbol "TPA3116D2DADR_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start -12.7 22.86)\n\t\t\t\t(end 12.7 -25.4)\n\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
           + '\t\t(symbol "TPA3116D2DADR_1_1"\n' + pins + '\t\t)\n\t)\n')
    lt = open(LCSC_SYM, encoding="utf-8").read().rstrip()
    assert lt.endswith(")")
    open(LCSC_SYM, "w", encoding="utf-8").write(lt[:-1].rstrip() + "\n" + sym + ")\n")
    g._lib_cache.pop("lcsc_imported", None)

# ---------------------------------------------------------------- helpers
sh = g.Sheet(); sh.npwr = 100
cnt = {"R": 20, "C": 20, "L": 1, "D": 10, "J": 9, "SW": 0, "Q": 0, "U": 1, "F": 0}
STUB = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}      # outward direction (screen coords) for a lib pin angle
LABEL_ANG = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}
RAILS = {"GND", "+3V3", "+24V"}
names = {}


def ref(p):
    cnt[p] = cnt.get(p, 0) + 1
    return "%s%d" % (p, cnt[p])


def part(prefix, lib, x, y, value, fp="", rot=0, lcsc="", r=None, extra=None):
    r = r or ref(prefix)
    sh.add(r, lib, x, y, rot=rot, value=value, fp=fp, lcsc=lcsc, fields="R", extra=extra or {}, key=r)
    p = sh.parts[r]
    nm, ang = {}, {}
    for sub in find_all(p["sym"], "symbol"):
        for pn in find_all(sub, "pin"):
            nm.setdefault(unq(find(pn, "name")[1]), []).append(unq(find(pn, "number")[1]))
            ang[unq(find(pn, "number")[1])] = int(round(float(find(pn, "at")[3])))
    names[r] = nm
    p["ang"] = ang
    return r


def out_dir(k, num):
    a = (sh.parts[k]["ang"][str(num)] + sh.parts[k]["rot"]) % 360
    return STUB[a]


def attach(pt, d, net):
    if net in RAILS:
        gnd = {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}
        vcc = {(0, -1): 0, (0, 1): 180, (-1, 0): 90, (1, 0): 270}
        sh.power(net, pt, (gnd if net == "GND" else vcc)[d])
    else:
        sh.label(net, pt, LABEL_ANG[d])


def conn(k, mapping):
    """mapping {pin number or pin name: net}: rails -> power symbol, everything else -> net label, at the pin end."""
    for key, net in mapping.items():
        nums = [str(key)] if str(key) in sh.parts[k]["pins"] else names[k][key]
        done = set()
        for n in nums:
            pt = sh.pin(k, n)
            if pt in done:
                continue
            done.add(pt)
            attach(pt, out_dir(k, n), net)


def nc(k, *keys):
    for key in keys:
        for n in ([str(key)] if str(key) in sh.parts[k]["pins"] else names[k][key]):
            sh.nc(sh.pin(k, n))


def two(prefix, lib, x, y, value, fp, a, b, rot=0, lcsc=""):
    k = part(prefix, lib, x, y, value, fp, rot, lcsc)
    conn(k, {"1": a, "2": b})
    return k


R0603 = "Resistor_SMD:R_0603_1608Metric"; C0603 = "Capacitor_SMD:C_0603_1608Metric"; C0805 = "Capacitor_SMD:C_0805_2012Metric"
CP = "Capacitor_SMD:CP_Elec_10x10.5"
R = lambda x, y, v, a, b, rot=0: two("R", "Device:R", x, y, v, R0603, a, b, rot)
C = lambda x, y, v, a, b, fp=C0603: two("C", "Device:C", x, y, v, fp, a, b)

# ================================================================ power: 24 V in, protection, 3.3 V buck
j = part("J", "Connector:Barrel_Jack", 260.35, 50.8, "24V DC in", "Connector_BarrelJack:BarrelJack_Horizontal")
conn(j, {"1": "VIN24", "2": "GND"})
two("F", "Device:Fuse", 292.1, 50.8, "4A PTC", "Fuse:Fuse_1812_4532Metric", "VIN24", "VIN24F")
two("D", "Device:D_Schottky", 317.5, 50.8, "SS54", "Diode_SMD:D_SMA", "+24V", "VIN24F")           # K=pin1 -> +24V, A=pin2
two("D", "Device:D_TVS", 342.9, 50.8, "SMAJ26A", "Diode_SMD:D_SMA", "+24V", "GND")
two("C", "Device:C_Polarized", 368.3, 50.8, "220uF 35V", CP, "+24V", "GND")
C(393.7, 50.8, "100nF 50V", "+24V", "GND", C0805)
sh.power("FLAG", (419.1, 50.8), 0); sh.label("+24V", (419.1, 50.8), 90)
u4 = part("U", "Regulator_Switching:AP63203WU", 281.94, 96.52, "AP63203WU-7", "Package_TO_SOT_SMD:TSOT-23-6", lcsc="C780769")
conn(u4, {"IN": "+24V", "EN": "BUCK_EN", "GND": "GND", "SW": "BUCK_SW", "BST": "BUCK_BST", "FB": "+3V3"})
R(313.69, 96.52, "100k", "+24V", "BUCK_EN")
C(332.74, 96.52, "10uF 50V", "+24V", "GND", "Capacitor_SMD:C_1206_3216Metric")
C(345.44, 96.52, "10uF 50V", "+24V", "GND", "Capacitor_SMD:C_1206_3216Metric")
C(358.14, 96.52, "100nF", "BUCK_BST", "BUCK_SW")
two("L", "Device:L", 373.38, 96.52, "4.7uH 3A", "Inductor_SMD:L_Bourns-SRN6028", "BUCK_SW", "+3V3")
C(391.16, 96.52, "22uF", "+3V3", "GND", C0805)
C(403.86, 96.52, "22uF", "+3V3", "GND", C0805)
sh.power("FLAG", (421.64, 96.52), 0); sh.label("+3V3", (421.64, 96.52), 90)
sh.power("FLAG", (434.34, 96.52), 0); sh.label("GND", (434.34, 96.52), 90)

# ================================================================ ESP32 (A2DP sink, I2S master) + UI
u2 = part("U", "RF_Module:ESP32-WROOM-32E", 281.94, 190.5, "ESP32-WROOM-32E-N4", "RF_Module:ESP32-WROOM-32E", lcsc="C701341")
conn(u2, {"VDD": "+3V3", "[1,15,38,39]": "GND", "EN": "EN", "SENSOR_VP": "POT_VOL", "SENSOR_VN": "POT_BT", "IO34": "POT_LINE", "IO35": "I2S_DIN", "IO32": "POT_TONE",
          "IO33": "POT_SPARE", "IO25": "I2S_WS", "IO26": "I2S_DOUT", "IO27": "I2S_BCLK", "IO14": "BTN_PREV", "IO13": "BTN_PLAY", "IO0": "I2S_MCLK",
          "IO2": "LED", "IO4": "BTN_NEXT", "IO17": "CODEC_RST", "IO18": "AMP_SD", "IO21": "I2C_SDA", "IO22": "I2C_SCL", "IO23": "AMP_FAULT",
          "RXD0/IO3": "UART_RX", "TXD0/IO1": "UART_TX"})
nc(u2, "IO12", "IO15", "IO16", "IO5", "IO19")
C(325.12, 152.4, "10uF", "+3V3", "GND", C0805); C(337.82, 152.4, "100nF", "+3V3", "GND")
R(350.52, 152.4, "10k", "+3V3", "EN"); C(363.22, 152.4, "1uF", "EN", "GND")
for i, (nm, net) in enumerate([("EN", "EN"), ("BOOT", "I2S_MCLK"), ("PLAY", "BTN_PLAY"), ("PREV", "BTN_PREV"), ("NEXT", "BTN_NEXT")]):
    k = part("SW", "Switch:SW_Push", 386.08 + 25.4 * i, 152.4, nm, "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", rot=90)
    conn(k, {"1": net, "2": "GND"})
R(514.35, 152.4, "1k", "LED", "LED_A", 0)
k = part("D", "Device:LED", 527.05, 152.4, "STATUS", "LED_SMD:LED_0603_1608Metric", rot=90)
conn(k, {"2": "LED_A", "1": "GND"})
R(542.29, 152.4, "4.7k", "+3V3", "I2C_SDA"); R(554.99, 152.4, "4.7k", "+3V3", "I2C_SCL"); R(567.69, 152.4, "10k", "+3V3", "CODEC_RST")
jp = part("J", "Connector:Conn_01x06_Pin", 330.2, 228.6, "UART / flash", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical")
conn(jp, {"1": "GND", "2": "UART_TX", "3": "UART_RX", "4": "EN", "5": "I2S_MCLK", "6": "+3V3"})
for i, nm in enumerate(["POT_VOL", "POT_BT", "POT_LINE", "POT_TONE", "POT_SPARE"]):
    x = 365.76 + 30.48 * i
    k = part("J", "Connector:Conn_01x03_Pin", x, 228.6, nm.replace("POT_", "Pot "), "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical")
    conn(k, {"1": "+3V3", "2": nm, "3": "GND"})
    C(x + 12.7, 254, "100nF", nm, "GND")
jin = part("J", "Connector_Audio:AudioJack3", 254, 228.6, "AUX IN", "Connector_Audio:Jack_3.5mm_CUI_SJ1-3524N_Horizontal")
conn(jin, {"T": "AIN_L", "R": "AIN_R", "S": "GND"})

# ================================================================ TPA3116D2 mono PBTL amp
u3 = part("U", "lcsc_imported:TPA3116D2DADR", 281.94, 342.9, "TPA3116D2DADR", "lcsc_footprints:HTSSOP-32_L11.0-W6.1-P0.65-LS8.1-BL", lcsc="C50144")
conn(u3, {"MODSEL": "GND", "SDZ": "AMP_SDZ", "FAULTZ": "AMP_FAULT", "RINP": "AMP_INP", "RINN": "AMP_INN", "PLIMIT": "GVDD", "GVDD": "GVDD", "GAIN/SLV": "AMP_GAIN",
          "LINP": "GND", "LINN": "GND", "MUTE": "AMP_MUTE", "AM2": "GND", "AM1": "GND", "AM0": "GND", "AVCC": "AMP_AVCC", "PVCC": "+24V",
          "BSNL": "BSNL", "BSPL": "BSPL", "BSNR": "BSNR", "BSPR": "BSPR", "OUTNL": "SPKN", "OUTPL": "SPKN", "OUTNR": "SPKP", "OUTPR": "SPKP", "PAD": "GND",
          "GND": "GND"})
nc(u3, "SYNC")
x0 = 330.2
C(x0, 322.58, "1uF", "AIN_AMP", "AMP_INP", C0805); C(x0 + 12.7, 322.58, "1uF", "AMP_INN", "GND", C0805)
R(x0 + 25.4, 322.58, "20k", "AMP_GAIN", "GND"); R(x0 + 38.1, 322.58, "100k", "AMP_GAIN", "GVDD"); C(x0 + 50.8, 322.58, "1uF", "GVDD", "GND", C0805)
R(x0 + 63.5, 322.58, "100k", "+24V", "AMP_SDZ"); R(x0 + 76.2, 322.58, "100k", "AMP_MUTE", "GND"); R(x0 + 88.9, 322.58, "10k", "+3V3", "AMP_FAULT")
q1 = part("Q", "Transistor_FET:2N7002", x0 + 114.3, 322.58, "2N7002", "Package_TO_SOT_SMD:SOT-23")
conn(q1, {"D": "AMP_SDZ", "S": "GND", "G": "AMP_SD"})
R(x0 + 139.7, 322.58, "100k", "AMP_SD", "GND")
R(x0, 345.44, "10", "+24V", "AMP_AVCC"); C(x0 + 12.7, 345.44, "1uF 50V", "AMP_AVCC", "GND", C0805); C(x0 + 25.4, 345.44, "100nF 50V", "AMP_AVCC", "GND", C0805)
for i in range(2):
    xx = x0 + 50.8 + 38.1 * i
    C(xx, 345.44, "1nF 50V", "+24V", "GND"); C(xx + 12.7, 345.44, "100nF 50V", "+24V", "GND", C0805)
    two("C", "Device:C_Polarized", xx + 25.4, 345.44, "220uF 35V", CP, "+24V", "GND")
for i, (a, b) in enumerate([("BSPR", "SPKP"), ("BSNR", "SPKP"), ("BSPL", "SPKN"), ("BSNL", "SPKN")]):
    C(x0 + 12.7 * i, 368.3, "220nF", a, b)
two("L", "Device:L", x0 + 63.5, 368.3, "10uH 6A", "Inductor_SMD:L_12x12mm_H8mm", "SPKP", "SPK_P")
two("L", "Device:L", x0 + 88.9, 368.3, "10uH 6A", "Inductor_SMD:L_12x12mm_H8mm", "SPKN", "SPK_N")
C(x0 + 114.3, 368.3, "1uF 50V", "SPK_P", "GND", C0805); C(x0 + 127, 368.3, "1uF 50V", "SPK_N", "GND", C0805)
C(x0 + 139.7, 368.3, "10nF", "SPK_P", "GND"); C(x0 + 152.4, 368.3, "10nF", "SPK_N", "GND")
R(x0 + 165.1, 368.3, "3.3", "SPK_P", "SNUB_P"); C(x0 + 177.8, 368.3, "1nF", "SNUB_P", "GND")
R(x0 + 190.5, 368.3, "3.3", "SPK_N", "SNUB_N"); C(x0 + 203.2, 368.3, "1nF", "SNUB_N", "GND")
js = part("J", "Connector:Screw_Terminal_01x02", x0 + 228.6, 368.3, "SPEAKER 4-8R", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal")
conn(js, {"1": "SPK_P", "2": "SPK_N"})
sh.text("Bluetooth speaker box: ESP32 A2DP -> I2S -> TLV320AIC3254 (mixer in the codec, ESP32 reads the pots) -> TPA3116D2 mono PBTL, 24 V, ~30 W into 8 R", 240, 18, 2.0, True)
sh.text("Amp: BD mode, 400 kHz (AM=000), master, 26 dB (20k/100k), PLIMIT = GVDD (none), SDZ pulled to 24 V, ESP32 pulls it low through Q (AMP_SD high = shutdown)", 240, 24, 1.27)
sh.text("Codec: I2S slave to ESP32 (MCLK from GPIO0 or PLL from BCLK), I2C 0x18; set DAC to L+R mono on LOL, which feeds the amp through the J3 coupling cap", 240, 29, 1.27)

# ================================================================ splice into the existing sheet
usym = g.flat_symbol("lcsc_imported:TLV320AIC3254IRHBR")
upins = g.pins_of(usym)
uang = {}
for sub in find_all(usym, "symbol"):
    for pn in find_all(sub, "pin"):
        uang[unq(find(pn, "number")[1])] = (unq(find(pn, "name")[1]), int(round(float(find(pn, "at")[3]))))


def upt(num):
    lx, ly = upins[str(num)]
    return (round(138.43 + lx, 3), round(97.79 - ly, 3))


for num, net in {"1": "I2S_MCLK", "2": "I2S_BCLK", "3": "I2S_WS", "4": "I2S_DOUT", "5": "I2S_DIN", "9": "I2C_SCL", "10": "I2C_SDA", "31": "CODEC_RST"}.items():
    pt = upt(num)
    sh.labels.append((net, pt[0], pt[1], LABEL_ANG[STUB[uang[num][1]]]))
    print("U1", num, uang[num][0], pt, net)


for num in ("8", "11", "19", "20", "21", "25", "27", "32"):          # unused codec pins (SPI/MFP, headphone, IN3, MICBIAS)
    sh.nc(upt(num))
sh.power("FLAG", (x0 - 25.4, 345.44), 0); sh.label("AMP_AVCC", (x0 - 25.4, 345.44), 90)


def hook(refname, libid, pin, net):
    m = re.search(r'\(lib_id "%s"\)\s*\(at ([\d.\-]+) ([\d.\-]+) (\d+)\)(?:(?!\n\t\(symbol).)*?\(property "Reference" "%s"' % (re.escape(libid), refname), t, re.S)
    x, y, rot = float(m.group(1)), float(m.group(2)), int(m.group(3))
    sym = g.flat_symbol(libid)
    lx, ly = g.pins_of(sym)[str(pin)]
    a = math.radians(rot); c, s = round(math.cos(a)), round(math.sin(a))
    sx, sy = lx, -ly
    pt = (round(x + sx * c + sy * s, 3), round(y - sx * s + sy * c, 3))
    ang = None
    for sub in find_all(sym, "symbol"):
        for pn in find_all(sub, "pin"):
            if unq(find(pn, "number")[1]) == str(pin):
                ang = int(round(float(find(pn, "at")[3])))
    d0 = STUB[ang]
    d = (round(d0[0] * c + d0[1] * s), round(-d0[0] * s + d0[1] * c))
    print("hook", refname, pin, pt, d)
    return (net, pt[0], pt[1], LABEL_ANG[d])


sh.labels += [hook("J1", "Connector:Screw_Terminal_01x02", 1, "AIN_R"), hook("J1", "Connector:Screw_Terminal_01x02", 2, "AIN_L"),
              hook("J3", "Connector:Screw_Terminal_01x02", 1, "AIN_AMP")]
g.finish(sh)

nodes = []
for (x, y) in sh.junctions:
    nodes.append(["junction", ["at", g.fmt(x), g.fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]])
for (x, y) in sh.ncs:
    nodes.append(["no_connect", ["at", g.fmt(x), g.fmt(y)], ["uuid", q(g.uid())]])
for w in sh.wires:
    nodes.append(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]])
for (name, x, y, ang) in sh.labels:
    just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
    nodes.append(["label", q(name), ["at", g.fmt(x), g.fmt(y), str(ang)], ["fields_autoplaced", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()], ["uuid", q(g.uid())]])
for (s, x, y, size, bold) in sh.texts:
    font = ["font", ["size", g.fmt(size), g.fmt(size)]]
    if bold:
        font += [["thickness", g.fmt(size * 0.2)], ["bold", "yes"]]
    nodes.append(["text", q(s), ["exclude_from_sim", "no"], ["at", g.fmt(x), g.fmt(y), "0"], ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(g.uid())]])
for r_ in sh.order:
    node = g.sym_instance(sh, sh.parts[r_])
    fixed = []
    for c in node:                                   # stacked pin "[1,15,38,39]" -> one pin entry per number
        if isinstance(c, list) and c and c[0] == "pin" and c[1].startswith('"['):
            for n in unq(c[1])[1:-1].split(","):
                fixed.append(["pin", q(n), ["uuid", q(g.uid())]])
        else:
            fixed.append(c)
    nodes.append(fixed)
body = "".join("\t" + dump(n, 1) + "\n" for n in nodes)
libs = ""
for lid in sh.lib_ids:
    if '(symbol "%s"' % lid in t:
        continue
    s = copy.deepcopy(g.flat_symbol(lid)); s[1] = q(lid)
    libs += "\t\t" + dump(s, 2) + "\n"
t = t.replace("(lib_symbols\n", "(lib_symbols\n" + libs, 1)
a = t.rindex("\t(sheet_instances")
t = t[:a] + body + t[a:]
t = t.replace('(paper "A4")', '(paper "A2")', 1)
for rf in ("C15", "C16", "C17", "C18"):          # 100 nF into a 10k input = 160 Hz high-pass -> 1 uF
    k = t.index('(property "Reference" "%s"' % rf)
    old = '(property "Value" "100 nF"'
    v = t.index(old, k)
    assert v - k < 600, rf
    t = t[:v] + '(property "Value" "1 uF"' + t[v + len(old):]
open(SCH, "w", encoding="utf-8", newline="").write(t)
print("parts added:", len(sh.order), "wires:", len(sh.wires), "labels:", len(sh.labels))
