"""Generate lib/VideoConv-V1.kicad_sym: TVP7002PZP, TVP5150AM1PBS (pin tables from the TI datasheets in
datasheets/) and a few extra power-rail symbols cloned from KiCad's +3V3.

Pin tables:
  TVP7002   SLES206C, Table 1 / pin diagram (100-pin HTQFP PZP)
  TVP5150   SLES209E, Table 2-1 (32-pin TQFP PBS)
"""
import os, sys, copy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexp import parse, dump, find, find_all, q, unq

PRJ = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(PRJ, "lib", "VideoConv-V1.kicad_sym")
STOCK_PWR = r"C:\Program Files\KiCad\10.0\share\kicad\symbols\power.kicad_sym"
FONT = "\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t)"
S = 2.54


def pin(etype, x, y, ang, name, num, length=5.08):
    return ("\t\t\t(pin %s line\n\t\t\t\t(at %s %s %d)\n\t\t\t\t(length %s)\n\t\t\t\t(name \"%s\"\n%s\n\t\t\t\t)\n"
            "\t\t\t\t(number \"%s\"\n%s\n\t\t\t\t)\n\t\t\t)\n") % (etype, fmt(x), fmt(y), ang, fmt(length), name, FONT, num, FONT)


def fmt(v):
    s = ("%.3f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def symbol(name, ref, footprint, datasheet, desc, left, right, top, bottom, width):
    """left/right: lists of (type, name, number) with None = gap; top/bottom: lists of (type, name, [numbers])."""
    nl, nr = len(left), len(right)
    rows = max(nl, nr, 4)
    height = rows * S
    half_h, half_w = height / 2, width / 2
    y0 = half_h - S / 2                                  # first row centre
    pins = []
    for i, p in enumerate(left):
        if p:
            pins.append(pin(p[0], -(half_w + 5.08), y0 - i * S, 0, p[1], p[2]))
    for i, p in enumerate(right):
        if p:
            pins.append(pin(p[0], half_w + 5.08, y0 - i * S, 180, p[1], p[2]))
    for group, y, ang in ((top, half_h + 5.08, 270), (bottom, -(half_h + 5.08), 90)):
        n = len(group)
        for i, (etype, nm, nums) in enumerate(group):
            x = (i - (n - 1) / 2) * 2 * S
            for num in nums:                              # stacked pins share one location
                pins.append(pin(etype, x, y, ang, nm, num))
    props = [("Reference", ref, half_w, half_h + 8, False), ("Value", name, half_w, half_h + 10.5, False),
             ("Footprint", footprint, 0, 0, True), ("Datasheet", datasheet, 0, 0, True),
             ("Description", desc, 0, 0, True)]
    out = ["\t(symbol \"%s\"\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n"
           "\t\t(duplicate_pin_numbers_are_jumpers no)\n" % name]
    for key, val, x, y, hide in props:
        out.append("\t\t(property \"%s\" \"%s\"\n\t\t\t(at %s %s 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n%s"
                   "\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n%s\t\t\t)\n\t\t)\n"
                   % (key, val, fmt(x), fmt(y), "\t\t\t(hide yes)\n" if hide else "",
                      "\t\t\t\t(justify left)\n" if not hide else ""))
    out.append("\t\t(symbol \"%s_0_1\"\n\t\t\t(rectangle\n\t\t\t\t(start %s %s)\n\t\t\t\t(end %s %s)\n"
               "\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n"
               "\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n"
               % (name, fmt(-half_w), fmt(half_h), fmt(half_w), fmt(-half_h)))
    out.append("\t\t(symbol \"%s_1_1\"\n%s\t\t)\n\t\t(embedded_fonts no)\n\t)\n" % (name, "".join(pins)))
    return "".join(out)


def tvp7002():
    I, O, IO, P = "input", "output", "bidirectional", "power_in"
    left = [(I, "RIN_1", "11"), (I, "RIN_2", "10"), (I, "RIN_3", "9"), None,
            (I, "GIN_1", "2"), (I, "GIN_2", "100"), (I, "GIN_3", "98"), (I, "GIN_4", "96"), None,
            (I, "BIN_1", "18"), (I, "BIN_2", "17"), (I, "BIN_3", "16"), None,
            (I, "SOGIN_1", "1"), (I, "SOGIN_2", "99"), (I, "SOGIN_3", "97"), None,
            (I, "HSYNC_A", "81"), (I, "HSYNC_B", "82"), (I, "VSYNC_A", "78"), (I, "VSYNC_B", "79"), None,
            (I, "CLAMP", "76"), (I, "COAST", "77"), (I, "EXT_CLK", "80"), None,
            (IO, "SDA", "75"), (I, "SCL", "74"), (I, "I2CA", "73"), (I, "RESETB", "71"), (I, "PWDN", "70"),
            (I, "TMS", "72"), None, (O, "FILT1", "87"), (O, "FILT2", "88"), (I, "PLL_F", "89")]
    right = []
    for nm, nums in (("R", [55, 56, 57, 58, 59, 61, 62, 63, 64, 65]), ("G", [43, 44, 45, 46, 47, 48, 49, 50, 51, 52]),
                     ("B", [29, 30, 31, 32, 33, 34, 35, 36, 37, 38])):
        for bit, num in zip(range(9, -1, -1), nums):
            right.append((O, "%s_%d" % (nm, bit), str(num)))
        right.append(None)
    right += [(O, "DATACLK", "28"), (O, "HSOUT", "24"), (O, "VSOUT", "23"), (O, "FIDOUT", "22"), (O, "SOGOUT", "25")]
    top = [(P, "A33VDD", [13, 14, 93, 94]), (P, "AVDD", [4, 6, 7, 19]), (P, "PLL_AVDD", [84, 85]),
           (P, "DVDD", [39, 69]), (P, "IOVDD", [26, 41, 53, 66])]
    bottom = [(P, "A33GND", [12, 15, 92, 95]), (P, "AGND", [3, 5, 8, 20]), (P, "PLL_AGND", [83, 86, 90]),
              (P, "NSUB", [21, 91]), (P, "DGND", [40, 68]), (P, "IOGND", [27, 42, 54, 60, 67]), (P, "EP", [101])]
    return symbol("TVP7002PZP", "U", "Package_QFP:TQFP-100-1EP_14x14mm_P0.5mm_EP5x5mm",
                  "https://www.ti.com/lit/ds/symlink/tvp7002.pdf",
                  "Triple 8/10-bit 165 MSPS video and graphics digitizer, 100-pin HTQFP (PZP); pin 101 = thermal pad",
                  left, right, top, bottom, 45.72)


def tvp5150():
    I, O, IO, P = "input", "output", "bidirectional", "power_in"
    left = [(I, "AIP1A", "1"), (I, "AIP1B", "2"), None, (I, "XTAL1/OSC", "5"), (O, "XTAL2", "6"), None,
            (IO, "SDA", "22"), (I, "SCL", "21"), (I, "RESETB", "8"), (I, "PDN", "28"), None,
            (O, "REFP", "29"), (O, "REFM", "30")]
    right = [(IO, "YOUT7/I2CSEL", "11"), (O, "YOUT6", "12"), (O, "YOUT5", "13"), (O, "YOUT4", "14"),
             (O, "YOUT3", "15"), (O, "YOUT2", "16"), (O, "YOUT1", "17"), (O, "YOUT0", "18"), None,
             (O, "SCLK", "9"), (O, "HSYNC", "25"), (O, "VSYNC/PALI", "24"), (O, "FID/GLCO", "23"),
             (O, "AVID", "26"), (O, "INTREQ/GPCL/VBLK", "27")]
    top = [(P, "CH_AVDD", [32]), (P, "PLL_AVDD", [4]), (P, "DVDD", [20]), (P, "IO_DVDD", [10])]
    bottom = [(P, "CH_AGND", [31]), (P, "PLL_AGND", [3]), (P, "AGND", [7]), (P, "DGND", [19])]
    return symbol("TVP5150AM1PBS", "U", "Package_QFP:TQFP-32_7x7mm_P0.8mm",
                  "https://www.ti.com/lit/ds/symlink/tvp5150am1.pdf",
                  "Ultralow-power NTSC/PAL/SECAM video decoder, 32-pin TQFP (PBS)",
                  left, right, top, bottom, 30.48)


def tpd12s016():
    """TPD12S016PW (24-pin TSSOP), SLLSE96F pin-function table.  The TMDS pins are plain pass-through ESD pins, so their
    order within the group is only a routing convenience; the order here follows the table (CLK 15,16 / data 17,18 and 20..23)."""
    I, O, IO, P, PO, PA = "input", "output", "bidirectional", "power_in", "power_out", "passive"
    left = [(IO, "CEC_A", "1"), (IO, "SCL_A", "2"), (IO, "SDA_A", "3"), (O, "HPD_A", "4"), (I, "LS_OE", "5"), (I, "CT_HPD", "12")]
    right = [(IO, "CEC_B", "7"), (IO, "SCL_B", "8"), (IO, "SDA_B", "9"), (I, "HPD_B", "10"), None,
             (PA, "CLK+", "15"), (PA, "CLK-", "16"), (PA, "D0+", "17"), (PA, "D0-", "18"),
             (PA, "D1+", "20"), (PA, "D1-", "21"), (PA, "D2+", "22"), (PA, "D2-", "23")]
    top = [(P, "VCCA", [24]), (P, "VCC5V", [11]), (PO, "5V_OUT", [13])]
    bottom = [(P, "GND", [6, 14, 19])]
    return symbol("TPD12S016PW", "U", "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
                  "https://www.ti.com/lit/ds/symlink/tpd12s016.pdf",
                  "HDMI source-port companion: 12-channel ESD, I2C/CEC/HPD level shifters, 5 V current-limit load switch (24-pin TSSOP)",
                  left, right, top, bottom, 22.86)


def power_symbols():
    stock = parse(open(STOCK_PWR, encoding="utf-8").read())[0]
    base = next(s for s in find_all(stock, "symbol") if unq(s[1]) == "+3V3")
    out = []
    for name in ("+1V9", "+1V9A", "+3V3A", "+1V8A", "+1V2A", "+3V3P", "+3V3T"):
        s = copy.deepcopy(base)
        s[1] = q(name)
        for sub in find_all(s, "symbol"):
            sub[1] = q(unq(sub[1]).replace("+3V3", name, 1))
        for p in find_all(s, "property"):
            if unq(p[1]) == "Value":
                p[2] = q(name)
            if unq(p[1]) == "Description":
                p[2] = q("Power symbol creates a global label with name \"%s\"" % name)
        out.append("\t" + dump(s, 1))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    text = ("(kicad_symbol_lib\n\t(version 20251024)\n\t(generator \"kicad_symbol_editor\")\n\t(generator_version \"10.0\")\n"
            + tvp7002() + tvp5150() + tpd12s016() + power_symbols() + ")\n")
    open(OUT, "w", encoding="utf-8").write(text)
    check = parse(text)[0]
    names = [unq(s[1]) for s in find_all(check, "symbol")]
    print("wrote", OUT, "-", names)
