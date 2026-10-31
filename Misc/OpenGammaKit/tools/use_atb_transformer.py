"""T20 = TDK ATB322515-0110-T000 (LCSC C415291, 1:10, 7 uH, 600 mA rms) instead of a custom transformer; LCSC numbers on U23.
In-place text edit of gamma-spectrometer.kicad_sch; footprint from easyeda2kicad (kicad-libraries/ATB322515)."""
import glob, os, re, shutil, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
EE = sys.argv[1]
SCH = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")
D = os.path.join(PRJ, "kicad-libraries", "ATB322515"); os.makedirs(D, exist_ok=True)
mod = glob.glob(os.path.join(EE, "ATB.pretty", "*.kicad_mod"))[0]; name = os.path.basename(mod)[:-10]
m = open(mod, encoding="utf-8").read().replace("(module easyeda2kicad:%s" % name, "(module %s" % name)
m = re.sub(r'\n\t\(model [^\n]*\n(?:\t\t[^\n]*\n)*\t\)', "", m)
stp = glob.glob(os.path.join(EE, "ATB.3dshapes", "*.step"))
if stp:
    shutil.copy(stp[0], D)
    m = m.rstrip()[:-1] + '\t(model "${KIPRJMOD}/kicad-libraries/ATB322515/%s"\n\t\t(offset (xyz 0.000 0.000 0.000))\n\t\t(scale (xyz 1 1 1))\n\t\t(rotate (xyz 0 0 0))\n\t)\n)\n' % os.path.basename(stp[0])
open(os.path.join(D, name + ".kicad_mod"), "w", encoding="utf-8").write(m)
ft = open(os.path.join(PRJ, "fp-lib-table"), encoding="utf-8").read()
if '(name "ATB322515")' not in ft:
    i = ft.rstrip().rfind(")")
    open(os.path.join(PRJ, "fp-lib-table"), "w", encoding="utf-8").write(ft[:i] + '  (lib (name "ATB322515")(type "KiCad")(uri "${KIPRJMOD}/kicad-libraries/ATB322515")(options "")(descr ""))\n)\n')


def closing(t, s):
    d, i = 0, s
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


t = open(SCH, encoding="utf-8").read()
a = t.index('\t(symbol\n\t\t(lib_id "Device:Transformer_1P_1S")')
b = closing(t, a + 1) + 1
blk = t[a:b]
blk = blk.replace('(property "Value" "1:10 flyback"', '(property "Value" "ATB322515-0110-T000"')
blk = blk.replace('(property "Footprint" ""', '(property "Footprint" "ATB322515:%s"' % name)
blk = re.sub(r'\(property "Note" "[^"]*"', '(property "Note" "TDK 1:10 step-up, 7 uH, 600 mA rms; pins 1-2 = primary, 3-4 = secondary (assumed, check datasheet). If HV does not rise swap pins 3 and 4"', blk)
if '"LCSC"' not in blk:
    k = blk.index('\t\t(property "Note"')
    blk = blk[:k] + '\t\t(property "LCSC" "C415291"\n\t\t\t(at 364.49 142.24 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n' + blk[k:]
t = t[:a] + blk + t[b:]
t = re.sub(r'\(text "T20: Np:Ns = 1:10[^"]*"', '(text "T20 = TDK ATB322515-0110-T000 (LCSC C415291): 1:10, Lp 7 uH, 600 mA rms. At ~0.1 W the LM5180 peaks at ~0.3 A, on-time ~0.4 us (min 140 ns). Check secondary voltage rating and pinout/polarity in the TDK datasheet before building."', t)
# LCSC number on the LM5180
a = t.index('(property "MPN" "LM5180NGUR"')
if '"LCSC" "C2868878"' not in t:
    s0 = t.rindex("\n", 0, a) + 1
    t = t[:s0] + '\t\t(property "LCSC" "C2868878"\n\t\t\t(at 0 0 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n' + t[s0:]
open(SCH, "w", encoding="utf-8").write(t)
print("T20 ->", name)
