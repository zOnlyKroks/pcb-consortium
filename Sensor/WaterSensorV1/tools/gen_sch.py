"""SUPERSEDED (2026-10-14): the schematic has since been edited in KiCad (J4 UART, ...). Do not re-run;
it would overwrite those edits. Kept for reference only.

Generate WaterSensorV1.kicad_sch: every part placed by hand, real wires, power symbols on short stubs,
net labels only where an MCU GPIO links to a peripheral block.

Wires are split automatically wherever a pin, label or another wire's end lands on them, and junctions are
added where three or more connections meet.  Run check_netlist.py afterwards.
"""
import copy, math, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
SCH = os.path.join(PRJ, "WaterSensorV1.kicad_sch")
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
LIBS = {"WaterSensorV1": os.path.join(PRJ, "lib", "WaterSensorV1.kicad_sym")}
ROOT_UUID = "d062679b-5a34-4425-8b92-ed950f80703e"
PROJECT = "WaterSensorV1"


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
            dnp=False):
        sym = flat_symbol(lib_id)
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)
        part = dict(ref=ref, lib_id=lib_id, x=x, y=y, rot=rot, mirror=mirror, sym=sym,
                    value=value if value is not None else unq(find_prop(sym, "Value")), fp=fp, lcsc=lcsc,
                    fields=fields, extra=extra or {}, dnp=dnp, pins=pins_of(sym))
        self.parts[ref] = part
        self.order.append(ref)
        return part

    def pin(self, ref, num):
        p = self.parts[ref]
        lx, ly = p["pins"][str(num)]
        return xform(p, lx, -ly)

    def P(self, spec):
        if isinstance(spec, str):
            ref, num = spec.split(".")
            return self.pin(ref, num)
        return spec

    def power(self, kind, at, rot=0):
        at = self.P(at)
        lib_id = {"VBAT": "WaterSensorV1:VBAT", "FLAG": "power:PWR_FLAG"}.get(kind, "power:" + kind)
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
    node += [["unit", "1"], ["exclude_from_sim", "no"], ["in_bom", "no" if is_pwr else "yes"],
             ["on_board", "no" if is_pwr else "yes"], ["dnp", "yes" if p["dnp"] else "no"], ["uuid", q(uid())]]
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
R0603, C0603, LED0603 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "LED_SMD:LED_0603_1608Metric"
SOT23, SOT235, SOT236 = "Package_TO_SOT_SMD:SOT-23", "Package_TO_SOT_SMD:SOT-23-5", "Package_TO_SOT_SMD:SOT-23-6"
SWFP = "WaterSensorV1:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5"
LCSC = {"5.1k": "C23186", "1k": "C21190", "10k": "C98220", "100k": "C25803", "1M": "C22935",
        "10uF": "C19702", "100nF": "C76711", "1uF": "C329944"}


def R(sh, ref, val, x, y, rot=0, fields="R"):
    return sh.add(ref, "Device:R", x, y, rot, value=val, fp=R0603, lcsc=LCSC[val], fields=fields)


def C(sh, ref, val, x, y, rot=0, fields="R"):
    return sh.add(ref, "Device:C", x, y, rot, value=val, fp=C0603, lcsc=LCSC[val], fields=fields)


def build():
    sh = Sheet()
    T = sh.text

    # ------------------------------------------------ USB-C, ESD, CC
    T("USB-C (charge + flash)", 17.78, 43.18, 2, True)
    sh.add("J1", "Connector:USB_C_Receptacle_USB2.0_16P", 30.48, 71.12, value="USB-C",
           fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", lcsc="C165948",
           fields=((30.48, 45.72, None), (30.48, 48.26, None)))
    sh.wire("J1.A4", (134.62, 55.88), (134.62, 63.5))                      # VBUS rail -> charger VCC
    sh.power("FLAG", (78.74, 55.88))
    sh.power("VBUS", (101.6, 55.88))
    sh.wire("J1.A5", (68.58, 60.96), (68.58, 63.5))                        # CC1
    R(sh, "R1", "5.1k", 68.58, 67.31)
    sh.power("GND", "R1.2")
    sh.wire("J1.B5", (58.42, 63.5))                                        # CC2
    R(sh, "R2", "5.1k", 58.42, 67.31)
    sh.power("GND", "R2.2")
    sh.wire("J1.A7", (53.34, 68.58))                                       # D- pair -> x 53.34
    sh.wire("J1.B7", (53.34, 71.12))
    sh.wire((53.34, 68.58), (53.34, 99.06))
    sh.wire("J1.A6", (48.26, 73.66))                                       # D+ pair -> x 48.26
    sh.wire("J1.B6", (48.26, 76.2))
    sh.wire((48.26, 73.66), (48.26, 101.6))
    sh.add("U1", "Power_Protection:USBLC6-2SC6", 66.04, 99.06, value="USBLC6-2SC6", fp=SOT236, lcsc="C2687116",
           fields=((71.12, 91.44, "left"), (71.12, 109.22, "left")))
    sh.wire((53.34, 99.06), "U1.1")
    sh.wire((48.26, 101.6), "U1.3")
    sh.label("USB_DN", (53.34, 88.9), 90)
    sh.label("USB_DP", (48.26, 88.9), 90)
    sh.power("VBUS", "U1.5")
    sh.power("GND", "U1.2")
    sh.label("USB_DN", sh.stub("U1.6", 7.62, 0))
    sh.label("USB_DP", sh.stub("U1.4", 7.62, 0))
    sh.nc("J1.A8")
    sh.nc("J1.B8")
    sh.wire("J1.A1", (30.48, 99.06))
    sh.power("GND", (30.48, 99.06))
    sh.wire("J1.SH", (22.86, 96.52), (30.48, 96.52))
    sh.wire((30.48, 96.52), (35.56, 96.52))
    sh.power("FLAG", (35.56, 96.52))

    # ------------------------------------------------ Li-ion charger
    T("Li-ion charger, 196 mA", 101.6, 43.18, 2, True)
    C(sh, "C1", "10uF", 88.9, 59.69)
    sh.power("GND", "C1.2")
    R(sh, "R4", "1k", 116.84, 59.69, fields="L")
    sh.add("D1", "Device:LED", 116.84, 67.31, rot=90, value="RED", fp=LED0603, lcsc="C125099", fields="L",
           extra={"Note": "lit while charging"})
    sh.add("U2", "Battery_Management:LTC4054ES5-4.2", 134.62, 71.12, value="TP4054-42", fp=SOT235, lcsc="C32574",
           fields=((137.16, 59.69, "left"), (137.16, 87.63, "left")),
           extra={"MPN": "TP4054-42-SOT25R (LTC4054 pinout)"})
    sh.wire("D1.1", "U2.1")
    sh.wire("U2.5", (121.92, 73.66))
    R(sh, "R3", "5.1k", 121.92, 77.47, fields="L")
    sh.power("GND", "R3.2")
    sh.power("GND", "U2.2")
    T("I = 1000 V / R3", 101.6, 92.71)

    # ------------------------------------------------ battery, reverse-polarity FET, LDO
    T("1S Li-ion / LiPo + 3.3 V LDO (Iq 2 uA)", 152.4, 43.18, 2, True)
    sh.wire("U2.3", (223.52, 71.12))                                       # VBAT line
    sh.power("VBAT", (152.4, 71.12))
    sh.add("Q1", "Transistor_FET:Q_PMOS_GSD", 175.26, 86.36, rot=90, value="SI2301CDS", fp=SOT23, lcsc="C10487",
           fields=((175.26, 78.74, None), (175.26, 80.645, None)), extra={"Note": "reverse-battery protection"})
    sh.wire("Q1.2", (180.34, 71.12))
    sh.power("GND", "Q1.1")
    sh.add("J2", "Connector_Generic:Conn_01x02", 157.48, 83.82, mirror="y", value="LiPo 1S",
           fp="WaterSensorV1:CONN-TH_2P-P2.00_BX-PH2.0-2PWZ", lcsc="C18077753",
           fields=((157.48, 78.74, None), (157.48, 92.71, None)), extra={"Pinout": "1 = BAT+, 2 = GND"})
    sh.wire("J2.1", "Q1.3")
    sh.wire("J2.2", (165.1, 86.36))
    sh.power("GND", (165.1, 86.36))
    T("BAT+", 163.83, 82.55)
    C(sh, "C2", "10uF", 190.5, 74.93)
    sh.power("GND", "C2.2")
    sh.add("U3", "Regulator_Linear:AP2112K-3.3", 231.14, 73.66, value="RT9080-33GJ5", fp=SOT235, lcsc="C841192",
           fields=((231.14, 64.77, None), (231.14, 86.36, None)), extra={"MPN": "RT9080-33GJ5 (AP2112K pinout)"})
    sh.wire("U3.3", (220.98, 73.66), (220.98, 71.12))
    sh.power("GND", "U3.2")
    sh.nc("U3.4")
    sh.wire("U3.5", (259.08, 71.12))
    C(sh, "C3", "10uF", 248.92, 74.93)
    sh.power("GND", "C3.2")
    sh.power("+3V3", (259.08, 71.12))

    # ------------------------------------------------ battery voltage (switched divider) + USB detect
    T("Battery sense (no drain while off)", 302.26, 35.56, 2, True)
    sh.add("Q2", "Transistor_FET:Q_PMOS_GSD", 342.9, 53.34, mirror="x", value="SI2301CDS", fp=SOT23, lcsc="C10487")
    sh.wire("Q2.2", (345.44, 43.18), (332.74, 43.18))
    sh.power("VBAT", (345.44, 43.18))
    R(sh, "R7", "1M", 332.74, 46.99, fields="L")
    sh.wire("R7.2", (332.74, 53.34), "Q2.1")
    sh.add("Q3", "Transistor_FET:BSS138", 330.2, 66.04, value="BSS138", fp=SOT23, lcsc="C78284",
           fields=((326.39, 59.69, "right"), (326.39, 61.595, "right")))
    sh.wire((332.74, 53.34), "Q3.3")
    sh.power("GND", "Q3.2")
    sh.wire("Q3.1", (312.42, 66.04))
    sh.label("VBAT_MEAS_EN", (312.42, 66.04), 180)
    R(sh, "R8", "1M", 317.5, 69.85, fields="L")
    sh.power("GND", "R8.2")
    R(sh, "R9", "100k", 345.44, 64.77)
    sh.wire("Q2.3", "R9.1")
    R(sh, "R10", "100k", 345.44, 77.47, fields="L")
    sh.wire("R9.2", "R10.1")
    sh.power("GND", "R10.2")
    sh.wire((345.44, 71.12), (360.68, 71.12))
    sh.label("VBAT_ADC", (360.68, 71.12), 0)
    C(sh, "C6", "100nF", 353.06, 74.93)
    sh.power("GND", "C6.2")
    T("ADC = VBAT / 2 while VBAT_MEAS_EN is high", 302.26, 90.17)

    T("USB detect", 302.26, 80.01, 2, True)
    R(sh, "R5", "100k", 304.8, 104.14 - 12.7, fields="L")
    sh.power("VBUS", "R5.1")
    R(sh, "R6", "100k", 304.8, 104.14, fields="L")
    sh.wire("R5.2", "R6.1")
    sh.power("GND", "R6.2")
    sh.wire((304.8, 97.79), (312.42, 97.79))
    sh.label("VBUS_DET", (312.42, 97.79), 0)

    # ------------------------------------------------ MCU
    T("ESP32-C6 (WiFi 6 / BLE / Zigbee / Thread)", 101.6, 154.94, 2, True)
    sh.add("U4", "WaterSensorV1:ESP32-C6-WROOM-1-N4", 153.67, 190.5, value="ESP32-C6-WROOM-1-N4",
           fp="WaterSensorV1:ESP32-C6-WROOM-1", lcsc="C6034714", fields="IC")
    sh.stub("U4.1", -2.54, 0)
    sh.power("GND", (139.7, 167.64), rot=270)
    sh.wire("U4.2", (134.62, 170.18), (134.62, 165.1))
    sh.power("+3V3", (134.62, 165.1))
    sh.wire("U4.3", (104.14, 172.72))                                      # EN
    R(sh, "R11", "10k", 124.46, 168.91, fields="L")
    sh.power("+3V3", "R11.1")
    C(sh, "C7", "1uF", 114.3, 176.53, fields="L")
    sh.power("GND", "C7.2")
    sh.add("SW1", "WaterSensorV1:SW_Tact_4P", 104.14, 177.8, rot=90, value="RESET", fp=SWFP, lcsc="C318884",
           fields=((101.6, 176.53, "right"), (101.6, 179.07, "right")))
    sh.power("GND", "SW1.1")
    for pin, net in (("4", "VBAT_MEAS_EN"), ("5", "PROBE_EN_N"), ("6", "LED"), ("8", "VBAT_ADC"),
                     ("9", "PROBE_ADC"), ("13", "USB_DN"), ("14", "USB_DP")):
        sh.label(net, sh.stub("U4." + pin, -5.08, 0), 180)
    for pin in ("7", "11", "12", "16", "17", "18", "19", "20", "21", "22", "23"):
        sh.nc("U4." + pin)
    sh.wire("U4.10", (124.46, 190.5))                                      # IO8 strap
    R(sh, "R13", "10k", 124.46, 186.69, fields="L")
    sh.power("+3V3", "R13.1")
    sh.wire("U4.15", (104.14, 203.2))                                      # IO9 BOOT
    R(sh, "R12", "10k", 114.3, 199.39, fields="L")
    sh.power("+3V3", "R12.1")
    sh.add("SW2", "WaterSensorV1:SW_Tact_4P", 104.14, 208.28, rot=90, value="BOOT", fp=SWFP, lcsc="C318884",
           fields=((101.6, 207.01, "right"), (101.6, 209.55, "right")))
    sh.power("GND", "SW2.1")
    sh.stub("U4.28", 2.54, 0)
    sh.power("GND", (167.64, 191.77), rot=90)
    for pin, net in (("27", "VBUS_DET"), ("26", "USER_BTN"), ("25", "TXD0"), ("24", "RXD0")):
        sh.label(net, sh.stub("U4." + pin, 5.08, 0), 0)
    T("IO8 high + IO9 low at reset = download mode", 101.6, 226.06)
    T("USB D-/D+ = IO12/IO13 (USB-Serial-JTAG)", 101.6, 229.87)
    T("Deep-sleep wake: USER_BTN (IO3), VBUS_DET (IO2), RTC timer", 101.6, 233.68)

    C(sh, "C4", "10uF", 180.34, 172.72)
    C(sh, "C5", "100nF", 190.5, 172.72)
    sh.wire("C4.1", "C5.1")
    sh.wire("C4.2", "C5.2")
    sh.power("+3V3", (185.42, 168.91))
    sh.power("GND", (185.42, 176.53))
    T("at U4 pin 2", 179.07, 182.88)

    # ------------------------------------------------ user I/O + test points
    T("User I/O", 203.2, 154.94, 2, True)
    sh.wire((205.74, 177.8), (214.63, 177.8))
    sh.label("LED", (205.74, 177.8), 180)
    R(sh, "R15", "1k", 218.44, 177.8, rot=90, fields="T")
    sh.add("D2", "Device:LED", 229.87, 177.8, rot=180, value="GREEN", fp=LED0603, lcsc="C125098",
           fields=((229.87, 173.355, None), (229.87, 182.245, None)))
    sh.wire("R15.2", "D2.2")
    sh.wire("D2.1", (236.22, 177.8))
    sh.power("GND", (236.22, 177.8))
    sh.wire((205.74, 200.66), (226.06, 200.66))
    sh.label("USER_BTN", (205.74, 200.66), 180)
    R(sh, "R14", "100k", 218.44, 196.85, fields="L")
    sh.power("+3V3", "R14.1")
    sh.add("SW3", "WaterSensorV1:SW_Tact_4P", 226.06, 205.74, rot=90, value="USER", fp=SWFP, lcsc="C318884",
           fields=((228.6, 204.47, "left"), (228.6, 207.01, "left")))
    sh.power("GND", "SW3.1")

    T("Test pads", 248.92, 154.94, 2, True)
    for i, (y, net) in enumerate(((165.1, "TXD0"), (172.72, "RXD0"), (184.15, "+3V3"), (194.31, "VBAT"),
                                   (201.93, "GND"))):
        ref = "TP%d" % (i + 1)
        sh.add(ref, "Connector:TestPoint", 251.46, y, rot=90, value=net if net != "+3V3" else "3V3",
               fp="TestPoint:TestPoint_Pad_D1.5mm", fields=((245.11, y - 1.27, "right"), (245.11, y + 1.27, "right")),
               extra={"hide_value": True})
        end = sh.stub(ref + ".1", 5.08, 0)
        if net in ("TXD0", "RXD0"):
            sh.label(net, end, 0)
        else:
            sh.power({"VBAT": "VBAT"}.get(net, net), end)

    # ------------------------------------------------ soil probe connector
    T("Soil probe (capacitive, 3-pin PH2.0)", 292.1, 144.78, 2, True)
    sh.add("Q4", "Transistor_FET:Q_PMOS_GSD", 335.28, 177.8, rot=270, value="SI2301CDS", fp=SOT23, lcsc="C10487",
           fields=((335.28, 186.69, None), (335.28, 188.595, None)), extra={"Note": "probe power switch"})
    sh.wire("Q4.2", (325.12, 180.34))
    sh.power("+3V3", (325.12, 180.34))
    sh.wire("Q4.1", (335.28, 170.18), (307.34, 170.18))
    sh.label("PROBE_EN_N", (307.34, 170.18), 180)
    R(sh, "R16", "100k", 317.5, 166.37)
    sh.power("+3V3", "R16.1")
    sh.add("J3", "Connector_Generic:Conn_01x03", 360.68, 180.34, mirror="x", value="SOIL PROBE",
           fp="WaterSensorV1:CONN-TH_3P-P2.00_BX-PH2.0-3PWZ", lcsc="C18077754",
           fields=((363.22, 175.26, "left"), (363.22, 186.69, "left")),
           extra={"Pinout": "1 = GND, 2 = VCC (switched 3V3), 3 = AOUT"})
    sh.wire("Q4.3", "J3.2")
    C(sh, "C8", "100nF", 345.44, 184.15, fields="L")
    sh.power("GND", "C8.2")
    sh.wire("J3.1", (353.06, 182.88))
    sh.power("GND", (353.06, 182.88))
    sh.wire("J3.3", (347.98, 177.8), (347.98, 154.94), (344.17, 154.94))
    R(sh, "R17", "1k", 340.36, 154.94, rot=90, fields="T")
    sh.wire("R17.1", (322.58, 154.94))
    sh.label("PROBE_ADC", (322.58, 154.94), 180)
    C(sh, "C9", "100nF", 330.2, 158.75)
    sh.power("GND", "C9.2")
    T("GND", 364.49, 183.515)
    T("VCC", 364.49, 180.975)
    T("AOUT", 364.49, 178.435)
    T("Fits the common 3-pin capacitive soil probes (v1.2 / v2.0, GND-VCC-AOUT).", 292.1, 200.66)
    T("Probe is powered only while measuring (PROBE_EN_N low, ~5 mA for ~150 ms).", 292.1, 204.47)

    tb = ["title_block", ["title", q("WaterSensorV1: ultra-low-power plant soil-moisture node")],
          ["date", q("2026-10-14")], ["rev", q("1")],
          ["comment", "1", q("ESP32-C6, 1S Li-ion + USB-C charging, external capacitive probe")],
          ["comment", "2", q("Report interval 10 min ... 24 h (RTC deep sleep, ~10 uA)")]]
    return sh, tb


if __name__ == "__main__":
    sh, tb = build()
    write(sh, tb)
    print("wrote", SCH, "-", len([r for r in sh.order if not r.startswith("#")]), "parts,", len(sh.wires), "wires,",
          len(sh.labels), "labels,", len(sh.junctions), "junctions")
