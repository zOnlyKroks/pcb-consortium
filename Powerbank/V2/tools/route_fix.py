"""Close the connections Freerouting left open without breaking clearance (run after route_finish.py).

Loop: KiCad DRC -> delete the copper this script added that DRC flags (items not in the Freerouting result,
route/routed2.kicad_pcb) -> route the open connections with route_leftovers' grid router -> repeat.  A net whose
new copper keeps failing DRC is routed again with its flagged spot ripped; after a few tries it is reported.
"""
import json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pcbnew
import route_leftovers as RL

PCB, CLI = RL.PCB, RL.CLI
BASE = os.path.join(os.path.dirname(PCB), "route", "routed2.kicad_pcb")
item = re.compile(r"\n\t\((segment|via|arc)\n.*?\n\t\)(?=\n)", re.S)


def uuids(path):
    return {re.search(r'\(uuid "([^"]*)"\)', m.group(0)).group(1) for m in item.finditer(open(path, encoding="utf-8").read())}


def drc():
    out = os.path.join(tempfile.gettempdir(), "route_fix_drc.json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", out, PCB], capture_output=True)
    return json.load(open(out, encoding="utf-8"))


def net_of(desc):
    m = re.search(r"\[([^\]]*)\]", desc)
    return m.group(1) if m else None


base = uuids(BASE)
for rnd in range(8):
    d = drc()
    bad = set()
    for v in d["violations"]:
        if v["type"] in ("clearance", "shorting_items", "hole_clearance", "track_dangling", "via_dangling"):
            for i in v["items"]:
                if i["uuid"] not in base:
                    bad.add(i["uuid"])
    opens = []
    for u in d["unconnected_items"]:
        n = net_of(u["items"][0]["description"])
        if n and n not in opens:
            opens.append(n)
    ncl = sum(v["type"] in ("clearance", "shorting_items", "hole_clearance") for v in d["violations"])
    print("round %d: %d clearance, %d open %s, removing %d added items" % (rnd, ncl, len(d["unconnected_items"]),
                                                                             opens, len(bad)), flush=True)
    if bad:
        txt = open(PCB, encoding="utf-8").read()
        txt = item.sub(lambda m: "" if re.search(r'\(uuid "([^"]*)"\)', m.group(0)).group(1) in bad else m.group(0), txt)
        open(PCB, "w", encoding="utf-8").write(txt)
        d = drc()
        opens = []
        for u in d["unconnected_items"]:
            n = net_of(u["items"][0]["description"])
            if n and n not in opens:
                opens.append(n)
    if not opens and not bad:
        break
    B = pcbnew.LoadBoard(PCB)
    hist = np.zeros((len(RL.LAYERS), RL.NX, RL.NY), np.float32)
    queue, tries = list(opens), 0
    while queue and tries < 60:
        net = queue.pop(0)
        tries += 1
        r = RL.route(B, net, RL.arm_mask(B), hist, RL.RIP_COST * (1.0 + tries / 6.0))
        if r is None:
            continue
        if r == "fail":
            print("  %-22s no path" % net, flush=True)
            continue
        path, vias = r
        hit, ripped = RL.rip(B, net, path, vias)
        hit = [h for h in hit if h not in base] if False else hit
        B = RL.strip(B, set(hit))
        n_t = RL.commit(B, net, path, vias)
        print("  %-22s %2d tracks %d vias%s" % (net, n_t, len(vias), ("  ripped " + " ".join(sorted(ripped))) if ripped else ""),
              flush=True)
        for n in sorted(ripped):
            if n not in queue:
                queue.append(n)
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    pcbnew.SaveBoard(PCB, B)
d = drc()
print("final: clearance %d, unconnected %d" % (sum(v["type"] in ("clearance", "shorting_items", "hole_clearance")
                                                  for v in d["violations"]), len(d["unconnected_items"])))
