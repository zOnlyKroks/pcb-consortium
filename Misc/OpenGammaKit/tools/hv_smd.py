"""hv_multiplier: IRF740 (D2PAK, 400 V) -> IRLML0060TRPBF (SOT-23, 60 V, logic level, LCSC C67274) and all UF4007 (DO-41 through-hole)
-> US1M (SMA, 1000 V, 75 ns, LCSC C7420317).  Pin geometry/numbering of the US1M symbol is identical to the old one, so no wire changes.
In-place text patch.  Run once with KiCad's python:  python -I tools/hv_smd.py"""
import copy, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import q, find, find_all, unq, dump
import gen_sch as g
HV = os.path.join(PRJ, "hv_multiplier.kicad_sch")
h = open(HV, encoding="utf-8").read()
if "US1M" in h and "IRLML0060" in h:
    print("already done"); sys.exit(0)
hv_uuid = re.search(r'\n\t\(uuid "([0-9a-f-]+)"\)', h).group(1)
root_uuid = re.search(r'\(path "/([0-9a-f-]+)/%s"' % hv_uuid, h).group(1)


def closing(s, k):
    d, i = 0, k
    while True:
        c = s[i]
        if c == '"':
            i = s.index('"', i + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i
        i += 1


def indent(text, n=1):
    return "".join(("\t" * n + l) if l.strip() else l for l in text.splitlines(True))


def setprop(s, key, val):
    pat = r'\(property "%s" "[^"]*"' % re.escape(key)
    if re.search(pat, s):
        return re.sub(pat, '(property "%s" "%s"' % (key, val), s, 1)
    at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", s)
    new = ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(hide yes)\n'
           '\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n') % (key, val, at.group(1), at.group(2))
    k = s.index("\n\t\t(pin ") + 1
    return s[:k] + new + s[k:]


# ---------------------------------------------------------------- diodes
FP = "lcsc_footprints:C7420317_SMA_L4.3-W2.6-LS5.0-FD"
pos, n = 0, 0
while True:
    m = re.compile(r'\n\t\(symbol\n\t\t\(lib_id "lcsc_imported:UF4007_C84067"\)\n').search(h, pos)
    if not m:
        break
    a = m.start() + 1
    b = closing(h, a + 1) + 1
    s = h[a:b]
    s = s.replace('(lib_id "lcsc_imported:UF4007_C84067")', '(lib_id "lcsc_imported:US1M")')
    for k, v in (("Value", "US1M"), ("Footprint", FP), ("LCSC", "C7420317"), ("Manufacturer", "R+O"),
                 ("Sim.Library", "us1m_spice.lib"), ("Sim.Name", "US1M")):
        s = setprop(s, k, v)
    h = h[:a] + s + h[b:]
    pos = a + len(s)
    n += 1
print("diodes swapped:", n)
g.LIBS = {"lcsc_imported": os.path.join(PRJ, "libs", "lcsc", "symbols", "lcsc_imported.kicad_sym")}
g.PROJECT = "gamma-spectrometer"
g.INST_PATH = "/%s/%s" % (root_uuid, hv_uuid)


def add_lib(lid):
    global h
    if '(symbol "%s"' % lid in h[:h.index("\n\t(junction")]:
        return
    s_ = copy.deepcopy(g.flat_symbol(lid)); s_[1] = q(lid)
    k = h.index("\n\t(lib_symbols"); kk = closing(h, k + 2)
    h = h[:kk] + "\n" + indent(dump(s_), 2).rstrip("\n") + "\n\t" + h[kk:]


add_lib("lcsc_imported:US1M")

# ---------------------------------------------------------------- MOSFET
a = h.index('(property "Reference" "Q1"'); a = h.rindex("\n\t(symbol\n", 0, a) + 1
b = closing(h, a + 1) + 1
old = h[a:b]
at = re.search(r"\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)", old)
x, y = float(at.group(1)), float(at.group(2))
flds = {}
for key in ("Reference", "Value"):
    mm = re.search(r'\(property "%s" "[^"]*"\s*\(at ([\d.\-]+) ([\d.\-]+) [\d.\-]+\)' % key, old)
    jj = re.search(r'\(property "%s" "[^"]*".*?\(justify ([a-z ]+)\)' % key, old, re.S)
    flds[key] = (float(mm.group(1)), float(mm.group(2)), jj.group(1) if jj else None)
print("Q1 at", x, y, flds)
h = h[:a] + h[b:].lstrip("\n")
# symbol IRLML0060TRPBF in the project's LCSC library: the stock IRLML6244 symbol (same SOT-23 pinout 1=G 2=S 3=D) with its own name/properties
LIBF = os.path.join(PRJ, "libs", "lcsc", "symbols", "lcsc_imported.kicad_sym")
lt = open(LIBF, encoding="utf-8").read()
if '(symbol "IRLML0060TRPBF"' not in lt:
    s_ = copy.deepcopy(g.flat_symbol("Transistor_FET:IRLML6244"))
    s_[1] = q("IRLML0060TRPBF")
    for sub in find_all(s_, "symbol"):
        sub[1] = q(unq(sub[1]).replace("IRLML6244_", "IRLML0060TRPBF_", 1))
    for p in find_all(s_, "property"):
        key = unq(p[1])
        if key == "Value":
            p[2] = q("IRLML0060TRPBF")
        elif key == "Footprint":
            p[2] = q("Package_TO_SOT_SMD:SOT-23")
        elif key == "Datasheet":
            p[2] = q("https://www.lcsc.com/product-detail/C67274.html")
    kk = lt.rstrip().rindex(")")
    lt = lt[:kk].rstrip("\n") + "\n  " + indent(dump(s_), 1).strip() + "\n)\n"
    open(LIBF, "w", encoding="utf-8").write(lt)
    g._lib_cache.clear()
add_lib("lcsc_imported:IRLML0060TRPBF")
sh = g.Sheet(); sh.npwr, sh.nflg = 950, 950
sh.add("Q1", "lcsc_imported:IRLML0060TRPBF", x, y, value="IRLML0060", fp="Package_TO_SOT_SMD:SOT-23", fields=(flds["Reference"], flds["Value"]),
       extra={"LCSC": "C67274", "Manufacturer": "Infineon", "Sim.Library": "irlml0060_spice.lib", "Sim.Name": "IRLML0060",
              "Sim.Device": "NMOS", "Sim.Type": "MOS1", "Sim.Pins": "1=G 2=S 3=D"})
print("Q1 pins:", {k_: sh.pin("Q1", k_) for k_ in ("1", "2", "3")})
blk_ = dump(g.sym_instance(sh, sh.parts["Q1"]))
k = h.rstrip().rindex(")")
h = h[:k] + indent(blk_, 1).rstrip("\n") + "\n" + h[k:]
open(HV, "w", encoding="utf-8").write(h)
print("hv_multiplier patched")
