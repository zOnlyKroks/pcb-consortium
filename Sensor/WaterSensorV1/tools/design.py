"""WaterSensorV1 design truth: every part's intended pin -> net map (checked against the schematic netlist)."""

NETS = {
    # USB-C, ESD, charger
    "J1": {"A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS", "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
           "A7": "USB_DN", "B7": "USB_DN", "A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND", "SH": "GND"},
    "U1": {"1": "USB_DN", "6": "USB_DN", "3": "USB_DP", "4": "USB_DP", "5": "VBUS", "2": "GND"},
    "R1": {"1": "CC1", "2": "GND"}, "R2": {"1": "CC2", "2": "GND"},
    "C1": {"1": "VBUS", "2": "GND"},
    "U2": {"1": "CHRG_N", "2": "GND", "3": "VBAT", "4": "VBUS", "5": "PROG"},
    "R3": {"1": "PROG", "2": "GND"},
    "R4": {"1": "VBUS", "2": "CHRG_LED"}, "D1": {"2": "CHRG_LED", "1": "CHRG_N"},
    # battery, reverse-polarity FET, LDO
    "J2": {"1": "BAT_RAW", "2": "GND"},
    "Q1": {"1": "GND", "2": "VBAT", "3": "BAT_RAW"},
    "C2": {"1": "VBAT", "2": "GND"},
    "U3": {"1": "VBAT", "2": "GND", "3": "VBAT", "5": "+3V3"},
    "C3": {"1": "+3V3", "2": "GND"}, "C4": {"1": "+3V3", "2": "GND"}, "C5": {"1": "+3V3", "2": "GND"},
    # VBUS detect, switched battery divider
    "R5": {"1": "VBUS", "2": "VBUS_DET"}, "R6": {"1": "VBUS_DET", "2": "GND"},
    "Q2": {"1": "VBAT_G", "2": "VBAT", "3": "VBAT_SW"},
    "R7": {"1": "VBAT", "2": "VBAT_G"},
    "Q3": {"1": "VBAT_MEAS_EN", "2": "GND", "3": "VBAT_G"},
    "R8": {"1": "VBAT_MEAS_EN", "2": "GND"},
    "R9": {"1": "VBAT_SW", "2": "VBAT_ADC"}, "R10": {"1": "VBAT_ADC", "2": "GND"}, "C6": {"1": "VBAT_ADC", "2": "GND"},
    # MCU
    "U4": {"1": "GND", "28": "GND", **{str(p): "GND" for p in range(29, 38)}, "2": "+3V3", "3": "EN",
           "4": "VBAT_MEAS_EN", "5": "PROBE_EN_N", "6": "LED", "8": "VBAT_ADC", "9": "PROBE_ADC", "10": "IO8",
           "13": "USB_DN", "14": "USB_DP", "15": "BOOT", "24": "RXD0", "25": "TXD0", "26": "USER_BTN", "27": "VBUS_DET"},
    "R11": {"1": "+3V3", "2": "EN"}, "C7": {"1": "EN", "2": "GND"},
    "SW1": {"3": "EN", "4": "EN", "1": "GND", "2": "GND"},
    "R12": {"1": "+3V3", "2": "BOOT"}, "SW2": {"3": "BOOT", "4": "BOOT", "1": "GND", "2": "GND"},
    "R13": {"1": "+3V3", "2": "IO8"},
    "SW3": {"3": "USER_BTN", "4": "USER_BTN", "1": "GND", "2": "GND"}, "R14": {"1": "+3V3", "2": "USER_BTN"},
    "R15": {"1": "LED", "2": "LED_A"}, "D2": {"2": "LED_A", "1": "GND"},
    "TP1": {"1": "TXD0"}, "TP2": {"1": "RXD0"}, "TP3": {"1": "+3V3"}, "TP4": {"1": "VBAT"}, "TP5": {"1": "GND"},
    # soil probe connector
    "Q4": {"1": "PROBE_EN_N", "2": "+3V3", "3": "PROBE_VCC"},
    "R16": {"1": "+3V3", "2": "PROBE_EN_N"},
    "C8": {"1": "PROBE_VCC", "2": "GND"},
    "R17": {"2": "PROBE_SIG", "1": "PROBE_ADC"}, "C9": {"1": "PROBE_ADC", "2": "GND"},
    "J3": {"1": "GND", "2": "PROBE_VCC", "3": "PROBE_SIG"},
}
