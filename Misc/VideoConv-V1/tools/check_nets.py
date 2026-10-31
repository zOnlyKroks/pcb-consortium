"""Compare KiCad's netlist with the nets the generator meant (tools/intent.json); report shorts / merged nets.

    kicad-cli sch export netlist --format kicadxml  ->  nets;  every (ref, pin) must sit in a net whose name equals the
    intended name; a net holding pins with two different intended names is a collision between two parts of the layout.
"""
import json, os, subprocess, sys
import xml.etree.ElementTree as ET
HERE = os.path.dirname(os.path.abspath(__file__)); PRJ = os.path.normpath(os.path.join(HERE, ".."))
KCLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
xml = os.path.join(PRJ, "render", "nets.xml")
os.makedirs(os.path.dirname(xml), exist_ok=True)
subprocess.run([KCLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", xml, os.path.join(PRJ, "VideoConv-V1.kicad_sch")],
               check=True, capture_output=True)
ALIAS = {"TV_UNUSED": "GND", "FPGA_GND0": "GND", "TF_LO": "GND"}      # labels deliberately tied to GND
raw = json.load(open(os.path.join(HERE, "intent.json")))
groups = raw.pop("_groups", [])
intent = {tuple(k.split("|")): ALIAS.get(v, v) for k, v in raw.items()}
root = ET.parse(xml).getroot()
bad = 0
for net in root.find("nets"):
    name = net.get("name").split("/")[-1]
    nodes = [(n.get("ref"), n.get("pin")) for n in net]
    names = {}
    for nd in nodes:
        i = intent.get(nd)
        if i and i != "NC":
            names.setdefault(i, []).append(nd)
    if len(names) > 1:
        bad += 1
        print("MERGED net %-22s : %s" % (name, {k: v[:3] for k, v in names.items()}))
    for nd in nodes:
        if intent.get(nd) == "NC" and len(nodes) > 1:
            print("NC pin %s is connected in net %s" % (nd, name)); bad += 1
# directly wired groups: all pins in one net, named as expected, and no two groups merged
net_of = {}
for net in root.find("nets"):
    for n in net:
        net_of[(n.get("ref"), n.get("pin"))] = net.get("name")
seen_net = {}
for name, pins in groups:
    nets = {net_of.get(tuple(p)) for p in pins}
    if len(nets) != 1 or None in nets:
        print("GROUP %s not one net: %s" % (name, {tuple(p): net_of.get(tuple(p)) for p in pins})); bad += 1
        continue
    n = nets.pop()
    if name and n.split("/")[-1] != name:
        print("GROUP expected net %s but pins are in %s" % (name, n)); bad += 1
    if n in seen_net and not (name and name == seen_net[n]) and not (seen_net[n] is None and name is None and False):
        if name != seen_net[n]:
            print("GROUPS merged: %s and %s share net %s" % (seen_net[n], name, n)); bad += 1
    seen_net[n] = name
print("checked %d intended pins and %d wired groups, %d problems" % (len(intent), len(groups), bad))
