"""Check the exported KiCad netlist against the design intent (pin groups that must share a net, pins that must be
unconnected).  Usage: check_netlist.py  (exports the netlist with kicad-cli first)."""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, find, find_all, unq

PRJ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

# ---------------------------------------------------------------- design intent
SAME = {
    "+3V3": ["J1.A9", "J1.A10", "J1.B8", "U2.4", "C3.1", "C4.1", "C5.1", "C6.1", "R1.1", "FB1.1",
             "U1.46", "U1.29", "U1.43", "U1.15", "U1.19", "U1.33", "R5.1", "R6.1", "R7.1", "R8.1", "R15.2", "R16.2",
             "R17.2"] + ["C%d.1" % n for n in range(11, 18)],
    "+0V95": ["L1.2", "C8.1", "R2.1", "C9.1", "C10.1", "U1.8", "U1.28", "U1.47", "U1.37", "U1.11", "U1.16", "U1.22"]
             + ["C%d.1" % n for n in range(23, 31)],
    "GND": ["J1.A4", "J1.B4", "U2.2", "U1.40", "U1.49", "R3.2", "R4.1", "R9.2", "R10.2", "Y1.2", "Y1.4", "C37.2", "J2.13",
            "C31.2", "C32.2", "C33.2", "C34.2", "C35.2", "C36.2"],
    "AVDD33_XTAL": ["U1.34", "FB1.2", "C21.1", "C22.1"],
    "REFCLK+": ["J1.A13", "U1.44"], "REFCLK-": ["J1.A14", "U1.45"],
    "RX+": ["J1.B14", "U1.41"], "RX-": ["J1.B15", "U1.42"],
    "TX+": ["U1.38", "C1.2"], "TX-": ["U1.39", "C2.2"], "PER+": ["J1.A16", "C1.1"], "PER-": ["J1.A17", "C2.1"],
    "PERST": ["J1.A11", "U1.36"], "PRSNT": ["J1.A1", "J1.B17"],
    "SW": ["U2.3", "L1.1"], "EN": ["U2.1", "R1.2", "C7.1"], "FB": ["U2.5", "R2.2", "R3.1", "C8.2"],
    "CLKREQ": ["U1.48", "R4.2"], "WAKE": ["U1.2", "R5.2"], "GPI": ["U1.3", "R6.2"], "SWR": ["U1.6", "R7.2"],
    "ISO": ["U1.1", "R8.2", "R9.1"], "RSET": ["U1.12", "R10.1"],
    "XI": ["U1.10", "Y1.1", "C31.1"], "XO": ["U1.9", "Y1.3", "C32.1"],
    "MDI0+": ["U1.13", "TR1.2"], "MDI0-": ["U1.14", "TR1.3"], "MDI1+": ["U1.17", "TR1.5"], "MDI1-": ["U1.18", "TR1.6"],
    "MDI2+": ["U1.20", "TR1.8"], "MDI2-": ["U1.21", "TR1.9"], "MDI3+": ["U1.23", "TR1.11"], "MDI3-": ["U1.24", "TR1.12"],
    "J1/2a": ["TR1.23", "J2.1"], "J1/2b": ["TR1.22", "J2.2"], "J3/6a": ["TR1.20", "J2.3"], "J3/6b": ["TR1.19", "J2.6"],
    "J4/5a": ["TR1.17", "J2.4"], "J4/5b": ["TR1.16", "J2.5"], "J7/8a": ["TR1.14", "J2.7"], "J7/8b": ["TR1.13", "J2.8"],
    "TCT1": ["TR1.1", "C33.1"], "TCT2": ["TR1.4", "C34.1"], "TCT3": ["TR1.7", "C35.1"], "TCT4": ["TR1.10", "C36.1"],
    "MCT1": ["TR1.24", "R11.1"], "MCT2": ["TR1.21", "R12.1"], "MCT3": ["TR1.18", "R13.1"], "MCT4": ["TR1.15", "R14.1"],
    "BOB": ["R11.2", "R12.2", "R13.2", "R14.2", "C37.1"],
    "LED1": ["U1.27", "J2.12", "R17.1"], "LED2": ["U1.25", "J2.10"], "Y+": ["J2.9", "R15.1"], "G+": ["J2.11", "R16.1"],
}
OPEN = ["U1.4", "U1.5", "U1.7", "U1.26", "U1.30", "U1.31", "U1.32", "U1.35", "J1.A2", "J1.B10", "J1.B11", "J1.B12",
        "J1.B5", "J1.B6", "J1.B9", "J1.A5", "J1.A6", "J1.A7", "J1.A8"]


def main():
    out = os.path.join(tempfile.gettempdir(), "2.5GPcieV1.net")
    subprocess.run([CLI, "sch", "export", "netlist", "-o", out, os.path.join(PRJ, "2.5GPcieV1.kicad_sch")],
                   check=True, capture_output=True)
    tree = parse(open(out, encoding="utf-8").read())[0]
    netof, members = {}, {}
    for net in find_all(find(tree, "nets"), "net"):
        name = unq(find(net, "name")[1])
        for nd in find_all(net, "node"):
            key = "%s.%s" % (unq(find(nd, "ref")[1]), unq(find(nd, "pin")[1]))
            netof[key] = name
            members.setdefault(name, set()).add(key)
    bad = 0
    used = set()
    for label, pins in SAME.items():
        nets = {netof.get(p, "<missing %s>" % p) for p in pins}
        if len(nets) != 1:
            bad += 1
            print("MISMATCH %-12s %s" % (label, {p: netof.get(p) for p in pins}))
            continue
        n = nets.pop()
        used.add(n)
        extra = members[n] - set(pins)
        if extra and label not in ("GND", "+3V3", "+0V95"):
            bad += 1
            print("EXTRA    %-12s %s has also %s" % (label, n, sorted(extra)))
    for p in OPEN:
        n = netof.get(p)
        if n and len(members[n]) > 1:
            bad += 1
            print("NOT OPEN %s on %s with %s" % (p, n, sorted(members[n])))
    parts = {k.split(".")[0] for k in netof}
    print("nets %d, parts with pins %d, checked groups %d, problems %d" % (len(members), len(parts), len(SAME), bad))
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
