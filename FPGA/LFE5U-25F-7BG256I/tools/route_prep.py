"""Write route/LFE5U-25F-7BG256I.dsn for Freerouting (run fanout_pcb.py first; route_finish.py imports the result).

Freerouting does not treat the inner planes as connecting anything, so the plane nets (GND, +3V3, +1V1) are taken
out of its job: no planes, no plane nets, and their fixed fan-out copper becomes a netless obstacle.  The few plane
pads the fan-out could not give a via (regulator side of +1V1, HDMI shield pins, a CH347 supply pin) are handed
over as small "<net>__<n>" nets, each tied to the nearest fan-out via of its net (route_finish.py renames them back).

Widths: 0.127 mm on F.Cu and 0.1 mm on B.Cu (the BGA escape ends there sit 0.2 mm apart), 0.1 mm clearance
(JLC multilayer: 0.09/0.09).  Router vias 0.6/0.3 where they fit, else 0.45/0.2.  +5V and the +1V1 regulator link
0.4 mm, USB 0.2 mm.  +2V5 (VCCAUX, a few mA) routes like a signal: its BGA escapes are 0.1 mm.
"""
import json, os, re, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, ".."))
PCB = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pcb")
PRO = os.path.join(PRJ, "LFE5U-25F-7BG256I.kicad_pro")
OUT = os.path.join(PRJ, "route")
DSN = os.path.join(OUT, "LFE5U-25F-7BG256I.dsn")
FM, TM = pcbnew.FromMM, pcbnew.ToMM
PLANE_NETS = ("GND", "+3V3", "+1V1")
GROUP_CLASS = {"+1V1": "Power"}                 # the others are single pins: default widths

# ---------------------------------------------------------------- project rules (read by LoadBoard)
pro = json.load(open(PRO, encoding="utf-8"))
r = pro["board"]["design_settings"]["rules"]
r.update({"min_clearance": 0.1, "min_track_width": 0.09, "min_via_diameter": 0.45, "min_via_annular_width": 0.1,
          "min_through_hole_diameter": 0.2, "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25,
          "min_copper_edge_clearance": 0.3})
ns = pro["net_settings"]
for c in ns["classes"]:
    if c["name"] in ("Default", "TMDS"):
        c.update({"track_width": 0.127, "clearance": 0.1, "via_diameter": 0.6, "via_drill": 0.3})
    elif c["name"] == "Power":
        c.update({"track_width": 0.4, "clearance": 0.1, "via_diameter": 0.7, "via_drill": 0.3})
    elif c["name"] == "USB":
        c.update({"track_width": 0.2, "clearance": 0.15, "via_diameter": 0.6, "via_drill": 0.3})
ns["netclass_patterns"] = [p for p in ns["netclass_patterns"] if p["pattern"] != "+2V5"]
json.dump(pro, open(PRO, "w", encoding="utf-8"), indent=2)

B = pcbnew.LoadBoard(PCB)
B.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)             # GND
B.SetLayerType(pcbnew.In4_Cu, pcbnew.LT_POWER)             # +3V3 with the +1V1 island
B.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_SIGNAL)
B.SetLayerType(pcbnew.In3_Cu, pcbnew.LT_SIGNAL)
tracks = list(B.GetTracks())
assert any(t.IsLocked() for t in tracks), "expects the locked fan-out"
# Unlocked tracks go to Freerouting as ordinary wires it may rip up; that is how a leftover is rerouted with a
# region of its neighbours.

# ---------------------------------------------------------------- plane pads without their own connection
ends = {n: [] for n in PLANE_NETS}
vias = {n: [] for n in PLANE_NETS}
for t in tracks:
    n = t.GetNetname()
    if n in ends:
        if t.Type() == pcbnew.PCB_VIA_T:
            vias[n].append(t.GetPosition())
            ends[n].append(t.GetPosition())
        else:
            ends[n] += [t.GetStart(), t.GetEnd()]
left = []
for f in B.GetFootprints():
    for p in f.Pads():
        n = p.GetNetname()
        if n not in ends or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue                                   # through-hole pads reach the planes on their own
        if not any(p.HitTest(e) for e in ends[n]):
            left.append(p)

groups = []                                            # (name, net, [pads], anchor via position)
for n in PLANE_NETS:
    pads = [p for p in left if p.GetNetname() == n]
    while pads:
        seed = pads.pop(0)
        g = [seed] + [p for p in pads if (p.GetPosition() - seed.GetPosition()).EuclideanNorm() < FM(8.0)]
        pads = [p for p in pads if p not in g]
        cx = sum(p.GetPosition().x for p in g) // len(g)
        cy = sum(p.GetPosition().y for p in g) // len(g)
        c = pcbnew.VECTOR2I(cx, cy)
        anchor = min(vias[n], key=lambda v: (v - c).EuclideanNorm())
        groups.append(("%s__%d" % (n, len(groups) + 1), n, g, anchor))
for name, n, g, a in groups:
    print("group %-8s %-24s anchor via %.2f %.2f" % (name, " ".join("%s-%s" % (p.GetParentFootprint().GetReference(),
          p.GetNumber()) for p in g), TM(a.x) - 160, TM(a.y) - 30))

pcbnew.SaveBoard(PCB, B)                               # keeps the inner layers as power planes
os.makedirs(OUT, exist_ok=True)
assert pcbnew.ExportSpecctraDSN(B, DSN)

# ---------------------------------------------------------------- DSN surgery
txt = open(DSN, encoding="utf-8").read()


def drop_block(text, head):
    """Remove every balanced (...) block that starts with `head`."""
    while True:
        i = text.find(head)
        if i < 0:
            return text
        depth, j = 0, i
        while True:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        k = text.rfind("\n", 0, i)
        text = text[:k] + text[j + 1:]


for n in PLANE_NETS:
    txt = drop_block(txt, "(plane %s " % n)
    txt = drop_block(txt, "(net %s\n" % n)
new_nets = "".join("    (net %s\n      (pins %s)\n    )\n" % (name, " ".join(
    "%s-%s" % (p.GetParentFootprint().GetReference(), p.GetNumber()) for p in g)) for name, n, g, a in groups)
i = txt.index("    (class ")
txt = txt[:i] + new_nets + txt[i:]

# classes: plane nets out, groups in, our widths and vias
extra = {}
for name, n, g, a in groups:
    extra.setdefault(GROUP_CLASS.get(n, "kicad_default"), []).append(name)
V = "Via[0-%d]_%%s_um" % (B.GetCopperLayerCount() - 1)        # KiCad's padstack names carry the layer span
V450, V600, V700 = ('"%s"' % (V % s) for s in ("450:200", "600:300", "700:300"))
RULES = {"kicad_default": (127, 100, 100, V600 + " " + V450),
         "TMDS": (127, 100, 100, V600 + " " + V450),
         "Power": (400, 100, 400, V700 + " " + V600),
         "USB": (200, 150, 200, V600)}


def fix_class(m):
    name, body = m.group(1), m.group(2)
    nets = [x for x in re.findall(r'"[^"]*"|\S+', body) if x not in PLANE_NETS] + extra.get(name, [])
    w, cl, wb, v = RULES[name]
    return ("(class %s %s\n      (circuit\n        (use_via %s)\n      )\n      (rule\n        (width %d)\n"
            "        (clearance %d)\n      )\n      (layer_rule B.Cu\n        (rule (width %d))\n      )\n    )"
            % (name, " ".join(nets), v, w, cl, wb))


txt, k = re.subn(r"\(class (\S+) (.*?)\n\s*\(circuit.*?\n    \)", fix_class, txt, flags=re.S)
assert k == 4, k
# the router's via list must offer the 0.45/0.2 BGA via too
if V450 not in txt.split("(via ", 1)[1].split(")", 1)[0]:
    txt = txt.replace("(via ", "(via %s " % V450, 1)
for v in (V450, V600, V700):                               # every via a class asks for must exist
    assert "(padstack %s" % v in txt, v

# fixed copper of the plane nets: a netless obstacle, except the anchor vias of the groups
anchors = {(round(TM(a.x) * 1000), round(-TM(a.y) * 1000)): name for name, n, g, a in groups}


def fix_wire(m):
    line, net = m.group(0), m.group(1)
    if line.lstrip().startswith("(via"):
        xy = re.findall(r'"\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\(net', line)
        if xy and (round(float(xy[0][0])), round(float(xy[0][1]))) in anchors:
            return line.replace("(net %s)" % net, "(net %s)" % anchors[(round(float(xy[0][0])), round(float(xy[0][1])))])
    return line.replace("(net %s)" % net, "")


txt = re.sub(r"^.*\(net (GND|\+3V3|\+1V1)\).*$", fix_wire, txt, flags=re.M)
assert not re.search(r"\(net (GND|\+3V3|\+1V1)\)", txt)
for name in anchors.values():
    assert "(net %s)" % name in txt, "anchor via not found for " + name
open(DSN, "w", encoding="utf-8").write(txt)
print("DSN", DSN, "nets:", txt.count("    (net "), "fixed:", txt.count("(type fix)"))
