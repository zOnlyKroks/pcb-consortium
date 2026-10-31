import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np
from ngrun import run
amp = sys.argv[1]
net = open(os.path.join(HERE, "..", "sim", "dv1.cir")).read()
net = re.sub(r"(?im)^\.end\s*$", "", net); net = re.sub(r"(?im)^\.tran.*$", ".tran 20n 8m uic", net)
net = re.sub(r"SIN\( 0 [\d.]+ ", "SIN( 0 %s " % amp, net); net = re.sub(r"(?im)^\.ic.*$", "", net); net = re.sub(r"(?im)^\.options.*$", "", net)
net += ".options method=gear\n.ic v(/vref_raw)=2.5 v(/vref)=2.5 v(/inac)=2.5 v(/inv)=2.5 v(/tri)=2.5 v(/e_a)=2.5 v(/e_b)=2.5 v(/ecmp_a)=2.5 v(/ecmp_b)=2.5 v(/out_a)=12 v(/out_b)=12 v(/sw_a)=12 v(/sw_b)=12 v(/vb_a)=23.4 v(/vb_b)=23.4 v(/fault)=0\n"
net += os.environ.get("EXTRA", "").replace(";", chr(10)) + chr(10)
vec, log = run(net, ["time", "v(/out_diff)", "v(/fault)", "v(/sense_a)", "v(/sense_b)", "v(/out_a)", "v(/out_b)"])
t = np.array(vec["time"]); d = np.array(vec["v(/out_diff)"]); fl = np.array(vec["v(/fault)"])
sa = np.array(vec["v(/sense_a)"]); sb = np.array(vec["v(/sense_b)"]); s = np.maximum(sa, sb)
pre = (t > 1e-3) & (t < 6.2e-3)
print("normal running 1-6.2 ms: out peak %.1f V, FAULT max %.2f V, raw shunt peak %.1f A" % (np.abs(d[pre]).max(), fl[pre].max(), s[pre].max() / 0.025))
n = 2; m = (t > 3.0e-3) & (t < 5.0e-3); tt = np.arange(3e-3, 5e-3, 100e-9); y = np.interp(tt, t, d)
F = np.fft.rfft(y - y.mean()) / len(y) * 2; a1 = abs(F[2]); thd = np.sqrt(sum(abs(F[2 * h]) ** 2 for h in range(2, 10))) / a1
print("3-5 ms (2 cycles): fundamental %.2f V  gain %.1f  THD %.3f %%" % (a1, a1 / float(amp), thd * 100))
trip = np.where((fl > 2.5) & (t > 6.2e-3))[0]
if len(trip):
    k = trip[0]; print("short at 6.25 ms -> FAULT latched at %.1f us after the short starts" % ((t[k] - 6.25e-3) * 1e6))
    post = t > t[k] + 30e-6
    print("after trip: out_diff max |%.3f| V, FAULT min %.2f V, shunt max %.2f A" % (np.abs(d[post]).max(), fl[post].min(), s[post].max() / 0.025))
    w = (t > 6.25e-3) & (t < t[k] + 1e-6); print("peak shunt current during the short: %.1f A" % (s[w].max() / 0.025))
else:
    print("no trip after the short (!)")
