#include <SPI.h>

// Pin definitions
#define PIN_SDO    13   // MISO
#define PIN_SDI    12   // MOSI
#define PIN_SCLK   11   // Clock
#define PIN_CSB    10   // Chip Select (active low)
#define PIN_DRDYB  4    // Data Ready (active low)
#define PIN_ALARMB 5    // Alarm (active low)
#define PIN_SYNCB  6    // Sync (active low)

// ADS1293 Register addresses
#define ADS1293_CONFIG          0x00  // Configuration register (start/stop)
#define ADS1293_FLEX_CH1_CN     0x01  // Channel 1 config
#define ADS1293_FLEX_CH2_CN     0x02  // Channel 2 config
#define ADS1293_CMDET_EN        0x0A  // Common-mode detector enable
#define ADS1293_RLD_CN          0x0C  // RLD amplifier control
#define ADS1293_OSC_CN          0x12  // Oscillator control
#define ADS1293_AFE_SHDN_CN     0x14  // Shutdown unused channels
#define ADS1293_R2_RATE         0x21  // R2 decimation rate
#define ADS1293_R3_RATE_CH1     0x22  // R3 decimation rate channel 1
#define ADS1293_R3_RATE_CH2     0x23  // R3 decimation rate channel 2
#define ADS1293_DRDYB_SRC       0x27  // DRDYB source select
#define ADS1293_LOOP_READ_BACK  0x2F  // Loop read-back mode
#define ADS1293_DATA_CH1_ECG    0x37  // Channel 1 ECG data (3 bytes: 0x37-0x39)
#define ADS1293_REVID           0x40  // Revision ID register

// SPI settings for ADS1293 (max 20MHz, CPOL=0, CPHA=1 -> SPI_MODE1)
SPISettings ads1293Settings(4000000, MSBFIRST, SPI_MODE1);

void setup() {
  Serial.begin(115200);
  delay(1000);  // Give time for serial monitor to connect

  Serial.println();
  Serial.println("=== ESP32 Starting ===");
  Serial.println("ADS1293 Ready Check");

  // Configure pins
  pinMode(PIN_CSB, OUTPUT);
  pinMode(PIN_DRDYB, INPUT);
  pinMode(PIN_ALARMB, INPUT);
  pinMode(PIN_SYNCB, OUTPUT);

  // Deselect chip and set sync high
  digitalWrite(PIN_CSB, HIGH);
  digitalWrite(PIN_SYNCB, HIGH);

  // Initialize SPI with custom pins
  SPI.begin(PIN_SCLK, PIN_SDO, PIN_SDI, PIN_CSB);

  delay(100);  // Allow ADS1293 to stabilize

  // Read and verify device ID
  uint8_t revId = readRegister(ADS1293_REVID);
  Serial.print("ADS1293 Revision ID: 0x");
  Serial.println(revId, HEX);

  if (revId == 0x01) {
    Serial.println("ADS1293 detected successfully!");

    // Initialize and configure the ADS1293
    Serial.println("Configuring ADS1293...");
    initializeADS1293();
    Serial.println("Configuration complete. Starting data acquisition.");
  } else if (revId == 0x00 || revId == 0xFF) {
    Serial.println("ERROR: No response from ADS1293. Check wiring.");
  } else {
    Serial.print("WARNING: Unexpected ID. Got 0x");
    Serial.println(revId, HEX);
  }
}

// Initialize and configure ADS1293 for ECG measurement
void initializeADS1293() {
  // Stop any ongoing conversions
  writeRegister(ADS1293_CONFIG, 0x00);
  delay(10);

  // Channel 1: INP=IN2, INN=IN1
  writeRegister(ADS1293_FLEX_CH1_CN, 0x11);

  // Channel 2: INP=IN3, INN=IN1
  writeRegister(ADS1293_FLEX_CH2_CN, 0x19);

  // Enable common-mode detector on IN1, IN2, IN3
  writeRegister(ADS1293_CMDET_EN, 0x07);

  // Connect RLD amplifier output internally to IN4
  writeRegister(ADS1293_RLD_CN, 0x04);

  // Use external crystal and feed internal oscillator
  writeRegister(ADS1293_OSC_CN, 0x04);

  // Shutdown unused channel 3
  writeRegister(ADS1293_AFE_SHDN_CN, 0x24);

  // R2 decimation rate
  writeRegister(ADS1293_R2_RATE, 0x02);

  // R3 decimation rate for channel 1
  writeRegister(ADS1293_R3_RATE_CH1, 0x02);

  // R3 decimation rate for channel 2
  writeRegister(ADS1293_R3_RATE_CH2, 0x02);

  // Configure DRDYB source to channel 1 ECG
  writeRegister(ADS1293_DRDYB_SRC, 0x08);

  // Enable channel 1 and 2 for loop read-back mode
  writeRegister(ADS1293_LOOP_READ_BACK, 0x30);

  delay(10);

  // Start data conversion
  writeRegister(ADS1293_CONFIG, 0x01);

  delay(50);  // Allow conversions to start
}

void loop() {
  // Check DRDYB pin state
  Serial.print("DRDYB: ");
  Serial.print(isDataReady() ? "LOW (ready)" : "HIGH (not ready)");

  // Read CONFIG register to verify chip is running
  uint8_t config = readRegister(ADS1293_CONFIG);
  Serial.print(" | CONFIG: 0x");
  Serial.print(config, HEX);

  // Read REVID again to verify communication
  uint8_t revId = readRegister(ADS1293_REVID);
  Serial.print(" | REVID: 0x");
  Serial.println(revId, HEX);

  delay(500);
}

// Check DRDYB pin - returns true if data is ready (pin is LOW)
bool isDataReady() {
  return (digitalRead(PIN_DRDYB) == LOW);
}

// Read a single register from ADS1293
uint8_t readRegister(uint8_t reg) {
  uint8_t value;

  SPI.beginTransaction(ads1293Settings);
  digitalWrite(PIN_CSB, LOW);
  delayMicroseconds(1);

  SPI.transfer(0x80 | reg);  // Read command: bit 7 = 1
  value = SPI.transfer(0x00);

  digitalWrite(PIN_CSB, HIGH);
  SPI.endTransaction();

  return value;
}

// Write a single register to ADS1293
void writeRegister(uint8_t reg, uint8_t value) {
  SPI.beginTransaction(ads1293Settings);
  digitalWrite(PIN_CSB, LOW);
  delayMicroseconds(1);

  SPI.transfer(reg & 0x7F);  // Write command: bit 7 = 0
  SPI.transfer(value);

  digitalWrite(PIN_CSB, HIGH);
  SPI.endTransaction();
}
