import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np
from ngrun import run
net = open(os.path.join(HERE, "..", "sim", "dv1.cir")).read()
net = re.sub(r"(?im)^(SSHORT|VSHORT|\.model SWSHORT).*$", "", net); net = re.sub(r"(?im)^\.end\s*$", "", net)
net = re.sub(r"(?im)^\.tran.*$", ".tran 20n 4m uic", net); net = re.sub(r"SIN\( 0 [\d.]+ ", "SIN( 0 0.7 ", net)
g = {"A": ("Net-_Q1-G_", "Net-_Q2-G_", "/SW_A"), "B": ("Net-_Q3-G_", "Net-_Q4-G_", "/SW_B")}
names = ["time"] + ["v(%s)" % n.lower() for x in g.values() for n in x]
vec, log = run(net, names)
t = np.array(vec["time"]); m = t > 1e-3
for X, (hg, lg, sw) in g.items():
    vh = np.array(vec["v(%s)" % hg.lower()]) - np.array(vec["v(%s)" % sw.lower()]); vl = np.array(vec["v(%s)" % lg.lower()])
    both = (vh > 2.0) & (vl > 2.0) & m
    print("leg %s: samples with both gates > 2 V: %d, worst min(Vgs_h, Vgs_l) = %.2f V" % (X, both.sum(), np.minimum(vh, vl)[m].max()))
