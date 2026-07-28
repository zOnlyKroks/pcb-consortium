# ADS1293 ECG Monitor

Real-time ECG data acquisition and visualization using ADS1293CISQ and ESP32.

## Hardware Setup

### Connections
- **SCLK** (ESP32 Pin 11) → ADS1293 SCLK
- **MISO** (ESP32 Pin 13) → ADS1293 SDO
- **MOSI** (ESP32 Pin 12) → ADS1293 SDI
- **CSB** (ESP32 Pin 10) → ADS1293 CSB
- **3.3V** → ADS1293 VDD
- **GND** → ADS1293 GND

### SPI Configuration
- **Mode**: SPI_MODE0 (CPOL=0, CPHA=0)
- **Speed**: 4 MHz
- **Bit Order**: MSB First

## Software Setup

### 1. Arduino Firmware

Upload `ekg/ekg.ino` to your ESP32:
1. Open in Arduino IDE
2. Select ESP32 board
3. Select correct COM port
4. Upload

### 2. Windows ECG Viewer

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Run the viewer:
```bash
python ekg_viewer.py
```

The application will:
- List available COM ports
- Let you select your ESP32
- Display real-time ECG waveform
- Show statistics (sample rate, min/max values)

## Features

### Arduino Firmware
- ✅ SPI communication with ADS1293
- ✅ Rev 1 chip detection
- ✅ Channel configuration (CH1: IN2-IN1, CH2: IN3-IN1)
- ✅ 24-bit ECG data acquisition
- ✅ CSV streaming over serial (timestamp,value)

### Windows Viewer
- ✅ Real-time waveform display
- ✅ Auto-scaling Y-axis
- ✅ Rolling window (last 1000 samples)
- ✅ Sample rate calculation
- ✅ Min/Max tracking
- ✅ 20 FPS refresh rate

## Data Format

Serial output format:
```
timestamp_ms,ecg_value
1234,6075041
1239,6047951
1244,6532032
```

Where:
- `timestamp_ms`: Milliseconds since ESP32 boot
- `ecg_value`: 24-bit signed integer (-8388608 to 8388607)

## Troubleshooting

### No data displayed
- Check COM port selection
- Verify ESP32 is connected and programmed
- Check serial monitor (115200 baud) for error messages

### Noisy data
- Check power supply (stable 3.3V)
- Verify proper grounding
- Check electrode connections
- Consider adding RLD (Right Leg Drive) connection

### SPI Communication Issues
- Verify SPI_MODE0 is used
- Check CSB is active LOW
- Measure 3.3V on ADS1293 VDD pins
- Verify all SPI signals with logic analyzer

## Technical Details

### ADS1293 Configuration
- **Input**: Differential (IN2-IN1 for CH1)
- **Sample Rate**: Configured via R2/R3 decimation
- **Common-Mode Detection**: Enabled on IN1, IN2, IN3
- **RLD**: Connected internally to IN4
- **Oscillator**: External crystal mode

### Performance
- **Resolution**: 24-bit
- **Typical Sample Rate**: ~200 Hz (configurable)
- **Serial Baud**: 115200

## License

Hardware schematics and PCB: See project files
Software: MIT License
