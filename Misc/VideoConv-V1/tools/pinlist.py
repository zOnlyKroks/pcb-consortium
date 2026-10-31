import importlib.util, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("g", r"C:\Users\finnr\Desktop\pcb-consortium\AMP\D-V1\tools\gen_sch.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
from sexp import find_all, find, unq
for lid in sys.argv[1:]:
    s = g.flat_symbol(lid)
    pins = []
    for sub in find_all(s, "symbol"):
        for pin in find_all(sub, "pin"):
            pins.append((unq(find(pin, "number")[1]), unq(find(pin, "name")[1]), pin[1]))
    def key(p):
        try: return (0, int(p[0]))
        except: return (1, p[0])
    print("==", lid, len(pins), "pins; footprint:", next((unq(p[2]) for p in find_all(s, "property") if unq(p[1]) == "Footprint"), ""))
    print("  " + "  ".join("%s:%s" % (n, nm) for n, nm, t in sorted(pins, key=key)))
