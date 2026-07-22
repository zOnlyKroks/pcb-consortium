/*
 * ADS1293 3-Lead ECG Monitor
 * Configuration per TI Datasheet Section 9.2.1.2
 *
 * Features:
 * - Lead I (LA-RA) and Lead II (LL-RA) measurement
 * - Fixed gain: 3.5 V/V
 * - Baseline wander removal: 2-second moving average filter
 * - Sample rate: ~85 Hz (after decimation)
 * - RLD (Right Leg Drive) enabled for common-mode rejection
 */

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
#define ADS1293_FLEX_CH3_CN     0x03  // Channel 3 config
#define ADS1293_CMDET_EN        0x0A  // Common-mode detector enable
#define ADS1293_DRDYB_SRC_CN    0x0B  // DRDYB source config
#define ADS1293_RLD_CN          0x0C  // RLD amplifier control
#define ADS1293_WILSON_EN1      0x0D  // Wilson reference enable 1
#define ADS1293_WILSON_EN2      0x0E  // Wilson reference enable 2
#define ADS1293_WILSON_EN3      0x0F  // Wilson reference enable 3
#define ADS1293_WILSON_CN       0x10  // Wilson reference control
#define ADS1293_REF_CN          0x11  // Reference control
#define ADS1293_OSC_CN          0x12  // Oscillator control
#define ADS1293_AFE_RES         0x13  // AFE reserved
#define ADS1293_AFE_SHDN_CN     0x14  // Shutdown unused channels
#define ADS1293_R2_RATE         0x21  // R2 decimation rate
#define ADS1293_R3_RATE_CH1     0x22  // R3 decimation rate channel 1
#define ADS1293_R3_RATE_CH2     0x23  // R3 decimation rate channel 2
#define ADS1293_DRDYB_SRC       0x27  // DRDYB source select
#define ADS1293_LOD_CN          0x06  // Lead-off detection control
#define ADS1293_LOD_EN          0x07  // Lead-off detection enable
#define ADS1293_LOD_CURRENT     0x08  // Lead-off current magnitude
#define ADS1293_LOD_AC_CN       0x09  // Lead-off AC configuration
#define ADS1293_CH_CNFG         0x2F  // Channel configuration (was LOOP_READ_BACK)
#define ADS1293_DATA_STATUS     0x30  // Data status (includes lead-off status)
#define ADS1293_DATA_CH1_ECG    0x37  // Channel 1 ECG data (3 bytes: 0x37-0x39)
#define ADS1293_REVID           0x40  // Revision ID register

// SPI settings for ADS1293 (max 20MHz, CPOL=0, CPHA=0 -> SPI_MODE0)
// Data is latched on RISING edge, shifted on FALLING edge
SPISettings ads1293Settings(4000000, MSBFIRST, SPI_MODE0);

// Forward declarations
uint8_t readRegister(uint8_t reg);

// Verify register value helper
void verifyReg(const char* name, uint8_t addr, uint8_t expected) {
  uint8_t actual = readRegister(addr);

  Serial.print("   ");
  Serial.print(name);
  for (int i = strlen(name); i < 15; i++) Serial.print(" ");
  Serial.print(" | 0x");
  if (addr < 0x10) Serial.print("0");
  Serial.print(addr, HEX);
  Serial.print(" | 0x");
  if (expected < 0x10) Serial.print("0");
  Serial.print(expected, HEX);
  Serial.print("     | 0x");
  if (actual < 0x10) Serial.print("0");
  Serial.print(actual, HEX);
  Serial.print("   | ");
  if (actual == expected) {
    Serial.println("OK");
  } else {
    Serial.println("MISMATCH!");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n\n=== ADS1293 3-Lead ECG - Diagnostic Mode ===\n");

  // Configure pins
  pinMode(PIN_CSB, OUTPUT);
  digitalWrite(PIN_CSB, HIGH);

  // Initialize SPI
  SPI.begin(PIN_SCLK, PIN_SDO, PIN_SDI, PIN_CSB);
  delay(100);

  // Verify communication with ADS1293
  Serial.println("1. Checking SPI communication...");
  uint8_t revId = readRegister(ADS1293_REVID);
  Serial.print("   Revision ID: 0x");
  Serial.println(revId, HEX);

  if (revId == 0x00 || revId == 0xFF) {
    Serial.println("   ERROR: Cannot communicate with ADS1293!");
    while(1) delay(1000);  // Halt on communication error
  }
  Serial.println("   OK - Communication working\n");

  // Initialize and configure the ADS1293
  Serial.println("2. Configuring ADS1293 for 3-lead ECG...");
  initializeADS1293();
  Serial.println("   Done\n");

  // Verify configuration - read back all critical registers
  Serial.println("3. Verifying configuration:");
  Serial.println("   Reg Name        | Addr | Expected | Actual | Status");
  Serial.println("   ----------------|------|----------|--------|-------");
  verifyReg("CONFIG", ADS1293_CONFIG, 0x01);
  verifyReg("FLEX_CH1_CN", ADS1293_FLEX_CH1_CN, 0x11);
  verifyReg("FLEX_CH2_CN", ADS1293_FLEX_CH2_CN, 0x19);
  verifyReg("CMDET_EN", ADS1293_CMDET_EN, 0x07);
  verifyReg("RLD_CN", ADS1293_RLD_CN, 0x0F);
  verifyReg("OSC_CN", ADS1293_OSC_CN, 0x04);
  verifyReg("AFE_SHDN_CN", ADS1293_AFE_SHDN_CN, 0x24);
  verifyReg("R2_RATE", ADS1293_R2_RATE, 0x02);
  verifyReg("R3_RATE_CH1", ADS1293_R3_RATE_CH1, 0x02);
  verifyReg("R3_RATE_CH2", ADS1293_R3_RATE_CH2, 0x02);
  verifyReg("DRDYB_SRC", ADS1293_DRDYB_SRC, 0x08);
  verifyReg("CH_CNFG", ADS1293_CH_CNFG, 0x30);
  Serial.println();

  // Brief startup delay
  Serial.println("4. Starting ECG acquisition...");
  Serial.println("   RLD: 0x0F (all inputs, testing for stability)");
  Serial.println("   DC removal: 0.2 Hz high-pass filter");
  Serial.println("   Viewer: FIXED Y-axis scale (no auto-zoom)");
  Serial.println("   Format: timestamp,raw_value,ac_signal_mV");
  Serial.println("   STATS: Watch for STABLE raw_range (not growing)\n");
  delay(100);
}

// Initialize and configure ADS1293 for 3-Lead ECG measurement
// Configuration follows TI datasheet section 9.2.1.2 exactly
// Electrode connections per datasheet section 9.2.1:
//   IN1 = RA (Right Arm)
//   IN2 = LA (Left Arm)
//   IN3 = LL (Left Leg)
//   IN4 = RL (Right Leg) - RLD output drives common-mode back to body
// Measures: Channel 1 = Lead I (LA-RA), Channel 2 = Lead II (LL-RA)
// Lead III can be calculated as: Lead III = Lead II - Lead I
void initializeADS1293() {
  // Stop any ongoing conversions - critical for writing config registers
  writeRegister(ADS1293_CONFIG, 0x00);
  delay(50);  // Longer delay to ensure fully stopped

  // Verify stopped
  uint8_t cfg = readRegister(ADS1293_CONFIG);
  if (cfg != 0x00) {
    // Try again
    writeRegister(ADS1293_CONFIG, 0x00);
    delay(50);
  }

  // Step 1: Channel 1 = Lead I (LA - RA): INP=IN2, INN=IN1
  writeRegister(ADS1293_FLEX_CH1_CN, 0x11);

  // Step 2: Channel 2 = Lead II (LL - RA): INP=IN3, INN=IN1
  writeRegister(ADS1293_FLEX_CH2_CN, 0x19);

  // Channel 3: Not used (will be shut down in step 6)

  // Step 3: Enable common-mode detector on IN1, IN2, IN3 (RA, LA, LL)
  writeRegister(ADS1293_CMDET_EN, 0x07);

  // Step 4: RLD Configuration
  // Testing different values to find stable configuration:
  // 0x04 = TI spec, active RLD → oscillation
  // 0x00 = RLD disabled → growing amplitude (no DC bias path)
  // 0x0F = RLD on all inputs, different mode
  writeRegister(ADS1293_RLD_CN, 0x0F);  // Try RLD on all inputs

  // Step 5: Use external crystal and feed internal oscillator to digital
  writeRegister(ADS1293_OSC_CN, 0x04);

  // Step 6: Shutdown unused channel 3's signal path
  writeRegister(ADS1293_AFE_SHDN_CN, 0x24);

  // Step 7: R2 decimation rate = 5 for all channels
  writeRegister(ADS1293_R2_RATE, 0x02);

  // Step 8: R3 decimation rate = 6 for channel 1
  writeRegister(ADS1293_R3_RATE_CH1, 0x02);

  // Step 9: R3 decimation rate = 6 for channel 2
  writeRegister(ADS1293_R3_RATE_CH2, 0x02);

  // Step 10: Configure DRDYB source to channel 1 ECG (fastest channel)
  writeRegister(ADS1293_DRDYB_SRC, 0x08);

  // Step 11: Enable channel 1 ECG and channel 2 ECG for loop read-back mode
  writeRegister(ADS1293_CH_CNFG, 0x30);
  delay(10);

  // Step 12: Start data conversion
  writeRegister(ADS1293_CONFIG, 0x01);
  delay(50);
}

// Simple DC offset removal with diagnostics
static uint32_t sampleCount = 0;
static int32_t minRaw = 2147483647;
static int32_t maxRaw = -2147483648;
static uint32_t lastStatsReport = 0;
static float dcOffset = 0;
static bool dcInitialized = false;
const float alpha = 0.998;  // High-pass filter: 0.2 Hz cutoff at 100 Hz

void loop() {
  // Read ECG data from channel 1 (Lead I: LA - RA)
  int32_t rawValue = readECGData();

  // Track min/max to see drift
  if (rawValue < minRaw) minRaw = rawValue;
  if (rawValue > maxRaw) maxRaw = rawValue;
  sampleCount++;

  // Convert to voltage - ADS1293 has FIXED GAIN of 3.5 V/V
  float voltage_mV = (rawValue / 8388607.0) * 342.857;

  // Initialize DC offset on first sample
  if (!dcInitialized) {
    dcOffset = voltage_mV;
    dcInitialized = true;
  }

  // Simple exponential DC tracking (high-pass filter)
  dcOffset = alpha * dcOffset + (1.0 - alpha) * voltage_mV;
  float acSignal_mV = voltage_mV - dcOffset;

  // Report statistics every 2 seconds
  if (millis() - lastStatsReport >= 2000) {
    Serial.print("# STATS: samples=");
    Serial.print(sampleCount);
    Serial.print(" raw_range=");
    Serial.print(maxRaw - minRaw);
    Serial.print(" (");
    Serial.print(((maxRaw - minRaw) / 8388607.0) * 342.857, 2);
    Serial.print(" mV) DC_offset=");
    Serial.print(dcOffset, 2);
    Serial.println(" mV");

    // Reset stats for next window
    minRaw = 2147483647;
    maxRaw = -2147483648;
    lastStatsReport = millis();
  }

  // Check for saturation
  if (rawValue >= 8000000 || rawValue <= -8000000) {
    Serial.print("# SATURATION at t=");
    Serial.print(millis());
    Serial.print(" raw=");
    Serial.println(rawValue);
  }

  // Output: timestamp, raw_value, AC signal (DC removed)
  Serial.print(millis());
  Serial.print(",");
  Serial.print(rawValue);
  Serial.print(",");
  Serial.println(acSignal_mV, 3);

  delay(10);  // ~100 Hz sampling
}

// Read 24-bit ECG data from channel 1
int32_t readECGData() {
  uint8_t data[3];

  SPI.beginTransaction(ads1293Settings);
  digitalWrite(PIN_CSB, LOW);   // Select chip (active LOW)
  delayMicroseconds(1);

  SPI.transfer(0x80 | ADS1293_DATA_CH1_ECG);  // Read command
  data[0] = SPI.transfer(0x00);  // MSB
  data[1] = SPI.transfer(0x00);  // Middle byte
  data[2] = SPI.transfer(0x00);  // LSB

  digitalWrite(PIN_CSB, HIGH);  // Deselect chip
  SPI.endTransaction();

  // Combine into 24-bit signed integer
  int32_t value = ((int32_t)data[0] << 16) | ((int32_t)data[1] << 8) | data[2];

  // Sign extend from 24-bit to 32-bit
  if (value & 0x800000) {
    value |= 0xFF000000;
  }

  return value;
}

// Read a single register from ADS1293
uint8_t readRegister(uint8_t reg) {
  uint8_t value;

  SPI.beginTransaction(ads1293Settings);
  digitalWrite(PIN_CSB, LOW);
  delayMicroseconds(1);

  SPI.transfer(0x80 | reg);  // Read command
  value = SPI.transfer(0x00);

  digitalWrite(PIN_CSB, HIGH);
  SPI.endTransaction();

  return value;
}

// Write a single register to ADS1293
void writeRegister(uint8_t reg, uint8_t value) {
  SPI.beginTransaction(ads1293Settings);
  digitalWrite(PIN_CSB, LOW);   // Select chip (active LOW)
  delayMicroseconds(1);

  SPI.transfer(reg & 0x7F);  // Write command: bit 7 = 0
  SPI.transfer(value);

  digitalWrite(PIN_CSB, HIGH);  // Deselect chip
  SPI.endTransaction();
}
