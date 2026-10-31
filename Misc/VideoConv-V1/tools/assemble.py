"""gen_sch.py = layout engine (above the first marker) + hier_part.py + design_part.py"""
import os
H = os.path.dirname(os.path.abspath(__file__))
g = open(os.path.join(H, "gen_sch.py"), encoding="utf-8").read()
for marker in ("# ================================================================ hierarchy", "# ================================================================ the design"):
    if marker in g:
        g = g[:g.index(marker)]
        break
hp = open(os.path.join(H, "hier_part.py"), encoding="utf-8").read()
d = open(os.path.join(H, "design_part.py"), encoding="utf-8").read()
open(os.path.join(H, "gen_sch.py"), "w", encoding="utf-8").write(g + hp + d)
print("assembled")
