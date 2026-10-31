"""Geiger-counter rework of OpenGammaKit: add, IN PLACE (text insert, nothing else touched), to gamma-spectrometer.kicad_sch

  * ESP32-C6-MINI-1 module on the board (no plug-in Pico), USB-C power + native USB, 3.3 V LDO (net VCC)
  * HV supply for the GM tube: TI LM5180 primary-side-regulated flyback IC (integrated 100 V switch) + 1:10 transformer,
    ~400 V on net HV, HV monitor divider to an ESP32 ADC pin, enable from an ESP32 GPIO
  * the existing comparator output INT goes to a GPIO

Run once:  python -I tools/add_esp32_hv.py   (layout engine from ../VideoConv-V1/tools)
"""
import copy, os, re, sys

H = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import find, find_all, q, unq, dump

ROOT = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")
LM_DIR = os.path.join(PRJ, "kicad-libraries", "LM5180")


def closing(t, start):
    d, i = 0, start
    while True:
        c = t[i]
        if c == '"':
            i = t.index('"', i + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i
        i += 1


def indent(text, n=1):
    return "".join(("\t" * n + l) if l.strip() else l for l in text.splitlines(True))


def add_table(path, name, uri):
    t = open(path, encoding="utf-8").read()
    if '(name "%s")' % name in t:
        return
    i = t.rstrip().rfind(")")
    open(path, "w", encoding="utf-8").write(t[:i] + '  (lib (name "%s")(type "KiCad")(uri "%s")(options "")(descr ""))\n)\n' % (name, uri))


# ================================================================ LM5180 symbol (pins from the TI datasheet SNVSB06D)
def pin(typ, x, y, ang, name, num):
    return ('\t\t\t(pin %s line\n\t\t\t\t(at %s %s %s)\n\t\t\t\t(length 2.54)\n\t\t\t\t(name "%s"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n'
            '\t\t\t\t(number "%s"\n\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n\t\t\t\t)\n\t\t\t)\n' % (typ, x, y, ang, name, num))


def prop(k, v, x, y, hide=False):
    return ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)%s\n\t\t\t)\n\t\t)\n'
            % (k, v, x, y, "\n\t\t\t\t(hide yes)" if hide else ""))


if not os.path.exists(os.path.join(LM_DIR, "LM5180.kicad_sym")):
    os.makedirs(LM_DIR, exist_ok=True)
    s = '(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "kicad_symbol_editor")\n\t(generator_version "9.0")\n\t(symbol "LM5180"\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
    s += prop("Reference", "U", 0, 10.16) + prop("Value", "LM5180", 0, -10.16)
    s += prop("Footprint", "Package_SON:HVSON-8-1EP_4x4mm_P0.8mm_EP2.2x3.1mm", 0, 0, True)
    s += prop("Datasheet", "https://www.ti.com/lit/ds/symlink/lm5180.pdf", 0, 0, True)
    s += prop("Description", "65 V in PSR flyback converter, 100 V 1.5 A integrated switch, WSON-8 (NGU0008B)", 0, 0, True)
    s += ('\t\t(symbol "LM5180_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start -7.62 7.62)\n\t\t\t\t(end 7.62 -7.62)\n\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n'
          '\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t\t(symbol "LM5180_1_1"\n')
    s += pin("power_in", -10.16, 5.08, 0, "VIN", 3) + pin("input", -10.16, 2.54, 0, "EN/UVLO", 4)
    s += pin("passive", -10.16, 0, 0, "SS/BIAS", 5) + pin("passive", -10.16, -2.54, 0, "TC", 6)
    s += pin("passive", 10.16, 5.08, 180, "SW", 1) + pin("input", 10.16, 2.54, 180, "FB", 2)
    s += pin("passive", 10.16, 0, 180, "RSET", 7)
    s += pin("power_in", 0, -10.16, 90, "GND", 8) + pin("passive", 0, -10.16, 90, "DAP", 9).replace("(pin passive", "(pin passive")
    s += "\t\t)\n\t\t(embedded_fonts no)\n\t)\n)\n"
    open(os.path.join(LM_DIR, "LM5180.kicad_sym"), "w", encoding="utf-8").write(s.replace('\t\t(pin passive line\n\t\t\t\t(at 0 -10.16 90)\n\t\t\t\t(length 2.54)\n\t\t\t\t(name "DAP"',
                                                                                          '\t\t(pin passive line\n\t\t\t\t(at 0 -10.16 90)\n\t\t\t\t(length 2.54)\n\t\t\t\t(name "DAP"'))
add_table(os.path.join(PRJ, "sym-lib-table"), "LM5180", "${KIPRJMOD}/kicad-libraries/LM5180/LM5180.kicad_sym")

# ================================================================ layout (engine of the VideoConv project)
r = open(ROOT, encoding="utf-8").read()
if "LM5180" in r:
    print("already added")
    sys.exit(0)
root_uuid = re.search(r'\(uuid "([0-9a-f-]+)"\)', r).group(1)
import gen_sch as g
g.LIBS = {"LM5180": os.path.join(LM_DIR, "LM5180.kicad_sym")}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/" + root_uuid
G = 2.54
STUB = {0: (-1, 0, 180), 180: (1, 0, 0), 90: (0, 1, 270), 270: (0, -1, 90)}
RAILS = {"GND", "VCC", "+5V"}
GLOBALS = {"INT", "HV"}          # nets that already exist as global labels in the sheet
sh = g.Sheet()
sh.npwr, sh.nflg = 300, 300
glabels, texts = [], []


def snap(v):
    return round(round(v / 1.27) * 1.27, 3)


def part(ref, lib, x, y, value, fp="", rot=0, fields="R", **kw):
    sh.add(ref, lib, snap(x), snap(y), rot=rot, value=value, fp=fp, fields=fields, **kw)
    return ref


def effang(k, num):
    p = sh.parts[k]
    if "ang" not in p:
        ang = {}
        for sub in find_all(p["sym"], "symbol"):
            for pn in find_all(sub, "pin"):
                ang[unq(find(pn, "number")[1])] = int(round(float(find(pn, "at")[3])))
        p["ang"] = ang
    return (p["ang"][str(num)] + p["rot"]) % 360


seen = set()


def tie(k, num, net, d=2, kind=None):
    """stub from a pin to a power symbol (rails), a local label, or (kind='gl') a global label"""
    pt = sh.pin(k, num)
    if (k, pt) in seen:
        return
    seen.add((k, pt))
    a = effang(k, num)
    dx, dy, la = STUB[a]
    end = sh.stub(pt, dx * d * G, dy * d * G)
    if net in RAILS:
        sh.power(net, end, 0 if a in (90, 270) else (90 if a == 0 else 270))
    elif kind == "gl" or net in GLOBALS:
        glabels.append((net, end[0], end[1], la))
    else:
        sh.label(net, end, la)


def nc(k, num):
    sh.nc(sh.pin(k, num))


def vt(ref, lib, val, fp, x, y, top, bot, rot=0, **kw):
    k = part(ref, lib, x, y, val, fp, rot, **kw)
    tie(k, 1, top)
    tie(k, 2, bot)
    return k


R, C = "Device:R", "Device:C"
R06, C06, C08 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_0805_2012Metric"
R12, C12 = "Resistor_SMD:R_1206_3216Metric", "Capacitor_SMD:C_1206_3216Metric"
SOT23_6, SOT23_5, SODX, SMA = "Package_TO_SOT_SMD:SOT-23-6", "Package_TO_SOT_SMD:SOT-23-5", "Diode_SMD:D_SOD-123", "Diode_SMD:D_SMA"
SWFP = "Button_Switch_SMD:SW_SPST_CK_RS282G05A3"

# ---------------------------------------------------------------- ESP32-C6 on the board
X, Y = 290.0, 75.0
texts.append(("ESP32-C6 module on the board (no plug-in Pico): pulse INT on IO1, HV monitor on IO0 (ADC), HV enable on IO2, native USB on IO12/IO13", 255.0, 30.0))
u20 = part("U20", "RF_Module:ESP32-C6-MINI-1", X, Y, "ESP32-C6-MINI-1", "RF_Module:ESP32-C6-MINI-1", fields="IC", extra={"MPN": "ESP32-C6-MINI-1-N4"})
tie(u20, 3, "VCC"); tie(u20, 1, "GND")
tie(u20, 12, "HV_MON", 3); tie(u20, 13, "INT", 3, "gl"); tie(u20, 5, "HV_EN", 3)
tie(u20, 8, "EN", 3); tie(u20, 23, "BOOT", 3)
tie(u20, 17, "USB_DM", 3); tie(u20, 18, "USB_DP", 3)
for n in (6, 9, 10, 15, 16, 22, 19, 20, 24, 25, 26, 27, 28, 29, 30, 31):
    nc(u20, n)
for n in (4, 7, 21, 32, 33, 34, 35):
    nc(u20, n)
vt("C20", C, "10uF", C08, 292, 40, "VCC", "GND")
vt("C21", C, "100nF", C06, 299, 40, "VCC", "GND")
vt("R30", R, "10k", R06, 258, 40, "VCC", "EN")
vt("C22", C, "1uF", C06, 265, 40, "EN", "GND")
vt("SW20", "Switch:SW_Push", "RESET", SWFP, 273, 40, "EN", "GND", rot=90)
vt("R31", R, "10k", R06, 258, 104, "VCC", "BOOT")
vt("SW21", "Switch:SW_Push", "BOOT", SWFP, 273, 104, "BOOT", "GND", rot=90)
vt("C23", C, "100nF", C06, 250, 66, "HV_MON", "GND")

# ---------------------------------------------------------------- USB-C power / data, 3.3 V LDO
UX, UY = 262.0, 225.0
texts.append(("USB-C 5 V in, PTC + TVS, ESD diodes on D+/D-, 3.3 V LDO (net VCC)", 255.0, 192.0))
j10 = part("J10", "Connector:USB_C_Receptacle_USB2.0_16P", UX, UY, "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", fields="IC", nosim=True)
tie(j10, "A4", "VBUS"); tie(j10, "A5", "CC1"); tie(j10, "B5", "CC2")
tie(j10, "A6", "USB_DP_C"); tie(j10, "B6", "USB_DP_C"); tie(j10, "A7", "USB_DM_C"); tie(j10, "B7", "USB_DM_C")
nc(j10, "A8"); nc(j10, "B8")
tie(j10, "A1", "GND"); tie(j10, "SH", "GND")
vt("R32", R, "5.1k", R06, 284, 224, "CC1", "GND"); vt("R33", R, "5.1k", R06, 289, 224, "CC2", "GND")
vt("F20", "Device:Polyfuse", "0.75A PTC", "Fuse:Fuse_1206_3216Metric", 296, 198, "VBUS", "+5V")
vt("D20", "Device:D_TVS", "SMF5.0A", SODX, 304, 198, "VBUS", "GND", rot=90)
vt("C24", C, "22uF", C12, 312, 198, "+5V", "GND"); vt("C25", C, "100nF", C06, 319, 198, "+5V", "GND")
u21 = part("U21", "Power_Protection:USBLC6-2SC6", 312, 227, "USBLC6-2SC6", SOT23_6, fields="IC")
tie(u21, 1, "USB_DP_C"); tie(u21, 6, "USB_DP"); tie(u21, 3, "USB_DM_C"); tie(u21, 4, "USB_DM"); tie(u21, 5, "+5V"); tie(u21, 2, "GND")
u22 = part("U22", "Regulator_Linear:AP2112K-3.3", 345, 225, "AP2112K-3.3", SOT23_5, fields="ICU", extra={"MPN": "AP2112K-3.3TRG1"})
pv, pe, po, pg = (sh.pin(u22, n) for n in (1, 3, 5, 2))
sh.wire(pv, (pv[0] - 12.7, pv[1])); sh.wire((pv[0] - 12.7, pv[1]), (pv[0] - 12.7, pv[1] - 7.62)); sh.power("+5V", (pv[0] - 12.7, pv[1] - 7.62))
sh.wire(pe, (pe[0] - 7.62, pe[1])); sh.wire((pe[0] - 7.62, pe[1]), (pe[0] - 7.62, pv[1]))
c26 = part("C26", C, pv[0] - 5.08, pv[1] + 3.81, "1uF", C06, fields="R")
sh.wire(sh.pin(c26, 2), (pv[0] - 5.08, pv[1] + 10.16)); sh.power("GND", (pv[0] - 5.08, pv[1] + 10.16))
sh.wire(po, (po[0] + 12.7, po[1])); sh.wire((po[0] + 12.7, po[1]), (po[0] + 12.7, po[1] - 7.62)); sh.power("VCC", (po[0] + 12.7, po[1] - 7.62))
c27 = part("C27", C, po[0] + 7.62, po[1] + 3.81, "2.2uF", C06, fields="R")
sh.wire(sh.pin(c27, 2), (po[0] + 7.62, po[1] + 10.16)); sh.power("GND", (po[0] + 7.62, po[1] + 10.16))
sh.wire(pg, (pg[0], pg[1] + 7.62)); sh.power("GND", (pg[0], pg[1] + 7.62))
nc(u22, 4)
fx5, fy5 = snap(385.0), snap(205.0)
sh.power("+5V", (fx5, fy5)); sh.wire((fx5, fy5), (fx5, fy5 + 2.54)); sh.power("FLAG", (fx5, fy5 + 2.54))
fxg, fyg = snap(395.0), snap(210.0)
sh.power("GND", (fxg, fyg)); sh.wire((fxg, fyg), (fxg, fyg - 2.54)); sh.power("FLAG", (fxg, fyg - 2.54))

# ---------------------------------------------------------------- HV: LM5180 PSR flyback, 1:10, ~400 V
FX, FY = 360.0, 110.0
texts.append(("GM tube HV (~400 V): LM5180 primary-side-regulated flyback, 5 V in. Vout = (Rfb x 1.2177 / Rset / Nps) - Vd with Rfb 402k, Rset 12.1k, Nps = Np/Ns = 1/10 -> ~404 V", 335.0, 90.0))
texts.append(("T20: Np:Ns = 1:10, Lp ~22 uH (Ls ~2.2 mH), Isat >= 1.5 A, secondary >= 600 V; wind both coils the same way, pin 2 (SW) and pin 3 (diode) are the in-phase ends. Not a stock LCSC part.", 335.0, 93.5))
texts.append(("SW sits at Vin + 10 x Vout/Nps ~ 45 V; zener clamp D23 keeps spikes below the 95 V rating. HV divider 9.9 M / 33 k -> HV_MON = HV / 301. Min load: divider draws ~40 uA.", 335.0, 97.0))
u23 = part("U23", "LM5180:LM5180", FX, FY, "LM5180", "Package_SON:HVSON-8-1EP_4x4mm_P0.8mm_EP2.2x3.1mm", fields="ICU", extra={"MPN": "LM5180NGUR"})
tie(u23, 3, "+5V", 3); tie(u23, 4, "HV_EN", 3); nc(u23, 5); nc(u23, 6)
tie(u23, 1, "VSW", 3); tie(u23, 2, "VFB", 3); tie(u23, 7, "RSET", 3); tie(u23, 8, "GND", 3)
vt("R40", R, "402k", R06, FX + 34, FY - 12, "VSW", "VFB")
vt("R41", R, "12.1k", R06, FX + 34, FY + 14, "RSET", "GND")
vt("R46", R, "100k", R06, FX - 36, FY + 6, "VCC", "HV_EN")
vt("C30", C, "10uF", C08, FX - 36, FY - 18, "+5V", "GND"); vt("C31", C, "2.2uF", C06, FX - 29, FY - 18, "+5V", "GND")
t20 = part("T20", "Device:Transformer_1P_1S", FX + 5, FY + 32, "1:10 flyback", "", fields="R", extra={"Note": "Np:Ns 1:10, Lp ~22uH, Isat>=1.5A, sec >= 600V"})
tie(t20, 1, "+5V"); tie(t20, 2, "VSW"); tie(t20, 3, "HVAC"); tie(t20, 4, "GND")
vt("D22", "Device:D", "ES1D", SMA, FX + 22, FY + 38, "VCL", "VSW", rot=90, fields="L")
vt("D23", "Device:D_Zener", "51V", SODX, FX + 29, FY + 38, "VCL", "+5V", rot=90, fields="L")
vt("D21", "Device:D", "ES1J", SMA, FX + 24, FY + 56, "HV", "HVAC", rot=90, fields="L", extra={"Note": "600 V ultrafast"})
vt("C32", C, "10nF 630V", C12, FX + 34, FY + 62, "HV", "GND")
# HV monitor divider (3 x 3.3M in series so each 1206 sees ~133 V) + 33k
vt("R42", R, "3.3M", R12, FX + 46, FY + 26, "HV", "HVD1")
vt("R43", R, "3.3M", R12, FX + 46, FY + 38, "HVD1", "HVD2")
vt("R44", R, "3.3M", R12, FX + 46, FY + 50, "HVD2", "HV_MON")
vt("R45", R, "33k", R06, FX + 46, FY + 62, "HV_MON", "GND")

g.finish(sh)
embedded = set(re.findall(r'\n\t\t\(symbol "([^"]+)"\n', r))
libsyms = ""
for lid in sh.lib_ids:
    if lid in embedded:
        continue
    s = copy.deepcopy(g.flat_symbol(lid))
    s[1] = q(lid)
    libsyms += indent(dump(s), 2).rstrip("\n") + "\n"
pieces = []
for (x, y) in sh.junctions:
    pieces.append(dump(["junction", ["at", g.fmt(x), g.fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(g.uid())]]))
for w in sh.wires:
    pieces.append(dump(["wire", ["pts", ["xy", g.fmt(w[0]), g.fmt(w[1])], ["xy", g.fmt(w[2]), g.fmt(w[3])]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(g.uid())]]))
for (name, x, y, ang) in sh.labels:
    just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
    pieces.append(dump(["label", q(name), ["at", g.fmt(x), g.fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                        ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()], ["uuid", q(g.uid())]]))


def glabel(name, x, y, ang):
    eff = ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "right" if ang == 180 else "left"]]
    return dump(["global_label", q(name), ["shape", "input"], ["at", g.fmt(x), g.fmt(y), str(ang)], ["fields_autoplaced", "yes"], eff, ["uuid", q(g.uid())],
                 ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"), ["at", g.fmt(x), g.fmt(y), "0"], ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]]])


for (name, x, y, ang) in glabels:
    pieces.append(glabel(name, x, y, ang))
for (x, y) in sh.ncs:
    pieces.append(dump(["no_connect", ["at", g.fmt(x), g.fmt(y)], ["uuid", q(g.uid())]]))
for (s, x, y) in texts:
    pieces.append(dump(["text", q(s), ["exclude_from_sim", "no"], ["at", g.fmt(x), g.fmt(y), "0"],
                        ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]], ["uuid", q(g.uid())]]))
for key in sh.order:
    pieces.append(dump(g.sym_instance(sh, sh.parts[key])))
body = "".join(indent(p, 1).rstrip("\n") + "\n" for p in pieces)
if libsyms:
    le = closing(r, r.index("(lib_symbols"))
    r = r[:le] + "\n" + libsyms.rstrip("\n") + "\n\t" + r[le:]
r = r.replace('(paper "A4")', '(paper "A3")', 1)
m = re.search(r"\n\t\(sheet_instances", r)
pos = m.start() + 1
open(ROOT, "w", encoding="utf-8").write(r[:pos] + body + r[pos:])
print("added", len(sh.order), "symbols")
