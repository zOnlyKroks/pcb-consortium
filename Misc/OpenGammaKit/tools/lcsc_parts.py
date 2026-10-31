"""Put LCSC part numbers on the schematic parts, use LCSC-stocked tube clips (2 x C3130 5x20 fuse clips = SBM-20 holder) and the
TS-1187A tactile switch (C318884).  In-place text edit of gamma-spectrometer.kicad_sch; footprints from easyeda2kicad.
Usage: python -I tools/lcsc_parts.py <TEMP>/ogk"""
import copy, glob, os, re, shutil, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import q, find, find_all, unq, dump
T = sys.argv[1]
SCH = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")


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


def indent(text, n=1):
    return "".join(("\t" * n + l) if l.strip() else l for l in text.splitlines(True))


def add_fp_lib(name, uri_dir):
    p = os.path.join(PRJ, "fp-lib-table")
    ft = open(p, encoding="utf-8").read()
    if '(name "%s")' % name not in ft:
        i = ft.rstrip().rfind(")")
        open(p, "w", encoding="utf-8").write(ft[:i] + '  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/kicad-libraries/%s")(options "")(descr ""))\n)\n' % (name, uri_dir))


def install_fp(src_dir, lib, newname=None, renumber=None):
    mod = glob.glob(os.path.join(src_dir, "*.pretty", "*.kicad_mod"))[0]
    name = os.path.basename(mod)[:-10]
    m = open(mod, encoding="utf-8").read().replace("(module easyeda2kicad:%s" % name, "(module %s" % (newname or name))
    m = re.sub(r'\n\t\(model [^\n]*\n(?:\t\t[^\n]*\n)*\t\)', "", m)
    if renumber:                       # pad number -> new pad number ("" = no net)
        for old, new in renumber.items():
            m = m.replace("(pad %s smd" % old, "(pad @%s smd" % old)
        for old, new in renumber.items():
            m = m.replace("(pad @%s smd" % old, '(pad "%s" smd' % new)
    d = os.path.join(PRJ, "kicad-libraries", lib)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, (newname or name) + ".kicad_mod"), "w", encoding="utf-8").write(m)
    add_fp_lib(lib, lib)
    return newname or name


clip_fp = install_fp(os.path.join(T, "ee_C3130"), "FUSECLIP")
sw_fp = install_fp(os.path.join(T, "ee_C318884"), "TS1187A", "SW_TS-1187A-B-A-B_2pin", renumber={"1": "1", "4": "2", "2": "", "3": ""})

t = open(SCH, encoding="utf-8").read()


def block(t, ref):
    k = t.index('(property "Reference" "%s"' % ref)
    a = t.rindex("\n\t(symbol\n", 0, k) + 1
    return a, closing(t, a + 1) + 1


def setp(t, ref, **kv):
    a, b = block(t, ref)
    blk = t[a:b]
    for key, val in kv.items():
        m = re.search(r'(\(property "%s" )"[^"]*"' % re.escape(key), blk)
        if m:
            blk = blk[:m.start()] + m.group(1) + '"%s"' % val + blk[m.end():]
        else:
            pos = re.search(r'\(property "Footprint"[^\n]*\n\t\t\t\(at ([^)]*)\)', blk)
            at = pos.group(1) if pos else "0 0 0"
            ins = '\t\t(property "%s" "%s"\n\t\t\t(at %s)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n' % (key, val, at)
            k2 = blk.index('\t\t(property "Datasheet"') if '\t\t(property "Datasheet"' in blk else blk.index('\t\t(property "Footprint"')
            blk = blk[:k2] + ins + blk[k2:]
    return t[:a] + blk + t[b:]


LCSC = {"F20": "C47002356", "D20": "C193402", "D22": "C313141", "R42": "C2077489", "R43": "C2077489", "R44": "C2077489", "C32": "C437561",
        "J10": "C165948", "D2": "C125094", "U3": "C105188", "U6": "C143326", "D3": "C458984"}
for ref, c in LCSC.items():
    t = setp(t, ref, LCSC=c)
for ref in ("SW20", "SW21"):
    t = setp(t, ref, LCSC="C318884", Footprint="TS1187A:" + sw_fp)

# ---- SBM-20 holder: J3 (JST) -> two single-pin clip parts J3 (anode) and J4 (cathode)
import gen_sch as g
root_uuid = re.search(r'\(uuid "([0-9a-f-]+)"\)', t).group(1)
g.LIBS = {}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/" + root_uuid
a, b = block(t, "J3")
at = re.search(r"\(at ([\d.]+) ([\d.]+) (\d+)\)", t[a:b])
jx, jy = float(at.group(1)), float(at.group(2))
ref_sh = g.Sheet()
ref_sh.add("JX", "Connector_Generic:Conn_01x02", jx, jy)
p1, p2 = ref_sh.pin("JX", "1"), ref_sh.pin("JX", "2")
t = t[:a] + t[b:].lstrip("\n").join(["", ""]) if False else t[:a] + t[b:]
sh = g.Sheet()
sh.npwr, sh.nflg = 400, 400
for ref, p, val in (("J3", p1, "SBM-20 anode clip"), ("J4", p2, "SBM-20 cathode clip")):
    sh.add(ref, "Connector_Generic:Conn_01x01", round(p[0] + 5.08, 3), p[1], value=val, fp="FUSECLIP:" + clip_fp, fields="R",
           extra={"LCSC": "C3130", "Note": "5x20 fuse clip; the tube's 6.5 mm end tip sits in it. Two clips ~100 mm apart"})
embedded = set(re.findall(r'\n\t\t\(symbol "([^"]+)"\n', t))
libsyms = ""
for lid in sh.lib_ids:
    if lid not in embedded:
        s = copy.deepcopy(g.flat_symbol(lid)); s[1] = q(lid)
        libsyms += indent(dump(s), 2).rstrip("\n") + "\n"
body = "".join(indent(dump(g.sym_instance(sh, sh.parts[k])), 1).rstrip("\n") + "\n" for k in sh.order)
if libsyms:
    le = closing(t, t.index("(lib_symbols"))
    t = t[:le] + "\n" + libsyms.rstrip("\n") + "\n\t" + t[le:]
m = re.search(r"\n\t\(sheet_instances", t)
t = t[:m.start() + 1] + body + t[m.start() + 1:]
t = re.sub(r'\(text "SBM-20 / J305 class tube:[^"]*"', '(text "SBM-20 / J305 class tube in two 5x20 fuse clips (LCSC C3130): J3 = anode (+, via the ballast), J4 = cathode (-). Tube sees ~400 V - keep clear of the PCB edge."', t)
open(SCH, "w", encoding="utf-8").write(t)
print("done; clip fp", clip_fp, "switch fp", sw_fp)
