"""Swap parts for JLCPCB Basic parts in the same footprint, editing only Value / LCSC fields in place.

Touches WaterSensorV1.kicad_sch, WaterSensorV1.kicad_pcb and jlcpcb/project.db; no geometry, nets or tracks.
python swap_parts.py [--dry]
"""
import os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, "..")
# reference -> (new value or None, new LCSC)
SWAP = {
    **{r: (None, "C14663") for r in ("C5", "C6", "C8", "C9")},      # 100nF X7R 50V  CC0603KRX7R9BB104 (Basic)
    **{r: (None, "C25804") for r in ("R11", "R12", "R13")},         # 10k 1%         0603WAF1002T5E    (Basic)
    "C7": (None, "C15849"),                                         # 1uF X5R 25V    CL10A105KB8NNNC   (Basic)
    "Q3": ("AO3400A", "C20917"),                                    # N-FET, same G-S-D SOT-23 pinout as BSS138 (Basic)
    "D1": ("RED", "C2286"),                                         # KT-0603R (Basic)
    "D2": ("RED", "C2286"),                                         # no Basic green 0603 exists; KT-0603R (Basic)
}


def blocks(text, head):
    """(start, end) of every top-level `(head ...` block, found by paren matching."""
    for m in re.finditer(r"\n\t\(" + head + r"\b", text):
        i = m.start() + 2
        depth = 0
        for j in range(i, len(text)):
            c = text[j]
            if c == '"':
                k = j + 1
                while text[k] != '"':
                    k += 2 if text[k] == "\\" else 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield i, j + 1
                    break


def set_prop(block, key, val):
    pat = re.compile(r'(\(property "' + re.escape(key) + r'" )"[^"]*"')
    if not pat.search(block):
        raise KeyError(key)
    return pat.sub(lambda m: m.group(1) + '"' + val + '"', block, count=1)


def edit(path, head, dry):
    text = open(path, encoding="utf-8", newline="").read()   # keep KiCad's CRLF
    out, last, done = [], 0, []
    for a, b in blocks(text, head):
        blk = text[a:b]
        m = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if not m or m.group(1) not in SWAP:
            continue
        ref = m.group(1)
        val, lcsc = SWAP[ref]
        if val:
            blk = set_prop(blk, "Value", val)
        blk = set_prop(blk, "LCSC Part #", lcsc)
        out += [text[last:a], blk]
        last = b
        done.append(ref)
    out.append(text[last:])
    new = "".join(out)
    missing = sorted(set(SWAP) - set(done))
    print(f"{os.path.basename(path)}: {len(done)} edited, {len(new) - len(text):+d} chars", "MISSING " + str(missing) if missing else "")
    if not dry:
        open(path, "w", encoding="utf-8", newline="").write(new)


def main():
    dry = "--dry" in sys.argv
    edit(os.path.join(PRJ, "WaterSensorV1.kicad_sch"), "symbol", dry)
    edit(os.path.join(PRJ, "WaterSensorV1.kicad_pcb"), "footprint", dry)
    db = sqlite3.connect(os.path.join(PRJ, "jlcpcb", "project.db"))
    for ref, (val, lcsc) in SWAP.items():
        if val:
            db.execute("update part_info set value=?, lcsc=? where reference=?", (val, lcsc, ref))
        else:
            db.execute("update part_info set lcsc=? where reference=?", (lcsc, ref))
    if not dry:
        db.commit()
    print("project.db updated" if not dry else "dry run")


if __name__ == "__main__":
    main()
