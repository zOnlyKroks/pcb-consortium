"""BOM with JLCPCB library type, stock and price: python bom.py [boards]   (default 5 boards)

Exports the grouped BOM with kicad-cli, looks every LCSC code up in the JLCPCB parts API and writes ../bom.csv.
Cost = JLC part price at the order quantity (qty per board x boards) + $3 per unique Extended part
(Basic and Preferred-extended parts have no loading fee).  DNP lines are listed but not costed.
"""
import csv, io, json, os, subprocess, sys, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, "..")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
API = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"


def export():
    out = os.path.join(tempfile.gettempdir(), "nsw1_bom.csv")
    subprocess.run([CLI, "sch", "export", "bom", "--fields", "Reference,Value,Footprint,LCSC Part #,${QUANTITY},${DNP}",
                    "--labels", "Refs,Value,Footprint,LCSC,Qty,DNP", "--group-by", "LCSC Part #,Value,${DNP}",
                    "--ref-range-delimiter", "", "-o", out, os.path.join(PRJ, "NetworkSwitchV1.kicad_sch")],
                   check=True, capture_output=True)
    return list(csv.DictReader(io.open(out, encoding="utf-8")))


def jlc(code):
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 5}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    lst = json.load(urllib.request.urlopen(req, timeout=30))["data"]["componentPageInfo"]["list"] or []
    hit = next((c for c in lst if c.get("componentCode") == code), None)
    if not hit:
        return None
    kind = {"base": "Basic", "expand": "Extended"}.get(hit["componentLibraryType"], hit["componentLibraryType"])
    if kind == "Extended" and hit.get("preferredComponentFlag"):
        kind = "Preferred"
    return dict(kind=kind, stock=hit.get("stockCount") or 0, mpn=hit.get("componentModelEn"),
                ladder=[(p["startNumber"], p["productPrice"]) for p in hit.get("componentPrices") or []])


def price(ladder, n):
    p = None
    for start, pr in ladder:
        if n >= start:
            p = pr
    return p if p is not None else (ladder[0][1] if ladder else 0.0)


def main():
    boards = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    rows, total, fees, ext = [], 0.0, 0.0, []
    for r in export():
        refs, qty, code, dnp = r["Refs"], int(r["Qty"]), r["LCSC"].strip(), r["DNP"].strip()
        info = jlc(code) if code else None
        line = dict(Refs=refs, Qty=qty, Value=r["Value"], LCSC=code, MPN=info["mpn"] if info else "",
                    JLC=info["kind"] if info else "-", Stock=info["stock"] if info else "", Unit="", Line="",
                    DNP="DNP" if dnp else "")
        if info and not dnp:
            unit = price(info["ladder"], qty * boards)
            line["Unit"] = "%.4f" % unit
            line["Line"] = "%.2f" % (unit * qty)
            total += unit * qty
            if info["kind"] == "Extended":
                ext.append(code)
            if info["stock"] < qty * boards:
                line["Stock"] = "%s  LOW" % info["stock"]
        rows.append(line)
    fees = 3.0 * len(set(ext))
    with open(os.path.join(PRJ, "bom.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    kinds = {}
    for r in rows:
        if not r["DNP"]:
            kinds[r["JLC"]] = kinds.get(r["JLC"], 0) + 1
    print("lines:", len(rows), " by JLC type:", kinds)
    print("parts per board: $%.2f   extended loading fees: %d x $3 = $%.2f per order (%d boards)"
          % (total, len(set(ext)), fees, boards))
    print("per board incl. fees: $%.2f" % (total + fees / boards))
    for r in rows:
        if "LOW" in str(r["Stock"]) or r["JLC"] == "-":
            print("  check:", r["Refs"][:40], r["Value"], r["LCSC"], r["JLC"], r["Stock"], r["DNP"])


if __name__ == "__main__":
    main()
