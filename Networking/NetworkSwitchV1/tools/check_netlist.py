"""Export the schematic netlist with kicad-cli and compare its connectivity with design.NETS.

Nets are compared as pin groups (names may differ where the sheet leaves a net unlabelled).  Two-pin
non-polar parts (R, C, L, FB, F) may be drawn either way round: their pins are matched as an unordered pair.
Also reports parts on the sheet that are missing from design.NETS and vice versa.
"""
import os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from design import NETS
SCH = os.path.join(HERE, "..", "NetworkSwitchV1.kicad_sch")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
POLAR = {"C108"}


def netlist():
    out = os.path.join(tempfile.gettempdir(), "nsw1_net.xml")
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", out, SCH], check=True,
                   capture_output=True)
    x = open(out, encoding="utf-8").read()
    nets = {}
    for m in re.finditer(r'<net code="\d+" name="([^"]*)"[^>]*>(.*?)</net>', x, re.S):
        nets[m.group(1).lstrip("/")] = {f"{n.group(1)}.{n.group(2)}" for n in
                                        re.finditer(r'<node ref="([^"]+)" pin="([^"]+)"', m.group(2))}
    comps = set(re.findall(r'<comp ref="([^"]+)"', x))
    return nets, comps


def unordered(ref, pins):
    return (re.match(r"(R|C|L|FB|F)\d", ref) and ref not in POLAR and set(pins) == {"1", "2"})


def main():
    got, comps = netlist()
    where = {pin: n for n, pins in got.items() for pin in pins}
    # design net -> actual net, learned from parts whose pins are not interchangeable
    fixed, loose = {}, {}
    for ref, pins in NETS.items():
        (loose if unordered(ref, pins) else fixed)[ref] = dict(pins)
    mapping = {}
    for ref, pins in fixed.items():
        for pin, net in pins.items():
            a = where.get(f"{ref}.{pin}")
            if a and net not in mapping:
                mapping[net] = a
    # orient two-pin parts by propagation from the learned mapping
    oriented = {}
    for _ in range(20):
        changed = False
        for ref, pins in loose.items():
            if ref in oriented:
                continue
            a1, a2 = where.get(ref + ".1"), where.get(ref + ".2")
            n1, n2 = pins["1"], pins["2"]
            swap = None
            if mapping.get(n1) == a1 or mapping.get(n2) == a2:
                swap = False
            elif mapping.get(n1) == a2 or mapping.get(n2) == a1:
                swap = True
            if swap is None:
                continue
            use = {"1": n2, "2": n1} if swap else pins
            oriented[ref] = use
            for pin, net in use.items():
                if net not in mapping and where.get(f"{ref}.{pin}"):
                    mapping[net] = where[f"{ref}.{pin}"]
            changed = True
        if not changed:
            break
    for ref, pins in loose.items():
        oriented.setdefault(ref, pins)
    want = {}
    for ref, pins in list(fixed.items()) + list(oriented.items()):
        for pin, net in pins.items():
            want.setdefault(net, set()).add(f"{ref}.{pin}")
    bad = 0
    for net, pins in sorted(want.items()):
        actual = {where.get(p) for p in pins}
        if len(actual) != 1 or None in actual:
            bad += 1
            print(f"{net}: split over {sorted(str(a) for a in actual)}  {sorted(pins)}")
            continue
        a = actual.pop()
        extra = {p for p in got[a] - pins if p.split(".")[0] in NETS}
        if extra:
            bad += 1
            print(f"{net} (= {a}) also has {sorted(extra)}")
    for n, pins in got.items():
        if len(pins) == 1 and not n.startswith("unconnected"):
            print("single-pin net:", n, pins)
    real = {c for c in comps if not c.startswith("#")}
    missing = sorted(set(NETS) - real)
    extra = sorted(real - set(NETS))
    if missing:
        print("in design.py but not on the sheet:", missing)
    if extra:
        print("on the sheet but not in design.py:", extra)
    print("nets checked:", len(want), " mismatches:", bad, " parts:", len(real))
    return bad + len(missing) + len(extra)


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
