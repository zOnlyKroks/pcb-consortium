# ================================================================ hierarchy
import collections

INST_PATH = "/" + ROOT_UUID          # instance path of the sheet being written (root only until write_hier changes it)
COLUMN = {"Power": 0, "Inputs": 0, "TVP7002": 1, "TVP5150": 1, "FPGA": 2, "HDMI": 3, "VGA": 3}
SHEET_TITLES = {"Power": "Power: USB-C 5 V, 3.3 V / 1.9 V bucks, 1.8 V / 1.2 V LDOs, filtered analog rails",
                "Inputs": "Analog inputs: SCART / component / composite, ESD, SCART sensing, audio",
                "TVP7002": "TVP7002 RGB / YPbPr / SCART RGB digitiser",
                "TVP5150": "TVP5150 composite / S-Video decoder",
                "FPGA": "iCE40HX4K FPGA, clock, config flash, UI",
                "HDMI": "TFP410 DVI transmitter + TPD12S016 + HDMI connector",
                "VGA": "VGA output: 3 x 6-bit R-2R DAC"}
PAPERS = (("A4", 297, 210), ("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841))


class Multi:
    """Forwards every call to the current sub-sheet, so the design code does not care which sheet it is drawing on."""

    def __init__(self):
        self.sheets = collections.OrderedDict()
        self.cur = None

    def S(self, name):
        if name not in self.sheets:
            self.sheets[name] = Sheet()
        self.cur = name

    def __getattr__(self, n):
        return getattr(self.sheets[self.cur], n)


def shift(sh, dx, dy):
    for p in sh.parts.values():
        p["x"], p["y"] = r2(p["x"] + dx), r2(p["y"] + dy)
    sh.wires = [(r2(a + dx), r2(b + dy), r2(c + dx), r2(d + dy)) for a, b, c, d in sh.wires]
    sh.labels = [(n, r2(x + dx), r2(y + dy), ang) for n, x, y, ang in sh.labels]
    sh.ncs = [(r2(x + dx), r2(y + dy)) for x, y in sh.ncs]
    sh.texts = [(s, r2(x + dx), r2(y + dy), size, bold) for s, x, y, size, bold in sh.texts]


def extent(sh):
    xs, ys = [], []
    for key, p in sh.parts.items():
        for n in p["pins"]:
            x, y = sh.pin(key, n)
            xs.append(x); ys.append(y)
        xs.append(p["x"]); ys.append(p["y"])
    for a, b, c, d in sh.wires:
        xs += [a, c]; ys += [b, d]
    for n, x, y, ang in sh.labels:
        w = 1.4 * len(n)
        xs += [x - w if ang == 180 else x, x + w if ang != 180 else x]; ys.append(y)
    for s, x, y, size, bold in sh.texts:
        xs += [x, x + 0.75 * size * len(s)]; ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def pick_paper(w, h):
    for name, pw, ph in PAPERS:
        if w + 60 <= pw and h + 80 <= ph:
            return name, pw, ph
    return PAPERS[-1]


def child_tb(tb, name):
    out = copy.deepcopy(tb)
    for c in out:
        if isinstance(c, list) and c[0] == "title":
            c[1] = q("VideoConv-V1 / %s: %s" % (name, SHEET_TITLES[name]))
    return out


def write_child(sh, name, path, tb, cross, sheet_uuid):
    global INST_PATH
    INST_PATH = "/%s/%s" % (ROOT_UUID, sheet_uuid)
    x0, y0, x1, y1 = extent(sh)
    paper, pw, ph = pick_paper(x1 - x0, y1 - y0)
    dx = round((30.48 - x0) / 2.54) * 2.54
    dy = round((40.64 - y0) / 2.54) * 2.54
    shift(sh, dx, dy)
    finish(sh)
    out = ["kicad_sch", ["version", "20260101"], ["generator", q("eeschema")], ["generator_version", q("10.0")],
           ["uuid", q(uid())], ["paper", q(paper)], child_tb(tb, name)]
    libsyms = ["lib_symbols"]
    for lid in sh.lib_ids:
        s = copy.deepcopy(flat_symbol(lid))
        s[1] = q(lid)
        libsyms.append(s)
    out.append(libsyms)
    for (x, y) in sh.junctions:
        out.append(["junction", ["at", fmt(x), fmt(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", q(uid())]])
    for (x, y) in sh.ncs:
        out.append(["no_connect", ["at", fmt(x), fmt(y)], ["uuid", q(uid())]])
    for w in sh.wires:
        out.append(["wire", ["pts", ["xy", fmt(w[0]), fmt(w[1])], ["xy", fmt(w[2]), fmt(w[3])]],
                    ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(uid())]])
    for (net, x, y, ang) in sh.labels:
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
        eff = ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()]
        if net in cross:
            out.append(["hierarchical_label", q(net), ["shape", "bidirectional"], ["at", fmt(x), fmt(y), str(ang)], eff,
                        ["uuid", q(uid())]])
        else:
            out.append(["label", q(net), ["at", fmt(x), fmt(y), str(ang)], ["fields_autoplaced", "yes"], eff, ["uuid", q(uid())]])
    for (s, x, y, size, bold) in sh.texts:
        font = ["font", ["size", fmt(size), fmt(size)]]
        if bold:
            font += [["thickness", fmt(size * 0.2)], ["bold", "yes"]]
        out.append(["text", q(s), ["exclude_from_sim", "no"], ["at", fmt(x), fmt(y), "0"],
                    ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(uid())]])
    for key in sh.order:
        out.append(sym_instance(sh, sh.parts[key]))
    out.append(["embedded_fonts", "no"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(dump(out) + "\n")
    INST_PATH = "/" + ROOT_UUID
    return paper


def write_hier(multi, tb):
    names = list(multi.sheets)
    users = collections.defaultdict(set)
    for name, sh in multi.sheets.items():
        for (net, x, y, ang) in sh.labels:
            users[net].add(name)
    cross = {n for n, s in users.items() if len(s) > 1}
    sheet_uuid = {n: str(uuid.uuid4()) for n in names}
    sheets_dir = os.path.join(PRJ, "sheets")
    for old in glob.glob(os.path.join(sheets_dir, "*.kicad_sch")):
        os.remove(old)
    info = {}
    for name in names:
        info[name] = write_child(multi.sheets[name], name, os.path.join(sheets_dir, name + ".kicad_sch"), tb, cross, sheet_uuid[name])
    # ---------------------------------------------------------------- root sheet: one sheet symbol per block
    pins = {}
    for name in names:
        mine = sorted(n for n in cross if name in users[n])
        side = {}
        for n in mine:
            others = [COLUMN[o] for o in users[n] if o != name]
            side[n] = "L" if (sum(others) / len(others)) < COLUMN[name] else "R"
        pins[name] = ([n for n in mine if side[n] == "L"], [n for n in mine if side[n] == "R"])
    W, GAP = 63.5, 25.4
    y_cursor = collections.defaultdict(lambda: 40.64)
    root = ["kicad_sch", ["version", "20260101"], ["generator", q("eeschema")], ["generator_version", q("10.0")],
            ["uuid", q(ROOT_UUID)], ["paper", q("A1")], tb, ["lib_symbols"]]
    wires, labels, texts = [], [], []
    for page, name in enumerate(names, start=2):
        col = COLUMN[name]
        x = 63.5 + col * 228.6
        y = round(y_cursor[col] / 2.54) * 2.54
        left, right = pins[name]
        H = max(len(left), len(right), 3) * 2.54 + 12.7
        node = ["sheet", ["at", fmt(x), fmt(y)], ["size", fmt(W), fmt(H)], ["exclude_from_sim", "no"], ["in_bom", "yes"],
                ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
                ["stroke", ["width", "0.1524"], ["type", "solid"]], ["fill", ["color", "0", "0", "0", "0.0"]], ["uuid", q(sheet_uuid[name])],
                ["property", q("Sheetname"), q(name), ["at", fmt(x), fmt(y - 0.7), "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "bottom"]]],
                ["property", q("Sheetfile"), q("sheets/%s.kicad_sch" % name), ["at", fmt(x), fmt(y + H + 0.6), "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left", "top"]]]]
        for side, nets in (("L", left), ("R", right)):
            for i, net in enumerate(nets):
                py = y + 6.35 + 2.54 * i
                px = x if side == "L" else x + W
                ang = 180 if side == "L" else 0
                node.append(["pin", q(net), "bidirectional", ["at", fmt(px), fmt(py), str(ang)], ["uuid", q(uid())],
                             ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left" if side == "L" else "right"]]])
                ex = px - 10.16 if side == "L" else px + 10.16
                wires.append((px, py, ex, py))
                labels.append((net, ex, py, 180 if side == "L" else 0))
        node.append(["instances", ["project", q(PROJECT), ["path", q("/" + ROOT_UUID), ["page", q(str(page))]]]])
        root.append(node)
        texts.append((SHEET_TITLES[name], x, y - 4.5, 1.4, False))
        y_cursor[col] = y + H + GAP + 12.7
    for (a, b, c, d) in wires:
        root.append(["wire", ["pts", ["xy", fmt(a), fmt(b)], ["xy", fmt(c), fmt(d)]], ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(uid())]])
    for (net, x, y, ang) in labels:
        just = "right bottom" if ang == 180 else "left bottom"
        root.append(["label", q(net), ["at", fmt(x), fmt(y), str(ang)], ["fields_autoplaced", "yes"],
                     ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just.split()], ["uuid", q(uid())]])
    notes = [("VideoConv-V1: analog video (SCART / component / composite / S-Video) to HDMI + VGA", 63.5, 15.24, 3.0, True),
             ("Signals that cross sheets are hierarchical labels on the sheets and net labels here; supply rails are global power symbols.", 63.5, 25.4, 1.4, False)]
    for (s, x, y, size, bold) in texts + notes:
        font = ["font", ["size", fmt(size), fmt(size)]]
        if bold:
            font += [["thickness", fmt(size * 0.2)], ["bold", "yes"]]
        root.append(["text", q(s), ["exclude_from_sim", "no"], ["at", fmt(x), fmt(y), "0"],
                     ["effects", font, ["justify", "left", "bottom"]], ["uuid", q(uid())]])
    root.append(["sheet_instances", ["path", q("/"), ["page", q("1")]]])
    root.append(["embedded_fonts", "no"])
    open(SCH, "w", encoding="utf-8").write(dump(root) + "\n")
    return info, cross


