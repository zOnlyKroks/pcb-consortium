"""Run boost.cir with KiCad's bundled libngspice and print/plot key numbers."""
import ctypes, os, sys

LIB = "/Applications/KiCad/KiCad.app/Contents/PlugIns/sim/libngspice.dylib"
here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)

CB = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
@CB
def out(msg, _id, _u):
    s = msg.decode(errors="replace")
    if "stderr" in s or "Error" in s or "error" in s or "Timestep" in s:
        print(s)
    return 0

ng = ctypes.CDLL(LIB)
ng.ngSpice_Init(out, None, None, None, None, None, None)
cmds = ["set ngbehavior=psa", "source boost.cir", "run",
        "set wr_vecnames", "set wr_singlescale",
        "wrdata out.csv v(hv) v(vin) i(vsrc) v(fb) v(comp) v(dr) i(l101)"]
for c in cmds:
    ng.ngSpice_Command(c.encode())
