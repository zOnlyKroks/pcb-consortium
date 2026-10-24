"""Design table for the ECP5 emulation board: which FPGA ball goes to which net.

Used by gen_sch.py (labels on U1), check_netlist.py (netlist check) and gen_lpf.py (pin constraints).
Unit numbers are the units of the LCSC symbol lcsc_imported:LFE5U-25F-7BG256I as placed by the user:
  1 bank 7 (PL2-PL23)   2 bank 6 (PL26-PL47)   3 bank 8 / config   4 JTAG   5 bank 3 (PR26-PR47)
  6 bank 2 (PR2-PR23)   7 bank 1 (PT33-PT67)   8 bank 0 (PT4-PT29)  9 power
All banks run at VCCIO = 3.3 V.
"""

# --------------------------------------------------------------------------- per bank, in symbol pin order
BANK7 = ["B1", "B2", "C3", "D3", "C1", "E3", "C2", "F3", "D1", "F4", "E2", "F5", "G5", "F2", "G4", "E1",
         "F1", "G3", "G2", "H3", "H5", "J4", "H4", "J5", "G1", "J3", "H2", "K3", "J1", "K1", "J2", "K2"]
BANK6 = ["L1", "M1", "L2", "M2", "K4", "L4", "K5", "L5", "N1", "L3", "P2", "M3", "P1", "M4", "R1", "N3",
         "N4", "R2", "P3", "T2", "P4", "R4", "R3", "T3", "R5", "M5", "T4", "N5", "M6", "N6", "P6", "P5"]
BANK3 = ["P12", "P11", "N11", "M11", "N12", "T13", "M12", "R12", "T14", "R14", "R13", "P13", "T15", "P14", "R15",
         "N13", "N14", "R16", "M13", "P16", "M14", "P15", "L14", "N16", "L12", "K12", "L13", "K13", "M15", "L15",
         "M16", "L16"]
BANK2 = ["K15", "J15", "K16", "J16", "K14", "H15", "J14", "G16", "J12", "H13", "J13", "H12", "H14", "G15", "G14",
         "F16", "E16", "G13", "F15", "G12", "F12", "E15", "F13", "D16", "F14", "C15", "E14", "C16", "D14", "C14",
         "B15", "B16"]
BANK1 = ["A15", "A14", "B14", "A13", "E13", "C13", "D13", "B13", "E12", "C12", "D12", "B12", "A12", "E11", "A11",
         "D11", "C11", "E10", "B11", "D10", "C10", "A10", "B10", "A9", "E9", "C9", "D9", "B9", "B8", "D8", "C8", "E8"]
BANK0 = ["A8", "B7", "A7", "C7", "D7", "B6", "E7", "C6", "D6", "A6", "E6", "A5", "B5", "D5", "C5", "E5", "B4",
         "D4", "C4", "E4", "A4", "B3", "A3", "A2"]

PINS = {}          # ball -> net
UNIT = {}          # ball -> symbol unit
IOSTD = {}         # net -> extra LPF attributes


def put(unit, balls, nets):
    assert len(balls) == len(nets), (balls, nets)
    for b, n in zip(balls, nets):
        if n:
            assert b not in PINS, b
            PINS[b] = n
        UNIT[b] = unit


# bank 7: CH347F UART0 + SPI (host <-> emulated core, both usable at the same time) + GPIO header
put(1, BANK7, ["CH_TXD", "CH_RXD", "CH_RTS", "CH_CTS", "CH_SCS", "CH_SCK", "CH_MOSI", "CH_MISO"]
    + ["GPIO%d" % i for i in range(24)])
# bank 6: user LEDs, DIP switches, 7-segment, 25 MHz clock (P6 = PLL input LLC_GPLL0T_IN), 3 GPIO
put(2, BANK6, ["LED%d" % i for i in range(8)] + ["SW%d" % i for i in range(8)]
    + ["SEG_%s" % s for s in "ABCDEFG"] + ["SEG_DP"] + ["DIG%d" % i for i in range(4)]
    + ["GPIO24", "GPIO25", "CLK25", "GPIO26"])
# bank 3: SDRAM data, address, bank, clock (16 MB W9812G6KH: A0-A11; M15 spare = A12 for a 32 MB part)
put(5, BANK3, ["RAM_DQ%d" % i for i in range(16)] + ["RAM_A%d" % i for i in range(12)] + [None]
    + ["RAM_BA0", "RAM_BA1", "RAM_CLK"])
# bank 2: SDRAM control, microSD, audio, PMOD C + D
put(6, BANK2, ["RAM_CKE", "RAM_CSn", "RAM_RASn", "RAM_CASn", "RAM_WEn", "RAM_DQML", "RAM_DQMH",
               "SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_CD", "AUDIO_L", "AUDIO_R"]
    + ["PMODC%d" % i for i in range(8)] + ["PMODD%d" % i for i in range(8)])
# bank 1: HDMI (DVI, LVCMOS33D on A/B pairs), VGA 12 bit, 7 spare
put(7, BANK1, ["HDMI_D0_N", "HDMI_D1_N", "HDMI_D0_P", "HDMI_D1_P", "HDMI_D2_N", "HDMI_CK_N", "HDMI_D2_P", "HDMI_CK_P",
               "HDMI_HPD", "HDMI_SCL", "HDMI_SDA", None,
               "VGA_R0", "VGA_R1", "VGA_R2", "VGA_R3", "VGA_G0", "VGA_G1", "VGA_G2", "VGA_G3",
               "VGA_B0", "VGA_B1", "VGA_B2", "VGA_B3", "VGA_HS", "VGA_VS"] + [None] * 6)
# bank 0: PMOD A + B, GPIO header, 1 spare
put(8, BANK0, ["PMODA%d" % i for i in range(8)] + ["PMODB%d" % i for i in range(8)]
    + ["GPIO%d" % i for i in range(27, 34)] + [None])
# bank 8 (config): SPI flash, user buttons on D4-D7, config control
put(3, ["R8", "N9", "T8", "T7", "M7", "N7", "P7", "R7", "R6", "T6", "R9", "T9", "P9", "N10", "P10", "R10",
        "N8", "P8", "M8", "M9"],
    ["FLASH_CSn", "FLASH_CLK", "FLASH_IO0", "FLASH_IO1", "FLASH_IO2", "FLASH_IO3",
     "BTN0", "BTN1", "BTN2", "BTN3", "PROGRAMN", "INITN", "DONE", "CFG0", "CFG1", "CFG2", None, None, None, None])
# JTAG
put(4, ["M10", "T10", "R11", "T11"], ["JTAG_TDO", "JTAG_TCK", "JTAG_TDI", "JTAG_TMS"])

# balls that stay open (spares)
SPARE = sorted(b for b, u in UNIT.items() if b not in PINS)

# power unit 9
POWER = {"GND": ["A16", "H16", "T16", "D15", "N15", "T12", "G10", "H10", "J10", "K10", "F9", "H9", "J9", "K9", "F8",
                 "G8", "H8", "J8", "K8", "K7", "K6", "T5", "D2", "N2", "A1", "H1", "T1"],
         "+1V1": ["L10", "G9", "L9", "L8", "G7", "G6"],
         "+2V5": ["G11", "L7"],
         "+3V3": ["F7", "F6", "F11", "F10", "H11", "J11", "K11", "L11", "L6", "J7", "J6", "H7", "H6"]}

# --------------------------------------------------------------------------- LPF attributes
for i in range(8):
    IOSTD["SW%d" % i] = "PULLMODE=DOWN"                 # DIP switches close to +3V3 through 1k
for i in range(4):
    IOSTD["BTN%d" % i] = "PULLMODE=UP"                  # external 10k too; buttons are active low
for n in ("SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3", "SD_CD"):
    IOSTD[n] = "PULLMODE=UP"                            # SD bus pull-ups are the FPGA's internal ones
for n in ("HDMI_D0", "HDMI_D1", "HDMI_D2", "HDMI_CK"):
    IOSTD[n + "_P"] = "IO_TYPE=LVCMOS33D DRIVE=8"       # pseudo-differential TMDS; _N is implied by the pair

if __name__ == "__main__":
    print("signals %d, spare balls %s" % (len(PINS), SPARE))
