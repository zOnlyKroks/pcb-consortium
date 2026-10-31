# ================================================================ the design
G = 2.54
RAILS = {"GND", "+5V", "+3V3", "+1V9", "+1V9A", "+3V3A", "+1V8", "+1V8A", "+1V2", "+1V2A", "+3V3P", "+3V3T"}

R_FP, C_FP = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
C0805, C1206 = "Capacitor_SMD:C_0805_2012Metric", "Capacitor_SMD:C_1206_3216Metric"
RPACK_FP = "Resistor_SMD:R_Array_Convex_4x0603"
STUB = {0: (-1, 0, 180), 180: (1, 0, 0), 90: (0, 1, 270), 270: (0, -1, 90)}   # effective pin angle -> stub dir, label angle

# FPGA pin -> net (also written to gateware/pins.pcf)
FPGA_PINS = {}
INTENT = {}      # (reference, pin) -> intended net, dumped for check_nets.py
GROUPS = []      # (net name or None, [(reference, pin), ...]) pins that are wired together directly


def U(x, y):
    return (round(x * G, 3), round(y * G, 3))


def build():
    sh = Multi()
    sh.S("Power")
    cnt = {}
    T = lambda *a, **k: sh.text(*a, **k)

    def ref(prefix):
        cnt[prefix] = cnt.get(prefix, 0) + 1
        return "%s%d" % (prefix, cnt[prefix])

    def part(prefix, lib, x, y, value, fp="", rot=0, unit=1, key=None, fields=None, extra=None, r=None, **kw):
        r = r or ref(prefix)
        if fields is None:
            fields = "T" if rot in (90, 270) else "R"
        k = key or r
        sh.add(r, lib, *U(x, y), rot=rot, value=value, fp=fp, fields=fields, extra=extra, unit=unit, key=k, **kw)
        return k

    # ------------------------------------------------------------------ pin side / tie helpers
    def effang(k, num):
        p = sh.parts[k]
        if "ang" not in p:
            ang = {}
            for sub in find_all(p["sym"], "symbol"):
                for pin in find_all(sub, "pin"):
                    at = find(pin, "at")
                    ang[unq(find(pin, "number")[1])] = int(round(float(at[3])))
            p["ang"] = ang
        return (p["ang"][str(num)] + p["rot"]) % 360

    seen = set()

    def tie(k, num, net, d=3):
        """Short stub from a pin to a power symbol (rails) or a net label (everything else)."""
        pt = sh.pin(k, num)
        if (k, pt) in seen:
            return
        seen.add((k, pt))
        INTENT[(sh.parts[k]["ref"], str(num))] = net
        a = effang(k, num)
        dx, dy, la = STUB[a]
        end = sh.stub(pt, dx * d * G, dy * d * G)
        if net in RAILS:
            rot = 0 if a in (90, 270) else (90 if a == 0 else 270)
            sh.power(net, end, rot)
        else:
            sh.label(net, end, la)

    def tie_group(k, nums, net, d=3):
        done = set()
        for n in nums:
            pt = sh.pin(k, n)
            if pt in done:
                continue
            done.add(pt)
            tie(k, n, net, d)

    def nc(k, num):
        INTENT[(sh.parts[k]["ref"], str(num))] = "NC"
        sh.nc(sh.pin(k, num))

    def lbl(net, x, y, ang=0):
        sh.label(net, U(x, y), ang)

    # ------------------------------------------------------------------ small passives
    def R_(val, x, y, rot=0, fp=R_FP, extra=None):
        return part("R", "Device:R", x, y, val, fp, rot, extra=extra)

    def C_(val, x, y, rot=0, fp=C_FP, extra=None):
        return part("C", "Device:C", x, y, val, fp, rot, extra=extra)

    def hr(prefix, val, x, y, na, nb, fp=R_FP, lib="Device:R", extra=None):
        """horizontal two-pin part between two labelled nets"""
        k = part(prefix, lib, x, y, val, fp, 90, extra=extra)
        tie(k, 1, na, 2)
        tie(k, 2, nb, 2)
        return k

    def vt(prefix, val, x, y, ntop, nbot, fp=R_FP, lib="Device:R", extra=None):
        """vertical two-pin part: top pin to ntop, bottom pin to nbot (rail or label)"""
        k = part(prefix, lib, x, y, val, fp, 0, extra=extra)
        tie(k, 1, ntop, 2)
        tie(k, 2, nbot, 2)
        return k

    def bypass(x, y, rail, val="100nF", fp=C_FP):
        return vt("C", val, x, y, rail, "GND", fp, "Device:C")

    def led(color, x, y, anode, cathode):
        k = part("LED", "Device:LED", x, y, color, "LED_SMD:LED_0603_1608Metric", 0)
        tie(k, 2, anode, 2)
        tie(k, 1, cathode, 2)
        return k

    def gnd_net(net, x, y):
        lbl(net, x, y, 90)
        sh.wire(U(x, y), U(x, y + 2))
        sh.power("GND", U(x, y + 2))

    def flag(rail, x, y):
        sh.power(rail, U(x, y))
        sh.wire(U(x, y), U(x + 4, y))
        sh.power("FLAG", U(x + 4, y))

    def section(title, x, y, size=2):
        T(title, x * G, y * G, size, True)

    # ============================================================ POWER (hand-routed: every passive sits on its wire)
    sh.S("Power")
    section("Power: USB-C 5 V -> 3.3 V / 1.9 V bucks, 1.8 V / 1.2 V LDOs, filtered analog rails", 4, 4)

    def Wu(*pts):
        sh.wire(*[U(*p) for p in pts])

    def Pu(k, n):
        x, y = sh.pin(k, n)
        return (round(x / G, 3), round(y / G, 3))

    def rail(kind, x, y, rot=0):
        sh.power(kind, U(x, y), rot)

    def grp(name, *pins):
        GROUPS.append((name, [(sh.parts[k]["ref"], str(n)) for k, n in pins]))

    def vcap(val, x, ytop, rail_name, fp=C_FP, extra=None):
        """capacitor hanging down from a wire at (x, ytop) to GND; returns its key"""
        c = part("C", "Device:C", x, ytop + 1.5, val, fp, 0, extra=extra)
        Wu((x, ytop + 3), (x, ytop + 5))
        rail("GND", x, ytop + 5)
        return c

    # ---- USB-C -> PTC -> +5V, TVS and bulk capacitors on the +5V line
    usb = part("J", "Connector:USB_C_Receptacle_USB2.0_16P", 20, 30, "USB-C 5 V in",
               "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", fields="IC", nosim=True)
    vb = Pu(usb, "A4")
    f1 = part("F", "Device:Polyfuse", 29.5, 24, "1.5A PTC", "Fuse:Fuse_1206_3216Metric", rot=90, extra={"MPN": "hold 1.5 A, 6 V"})
    Wu(vb, (28, 24))
    Wu((31, 24), (52, 24))
    rail("+5V", 36, 21)
    Wu((36, 24), (36, 21))
    d1 = part("D", "Device:D_TVS", 36, 25.5, "SMF5.0A", "Diode_SMD:D_SOD-123", rot=90)
    Wu((36, 27), (36, 29))
    rail("GND", 36, 29)
    caps5 = [vcap(v, x, 24, "+5V", C1206 if v == "22uF" else C_FP) for x, v in ((41, "22uF"), (47, "22uF"), (53, "100nF"))]
    Wu((52, 24), (53, 24))
    sh.power("FLAG", U(56, 24))
    Wu((53, 24), (56, 24))
    grp(None, (usb, "A4"), (f1, 1))
    grp("+5V", (f1, 2), (d1, 2), (caps5[0], 1), (caps5[1], 1), (caps5[2], 1))
    # CC pull-downs hang straight off the CC pins
    cc1, cc2 = Pu(usb, "A5"), Pu(usb, "B5")
    r_cc1 = part("R", "Device:R", 32, 27.5, "5.1k", R_FP)
    Wu(cc1, (32, 26)); Wu((32, 29), (32, 31)); rail("GND", 32, 31)
    r_cc2 = part("R", "Device:R", 29, 28.5, "5.1k", R_FP, fields="L")
    Wu(cc2, (29, 27)); Wu((29, 30), (29, 32)); rail("GND", 29, 32)
    grp(None, (usb, "A5"), (r_cc1, 1))
    grp(None, (usb, "B5"), (r_cc2, 1))
    for n in ("A6", "A7", "A8", "B6", "B7", "B8"):
        sh.nc(sh.pin(usb, n))
    gp, shp = Pu(usb, "A1"), Pu(usb, "SH")
    Wu(gp, (20, 41)); rail("GND", 20, 41)
    Wu((20, 41), (24, 41)); sh.power("FLAG", U(24, 41))
    Wu(shp, (17, 41)); rail("GND", 17, 41)

    # ---- AP62300 bucks: every passive on its own pin's wire
    def buck(X, Y, name, vout, r1, l_val):
        u = part("U", "Regulator_Switching:AP62300WU", X, Y, "AP62300", "Package_TO_SOT_SMD:TSOT-23-6", fields="ICU",
                 extra={"MPN": "AP62300WU-7", "Note": name})
        vin, en, sw, bst, fb, gnd = (Pu(u, n) for n in (3, 5, 2, 6, 4, 1))
        # VIN line, +5V at its far end, input cap hanging off it, EN pull-up inline on the EN line
        Wu(vin, (X - 18, Y - 1)); Wu((X - 18, Y - 1), (X - 18, Y - 3)); rail("+5V", X - 18, Y - 3)
        cin = vcap("10uF", X - 15, Y - 1, "+5V", C0805)
        ren = part("R", "Device:R", X - 9.5, Y + 1, "100k", R_FP, rot=90, extra={"Note": "EN pull-up"})
        Wu(en, (X - 8, Y + 1)); Wu((X - 11, Y + 1), (X - 13, Y + 1)); Wu((X - 13, Y + 1), (X - 13, Y - 1))
        # switch node: boot cap from BST, inductor to the output rail
        Wu(sw, (X + 16, Y - 1))
        cb = part("C", "Device:C", X + 7.5, Y, "100nF", C_FP, 90, fields="B")
        Wu(bst, (X + 6, Y)); Wu((X + 9, Y), (X + 9, Y - 1))
        lk = part("L", "Device:L", X + 17.5, Y - 1, l_val, "Inductor_SMD:L_Bourns-SRN6028", 90)
        Wu((X + 19, Y - 1), (X + 36, Y - 1))
        Wu((X + 36, Y - 1), (X + 36, Y - 3)); rail(vout, X + 36, Y - 3)
        couts = [vcap("22uF", X + 23 + 5 * i, Y - 1, vout, C1206) for i in range(2)]
        sh.power("FLAG", U(X + 39, Y - 1)); Wu((X + 36, Y - 1), (X + 39, Y - 1))
        # feedback divider hangs between the output node and ground, tapped into the FB pin
        Wu(fb, (X + 5, Y + 1)); Wu((X + 5, Y + 1), (X + 5, Y + 8)); Wu((X + 5, Y + 8), (X + 33, Y + 8))
        rt = part("R", "Device:R", X + 33, Y + 6.5, r1, R_FP, extra={"Tolerance": "1%"})
        rb = part("R", "Device:R", X + 33, Y + 9.5, "10k", R_FP, extra={"Tolerance": "1%"})
        Wu((X + 33, Y + 5), (X + 33, Y - 1))
        Wu((X + 33, Y + 11), (X + 33, Y + 13)); rail("GND", X + 33, Y + 13)
        Wu(gnd, (X, Y + 5)); rail("GND", X, Y + 5)
        grp("+5V", (u, 3), (cin, 1), (ren, 1))
        grp(None, (u, 5), (ren, 2))
        grp(None, (u, 2), (cb, 2), (lk, 1))
        grp(None, (u, 6), (cb, 1))
        grp(vout, (lk, 2), (couts[0], 1), (couts[1], 1), (rt, 1))
        grp(None, (u, 4), (rt, 2), (rb, 1))
        grp("GND", (u, 1), (rb, 2))
        return u
    buck(24, 62, "3V3", "+3V3", "31.6k", "3.3uH")
    buck(24, 94, "1V9", "+1V9", "13.7k", "2.2uH")

    # ---- AP2112K LDOs
    def ldo(X, Y, lib, vin, vout, name):
        u = part("U", lib, X, Y, name, "Package_TO_SOT_SMD:SOT-23-5", fields="ICU", extra={"MPN": name})
        pv, pen, pvo, pg, pnc = (Pu(u, n) for n in (1, 3, 5, 2, 4))
        Wu(pv, (X - 9, Y - 1)); Wu((X - 9, Y - 1), (X - 9, Y - 3)); rail(vin, X - 9, Y - 3)
        Wu(pen, (X - 5, Y)); Wu((X - 5, Y), (X - 5, Y - 1))
        cin = vcap("1uF", X - 7, Y - 1, vin, C_FP)
        Wu(pvo, (X + 11, Y - 1)); Wu((X + 11, Y - 1), (X + 11, Y - 3)); rail(vout, X + 11, Y - 3)
        cout = vcap("2.2uF", X + 7, Y - 1, vout, C_FP)
        Wu(pg, (X, Y + 5)); rail("GND", X, Y + 5)
        sh.nc(sh.pin(u, 4))
        return u
    ldo(100, 62, "Regulator_Linear:AP2112K-1.8", "+3V3", "+1V8", "AP2112K-1.8")
    ldo(100, 94, "Regulator_Linear:AP2112K-1.2", "+1V8", "+1V2", "AP2112K-1.2")

    # ---- ferrite-filtered analog rails: rail -> bead -> filtered rail, caps hanging off the filtered node
    for i, (src, dst) in enumerate((("+3V3", "+3V3A"), ("+1V9", "+1V9A"), ("+1V8", "+1V8A"), ("+1V2", "+1V2A"),
                                    ("+3V3", "+3V3P"), ("+3V3", "+3V3T"))):
        X, Y = 134, 60 + 11 * i
        rail(src, X, Y - 2); Wu((X, Y - 2), (X, Y)); Wu((X, Y), (X + 2, Y))
        fbk = part("FB", "Device:FerriteBead", X + 3.5, Y, "600R@100MHz", "Inductor_SMD:L_0805_2012Metric", 90)
        Wu((X + 5, Y), (X + 20, Y))
        rail(dst, X + 20, Y - 2); Wu((X + 20, Y), (X + 20, Y - 2))
        c1 = vcap("10uF" if i != 3 else "4.7uF", X + 9, Y, dst, C0805)
        c2 = vcap("100nF", X + 14, Y, dst, C_FP)
        sh.power("FLAG", U(X + 23, Y)); Wu((X + 20, Y), (X + 23, Y))
        grp(dst, (fbk, 2), (c1, 1), (c2, 1))

    # ============================================================ ANALOG INPUTS
    sh.S("Inputs")
    section("Analog inputs: SCART (RGB / CVBS / S-Video), component YPbPr, composite", 4, 96)
    sc = part("J", "Connector:SCART-F", 20, 116, "SCART", "VideoConv-V1:SCART_Tyco_1483465-1", fields="IC", nosim=True,
              extra={"Note": "21-pin SCART socket, footprint to be chosen (not in KiCad stock)"})
    sc_nets = {7: "SC_B", 11: "SC_G", 15: "SC_R", 20: "SC_CVBS", 2: "SC_AR", 6: "SC_AL", 16: "SC_BLK", 8: "SC_FS"}
    for pin in (1, 3, 10, 12, 19):
        nc(sc, pin)
    tie_group(sc, (4, 5, 9, 13, 14, 17, 18, 21), "GND")
    for pin, net in sc_nets.items():
        tie(sc, pin, net, 3)
    rcas = {}
    for i, net in enumerate(("RCA_CV", "CP_Y", "CP_PB", "CP_PR")):
        j = part("J", "Connector:Conn_Coaxial", 14, 150 + 9 * i, {"RCA_CV": "CVBS", "CP_Y": "Y", "CP_PB": "Pb", "CP_PR": "Pr"}[net],
                 "VideoConv-V1:RCA_XDJK-0271-1650", fields="IC", nosim=True, extra={"Note": "RCA jack, LCSC C7527522"})
        tie(j, 1, net, 3)
        tie(j, 2, "GND", 3)

    # 75 ohm terminations + 0.1 uF coupling into the TVP7002
    xr = 44
    rows = (("SC_R", "TV_RIN1"), ("SC_G", "TV_GIN1"), ("SC_B", "TV_BIN1"),
            ("CP_PR", "TV_RIN2"), ("CP_Y", "TV_GIN2"), ("CP_PB", "TV_BIN2"))
    for i, (na, nb) in enumerate(rows):
        y = 100 + 9 * i
        vt("R", "75", xr, y, na, "GND", extra={"Tolerance": "1%"})
        hr("C", "100nF", xr + 12, y - 3.5, na, nb, C_FP, "Device:C")
    hr("C", "1nF", xr + 12, 100 + 9 * 6 - 3.5, "SC_CVBS", "TV_SOG1", C_FP, "Device:C", extra={"Note": "sync-on-green coupling, 1 nF per TVP7002 datasheet"})
    hr("C", "1nF", xr + 12, 100 + 9 * 7 - 3.5, "CP_Y", "TV_SOG2", C_FP, "Device:C", extra={"Note": "sync-on-green coupling, 1 nF per TVP7002 datasheet"})
    sh.S("TVP7002")
    # unused TVP7002 inputs: 10 nF (analog) / 1 nF (SOG) to ground
    for i, net in enumerate(("TV_RIN3", "TV_GIN3", "TV_GIN4", "TV_BIN3")):
        vt("C", "10nF", xr + 30 + 5 * i, 104, net, "GND", C_FP, "Device:C")
    vt("C", "1nF", xr + 50, 104, "TV_SOG3", "GND", C_FP, "Device:C")

    sh.S("Inputs")
    # TVP5150 composite / S-Video front end
    y = 176
    for k, (src, nsel) in enumerate((("RCA_CV", "N_RCA"), ("SC_CVBS", "N_SC"))):
        yy = y + 11 * k
        hr("R", "24.9", xr, yy, src, nsel, extra={"Tolerance": "1%", "Note": "75 ohm termination = 24.9 + 49.9, gives 0.67x for the 0.75 Vpp input range"})
        vt("R", "49.9", xr + 10, yy + 5, nsel, "GND", extra={"Tolerance": "1%"})
        vt("C", "820pF", xr + 16, yy + 5, nsel, "GND", C_FP, "Device:C", extra={"Note": "anti-alias, NP0"})
    jp = part("JP", "Jumper:SolderJumper_3_Open", xr + 30, y + 8, "CVBS source", "Jumper:SolderJumper-3_P1.3mm_Open_Pad1.0x1.5mm",
              fields="IC", nosim=True, extra={"Note": "A = RCA composite, B = SCART pin 20 (CVBS or S-Video Y)"})
    tie(jp, 1, "N_RCA", 3)
    tie(jp, 3, "N_SC", 3)
    tie(jp, 2, "CV_SEL", 3)
    hr("C", "100nF", xr + 42, y + 14, "CV_SEL", "T5_AIP1A", C_FP, "Device:C")
    hr("C", "100nF", xr + 42, y + 22, "SC_R", "T5_AIP1B", C_FP, "Device:C", extra={"Note": "S-Video chroma from SCART pin 15"})

    sh.S("TVP7002")
    # TVP7002 support: unused pins to ground, I2CA, PLL filter, reset pull-up
    gnd_net("TV_UNUSED", 134, 160)
    vt("R", "2.2k", 142, 162, "TV_I2CA", "GND")
    vt("R", "10k", 150, 162, "+3V3", "NRST_VID")
    hr("R", "1.5k", 164, 160, "TV_FILT1", "TV_FILT1B")
    hr("C", "100nF", 178, 160, "TV_FILT1B", "TV_PLLF", C_FP, "Device:C")
    hr("C", "4.7nF", 178, 166, "TV_FILT2", "TV_PLLF", C_FP, "Device:C")

    sh.S("Inputs")
    # SCART audio -> 3.5 mm line out
    for i, (na, nb) in enumerate((("SC_AL", "AUD_L"), ("SC_AR", "AUD_R"))):
        hr("C", "4.7uF", xr + 4, 210 + 8 * i, na, nb, C0805, "Device:C", extra={"Note": "film or X7R, DC block"})
        vt("R", "100k", xr + 14, 215 + 8 * i, nb, "GND")
    ja = part("J", "Connector_Audio:AudioJack3", xr + 26, 214, "Line out", "Connector_Audio:Jack_3.5mm_CUI_SJ1-3524N_Horizontal",
              fields="IC", nosim=True, extra={"Note": "SCART audio pass-through (no HDMI audio in v1)"})
    tie(ja, "T", "AUD_L", 3)
    tie(ja, "R", "AUD_R", 3)
    tie(ja, "S", "GND", 3)


    # ============================================================ input protection + SCART sensing
    sh.S("Inputs")
    section("Input protection (USBLC6-4SC6 ESD arrays, bidirectional TVS on audio) + SCART fast-blank / function-switch sensing", 4, 250)
    esd_groups = (("SC_R", "SC_G", "SC_B", "SC_CVBS"), ("CP_Y", "CP_PB", "CP_PR", "RCA_CV"), ("SC_BLK", "SC_FSD", None, None))
    for gi, grp in enumerate(esd_groups):
        e = part("U", "Power_Protection:USBLC6-4SC6", 28, 262 + 18 * gi, "USBLC6-4SC6", "Package_TO_SOT_SMD:SOT-23-6", fields="IC",
                 extra={"MPN": "USBLC6-4SC6", "Note": "clamps to +5V / GND; place next to the connector"})
        for pin, net in zip((1, 3, 4, 6), grp):
            if net:
                tie(e, pin, net, 3)
            else:
                nc(e, pin)
        tie(e, 5, "+5V", 2)
        tie(e, 2, "GND", 2)
    for i, net in enumerate(("SC_AL", "SC_AR")):
        vt("D", "SMF5.0CA", 46 + 8 * i, 268, net, "GND", "Diode_SMD:D_SOD-123", "Device:D_TVS",
           extra={"Note": "bidirectional: line-level audio swings both ways"})
    # pin 16: 75 ohm load, pin 8: 33k/10k divider (input impedance >= 10k per SCART spec)
    vt("R", "75", 60, 268, "SC_BLK", "GND", extra={"Tolerance": "1%", "Note": "fast-blanking input termination"})
    hr("R", "33k", 72, 276, "SC_FS", "SC_FSD")
    vt("R", "10k", 80, 281, "SC_FSD", "GND")
    # comparators: LM339 on 5 V, thresholds from 3.3 V dividers, open-collector outputs pulled up to 3.3 V
    cm = {}
    for unit, (x, y) in {1: (110, 264), 2: (110, 276), 3: (110, 288), 4: (110, 300), 5: (130, 280)}.items():
        cm[unit] = part("U", "Comparator:LM339", x, y, "LM339", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", unit=unit, fields="IC",
                        key="UCM%d" % unit, r=(sh.parts["UCM1"]["ref"] if unit != 1 else None), extra={"MPN": "LM339DR"})
    tie(cm[5], 3, "+5V", 2)
    tie(cm[5], 12, "GND", 2)
    # unit 1: RGB present (pin 16 > 0.7 V)
    tie(cm[1], 5, "SC_BLK", 3)
    tie(cm[1], 4, "SC_VL", 3)
    tie(cm[1], 2, "SC_RGB", 3)
    # unit 2: function switch > 3 V (16:9 or 4:3)
    tie(cm[2], 7, "SC_FSD", 3)
    tie(cm[2], 6, "SC_VL", 3)
    tie(cm[2], 1, "SC_FS1", 3)
    # unit 3: function switch > 8 V (4:3)
    tie(cm[3], 11, "SC_FSD", 3)
    tie(cm[3], 10, "SC_VH", 3)
    tie(cm[3], 13, "SC_FS2", 3)
    # unit 4 unused: input held low, output left open
    tie(cm[4], 9, "GND", 3)
    tie(cm[4], 8, "SC_VL", 3)
    nc(cm[4], 14)
    vt("R", "100k", 60, 292, "+3V3", "SC_VL", extra={"Note": "0.71 V threshold = 3 V on pin 8 after /4.3, or 0.7 V on pin 16"})
    vt("R", "27.4k", 60, 300, "SC_VL", "GND", extra={"Tolerance": "1%"})
    vt("R", "10k", 70, 292, "+3V3", "SC_VH", extra={"Note": "1.87 V threshold = 8 V on pin 8 after /4.3"})
    vt("R", "13k", 70, 300, "SC_VH", "GND", extra={"Tolerance": "1%"})
    for i, net in enumerate(("SC_RGB", "SC_FS1", "SC_FS2")):
        vt("R", "10k", 80 + 6 * i, 292, "+3V3", net)
    bypass(140, 292, "+5V")
    T("SC_RGB = pin 16 above 0.7 V (RGB active).  SC_FS1 = pin 8 above 3 V (widescreen or 4:3 AV).  SC_FS2 = pin 8 above 8 V (4:3).", 4 * G, 318 * G, 1.2)

    # ============================================================ TVP7002
    sh.S("TVP7002")
    section("TVP7002: RGB / YPbPr / SCART RGB digitiser (I2C 0xB8)", 120, 98)
    tv = part("U", "VideoConv-V1:TVP7002PZP", 150, 125, "TVP7002", "Package_QFP:TQFP-100-1EP_14x14mm_P0.5mm_EP5x5mm", fields="IC",
              extra={"MPN": "TVP7002PZP", "Note": "check exposed-pad size against the TI PZP drawing"}, key="UTV7")
    left_nets = {"RIN_1": "TV_RIN1", "RIN_2": "TV_RIN2", "RIN_3": "TV_RIN3", "GIN_1": "TV_GIN1", "GIN_2": "TV_GIN2",
                 "GIN_3": "TV_GIN3", "GIN_4": "TV_GIN4", "BIN_1": "TV_BIN1", "BIN_2": "TV_BIN2", "BIN_3": "TV_BIN3",
                 "SOGIN_1": "TV_SOG1", "SOGIN_2": "TV_SOG2", "SOGIN_3": "TV_SOG3",
                 "HSYNC_A": "TV_UNUSED", "HSYNC_B": "TV_UNUSED", "VSYNC_A": "TV_UNUSED", "VSYNC_B": "TV_UNUSED",
                 "CLAMP": "TV_UNUSED", "COAST": "TV_UNUSED", "TMS": "TV_UNUSED", "PWDN": "TV_UNUSED",
                 "EXT_CLK": "CLK27_TV", "SDA": "I2C_SDA", "SCL": "I2C_SCL", "I2CA": "TV_I2CA", "RESETB": "NRST_VID",
                 "FILT1": "TV_FILT1", "FILT2": "TV_FILT2", "PLL_F": "TV_PLLF"}
    tvpin = {"RIN_1": 11, "RIN_2": 10, "RIN_3": 9, "GIN_1": 2, "GIN_2": 100, "GIN_3": 98, "GIN_4": 96, "BIN_1": 18, "BIN_2": 17,
             "BIN_3": 16, "SOGIN_1": 1, "SOGIN_2": 99, "SOGIN_3": 97, "HSYNC_A": 81, "HSYNC_B": 82, "VSYNC_A": 78,
             "VSYNC_B": 79, "CLAMP": 76, "COAST": 77, "TMS": 72, "PWDN": 70, "EXT_CLK": 80, "SDA": 75, "SCL": 74,
             "I2CA": 73, "RESETB": 71, "FILT1": 87, "FILT2": 88, "PLL_F": 89}
    for nm, net in left_nets.items():
        tie(tv, tvpin[nm], net, 3)
    tie_group(tv, (13, 14, 93, 94), "+3V3A", 2)
    tie_group(tv, (4, 6, 7, 19), "+1V9A", 2)
    tie_group(tv, (84, 85), "+1V9A", 2)
    tie_group(tv, (39, 69), "+1V9", 2)
    tie_group(tv, (26, 41, 53, 66), "+3V3", 2)
    for grp in ((12, 15, 92, 95), (3, 5, 8, 20), (83, 86, 90), (21, 91), (40, 68), (27, 42, 54, 60, 67), (101,)):
        tie_group(tv, grp, "GND", 2)
    # 8 MSBs of each colour through 22 ohm packs, then to the FPGA
    def pack_row(first_pin_ic, ic_key, pins_nums, out_nets, x_off=4):
        """4 consecutive IC output rows -> R_Pack04 -> labels"""
        rk = part("R", "Device:R_Pack04", 0, 0, "22", RPACK_FP, rot=270, fields="IC", extra={"Note": "4x22 ohm array"})
        p1 = sh.pin(rk, 1)
        ic0 = sh.pin(ic_key, pins_nums[0])
        want = (ic0[0] + x_off * G, ic0[1])
        sh.parts[rk]["x"] += want[0] - p1[0]
        sh.parts[rk]["y"] += want[1] - p1[1]
        for i, n in enumerate(pins_nums):
            sh.wire(sh.pin(ic_key, n), sh.pin(rk, i + 1))
            tie(rk, 8 - i, out_nets[i], 3)
        return rk
    cols = {"R": [55, 56, 57, 58, 59, 61, 62, 63, 64, 65], "G": [43, 44, 45, 46, 47, 48, 49, 50, 51, 52],
            "B": [29, 30, 31, 32, 33, 34, 35, 36, 37, 38]}
    for c, nums in cols.items():
        pack_row(0, tv, nums[0:4], ["TV%s%d" % (c, 7 - i) for i in range(4)])
        pack_row(0, tv, nums[4:8], ["TV%s%d" % (c, 3 - i) for i in range(4)])
        nc(tv, nums[8])
        nc(tv, nums[9])
    pack_row(0, tv, [28, 24, 23, 22], ["TVCLK", "TV_HS", "TV_VS", "TV_FID"])
    s = pack_row(0, tv, [25], ["TV_SOG"])
    for i in (2, 3, 4):
        nc(s, i)
        nc(s, 9 - i)
    bypass(134, 94, "+3V3A")
    bypass(139, 94, "+1V9A")
    bypass(144, 94, "+1V9")
    bypass(149, 94, "+3V3")
    bypass(154, 94, "+1V9A", "10uF", C0805)

    # ============================================================ TVP5150
    sh.S("TVP5150")
    section("TVP5150AM1: composite / S-Video decoder, BT.656 out (I2C 0xBA)", 100, 180)
    t5 = part("U", "VideoConv-V1:TVP5150AM1PBS", 150, 215, "TVP5150AM1", "Package_QFP:TQFP-32_7x7mm_P0.8mm", fields="IC",
              extra={"MPN": "TVP5150AM1PBS"}, key="UT51")
    for nm, num, net in (("AIP1A", 1, "T5_AIP1A"), ("AIP1B", 2, "T5_AIP1B"), ("XTAL1", 5, "T5_X1"), ("XTAL2", 6, "T5_X2"),
                         ("SDA", 22, "I2C_SDA"), ("SCL", 21, "I2C_SCL"), ("RESETB", 8, "NRST_VID"), ("PDN", 28, "T5_PDN"),
                         ("REFP", 29, "T5_REFP"), ("REFM", 30, "T5_REFM")):
        tie(t5, num, net, 3)
    for i, num in enumerate((11, 12, 13, 14, 15, 16, 17, 18)):
        tie(t5, num, "CY%d" % (7 - i), 3)
    tie(t5, 9, "CSCLK", 3)
    for num in (25, 24, 23, 26):
        nc(t5, num)
    tie(t5, 27, "T5_INT", 3)
    tie(t5, 32, "+1V8A", 2)
    tie(t5, 4, "+1V8A", 2)
    tie(t5, 20, "+1V8", 2)
    tie(t5, 10, "+3V3", 2)
    for num in (31, 3, 7, 19):
        tie(t5, num, "GND", 2)
    vt("R", "10k", 174, 200, "+3V3", "CY7", extra={"Note": "I2CSEL pull-up: TVP5150 at 0xBA, TVP7002 at 0xB8"})
    vt("R", "10k", 180, 200, "+3V3", "T5_PDN")
    vt("R", "10k", 186, 200, "T5_INT", "GND")
    yx = part("Y", "Device:Crystal_GND24", 112, 215, "14.31818MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", fields="IC",
              extra={"Note": "CL = 18 pF -> 27 pF loads (2*CL - Cstray)"})
    tie(yx, 1, "T5_X1", 3)
    tie(yx, 3, "T5_X2", 3)
    tie_group(yx, (2, 4), "GND", 3)
    vt("C", "27pF", 100, 226, "T5_X1", "GND", C_FP, "Device:C")
    vt("C", "27pF", 106, 226, "T5_X2", "GND", C_FP, "Device:C")
    hr("R", "100k", 114, 204, "T5_X1", "T5_X2")
    hr("C", "1uF", 124, 236, "T5_REFP", "T5_REFM", C_FP, "Device:C")
    vt("C", "1uF", 116, 236, "T5_REFP", "GND", C_FP, "Device:C")
    vt("C", "1uF", 132, 236, "T5_REFM", "GND", C_FP, "Device:C")
    bypass(140, 186, "+1V8A")
    bypass(146, 186, "+1V8")
    bypass(152, 186, "+3V3")

    # ============================================================ clocks
    sh.S("FPGA")
    section("Clock: 27 MHz oscillator -> TVP7002 reference + FPGA", 150, 4)
    osc = part("X", "Oscillator:ASE-xxxMHz", 162, 24, "27MHz", "Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm", fields="IC",
               extra={"MPN": "27 MHz, 3.3 V, +-50 ppm"})
    tie(osc, 1, "+3V3", 3)
    tie(osc, 4, "+3V3", 3)
    tie(osc, 2, "GND", 3)
    tie(osc, 3, "CLK27", 3)
    hr("R", "33", 176, 18, "CLK27", "CLK27_TV")
    hr("R", "33", 176, 26, "CLK27", "CLK27F")
    bypass(162, 36, "+3V3")

    # ============================================================ FPGA
    section("iCE40HX4K-TQ144: line-doubler / deinterlacer / colour-space converter, I2C master", 205, 90)
    unit_pos = {4: (225, 125), 3: (225, 190), 1: (285, 125), 2: (285, 190), 5: (345, 160)}
    fp = "Package_QFP:TQFP-144_20x20mm_P0.5mm"
    keys = {}
    for unit, (x, y) in unit_pos.items():
        r_fp = sh.parts[keys[4]]["ref"] if unit != 4 else None
        keys[unit] = part("U", "FPGA_Lattice:ICE40HX4K-TQ144", x, y, "ICE40HX4K-TQ144", fp, unit=unit,
                          key="UFP%d" % unit, r=r_fp, fields="IC", extra={"MPN": "ICE40HX4K-TQ144"})

    def assign(unit, pin_nums, nets, clock=None):
        k = keys[unit]
        pins = [n for n in pin_nums]
        nets = list(nets)
        for n in pins:
            if clock and n in clock:
                net = clock[n]
            elif nets:
                net = nets.pop(0)
            else:
                nc(k, n)
                continue
            if net is None:
                nc(k, n)
            else:
                tie(k, n, net, 3)
                FPGA_PINS[net] = n
        assert not nets, ("unassigned nets", unit, nets)

    bus = lambda p, n: ["%s%d" % (p, i) for i in range(n - 1, -1, -1)]
    assign(4, [1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34],
           bus("TVR", 8) + bus("TVG", 8) + bus("TVB", 8) + ["TV_HS", "TV_VS", "TV_FID"], clock={20: "TVCLK"})
    assign(3, [37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 52, 55, 56, 60, 61, 62, 63, 64],
           bus("CY", 8) + ["TV_SOG", "I2C_SCL", "I2C_SDA", "NRST_VID", "BTN_MODE", "LED_A", "LED_B"],
           clock={49: "CSCLK", 63: "FPGA_GND0", 64: "FPGA_GND0"})
    assign(1, [110, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 124, 125, 128, 129, 130, 134, 135, 136, 137, 138, 139,
               141, 142, 143, 144], bus("DR", 8) + bus("DG", 8) + bus("DB", 8) + ["DVI_CLK", "DVI_DE", "DVI_HS"])
    assign(2, [73, 74, 75, 76, 78, 79, 80, 81, 82, 83, 84, 85, 87, 88, 90, 91, 93, 94, 95, 96, 97, 98, 99, 101, 102, 104, 105, 106, 107],
           ["DVI_VS"] + bus("VR", 6) + bus("VG", 6) + bus("VB", 6) + ["VGA_HS", "VGA_VS", "HDMI_HPD", "DDC_SCL", "DDC_SDA", "SC_RGB", "SC_FS1", "SC_FS2"],
           clock={93: "CLK27F"})
    for unit, pins in ((1, (123, 131)), (2, (89, 100)), (3, (46, 57)), (4, (6, 30))):
        tie_group(keys[unit], pins, "+3V3", 2)
    k5 = keys[5]
    tie_group(k5, (27, 40, 92, 111), "+1V2", 2)
    tie(k5, 54, "+1V2A", 2)
    tie(k5, 126, "+1V2A", 2)
    tie(k5, 72, "+3V3", 2)
    tie(k5, 108, "+3V3", 2)
    nc(k5, 109)
    for n in (5, 13, 14, 53, 59, 69, 86, 103, 127, 132, 140):
        tie(k5, n, "GND", 2)
    for n in (35, 36, 50, 51, 58, 77, 133):
        nc(k5, n)
    tie(k5, 65, "CDONE", 3)
    tie(k5, 66, "CRESET", 3)
    tie(k5, 67, "SPI_SDO", 3)
    tie(k5, 68, "SPI_SDI", 3)
    tie(k5, 70, "SPI_SCK", 3)
    tie(k5, 71, "SPI_SS", 3)
    gnd_net("FPGA_GND0", 200, 215)
    for i in range(6):
        bypass(325 + 5 * i, 196, "+1V2")
    for i in range(4):
        bypass(325 + 5 * i, 206, "+3V3")
    bypass(355, 196, "+1V2A")
    bypass(360, 196, "+1V2A", "10nF")
    bypass(355, 206, "+1V2", "10uF", C0805)
    bypass(360, 206, "+3V3", "10uF", C0805)

    # SPI flash + programming header
    section("Config flash + programming header", 322, 236)
    fl = part("U", "Memory_Flash:W25Q32JVSS", 340, 252, "W25Q32JV", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm", fields="IC",
              extra={"MPN": "W25Q32JVSSIQ"})
    tie(fl, 1, "SPI_SS", 3)
    tie(fl, 2, "SPI_SDI", 3)
    tie(fl, 3, "FL_WP", 3)
    tie(fl, 4, "GND", 3)
    tie(fl, 5, "SPI_SDO", 3)
    tie(fl, 6, "SPI_SCK", 3)
    tie(fl, 7, "FL_HOLD", 3)
    tie(fl, 8, "+3V3", 3)
    vt("R", "10k", 322, 246, "+3V3", "FL_WP")
    vt("R", "10k", 328, 246, "+3V3", "FL_HOLD")
    vt("R", "10k", 334, 266, "+3V3", "SPI_SS")
    vt("R", "10k", 340, 266, "+3V3", "CRESET")
    vt("R", "10k", 346, 266, "+3V3", "CDONE")
    bypass(352, 246, "+3V3")
    hd = part("J", "Connector_Generic:Conn_01x07", 372, 256, "PROG", "Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical",
              fields="IC", nosim=True, extra={"Pinout": "1 GND, 2 SCK, 3 SDO(MOSI), 4 SDI(MISO), 5 SS, 6 CRESET, 7 CDONE (hold CRESET low to program)"})
    for pin, net in zip(range(1, 8), ("GND", "SPI_SCK", "SPI_SDO", "SPI_SDI", "SPI_SS", "CRESET", "CDONE")):
        tie(hd, pin, net, 3)
    hr("R", "1k", 356, 266, "CDONE", "LED_D")
    led("GRN", 368, 266, "LED_D", "GND")

    # user interface
    section("UI: mode button + 2 LEDs", 330, 4)
    sw = part("SW", "Switch:SW_Push", 340, 20, "MODE", "Button_Switch_SMD:SW_SPST_CK_RS282G05A3", fields="IC", nosim=True,
              extra={"Note": "cycles input: SCART RGB / component / composite / S-Video"})
    tie(sw, 1, "BTN_MODE", 3)
    tie(sw, 2, "GND", 3)
    vt("R", "10k", 330, 14, "+3V3", "BTN_MODE")
    for i, net in enumerate(("LED_A", "LED_B")):
        hr("R", "1k", 356 + 24 * i, 14, net, "LEDD%d" % i)
        led("GRN" if i else "RED", 372 + 24 * i, 14, "LEDD%d" % i, "GND")

    # ============================================================ I2C pull-ups
    vt("R", "2.2k", 190, 164, "+3V3", "I2C_SDA")
    vt("R", "2.2k", 196, 164, "+3V3", "I2C_SCL")

    # ============================================================ TFP410 + HDMI
    sh.S("HDMI")
    section("TFP410 DVI/HDMI transmitter (pin-strapped: 24-bit, rising edge, no I2C)", 395, 40)
    dv = part("U", "Video:TFP410PAP", 430, 80, "TFP410PAP", "Package_QFP:Texas_TQFP-64-1EP_10x10mm_P0.5mm_EP8x8mm_Mask5x5mm_ThermalVias",
              fields="IC", extra={"MPN": "TFP410PAPR"}, key="UDVI")
    names = {"DATA23": "DR7", "DATA22": "DR6", "DATA21": "DR5", "DATA20": "DR4", "DATA19": "DR3", "DATA18": "DR2", "DATA17": "DR1",
             "DATA16": "DR0", "DATA15": "DG7", "DATA14": "DG6", "DATA13": "DG5", "DATA12": "DG4", "DATA11": "DG3", "DATA10": "DG2",
             "DATA9": "DG1", "DATA8": "DG0", "DATA7": "DB7", "DATA6": "DB6", "DATA5": "DB5", "DATA4": "DB4", "DATA3": "DB3",
             "DATA2": "DB2", "DATA1": "DB1", "DATA0": "DB0"}
    tf = {36: "DATA23", 37: "DATA22", 38: "DATA21", 39: "DATA20", 40: "DATA19", 41: "DATA18", 42: "DATA17", 43: "DATA16",
          44: "DATA15", 45: "DATA14", 46: "DATA13", 47: "DATA12", 50: "DATA11", 51: "DATA10", 52: "DATA9", 53: "DATA8",
          54: "DATA7", 55: "DATA6", 58: "DATA5", 59: "DATA4", 60: "DATA3", 61: "DATA2", 62: "DATA1", 63: "DATA0"}
    for pin, nm in tf.items():
        tie(dv, pin, names[nm], 3)
    tie(dv, 57, "DVI_CLK", 3)
    tie(dv, 56, "TF_LO", 3)
    tie(dv, 2, "DVI_DE", 3)
    tie(dv, 4, "DVI_HS", 3)
    tie(dv, 5, "DVI_VS", 3)
    for pin in (6, 7, 8, 13, 14, 35, 34):
        tie(dv, pin, "TF_LO", 3)
    for pin in (9, 10, 15, 3):
        tie(dv, pin, "TF_HI", 3)
    tie(dv, 11, "TF_MSEN", 3)
    tie(dv, 19, "TF_TFADJ", 3)
    nc(dv, 49)
    for pin, net in ((21, "TXCN"), (22, "TXCP"), (24, "TX0N"), (25, "TX0P"), (27, "TX1N"), (28, "TX1P"), (30, "TX2N"), (31, "TX2P")):
        tie(dv, pin, net, 3)
    tie_group(dv, (1, 12, 33), "+3V3", 2)
    tie(dv, 18, "+3V3P", 2)
    tie_group(dv, (23, 29), "+3V3T", 2)
    tie_group(dv, (16, 48, 64, 17, 20, 26, 32, 65), "GND", 2)
    gnd_net("TF_LO", 395, 112)
    vt("R", "10k", 395, 104, "+3V3", "TF_HI", extra={"Note": "VREF = DVDD (high-swing inputs), BSEL = 24-bit, EDGE = rising, PD high"})
    vt("R", "4.7k", 401, 104, "+3V3", "TF_MSEN")
    vt("R", "510", 407, 104, "+3V3T", "TF_TFADJ", extra={"Tolerance": "1%", "Note": "TFADJ pull-up to TVDD, DVI swing"})
    for i, rail in enumerate(("+3V3", "+3V3", "+3V3", "+3V3P", "+3V3T", "+3V3T")):
        bypass(395 + 5 * i, 124, rail)
    bypass(395, 132, "+3V3P", "10uF", C0805)
    bypass(401, 132, "+3V3T", "10uF", C0805)
    bypass(407, 132, "+3V3", "10uF", C0805)

    section("HDMI connector + TPD12S016 source-port companion (ESD, DDC/HPD/CEC level shift, 5 V current-limited switch)", 395, 150)
    es = part("U", "VideoConv-V1:TPD12S016PW", 430, 190, "TPD12S016", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm", fields="IC",
              extra={"MPN": "TPD12S016PWR", "Note": "TMDS pins are pass-through ESD pins, order within the group is only a routing convenience"}, key="UESD")
    for pin, net in ((15, "TXCP"), (16, "TXCN"), (17, "TX0P"), (18, "TX0N"), (20, "TX1P"), (21, "TX1N"), (22, "TX2P"), (23, "TX2N")):
        tie(es, pin, net, 3)
    tie(es, 24, "+3V3", 2)
    tie(es, 11, "+5V", 2)
    tie(es, 13, "HDMI5V", 2)
    tie_group(es, (6, 14, 19), "GND", 2)
    tie(es, 12, "HDMI_CT", 3)            # CT_HPD high enables the part (datasheet Fig. 15: HPD_A also drives LS_OE)
    tie(es, 4, "HDMI_HPD", 3)
    tie(es, 5, "HDMI_HPD", 3)
    nc(es, 1)
    tie(es, 2, "DDC_SCL", 3)
    tie(es, 3, "DDC_SDA", 3)
    tie(es, 7, "H_CEC", 3)
    tie(es, 8, "H_SCL", 3)
    tie(es, 9, "H_SDA", 3)
    tie(es, 10, "HDMI_HPD_B", 3)
    vt("R", "10k", 395, 196, "+3V3", "HDMI_CT", extra={"Note": "CT_HPD high = level shifters + load switch enabled"})
    bypass(401, 196, "+3V3")
    bypass(407, 196, "+5V")
    bypass(413, 196, "HDMI5V", "1uF", C0805)
    hdmi = part("J", "Connector:HDMI_A", 455, 190, "HDMI", "Connector_Video:HDMI_A_Molex_208658-1001_Horizontal", fields="IC", nosim=True)
    for pin, net in ((1, "TX2P"), (3, "TX2N"), (4, "TX1P"), (6, "TX1N"), (7, "TX0P"), (9, "TX0N"), (10, "TXCP"), (12, "TXCN"),
                     (13, "H_CEC"), (15, "H_SCL"), (16, "H_SDA"), (18, "HDMI5V"), (19, "HDMI_HPD_B")):
        tie(hdmi, pin, net, 3)
    for pin in (2, 5, 8, 11, 17, "SH"):
        tie(hdmi, pin, "GND", 3)
    nc(hdmi, 14)

    # ============================================================ VGA out
    sh.S("VGA")
    section("VGA out: 3 x 6-bit R-2R DAC (R 287, 2R 576 into 75 ohm) + sync", 200, 256)
    vga = part("J", "Connector:DE15_Socket_HighDensity", 320, 290, "VGA", "Connector_Dsub:DSUB-15-HD_Socket_Horizontal_P2.29x1.90mm_EdgePinOffset3.03mm_Housed_MountingHolesOffset4.94mm",
               fields="IC", nosim=True)
    for pin, net in ((1, "VGA_R"), (2, "VGA_G"), (3, "VGA_B"), (13, "VGA_HSO"), (14, "VGA_VSO")):
        tie(vga, pin, net, 3)
    tie_group(vga, (5, 6, 7, 8, 10), "GND", 3)
    for pin in (4, 9, 11, 12, 15):
        nc(vga, pin)
    hr("R", "100", 300, 266, "VGA_HS", "VGA_HSO")
    hr("R", "100", 300, 272, "VGA_VS", "VGA_VSO")
    for c, (ch, net) in enumerate((("VR", "VGA_R"), ("VG", "VGA_G"), ("VB", "VGA_B"))):
        y = 282 + 15 * c
        n = [None] * 6
        for bit in range(6):
            x = 212 + 12 * bit
            vt("R", "576", x, y - 6, "%s%d" % (ch, bit), "LAD_%s%d" % (ch, bit), extra={"Tolerance": "1%", "Note": "2R"})
            n[bit] = "LAD_%s%d" % (ch, bit)
        for bit in range(5):
            hr("R", "287", 212 + 12 * bit + 6, y + 2, n[bit], n[bit + 1], extra={"Tolerance": "1%", "Note": "R"})
        vt("R", "576", 212 - 6, y + 6, n[0], "GND", extra={"Tolerance": "1%", "Note": "2R termination"})
        hr("R", "0", 212 + 12 * 5 + 8, y + 2, n[5], net, extra={"Note": "output (0 ohm, tune with a series R if needed)"})

    tb = ["title_block", ["title", q("VideoConv-V1: analog video to HDMI + VGA converter")],
          ["date", q("2026-10-30")], ["rev", q("1")],
          ["comment", "1", q("SCART RGB/CVBS/S-Video, component YPbPr, composite -> TVP7002/TVP5150 -> iCE40 -> TFP410 HDMI + VGA")],
          ["comment", "2", q("FPGA configures the decoders over I2C; schematic only, footprints for SCART/RCA still to choose")]]
    return sh, tb


if __name__ == "__main__":
    sh, tb = build()
    write_hier(sh, tb)
    import json
    dump_i = {"%s|%s" % k: v for k, v in INTENT.items()}
    dump_i["_groups"] = [[n, [list(x) for x in pins]] for n, pins in GROUPS]
    json.dump(dump_i, open(os.path.join(PRJ, "tools", "intent.json"), "w"), indent=0)
    tot = collections.Counter()
    for name, sub in sh.sheets.items():
        k = [r for r in sub.order if not sub.parts[r]["ref"].startswith("#")]
        print("  %-8s %3d parts %4d wires %4d labels" % (name, len(k), len(sub.wires), len(sub.labels)))
    print("wrote", SCH, "+", len(sh.sheets), "sub-sheets in sheets/")
