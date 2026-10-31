"""One-off: swap the label-based POWER section of design_part.py for the hand-routed one in power_part.py,
add the ICU field mode (reference + value above the IC) and group checks for directly wired nets."""
import os
H = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- design_part.py
p = os.path.join(H, "design_part.py")
s = open(p, encoding="utf-8").read()
a = s.index("    # ============================================================ POWER\n")
b = s.index("    # ============================================================ ANALOG INPUTS\n")
new = open(os.path.join(H, "power_part.py"), encoding="utf-8").read()
s = s[:a] + new + s[b:]
assert "GROUPS = []" not in s
s = s.replace("INTENT = {}      # (reference, pin) -> intended net, dumped for check_nets.py\n",
              "INTENT = {}      # (reference, pin) -> intended net, dumped for check_nets.py\nGROUPS = []      # (net name or None, [(reference, pin), ...]) pins that are wired together directly\n", 1)
old = '    json.dump({"%s|%s" % k: v for k, v in INTENT.items()}, open(os.path.join(PRJ, "tools", "intent.json"), "w"), indent=0)'
assert old in s
s = s.replace(old, '''    dump_i = {"%s|%s" % k: v for k, v in INTENT.items()}
    dump_i["_groups"] = [[n, [list(x) for x in pins]] for n, pins in GROUPS]
    json.dump(dump_i, open(os.path.join(PRJ, "tools", "intent.json"), "w"), indent=0)''')
open(p, "w", encoding="utf-8").write(s)

# ---------------------------------------------------------------- engine: ICU mode
g = open(os.path.join(H, "gen_sch.py"), encoding="utf-8").read()
if '"ICU"' not in g:
    old = '    if mode == "R":\n        return ((x + 2.54, y - 1.27, "left"), (x + 2.54, y + 1.27, "left"))'
    assert g.count(old) == 1
    g = g.replace(old, '    if mode == "ICU":                                 # reference and value above the IC\n        return ((x, min(ys) - 2.54, None), (x, min(ys) - 5.08, None))\n' + old)
    open(os.path.join(H, "gen_sch.py"), "w", encoding="utf-8").write(g)

# ---------------------------------------------------------------- check_nets.py: group checks
c = open(os.path.join(H, "check_nets.py"), encoding="utf-8").read()
if "_groups" not in c:
    c = c.replace('intent = {tuple(k.split("|")): ALIAS.get(v, v) for k, v in json.load(open(os.path.join(HERE, "intent.json"))).items()}',
                  'raw = json.load(open(os.path.join(HERE, "intent.json")))\ngroups = raw.pop("_groups", [])\nintent = {tuple(k.split("|")): ALIAS.get(v, v) for k, v in raw.items()}')
    c = c.replace('print("checked %d intended pins, %d problems" % (len(intent), bad))', '''# directly wired groups: all pins in one net, named as expected, and no two groups merged
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
print("checked %d intended pins and %d wired groups, %d problems" % (len(intent), len(groups), bad))''')
    open(os.path.join(H, "check_nets.py"), "w", encoding="utf-8").write(c)
print("applied")
