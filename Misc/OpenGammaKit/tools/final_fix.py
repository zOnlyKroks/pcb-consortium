"""Last ERC fixes: PWR_FLAG on the GND and +5V nets of the root sheet (the nets are fed by connector pins / the PTC, which are passive, so ERC
reports 'power pin not driven'), and the orphaned GND symbol that was left under the removed Rload1 on hv_multiplier.
In-place text patch.  Run once with KiCad's python:  python -I tools/final_fix.py"""
import copy, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(H, ".."))
sys.path.insert(0, os.path.normpath(os.path.join(PRJ, "..", "VideoConv-V1", "tools")))
from sexp import q, dump
import gen_sch as g
ROOT = os.path.join(PRJ, "gamma-spectrometer.kicad_sch")
HV = os.path.join(PRJ, "hv_multiplier.kicad_sch")
r = open(ROOT, encoding="utf-8").read()
h = open(HV, encoding="utf-8").read()


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


# 1. orphan GND under the removed load
m = re.search(r'\n\t\(symbol\n\t\t\(lib_id "power:GND"\)\n\t\t\(at 795\.02 177\.8 0\)', h)
if m:
    a = m.start() + 1; b = closing(h, a + 1) + 1
    if h[b] == "\n":
        b += 1
    h = h[:a] + h[b:]
    open(HV, "w", encoding="utf-8").write(h)
    print("orphan GND removed")
# 2. PWR_FLAGs in the root sheet
if "PWR_FLAG" not in r:
    root_uuid = re.search(r'\n\t\(uuid "([0-9a-f-]+)"\)', r).group(1)
    g.LIBS = {}
    g.PROJECT = "gamma-spectrometer"
    g.INST_PATH = "/" + root_uuid
    sh = g.Sheet(); sh.npwr, sh.nflg = 970, 970
    sh.power("FLAG", (25.4, 200.66))      # GND net
    sh.power("FLAG", (85.09, 157.48))     # +5V net
    s_ = copy.deepcopy(g.flat_symbol("power:PWR_FLAG")); s_[1] = q("power:PWR_FLAG")
    k = r.index("\n\t(lib_symbols"); kk = closing(r, k + 2)
    r = r[:kk] + "\n" + indent(dump(s_), 2).rstrip("\n") + "\n\t" + r[kk:]
    body = []
    for key in sh.order:
        t_ = dump(g.sym_instance(sh, sh.parts[key]))
        t_ = re.sub(r'(\(property "Value" "PWR_FLAG".*?)\(effects(\s*)', r'\1(effects\2(hide yes)\2', t_, 1, re.S) if False else t_
        body.append(t_)
    m = re.search(r"\n\t\(sheet_instances", r)
    ins = "".join(indent(b, 1).rstrip("\n") + "\n" for b in body)
    # hide the value text of the flags (they sit on top of the GND / +5V symbols)
    ins = re.sub(r'(\(property "Value" "PWR_FLAG"\s*\(at [^)]*\)\s*)\(effects', r'\1(hide yes)\n\t\t\t(effects', ins)
    r = r[:m.start() + 1] + ins + r[m.start() + 1:]
    open(ROOT, "w", encoding="utf-8").write(r)
    print("PWR_FLAGs added")
