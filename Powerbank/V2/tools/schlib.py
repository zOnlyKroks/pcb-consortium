"""Small KiCad 10 schematic writer used by gen_sch.py (hierarchical, multi-unit, global labels).

Copied from Networking/NetworkSwitchV1/tools (framework only); project paths and power symbols adapted.

Everything is placed by explicit coordinates: parts, real wires, power symbols, global labels only for nets
that leave a sheet.  Wires are split wherever a pin, label or another wire end lands on them and junctions are
added where three or more items meet.  UUIDs are derived from the sheet name and item order, so re-running the
generator gives stable files.
"""
import copy, math, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
LIBS = {"PowerbankV2": os.path.join(PRJ, "lib", "PowerbankV2.kicad_sym")}
NS = uuid.UUID("b3d1f0a4-7c2e-4f55-8a19-2e6c4d9b7a30")


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
    """Library symbol with `extends` resolved."""
    lib, name = lib_id.split(":")
    sym = copy.deepcopy(lib_tree(lib)[name])
    ext = find(sym, "extends")
    if ext:
        pname = unq(ext[1])
        base = flat_symbol(lib + ":" + pname)
        base[1] = q(name)
        for sub in find_all(base, "symbol"):
            sub[1] = q(unq(sub[1]).replace(pname + "_", name + "_", 1))
        child = {unq(p[1]): p for p in find_all(sym, "property")}
        for i, c in enumerate(base):
            if isinstance(c, list) and c[0] == "property" and unq(c[1]) in child:
                base[i] = child.pop(unq(c[1]))
        idx = max(i for i, c in enumerate(base) if isinstance(c, list) and c[0] == "property")
        for p in child.values():
            idx += 1
            base.insert(idx, p)
        sym = base
    else:
        sym[1] = q(name)
    return sym


def pins_of(sym, unit=1):
    """{number: (x, y)} in symbol coordinates (Y up) for `unit` (plus common unit 0), body style 1."""
    out = {}
    for sub in find_all(sym, "symbol"):
        parts = unq(sub[1]).rsplit("_", 2)
        if len(parts) == 3 and (parts[1] not in ("0", str(unit)) or parts[2] not in ("0", "1")):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            out[unq(find(p, "number")[1])] = (float(at[1]), float(at[2]))
    return out


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


# ---------------------------------------------------------------- sheet model
POWER_LIB = {"FLAG": "power:PWR_FLAG"}
DOWN_POWER = ("GND",)


class Project:
    def __init__(self, name, root_uuid):
        self.name = name
        self.root_uuid = root_uuid
        self.sheets = []
        self.npwr = 0
        self.nflg = 0

    def sheet(self, file, title, page):
        sh = Sheet(self, file, title, page)
        self.sheets.append(sh)
        return sh


class Sheet:
    def __init__(self, prj, file, title, page):
        self.prj, self.file, self.title, self.page = prj, file, title, page
        self.uuid = str(uuid.uuid5(NS, "sheetfile:" + file))
        self.block_uuid = str(uuid.uuid5(NS, "sheetblock:" + file))
        self.parts, self.order = {}, []
        self.wires, self.labels, self.glabels, self.ncs, self.texts, self.lib_ids = [], [], [], [], [], []
        self.n = 0
        self.block = None

    def uid(self):
        self.n += 1
        return str(uuid.uuid5(NS, "%s:%d" % (self.file, self.n)))

    # placement ---------------------------------------------------------
    def add(self, ref, lib_id, x, y, rot=0, mirror=None, value=None, fp="", lcsc="", fields="R", extra=None,
            dnp=False, unit=1):
        sym = flat_symbol(lib_id)
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)
        key = ref if unit == 1 or ref.startswith("#") else "%s.%d" % (ref, unit)
        part = dict(ref=ref, key=key, lib_id=lib_id, x=r2(x), y=r2(y), rot=rot, mirror=mirror, sym=sym, unit=unit,
                    value=value if value is not None else unq(find_prop(sym, "Value")), fp=fp, lcsc=lcsc,
                    fields=fields, extra=extra or {}, dnp=dnp, pins=pins_of(sym, unit))
        if key in self.parts:
            raise ValueError("duplicate " + key)
        self.parts[key] = part
        self.order.append(key)
        return part

    def pin(self, key, num):
        p = self.parts[key]
        lx, ly = p["pins"][str(num)]
        return xform(p, lx, -ly)

    def P(self, spec):
        """'R1.2' -> pin position (unit parts: 'U201.3:98' = unit 3 pin 98); tuples pass through."""
        if isinstance(spec, str):
            key, num = spec.rsplit(".", 1)
            return self.pin(key, num)
        return (r2(spec[0]), r2(spec[1]))

    def power(self, kind, at, rot=0):
        at = self.P(at)
        lib_id = POWER_LIB.get(kind, "power:" + kind)
        if kind == "FLAG":
            self.prj.nflg += 1
            ref = "#FLG%03d" % self.prj.nflg
        else:
            self.prj.npwr += 1
            ref = "#PWR%03d" % self.prj.npwr
        self.add(ref, lib_id, at[0], at[1], rot=rot, fields="pwr")

    # wiring --------------------------------------------------------------
    def wire(self, *pts):
        pts = [self.P(p) for p in pts]
        for a, b in zip(pts, pts[1:]):
            if abs(a[0] - b[0]) > 1e-6 and abs(a[1] - b[1]) > 1e-6:
                raise ValueError("diagonal wire %s -> %s in %s" % (a, b, self.file))
            if a != b:
                self.wires.append((a[0], a[1], b[0], b[1]))
        return pts[-1]

    def stub(self, spec, dx, dy):
        a = self.P(spec)
        b = (r2(a[0] + dx), r2(a[1] + dy))
        self.wire(a, b)
        return b

    def label(self, name, at, angle=0):
        at = self.P(at)
        self.labels.append((name, at[0], at[1], angle))

    def glabel(self, name, at, angle=0, shape="bidirectional"):
        at = self.P(at)
        self.glabels.append((name, at[0], at[1], angle, shape))

    def nc(self, spec):
        self.ncs.append(self.P(spec))

    def text(self, s, x, y, size=1.27, bold=False):
        self.texts.append((s, r2(x), r2(y), size, bold))


# ---------------------------------------------------------------- connectivity post-processing
def on_seg(pt, w):
    x, y = pt
    x1, y1, x2, y2 = w
    if x1 == x2 == x:
        return min(y1, y2) < y < max(y1, y2)
    if y1 == y2 == y:
        return min(x1, x2) < x < max(x1, x2)
    return False


def pin_points(sh):
    pts = []
    for key in sh.order:
        p = sh.parts[key]
        seen = set()
        for n in p["pins"]:
            e = sh.pin(key, n)
            if e not in seen:
                seen.add(e)
                pts.append(e)
    return pts


def finish(sh):
    pins = pin_points(sh)
    pts = set(pins)
    anchors = {(l[1], l[2]) for l in sh.labels} | {(g[1], g[2]) for g in sh.glabels}
    pts |= anchors
    for w in sh.wires:
        pts.add((w[0], w[1]))
        pts.add((w[2], w[3]))
    # overlapping collinear wires are always a mistake here
    ws = list(dict.fromkeys(sh.wires))
    for i, a in enumerate(ws):
        for b in ws[i + 1:]:
            if a[0] == a[2] == b[0] == b[2]:
                lo, hi = max(min(a[1], a[3]), min(b[1], b[3])), min(max(a[1], a[3]), max(b[1], b[3]))
                if hi > lo:
                    raise ValueError("%s: overlapping vertical wires %s %s" % (sh.file, a, b))
            if a[1] == a[3] == b[1] == b[3]:
                lo, hi = max(min(a[0], a[2]), min(b[0], b[2])), min(max(a[0], a[2]), max(b[0], b[2]))
                if hi > lo:
                    raise ValueError("%s: overlapping horizontal wires %s %s" % (sh.file, a, b))
    changed = True
    wires = ws
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
    count = {}
    for w in wires:
        for e in ((w[0], w[1]), (w[2], w[3])):
            count[e] = count.get(e, 0) + 1
    for e in pins:
        count[e] = count.get(e, 0) + 1
    sh.junctions = sorted(e for e, c in count.items() if c >= 3)
    sh.crossings = []
    for i, a in enumerate(wires):
        for b in wires[i + 1:]:
            if (a[0] == a[2]) != (b[0] == b[2]):
                v, h = (a, b) if a[0] == a[2] else (b, a)
                if min(h[0], h[2]) < v[0] < max(h[0], h[2]) and min(v[1], v[3]) < h[1] < max(v[1], v[3]):
                    sh.crossings.append((v[0], h[1]))
    pinset = set(pins)
    sh.dangling = [e for e, c in count.items() if c == 1 and e not in anchors and e not in pinset]
    # pins of different parts touching without a wire are fine; pins that touch nothing are reported by ERC


# ---------------------------------------------------------------- writer
def prop(key, val, x, y, angle=0, hide=False, justify=None):
    eff = ["effects", ["font", ["size", "1.27", "1.27"]]]
    if justify:
        eff.append(["justify"] + justify.split())
    node = ["property", q(key), q(val), ["at", fmt(x), fmt(y), str(angle)]]
    if hide:
        node.append(["hide", "yes"])
    node.append(eff)
    return node


def field_pos(sh, p):
    x, y = p["x"], p["y"]
    pins = [sh.pin(p["key"], n) for n in p["pins"]]
    ys = [b for _, b in pins] + [y]
    mode = p["fields"]
    if isinstance(mode, tuple):
        return mode
    if mode == "R":
        return ((x + 2.54, y - 1.27, "left"), (x + 2.54, y + 1.27, "left"))
    if mode == "L":
        return ((x - 2.54, y - 1.27, "right"), (x - 2.54, y + 1.27, "right"))
    if mode == "T":
        return ((x, y - 4.445, None), (x, y - 2.54, None))
    if mode == "B":
        return ((x, y + 2.54, None), (x, y + 4.445, None))
    if mode == "IC":
        return ((x, min(ys) - 2.54, None), (x, max(ys) + 2.54, None))
    raise ValueError(mode)


def sym_instance(sh, p, path):
    node = ["symbol", ["lib_id", q(p["lib_id"])], ["at", fmt(p["x"]), fmt(p["y"]), str(p["rot"])]]
    if p["mirror"]:
        node.append(["mirror", p["mirror"]])
    is_pwr = p["fields"] == "pwr"
    lib_bom = find(p["sym"], "in_bom")
    lib_board = find(p["sym"], "on_board")
    in_bom = "no" if is_pwr or (lib_bom and lib_bom[1] == "no") else "yes"
    on_board = "no" if is_pwr or (lib_board and lib_board[1] == "no") else "yes"
    node += [["unit", str(p["unit"])], ["exclude_from_sim", "no"], ["in_bom", in_bom],
             ["on_board", on_board], ["dnp", "yes" if p["dnp"] else "no"], ["uuid", q(sh.uid())]]
    fa = 90 if p["rot"] in (90, 270) else 0
    if is_pwr:
        down = any(p["lib_id"].endswith(":" + k) for k in DOWN_POWER)
        if p["rot"] == 180:
            down = not down
        vx, vy = p["x"], p["y"] + (3.81 if down else -3.81)
        if p["rot"] in (90, 270):
            # glyph points sideways: text beyond the glyph tip, horizontal
            left = (p["rot"] == 90) != down
            vx, vy = p["x"] + (-3.81 if left else 3.81), p["y"]
            just = "right" if left else "left"
            if p["rot"] == 90:            # KiCad mirrors the justification at this orientation
                just = "left" if left else "right"
            node.append(prop("Reference", p["ref"], p["x"], p["y"], fa, hide=True))
            node.append(prop("Value", p["value"], vx, vy, fa, justify=just))
        else:
            node.append(prop("Reference", p["ref"], p["x"], p["y"], 0, hide=True))
            node.append(prop("Value", p["value"], vx, vy, 0, hide=p["lib_id"] == "power:PWR_FLAG" and False))
        node.append(prop("Footprint", "", p["x"], p["y"], 0, hide=True))
        node.append(prop("Datasheet", "", p["x"], p["y"], 0, hide=True))
    else:
        (rx, ry, rj, *ra), (vx, vy, vj, *va) = field_pos(sh, p)
        if p["rot"] in (90, 180):        # KiCad mirrors the justification of fields on these orientations
            flip = {"left": "right", "right": "left"}
            rj, vj = flip.get(rj, rj), flip.get(vj, vj)
        node.append(prop("Reference", p["ref"], rx, ry, ra[0] if ra else fa, justify=rj))
        node.append(prop("Value", p["value"], vx, vy, va[0] if va else fa, justify=vj,
                         hide=p["extra"].get("hide_value", False)))
        node.append(prop("Footprint", p["fp"], p["x"], p["y"], 0, hide=True))
        node.append(prop("Datasheet", unq(find_prop(p["sym"], "Datasheet")), p["x"], p["y"], 0, hide=True))
        node.append(prop("Description", unq(find_prop(p["sym"], "Description")), p["x"], p["y"], 0, hide=True))
        if p["lcsc"]:
            node.append(prop("LCSC Part #", p["lcsc"], p["x"], p["y"], 0, hide=True))
        for k, v in p["extra"].items():
            if k != "hide_value":
                node.append(prop(k, v, p["x"], p["y"], 0, hide=True))
    seen = []
    for n in p["pins"]:
        if n not in seen:
            seen.append(n)
            node.append(["pin", q(n), ["uuid", q(sh.uid())]])
    node.append(["instances", ["project", q(sh.prj.name),
                               ["path", q(path), ["reference", q(p["ref"])], ["unit", str(p["unit"])]]]])
    return node


def title_block(prj, title, date, rev, comments):
    tb = ["title_block", ["title", q(title)], ["date", q(date)], ["rev", q(rev)], ["company", q(prj.name)]]
    for i, c in enumerate(comments, 1):
        tb.append(["comment", str(i), q(c)])
    return tb


def items(sh, path):
    out = []
    for (x, y) in sh.junctions:
        out.append(["junction", ["at", fmt(x), fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(sh.uid())]])
    for (x, y) in sh.ncs:
        out.append(["no_connect", ["at", fmt(x), fmt(y)], ["uuid", q(sh.uid())]])
    for w in sh.wires:
        out.append(["wire", ["pts", ["xy", fmt(w[0]), fmt(w[1])], ["xy", fmt(w[2]), fmt(w[3])]],
                    ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(sh.uid())]])
    for (name, x, y, ang) in sh.labels:
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
        out.append(["label", q(name), ["at", fmt(x), fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                    ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()], ["uuid", q(sh.uid())]])
    for (name, x, y, ang, shape) in sh.glabels:
        just = "left" if ang in (0, 90) else "right"
        out.append(["global_label", q(name), ["shape", shape], ["at", fmt(x), fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                    ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]], ["uuid", q(sh.uid())],
                    ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"), ["at", fmt(x), fmt(y), "0"], ["hide", "yes"],
                     ["show_name", "no"], ["do_not_autoplace", "no"], ["effects", ["font", ["size", "1.27", "1.27"]]]]])
    for (s, x, y, size, bold) in sh.texts:
        font = ["font", ["size", fmt(size), fmt(size)]]
        if bold:
            font += [["thickness", fmt(size * 0.2)], ["bold", "yes"]]
        out.append(["text", q(s), ["exclude_from_sim", "no"], ["at", fmt(x), fmt(y), "0"],
                    ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(sh.uid())]])
    for key in sh.order:
        out.append(sym_instance(sh, sh.parts[key], path))
    return out


def write_sheet(sh, tb, paper="A3"):
    finish(sh)
    path = "/%s/%s" % (sh.prj.root_uuid, sh.block_uuid)
    out = ["kicad_sch", ["version", "20260306"], ["generator", q("eeschema")], ["generator_version", q("10.0")],
           ["uuid", q(sh.uuid)], ["paper", q(paper)], tb]
    libsyms = ["lib_symbols"]
    for lid in sh.lib_ids:
        s = copy.deepcopy(flat_symbol(lid))
        s[1] = q(lid)
        libsyms.append(s)
    out.append(libsyms)
    out += items(sh, path)
    out.append(["sheet_instances", ["path", q("/"), ["page", q("1")]]])
    out.append(["embedded_fonts", "no"])
    open(os.path.join(PRJ, sh.file), "w", encoding="utf-8").write(dump(out) + "\n")
    return sh


def sheet_block(sh, x, y, w, h, name):
    u = sh.block_uuid
    return ["sheet", ["at", fmt(x), fmt(y)], ["size", fmt(w), fmt(h)], ["exclude_from_sim", "no"], ["in_bom", "yes"],
            ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
            ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0"]], ["uuid", q(u)],
            ["property", q("Sheetname"), q(name), ["at", fmt(x), fmt(y - 0.7116), "0"], ["show_name", "no"],
             ["do_not_autoplace", "no"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
            ["property", q("Sheetfile"), q(sh.file), ["at", fmt(x), fmt(y + h + 0.5846), "0"], ["show_name", "no"],
             ["do_not_autoplace", "no"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]],
            ["instances", ["project", q(sh.prj.name), ["path", q("/" + sh.prj.root_uuid), ["page", q(str(sh.page))]]]]]


def write_root(prj, file, tb, blocks, root_sheet, paper="A3"):
    """blocks: [(sheet, x, y, w, h, name)]; root_sheet: a Sheet holding the root's own texts/parts."""
    finish(root_sheet)
    out = ["kicad_sch", ["version", "20260306"], ["generator", q("eeschema")], ["generator_version", q("10.0")],
           ["uuid", q(prj.root_uuid)], ["paper", q(paper)], tb]
    libsyms = ["lib_symbols"]
    for lid in root_sheet.lib_ids:
        s = copy.deepcopy(flat_symbol(lid))
        s[1] = q(lid)
        libsyms.append(s)
    out.append(libsyms)
    out += items(root_sheet, "/" + prj.root_uuid)
    for (sh, x, y, w, h, name) in blocks:
        out.append(sheet_block(sh, x, y, w, h, name))
    out.append(["sheet_instances", ["path", q("/"), ["page", q("1")]]])
    out.append(["embedded_fonts", "no"])
    open(os.path.join(PRJ, file), "w", encoding="utf-8").write(dump(out) + "\n")


def report(sh):
    parts = [k for k in sh.order if not k.startswith("#")]
    print("%-22s %3d parts %4d wires %3d glabels %3d junctions  crossings %d  dangling %d" % (
        sh.file, len(parts), len(sh.wires), len(sh.glabels), len(sh.junctions), len(sh.crossings), len(sh.dangling)))
    for c in sh.crossings:
        print("    crossing at", c)
    for d in sh.dangling:
        print("    DANGLING wire end at", d)
