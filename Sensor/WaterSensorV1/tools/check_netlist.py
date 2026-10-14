"""Export the schematic netlist with kicad-cli and compare its connectivity with design.NETS.

Nets are compared as pin groups (names may differ where the sheet leaves a net unlabelled).
"""
import os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from design import NETS
SCH = os.path.join(HERE, "..", "WaterSensorV1.kicad_sch")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def netlist():
    out = os.path.join(tempfile.gettempdir(), "ws1_net.xml")
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", out, SCH], check=True,
                   capture_output=True)
    x = open(out, encoding="utf-8").read()
    nets = {}
    for m in re.finditer(r'<net code="\d+" name="([^"]*)"[^>]*>(.*?)</net>', x, re.S):
        nets[m.group(1).lstrip("/")] = {f"{n.group(1)}.{n.group(2)}" for n in
                                        re.finditer(r'<node ref="([^"]+)" pin="([^"]+)"', m.group(2))}
    return nets


def main():
    got = netlist()
    where = {pin: n for n, pins in got.items() for pin in pins}
    want = {}
    for ref, pins in NETS.items():
        for pin, net in pins.items():
            want.setdefault(net, set()).add(f"{ref}.{pin}")
    bad = 0
    for net, pins in sorted(want.items()):
        actual = {where.get(p) for p in pins}
        if len(actual) != 1 or None in actual:
            bad += 1
            print(f"{net}: split over {sorted(str(a) for a in actual)}")
            continue
        a = actual.pop()
        extra = {p for p in got[a] - pins if p.split(".")[0] in NETS}
        if extra:
            bad += 1
            print(f"{net} (= {a}) also has {sorted(extra)}")
    for n, pins in got.items():
        if len(pins) == 1 and not n.startswith("unconnected"):
            print("single-pin net:", n, pins)
    print("nets checked:", len(want), " mismatches:", bad)
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
