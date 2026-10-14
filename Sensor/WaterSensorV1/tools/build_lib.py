"""Tidy the project symbol library (lib/WaterSensorV1.kicad_sym).

* keeps the easyeda2kicad ESP32-C6-WROOM-1-N4 symbol (pin types fixed, ground-pad pins stacked on pin 28)
* drops the generated TP4054 / RT9080 / PH symbols: the stock LTC4054ES5-4.2 and AP2112K-3.3 symbols have
  the same SOT-23-5 pinout and a cleaner body; the PH connectors use Connector_Generic
* adds SW_Tact_4P: Switch:SW_Push with hidden pins 2 / 4 stacked on 1 / 3 (TS-1187A pads 1-2 and 3-4 are
  internally connected)
* adds the VBAT power symbol (copy of power:VBUS)
"""
import copy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import parse, dump, find, find_all, q, unq

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "lib", "WaterSensorV1.kicad_sym")
STOCK = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"


def stock(lib, name):
    tree = parse(open(os.path.join(STOCK, lib + ".kicad_sym"), encoding="utf-8").read())[0]
    for s in find_all(tree, "symbol"):
        if unq(s[1]) == name:
            return copy.deepcopy(s)
    raise KeyError(name)


def rename(sym, old, new):
    sym[1] = q(new)
    for sub in find_all(sym, "symbol"):
        sub[1] = sub[1].replace(old + "_", new + "_", 1)


def set_prop(sym, key, val):
    for p in find_all(sym, "property"):
        if unq(p[1]) == key:
            p[2] = q(val)
            return
    raise KeyError(key)


def main():
    tree = parse(open(LIB, encoding="utf-8").read())[0]
    keep = [c for c in tree if not (isinstance(c, list) and c[0] == "symbol")]
    syms = {unq(s[1]): s for s in find_all(tree, "symbol")}
    out = keep + [syms["ESP32-C6-WROOM-1-N4"]]

    sw = stock("Switch", "SW_Push")
    rename(sw, "SW_Push", "SW_Tact_4P")
    set_prop(sw, "Description", "Tactile switch, 4 pads: 1-2 and 3-4 internally connected (TS-1187A)")
    for sub in find_all(sw, "symbol"):
        for pin in find_all(sub, "pin"):
            num = find(pin, "number")
            if unq(num[1]) == "2":            # right pin becomes 3, add hidden stacked twins 2 / 4
                num[1] = q("3")
        pins = find_all(sub, "pin")
        for pin in list(pins):
            twin = copy.deepcopy(pin)
            n = unq(find(twin, "number")[1])
            find(twin, "number")[1] = q({"1": "2", "3": "4"}[n])
            twin.insert(5, ["hide", "yes"])
            sub.append(twin)
    out.append(sw)

    vb = stock("power", "VBUS")
    rename(vb, "VBUS", "VBAT")
    set_prop(vb, "Value", "VBAT")
    set_prop(vb, "Description", "Power symbol creates a global label with name \"VBAT\" (battery rail)")
    out.append(vb)

    open(LIB, "w", encoding="utf-8").write(dump(out) + "\n")
    print("library:", [unq(s[1]) for s in find_all(out, "symbol")])


if __name__ == "__main__":
    main()
