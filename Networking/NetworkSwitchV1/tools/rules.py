"""Net-class clearances/widths from the project file (NETINFO.GetNetClass() is not usable from KiCad 10 python)."""
import json, os
import pcbnew

PRO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "NetworkSwitchV1.kicad_pro")
_classes = {c["name"]: c for c in json.load(open(PRO, encoding="utf-8"))["net_settings"]["classes"]}


class Rules:
    def __init__(self, B):
        self.nets = B.GetNetsByName()
        self.cache = {}

    def cls(self, net):
        if net not in self.cache:
            try:
                name = str(self.nets[net].GetNetClassName())
            except Exception:
                name = "Default"
            self.cache[net] = _classes.get(name, _classes["Default"])
        return self.cache[net]

    def clearance(self, net):
        return max(0.15, self.cls(net)["clearance"]) if net else 0.15

    def width(self, net):
        return self.cls(net)["track_width"]

    def gap(self, a, b):
        return max(self.clearance(a), self.clearance(b))
