"""Generate D-V1.kicad_sch: analog (discrete) class D amplifier, mono, single-ended (speaker to GND), no class D IC.

Every part placed by hand, real wires, power symbols on short stubs, net labels only where a net has to
jump across the sheet.  Behavioural SPICE models are attached to the active parts (Sim.* fields) so the
sheet simulates inside KiCad (models/DV1_models.lib).  Run check_sim.py afterwards.
"""
import copy, math, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
SCH = os.path.join(PRJ, "D-V1.kicad_sch")
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
LIBS = {}
ROOT_UUID = "5b0e7c1a-3d52-4e8f-9a61-7c2d40b8e913"
PROJECT = "D-V1"


def uid():
    return str(uuid.uuid4())


def r2(v):
    return round(v + 0.0, 3)


def fmt(v):
    s = ("%.4f" % r2(v)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---------------------------------------------------------------- library symbols
_lib_cache = {}


def lib_tree(lib):
    if lib not in _lib_cache:
        path = LIBS.get(lib) or os.path.join(STOCK, lib + ".kicad_sym")
        _lib_cache[lib] = {unq(s[1]): s for s in find_all(parse(open(path, encoding="utf-8").read())[0], "symbol")}
    return _lib_cache[lib]


def flat_symbol(lib_id):
    """Library symbol with `extends` resolved, renamed to lib_id for the sheet's lib_symbols."""
    lib, name = lib_id.split(":")
    syms = lib_tree(lib)
    sym = copy.deepcopy(syms[name])
    ext = find(sym, "extends")
    if ext:
        parent = flat_symbol(lib + ":" + unq(ext[1]))
        pname = unq(ext[1])
        base = copy.deepcopy(parent)
        base[1] = q(name)
        for sub in find_all(base, "symbol"):
            sub[1] = q(unq(sub[1]).replace(pname + "_", name + "_", 1))
        child_props = {unq(p[1]): p for p in find_all(sym, "property")}
        for i, c in enumerate(base):
            if isinstance(c, list) and c[0] == "property" and unq(c[1]) in child_props:
                base[i] = child_props.pop(unq(c[1]))
        idx = max(i for i, c in enumerate(base) if isinstance(c, list) and c[0] == "property")
        for p in child_props.values():
            idx += 1
            base.insert(idx, p)
        sym = base
    else:
        sym[1] = q(name)
    return sym


def pins_of(sym):
    """{number: (x, y)} in symbol coordinates (Y up), unit 0/1 body style 1."""
    out = {}
    for sub in find_all(sym, "symbol"):
        parts = unq(sub[1]).rsplit("_", 2)
        if len(parts) == 3 and parts[2] not in ("0", "1"):
            continue
        for pin in find_all(sub, "pin"):
            at = find(pin, "at")
            out[unq(find(pin, "number")[1])] = (float(at[1]), float(at[2]))
    return out


# ---------------------------------------------------------------- sheet model
class Sheet:
    def __init__(self):
        self.parts = {}          # ref -> dict
        self.order = []
        self.wires = []          # [(x1,y1,x2,y2)]
        self.labels = []         # (name, x, y, angle)
        self.ncs = []
        self.texts = []
        self.lib_ids = []
        self.npwr = 0
        self.nflg = 0

    # placement ---------------------------------------------------------
    def add(self, ref, lib_id, x, y, rot=0, mirror=None, value=None, fp="", lcsc="", fields="R", extra=None,
            dnp=False, nosim=False, simonly=False):
        sym = flat_symbol(lib_id)
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)
        part = dict(ref=ref, lib_id=lib_id, x=x, y=y, rot=rot, mirror=mirror, sym=sym,
                    value=value if value is not None else unq(find_prop(sym, "Value")), fp=fp, lcsc=lcsc,
                    fields=fields, extra=extra or {}, dnp=dnp, pins=pins_of(sym), nosim=nosim,
                    simonly=simonly)
        self.parts[ref] = part
        self.order.append(ref)
        return part

    def pin(self, ref, num):
        p = self.parts[ref]
        num = str(num)
        lx, ly = p["pins"][str(num)]
        return xform(p, lx, -ly)

    def P(self, spec):
        if isinstance(spec, str):
            ref, num = spec.split(".")
            return self.pin(ref, num)
        return spec

    def power(self, kind, at, rot=0):
        at = self.P(at)
        lib_id = {"FLAG": "power:PWR_FLAG"}.get(kind, "power:" + kind)
        if kind == "FLAG":
            self.nflg += 1
            ref = "#FLG%02d" % self.nflg
        else:
            self.npwr += 1
            ref = "#PWR%03d" % self.npwr
        self.add(ref, lib_id, at[0], at[1], rot=rot, fields="pwr")

    # wiring --------------------------------------------------------------
    def wire(self, *pts):
        pts = [self.P(p) for p in pts]
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6:
                raise ValueError("diagonal wire %s -> %s" % (a, b))
            if a != b:
                self.wires.append((r2(a[0]), r2(a[1]), r2(b[0]), r2(b[1])))
        return pts[-1]

    def stub(self, spec, dx, dy):
        a = self.P(spec)
        b = (a[0] + dx, a[1] + dy)
        self.wire(a, b)
        return b

    def label(self, name, at, angle=0):
        at = self.P(at)
        self.labels.append((name, r2(at[0]), r2(at[1]), angle))

    def nc(self, spec):
        self.ncs.append(self.P(spec))

    def text(self, s, x, y, size=1.27, bold=False):
        self.texts.append((s, x, y, size, bold))


def find_prop(sym, key):
    for p in find_all(sym, "property"):
        if unq(p[1]) == key:
            return p[2]
    return '""'


def xform(p, sx, sy):
    """Symbol-local point (already Y-flipped to screen sense) -> sheet coordinates."""
    a = math.radians(p["rot"])
    c, s = round(math.cos(a)), round(math.sin(a))
    x = sx * c + sy * s
    y = -sx * s + sy * c
    if p["mirror"] == "x":
        y = -y
    elif p["mirror"] == "y":
        x = -x
    return (r2(p["x"] + x), r2(p["y"] + y))


# ---------------------------------------------------------------- connectivity post-processing
def on_seg(pt, w):
    x, y = pt
    x1, y1, x2, y2 = w
    if x1 == x2 == x:
        return min(y1, y2) < y < max(y1, y2)
    if y1 == y2 == y:
        return min(x1, x2) < x < max(x1, x2)
    return False


def finish(sh):
    pts = set()
    for ref in sh.order:
        p = sh.parts[ref]
        for n in p["pins"]:
            pts.add(sh.pin(ref, n))
    for l in sh.labels:
        pts.add((l[1], l[2]))
    for w in sh.wires:
        pts.add((w[0], w[1]))
        pts.add((w[2], w[3]))
    # split wires at every point on their interior
    changed = True
    wires = list(dict.fromkeys(sh.wires))
    while changed:
        changed = False
        out = []
        for w in wires:
            hit = next((pt for pt in pts if on_seg(pt, w)), None)
            if hit:
                out += [(w[0], w[1], hit[0], hit[1]), (hit[0], hit[1], w[2], w[3])]
                changed = True
            else:
                out.append(w)
        wires = out
    sh.wires = wires
    # junctions: 3+ items meeting at a point
    count = {}
    for w in wires:
        for e in ((w[0], w[1]), (w[2], w[3])):
            count[e] = count.get(e, 0) + 1
    for ref in sh.order:
        p = sh.parts[ref]
        seen = set()
        for n in p["pins"]:
            e = sh.pin(ref, n)
            if e in seen:              # stacked pins count once
                continue
            seen.add(e)
            count[e] = count.get(e, 0) + 1
    sh.junctions = sorted(e for e, c in count.items() if c >= 3)
    # crossings without junction (informational)
    for i, a in enumerate(wires):
        for b in wires[i + 1:]:
            if (a[0] == a[2]) != (b[0] == b[2]):
                v, h = (a, b) if a[0] == a[2] else (b, a)
                if min(h[0], h[2]) < v[0] < max(h[0], h[2]) and min(v[1], v[3]) < h[1] < max(v[1], v[3]):
                    print("  note: wires cross at", (v[0], h[1]))
    # dangling wire ends
    for e, c in count.items():
        if c == 1 and e not in {(l[1], l[2]) for l in sh.labels}:
            if not any(e == sh.pin(r, n) for r in sh.order for n in sh.parts[r]["pins"]):
                print("  WARNING: dangling wire end at", e)


# ---------------------------------------------------------------- writer
FONT = ["effects", ["font", ["size", "1.27", "1.27"]]]


def prop(key, val, x, y, angle=0, hide=False, justify=None):
    eff = ["effects", ["font", ["size", "1.27", "1.27"]]]
    if justify:
        eff.append(["justify"] + justify.split())
    if hide:
        eff.append(["hide", "yes"])
    return ["property", q(key), q(val), ["at", fmt(x), fmt(y), str(angle)], eff]


def field_pos(sh, p):
    """Reference / Value positions and text angle for a placed part."""
    x, y = p["x"], p["y"]
    pins = [sh.pin(p["ref"], n) for n in p["pins"]]
    xs = [a for a, _ in pins] + [x]
    ys = [b for _, b in pins] + [y]
    mode = p["fields"]
    if isinstance(mode, tuple):                       # explicit ((rx, ry, just), (vx, vy, just))
        return mode
    if mode == "R":
        return ((x + 2.54, y - 1.27, "left"), (x + 2.54, y + 1.27, "left"))
    if mode == "L":
        return ((x - 2.54, y - 1.27, "right"), (x - 2.54, y + 1.27, "right"))
    if mode == "T":                                   # horizontal two-pin part, text above
        return ((x, y - 3.81, None), (x, y - 1.905, None))
    if mode == "B":
        return ((x, y + 2.54, None), (x, y + 4.445, None))
    if mode == "IC":                                  # above / below the pin envelope
        return ((x, min(ys) - 2.54, None), (x, max(ys) + 2.54, None))
    raise ValueError(mode)


def sym_instance(sh, p):
    at = ["at", fmt(p["x"]), fmt(p["y"]), str(p["rot"])]
    node = ["symbol", ["lib_id", q(p["lib_id"])], at]
    if p["mirror"]:
        node.append(["mirror", p["mirror"]])
    is_pwr = p["fields"] == "pwr"
    node += [["unit", "1"], ["exclude_from_sim", "yes" if p["nosim"] else "no"],
             ["in_bom", "no" if (is_pwr or p["simonly"]) else "yes"],
             ["on_board", "no" if (is_pwr or p["simonly"]) else "yes"], ["dnp", "yes" if p["dnp"] else "no"], ["uuid", q(uid())]]
    # field text angle is stored relative to the symbol: undo the symbol rotation so text reads horizontally
    fa = (360 - p["rot"]) % 180 if p["rot"] in (90, 270) else 0
    if is_pwr:
        up = p["lib_id"] in ("power:GND",)
        node.append(prop("Reference", p["ref"], p["x"], p["y"], 0, hide=True))
        vy = p["y"] + (3.81 if up else -3.556)
        vx = p["x"]
        if p["rot"] == 90:
            vx, vy = p["x"] + 4.5, p["y"]
        elif p["rot"] == 270:
            vx, vy = p["x"] - 4.5, p["y"]
        hide_val = p["lib_id"] == "power:PWR_FLAG" and False
        node.append(prop("Value", p["value"], vx, vy, fa, hide=hide_val))
        node.append(prop("Footprint", "", p["x"], p["y"], 0, hide=True))
        node.append(prop("Datasheet", "", p["x"], p["y"], 0, hide=True))
    else:
        (rx, ry, rj), (vx, vy, vj) = field_pos(sh, p)
        node.append(prop("Reference", p["ref"], rx, ry, fa, justify=rj))
        node.append(prop("Value", p["value"], vx, vy, fa, justify=vj, hide=p["extra"].get("hide_value", False)))
        node.append(prop("Footprint", p["fp"], p["x"], p["y"], 0, hide=True))
        node.append(prop("Datasheet", unq(find_prop(p["sym"], "Datasheet")), p["x"], p["y"], 0, hide=True))
        if p["lcsc"]:
            node.append(prop("LCSC Part #", p["lcsc"], p["x"], p["y"], 0, hide=True))
        for k, v in p["extra"].items():
            if k != "hide_value":
                node.append(prop(k, v, p["x"], p["y"], 0, hide=True))
    seen = []
    for n in p["pins"]:
        if n not in seen:
            seen.append(n)
            node.append(["pin", q(n), ["uuid", q(uid())]])
    node.append(["instances", ["project", q(PROJECT),
                               ["path", q("/" + ROOT_UUID), ["reference", q(p["ref"])], ["unit", "1"]]]])
    return node


def write(sh, title_block):
    finish(sh)
    out = ["kicad_sch", ["version", "20260101"], ["generator", q("eeschema")], ["generator_version", q("10.0")],
           ["uuid", q(ROOT_UUID)], ["paper", q("A3")], title_block]
    libsyms = ["lib_symbols"]
    for lid in sh.lib_ids:
        s = copy.deepcopy(flat_symbol(lid))
        s[1] = q(lid)
        libsyms.append(s)
    out.append(libsyms)
    for (x, y) in sh.junctions:
        out.append(["junction", ["at", fmt(x), fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"],
                    ["uuid", q(uid())]])
    for (x, y) in sh.ncs:
        out.append(["no_connect", ["at", fmt(x), fmt(y)], ["uuid", q(uid())]])
    for w in sh.wires:
        out.append(["wire", ["pts", ["xy", fmt(w[0]), fmt(w[1])], ["xy", fmt(w[2]), fmt(w[3])]],
                    ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(uid())]])
    for (name, x, y, ang) in sh.labels:
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
        out.append(["label", q(name), ["at", fmt(x), fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                    ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()], ["uuid", q(uid())]])
    for (s, x, y, size, bold) in sh.texts:
        font = ["font", ["size", fmt(size), fmt(size)]]
        if bold:
            font += [["thickness", fmt(size * 0.2)], ["bold", "yes"]]
        out.append(["text", q(s), ["exclude_from_sim", "no"], ["at", fmt(x), fmt(y), "0"],
                    ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(uid())]])
    for ref in sh.order:
        out.append(sym_instance(sh, sh.parts[ref]))
    out.append(["sheet_instances", ["path", q("/"), ["page", q("1")]]])
    out.append(["embedded_fonts", "no"])
    open(SCH, "w", encoding="utf-8").write(dump(out) + "\n")


# ================================================================ the design
LIB = "${KIPRJMOD}/models/DV1_models.lib"
R0603, C0603, C0805, C1206 = ("Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric",
                              "Capacitor_SMD:C_0805_2012Metric", "Capacitor_SMD:C_1206_3216Metric")
C1210 = "Capacitor_SMD:C_1210_3225Metric"
SOT235, SOT236 = "Package_TO_SOT_SMD:SOT-23-5", "Package_TO_SOT_SMD:SOT-23-6"
SOD123, SMB = "Diode_SMD:D_SOD-123", "Diode_SMD:D_SMB"
TERM = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal"
HDR2 = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
OPAMP, COMP = "Amplifier_Operational:TLV9061xDBV", "Comparator:TLV3501AIDBV"
NMOS_FP = "Package_TO_SOT_SMD:TO-252-2"
G = 2.54


def U(x, y):
    return (round(x * G, 3), round(y * G, 3))


def simx(name, pins, dev="SUBCKT"):
    return {"Sim.Device": dev, "Sim.Library": LIB, "Sim.Name": name, "Sim.Pins": pins}


class Refs:
    def __init__(self):
        self.n = {}

    def __call__(self, prefix):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return "%s%d" % (prefix, self.n[prefix])


def W(sh, *pts):
    sh.wire(*[p if isinstance(p, str) else U(*p) for p in pts])


def LBL(sh, name, pt, ang=0):
    sh.label(name, U(*pt), ang)


def up(sh, spec, kind, d=1.5):
    spec = spec if isinstance(spec, str) else U(*spec)
    end = sh.stub(spec, 0, -d * G)
    sh.power(kind, end)


def dn(sh, spec, d=1.5):
    spec = spec if isinstance(spec, str) else U(*spec)
    end = sh.stub(spec, 0, d * G)
    sh.power("GND", end)


def lblstub(sh, spec, name, ang, d=1.5):
    """Short stub from a pin (down for 270, up for 90) ending in a net label."""
    spec = spec if isinstance(spec, str) else U(*spec)
    end = sh.stub(spec, 0, d * G if ang == 270 else -d * G)
    sh.label(name, end, ang)


def build():
    sh = Sheet()
    ref = Refs()
    T = sh.text

    def part(prefix, lib, x, y, value, fp="", rot=0, mirror=None, fields=None, extra=None, **kw):
        r = ref(prefix)
        if fields is None:
            fields = "T" if rot in (90, 270) else "R"
        sh.add(r, lib, *U(x, y), rot=rot, mirror=mirror, value=value, fp=fp, fields=fields, extra=extra, **kw)
        return r

    def res(val, x, y, rot=0, fp=R0603, extra=None):
        return part("R", "Device:R", x, y, val, fp, rot, extra=extra)

    def cap(val, x, y, rot=0, fp=C0603, extra=None):
        return part("C", "Device:C", x, y, val, fp, rot, extra=extra)

    def opamp(x, y):
        return part("U", OPAMP, x, y, "TLV9061", SOT235, fields="IC",
                    extra=dict(simx("OPAMP_RR", "1=out 2=vee 3=inp 4=inn 5=vcc"), MPN="TLV9061IDBVR"))

    def comp(x, y):
        return part("U", COMP, x, y, "TLV3501", SOT236, fields="IC",
                    extra=dict(simx("COMP_RR", "1=inn 2=vee 3=inp 4=vcc 5=out"), MPN="TLV3501AIDBVR"))

    def bypass(x, y, rail="+5V", val="100nF", fp=C0603):
        c = cap(val, x, y, 0, fp)
        up(sh, c + ".1", rail)
        dn(sh, c + ".2")
        return c

    def diode(x, y, rot=0):
        return part("D", "Device:D", x, y, "1N4148W", SOD123, rot,
                    extra=dict(simx("D1N4148W", "1=K 2=A", "D"), MPN="1N4148W"))

    # ============================================================ one half-bridge channel
    def leg(X, ox, oy, sig):
        def t(x, y):
            return (ox + x, oy + y)

        T("Channel %s: error integrator, PWM comparators, dead time, bridge leg, LC filter" % X,
          ox * G, (oy - 0.5) * G, 1.8, True)
        # ---- error integrator: SIG -> Rin -> (-), feedback from the switch node through Rt / Rb / Cx / Rf2
        rin = res("10k", *t(7, 21), rot=90)
        W(sh, rin + ".1", t(3, 21))
        LBL(sh, sig, t(3, 21), 180)
        ui = opamp(*t(22, 20))
        W(sh, rin + ".2", ui + ".4")
        rf2 = res("15k", *t(11, 25))
        W(sh, t(11, 21), rf2 + ".1")
        W(sh, rf2 + ".2", t(11, 29))
        rt = res("38.3k", *t(5, 29), rot=90, extra={"Tolerance": "0.1%"})
        W(sh, rt + ".2", t(11, 29))
        W(sh, rt + ".1", t(1, 29))
        LBL(sh, "SW_" + X, t(1, 29), 180)
        rb = res("10k", *t(11, 32.5), extra={"Tolerance": "0.1%"})
        W(sh, t(11, 29), rb + ".1")
        cx = cap("470pF", *t(15, 32.5), extra={"Dielectric": "C0G"})
        W(sh, t(11, 29), t(15, 29), cx + ".1")
        dn(sh, rb + ".2")
        dn(sh, cx + ".2")
        cint = cap("330pF", *t(22, 10), rot=90, extra={"Dielectric": "C0G"})
        W(sh, t(11, 21), t(11, 10), cint + ".1")
        W(sh, cint + ".2", t(28, 10), t(28, 20), ui + ".1")
        W(sh, ui + ".3", t(16, 19))
        LBL(sh, "VREF", t(16, 19), 180)
        up(sh, ui + ".5", "+5V")
        dn(sh, ui + ".2")
        bypass(*t(31, 14.5))
        # ---- two PWM comparators sharing the error and the triangle
        c1 = comp(*t(44, 14))
        c2 = comp(*t(44, 28))
        W(sh, t(28, 20), t(34, 20))
        LBL(sh, "E_" + X, t(31, 20), 0)
        W(sh, t(34, 13), t(34, 29))
        W(sh, t(34, 13), c1 + ".3")
        W(sh, t(34, 29), c2 + ".1")
        W(sh, t(37, 9), t(37, 27))
        W(sh, t(37, 15), c1 + ".1")
        W(sh, t(37, 27), c2 + ".3")
        LBL(sh, "TRI", t(37, 9), 90)
        for c in (c1, c2):
            up(sh, c + ".4", "+5V")
            dn(sh, c + ".2")
            lblstub(sh, c + ".6", "CMP_EN", 270)
        bypass(*t(46, 9))
        bypass(*t(46, 33.5))
        # ---- dead-time networks (rising edge delayed by Rd*Cd, falling edge through the diode)
        rdh = res("2.2k", *t(51, 14), rot=90)
        ddh = diode(*t(51, 11))
        cdh = cap("150pF", *t(54, 17), extra={"Dielectric": "C0G"})
        W(sh, c1 + ".5", rdh + ".1")
        W(sh, ddh + ".1", t(48.5, 11), t(48.5, 14))
        W(sh, ddh + ".2", t(54, 11), t(54, 14))
        W(sh, rdh + ".2", t(54, 14))
        W(sh, t(54, 14), cdh + ".1")
        dn(sh, cdh + ".2")
        rdl = res("2.2k", *t(51, 28), rot=90)
        ddl = diode(*t(51, 25))
        cdl = cap("150pF", *t(54, 31), extra={"Dielectric": "C0G"})
        W(sh, c2 + ".5", rdl + ".1")
        W(sh, ddl + ".1", t(48.5, 25), t(48.5, 28))
        W(sh, ddl + ".2", t(54, 25), t(54, 28))
        W(sh, rdl + ".2", t(54, 28))
        W(sh, t(54, 28), cdl + ".1")
        dn(sh, cdl + ".2")
        # ---- gate driver
        drv = part("U", "Driver_FET:IR2181", *t(66, 21), "IR2181", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                   fields="IC", extra=dict(simx("HBRIDGE_DRV", "1=hin 2=lin 3=com 4=lo 5=vcc 6=vs 7=ho 8=vb"),
                                           MPN="IR2181S"))
        W(sh, t(54, 14), t(58, 14), t(58, 21), drv + ".1")
        W(sh, t(54, 28), t(60, 28), t(60, 22), drv + ".2")
        up(sh, drv + ".5", "+12V", 4)
        cvcc = cap("100nF", *t(62, 13), rot=90)
        W(sh, cvcc + ".2", t(66, 13))
        dn(sh, cvcc + ".1")
        dn(sh, drv + ".3")
        # ---- bridge leg
        rgh = res("4.7", *t(73, 19), rot=90)
        qh = part("Q", "Transistor_FET:Q_NMOS_GDS", *t(77, 19), "IRFR3806", NMOS_FP,
                  extra=dict(simx("NMOS_60V", "1=g 2=d 3=s"), MPN="IRFR3806TRPBF"))
        W(sh, drv + ".7", rgh + ".1")
        W(sh, rgh + ".2", qh + ".1")
        rpd = res("10k", *t(74.5, 21.5))
        W(sh, rgh + ".2", rpd + ".1")
        W(sh, qh + ".3", t(78, 23))
        W(sh, drv + ".6", rpd + ".2")
        W(sh, rpd + ".2", t(78, 23))
        ql = part("Q", "Transistor_FET:Q_NMOS_GDS", *t(77, 29), "IRFR3806", NMOS_FP,
                  extra=dict(simx("NMOS_60V", "1=g 2=d 3=s"), MPN="IRFR3806TRPBF"))
        W(sh, t(78, 23), ql + ".2")
        rgl = res("4.7", *t(73, 29), rot=90)
        W(sh, drv + ".4", t(70, 24), t(70, 29), rgl + ".1")
        W(sh, rgl + ".2", ql + ".1")
        rpl = res("10k", *t(74.5, 31.5))
        W(sh, rgl + ".2", rpl + ".1")
        W(sh, rpl + ".2", t(78, 33))
        W(sh, ql + ".3", t(78, 33))
        dn(sh, t(78, 33))
        # high-side drain rail and local decoupling
        W(sh, qh + ".2", t(78, 14))
        up(sh, t(78, 14), "+24V", 2)
        cp1 = cap("4.7uF", *t(81, 16.5), fp=C1210, extra={"Note": "50 V X7R"})
        cp2 = cap("100nF", *t(83, 16.5))
        W(sh, t(78, 14), t(81, 14), cp1 + ".1")
        W(sh, t(81, 14), t(83, 14), cp2 + ".1")
        dn(sh, cp1 + ".2")
        dn(sh, cp2 + ".2")
        # ---- bootstrap
        dbt = diode(*t(86, 10), rot=90)
        rbt = res("10", *t(86, 14))
        cbt = cap("1uF", *t(86, 19), fp=C0805, extra={"Note": "25 V X7R"})
        a_pin, k_pin = sh.pin(dbt, 2), sh.pin(dbt, 1)
        assert k_pin[1] > a_pin[1], "bootstrap diode must have its anode on top"
        up(sh, dbt + ".2", "+12V", 2)
        W(sh, dbt + ".1", rbt + ".1")
        W(sh, rbt + ".2", cbt + ".1")
        W(sh, t(86, 16.5), t(87.5, 16.5))
        LBL(sh, "VB_" + X, t(87.5, 16.5), 0)
        W(sh, drv + ".8", t(70, 18))
        LBL(sh, "VB_" + X, t(70, 18), 90)
        W(sh, cbt + ".2", t(86, 23))
        # ---- switch node, LC filter
        lf = part("L", "Device:L", *t(96, 23), "33uH", "Inductor_SMD:L_Bourns-SRU1028_10.0x10.0mm", rot=90,
                  extra={"Note": "shielded, Isat >= 6 A (verify a real part)"})
        W(sh, t(78, 23), lf + ".1")
        LBL(sh, "SW_" + X, t(90, 23), 0)
        W(sh, lf + ".2", t(100, 23))
        ccm = cap("2.2uF", *t(100, 26.5), fp=C1206, extra={"Note": "50 V X7R, filter cap to GND"})
        W(sh, t(100, 23), ccm + ".1")
        dn(sh, ccm + ".2")
        W(sh, t(100, 23), t(103, 23))
        LBL(sh, "OUT_" + X, t(103, 23), 0)

    leg("A", 6, 4, "INV")

    # ============================================================ output
    T("Speaker output (one side GND)", 120 * G, 36 * G, 1.8, True)
    LBL(sh, "OUT_A", (120, 40), 180)
    cdc = part("C", "Device:C_Polarized", 128, 40, "2200uF", "Capacitor_THT:CP_Radial_D13.0mm_P5.00mm", rot=90,
               extra={"Note": "25 V, DC block: 12 V mid-rail sits on OUT_A; -3 dB at 18 Hz into 4 ohm"})
    W(sh, (120, 40), cdc + ".1")
    W(sh, cdc + ".2", (150, 40), (150, 46))
    LBL(sh, "SPK", (135, 40), 0)
    j3 = part("J", "Connector_Generic:Conn_01x02", 155, 46, "SPEAKER", TERM, fields=None, nosim=True,
              extra={"Pinout": "1 = signal (after DC-block cap), 2 = GND"})
    W(sh, (150, 46), j3 + ".1")
    W(sh, j3 + ".2", (151, 47))
    dn(sh, (151, 47))
    rl = part("R", "Device:R", 140, 43.5, "4", R0603, simonly=True, extra={"Note": "simulation load"})
    W(sh, (140, 40), rl + ".1")
    dn(sh, rl + ".2")
    T("4 ohm sim load", 142 * G, 44 * G, 1.27)
    T("Filter: 33 uH + 2.2 uF to GND, Butterworth ~30 kHz into 4 ohm", 120 * G, 55 * G, 1.27)

    # ============================================================ power input and rails
    T("Power: 24 V in, 12 V gate / 5 V logic rails", 3 * G, 91 * G, 1.8, True)
    j1 = part("J", "Connector_Generic:Conn_01x02", 9, 96, "24V IN", TERM, mirror="y", fields=None, nosim=True,
              extra={"Pinout": "1 = +24 V, 2 = GND"})
    W(sh, j1 + ".1", (14, 96), (28, 96))
    W(sh, j1 + ".2", (13, 97))
    dn(sh, (13, 97))
    W(sh, (13, 97), (15, 97))
    sh.power("FLAG", U(15, 97))
    up(sh, (14, 96), "+24V", 2)
    sh.power("FLAG", sh.stub(U(16, 96), 0, -1.5 * G))
    d1 = part("D", "Device:D_TVS", 18, 99, "SMBJ26CA", SMB, rot=90, nosim=True, extra={"MPN": "SMBJ26CA"})
    W(sh, (18, 96), d1 + ".2")          # rotated 90: pin 2 is the top pin
    dn(sh, d1 + ".1")
    c1 = part("C", "Device:C_Polarized", 23, 99, "470uF", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
              extra={"Note": "35 V"})
    W(sh, (23, 96), c1 + ".1")
    dn(sh, c1 + ".2")
    u1 = part("U", "Regulator_Linear:L7812", 34, 98, "L7812", "Package_TO_SOT_THT:TO-220-3_Vertical", fields="IC",
              extra=dict(simx("LDO_12V", "1=vin 2=gnd 3=vout"), MPN="L7812CV"))
    W(sh, (28, 96), (28, 98), u1 + ".1")
    cin = cap("100nF", 28, 101)
    W(sh, (28, 98), cin + ".1")
    dn(sh, cin + ".2")
    dn(sh, u1 + ".2")
    W(sh, u1 + ".3", (44, 98))
    c12 = cap("10uF", 41, 101, fp=C0805, extra={"Note": "25 V"})
    W(sh, (41, 98), c12 + ".1")
    dn(sh, c12 + ".2")
    up(sh, (44, 98), "+12V", 2)
    u2 = part("U", "Regulator_Linear:L78L05_SOT89", 52, 98, "L78L05", "Package_TO_SOT_SMD:SOT-89-3", fields="IC",
              extra=dict(simx("LDO_5V", "3=vin 2=gnd 1=vout"), MPN="L78L05ABUTR"))
    W(sh, (44, 98), u2 + ".3")
    cin5 = cap("100nF", 46, 101)
    W(sh, (46, 98), cin5 + ".1")
    dn(sh, cin5 + ".2")
    dn(sh, u2 + ".2")
    W(sh, u2 + ".1", (58, 98))
    c5 = cap("10uF", 58, 101, fp=C0805, extra={"Note": "10 V"})
    W(sh, (58, 98), c5 + ".1")
    dn(sh, c5 + ".2")
    up(sh, (58, 98), "+5V", 2)

    # ============================================================ audio input, inverter, VREF
    T("Audio input, inverter, 2.5 V reference", 62 * G, 87 * G, 1.8, True)
    j2 = part("J", "Connector_Generic:Conn_01x02", 64, 96, "AUDIO IN", HDR2, mirror="y", fields=None, nosim=True,
              extra={"Pinout": "1 = signal, 2 = GND"})
    cinp = cap("1uF", 71, 96, rot=90, fp=C0805, extra={"Note": "input coupling, film or C0G preferred"})
    W(sh, j2 + ".1", cinp + ".1")
    lblstub(sh, (68, 96), "AUDIO_IN", 90)
    W(sh, j2 + ".2", (67, 97))
    dn(sh, (67, 97))
    W(sh, cinp + ".2", (75, 96))
    lblstub(sh, (75, 96), "INAC", 270, 2.5)
    rbias = res("47k", 75, 92)
    W(sh, (75, 96), rbias + ".2")
    lblstub(sh, rbias + ".1", "VREF", 90)
    rinv1 = res("10k", 82, 97, rot=90)
    W(sh, (75, 96), (78, 96), (78, 97), rinv1 + ".1")
    u3 = opamp(92, 96)
    W(sh, rinv1 + ".2", u3 + ".4")
    rinv2 = res("10k", 92, 104, rot=90)
    W(sh, (86, 97), (86, 104), rinv2 + ".1")
    W(sh, u3 + ".1", (97, 96), (97, 104), rinv2 + ".2")
    W(sh, (97, 96), (99, 96))
    LBL(sh, "INV", (99, 96), 0)
    W(sh, u3 + ".3", (87, 95))
    LBL(sh, "VREF", (87, 95), 180)
    up(sh, u3 + ".5", "+5V")
    dn(sh, u3 + ".2")
    bypass(94, 90.5)
    rr1 = res("10k", 64, 104)
    rr2 = res("10k", 64, 109)
    cref = cap("10uF", 68, 109, fp=C0805, extra={"Note": "10 V"})
    W(sh, rr1 + ".2", rr2 + ".1")
    W(sh, (64, 106.5), (70, 106.5))
    LBL(sh, "VREF", (70, 106.5), 0)
    W(sh, (68, 106.5), cref + ".1")
    up(sh, rr1 + ".1", "+5V", 2)
    dn(sh, rr2 + ".2")
    dn(sh, cref + ".2")

    # ============================================================ triangle generator
    T("Triangle carrier, ~250 kHz, 1.8 Vpp around VREF", 112 * G, 87 * G, 1.8, True)
    uc = comp(125, 96)
    ui = opamp(150, 96)
    W(sh, uc + ".1", (120, 97))
    LBL(sh, "VREF", (120, 97), 180)
    rh1 = res("10k", 114, 95, rot=90)
    rh2 = res("24.9k", 125, 88, rot=90)
    W(sh, uc + ".3", (118, 95))
    W(sh, rh1 + ".2", (118, 95))
    W(sh, rh1 + ".1", (111, 95))
    LBL(sh, "TRI", (111, 95), 180)
    W(sh, rh2 + ".1", (118, 88), (118, 95))
    W(sh, rh2 + ".2", (130, 88), (130, 96))
    W(sh, uc + ".5", (132, 96))
    ri = res("10k", 135, 97, rot=90)
    W(sh, (132, 96), (132, 97), ri + ".1")
    W(sh, ri + ".2", ui + ".4")
    ct = cap("250pF", 143, 88, rot=90, extra={"Dielectric": "C0G", "Note": "sets fsw = 1/(1.6 Ri Ct)"})
    W(sh, (140, 97), (140, 88), ct + ".1")
    W(sh, ct + ".2", (156, 88), (156, 96))
    W(sh, ui + ".1", (158, 96))
    LBL(sh, "TRI", (158, 96), 0)
    W(sh, ui + ".3", (145, 95))
    LBL(sh, "VREF", (145, 95), 180)
    up(sh, uc + ".4", "+5V")
    up(sh, ui + ".5", "+5V")
    dn(sh, uc + ".2")
    dn(sh, ui + ".2")
    lblstub(sh, uc + ".6", "CMP_EN", 270)
    bypass(134, 92)
    bypass(161, 102)
    jp = part("JP", "Jumper:SolderJumper_3_Open", 135, 108, "CMP_EN",
              "Jumper:SolderJumper-3_P1.3mm_Open_Pad1.0x1.5mm", fields="IC", nosim=True,
              extra={"Note": "bridge to +5V or GND once the TLV3501 SHDN polarity is confirmed in the datasheet"})
    up(sh, jp + ".1", "+5V")
    dn(sh, jp + ".3")
    lblstub(sh, jp + ".2", "CMP_EN", 270)
    T("JP1: SHDN polarity - check TI datasheet before closing", 122 * G, 112 * G, 1.27)

    # ============================================================ simulation-only parts
    T("Simulation (not on the PCB)", 3 * G, 103 * G, 1.8, True)
    v1 = part("V", "Simulation_SPICE:VDC", 6, 108, "24", fields=None, simonly=True,
              extra={"Sim.Device": "V", "Sim.Type": "DC", "Sim.Pins": "1=+ 2=-", "Sim.Params": "dc=24"})
    up(sh, v1 + ".1", "+24V")
    dn(sh, v1 + ".2")
    v2 = part("V", "Simulation_SPICE:VSIN", 13, 108, "SIN", fields=None, simonly=True,
              extra={"Sim.Device": "V", "Sim.Type": "SIN", "Sim.Pins": "1=+ 2=-",
                     "Sim.Params": "dc=0 ampl=0.3 f=1k ac=1"})
    lblstub(sh, v2 + ".1", "AUDIO_IN", 90)
    dn(sh, v2 + ".2")
    T(".tran 20n 4m uic", 3 * G, 113 * G, 1.27)
    T(".ic v(/vref)=2.5 v(/inac)=2.5 v(/inv)=2.5 v(/e_a)=2.5 v(/tri)=2.5 v(/out_a)=12 v(/spk)=0", 3 * G, 115 * G, 1.27)
    T("(start the 1 uF / 47 k input bias and the VREF cap at their DC values; they settle in tens of ms)",
      3 * G, 116.5 * G, 1.0)

    tb = ["title_block", ["title", q("D-V1: analog class D amplifier, discrete, mono")],
          ["date", q("2026-10-30")], ["rev", q("1")],
          ["comment", "1", q("No class D IC: triangle oscillator, PWM comparators, IR2181 gate drivers, 4 N-MOSFETs")],
          ["comment", "2", q("24 V, ~15 W into 4 ohm, speaker one side GND via DC-block cap; closed loop from the switch node")]]
    return sh, tb


if __name__ == "__main__":
    sh, tb = build()
    write(sh, tb)
    print("wrote", SCH, "-", len([r for r in sh.order if not r.startswith("#")]), "parts,", len(sh.wires), "wires,",
          len(sh.labels), "labels,", len(sh.junctions), "junctions")
