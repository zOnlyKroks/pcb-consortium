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
    r_cc2 = part("R", "Device:R", 29, 28.5, "5.1k", fields="L")
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
        ren = part("R", "Device:R", X - 9.5, Y + 1, "100k", rot=90, extra={"Note": "EN pull-up"})
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
        rt = part("R", "Device:R", X + 33, Y + 6.5, r1, extra={"Tolerance": "1%"})
        rb = part("R", "Device:R", X + 33, Y + 9.5, "10k", extra={"Tolerance": "1%"})
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

