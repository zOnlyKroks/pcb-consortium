// NixiClockV1 - 6 x IN-16, hh:mm:ss, time from NTP over WiFi.
//
// Hardware (see ../NixiClockV1.kicad_sch):
//   IO4 SRCLK, IO5 RCLK, IO6 SER -> 3 x 74HC595 (U301 first in the chain, U303 last)
//   IO7 OE_N (low = outputs on), IO10 HV_OFF (high = 185 V boost off), IO9 BOOT button (low = pressed)
//   IO1 VIN_SNS (VIN x 22k / 122k), IO3 PD_OK_N (low = CH221K got 9 V by USB PD)
// The HV only runs while VIN > 7 V: 9 V from a PD charger or from the internal terminal J102. On a plain 5 V USB
// port the clock still syncs and can be flashed, but the tubes stay dark.
// Shift register bits (QA = bit 0):
//   U301: K0..K7          U302: K8 K9 KDL KDR A1 A2 A3 A4          U303: A5 A6 (rest unused)
// One anode per 2 ms slot (6 slots = 83 Hz), all bits cleared for 200 us between slots against ghosting.
//
// First boot: join WiFi "NixiClock-Setup" with a phone, pick the network and (optionally) the time zone.
// Hold BOOT for 5 s while plugging in to forget the WiFi settings.

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>
#include <esp_sntp.h>
#include <time.h>
#include "soc/gpio_reg.h"

// ----------------------------------------------------------------------------- pins
static constexpr int PIN_SRCLK = 4, PIN_RCLK = 5, PIN_SER = 6, PIN_OE_N = 7, PIN_BOOT = 9, PIN_HV_OFF = 10;
static constexpr int PIN_VIN_SNS = 1, PIN_PD_OK_N = 3;
static constexpr float VIN_DIVIDER = 122.0f / 22.0f;
static constexpr float VIN_HV_ON = 7.0f, VIN_HV_OFF = 6.5f;     // hysteresis for the HV enable

// ----------------------------------------------------------------------------- settings
static const char *DEFAULT_TZ = "CET-1CEST,M3.5.0,M10.5.0/3";   // Europe/Berlin; POSIX TZ string
static constexpr int NIGHT_FROM = 23, NIGHT_TO = 7;              // dimmed between these hours
static constexpr int BRIGHT_DAY = 16, BRIGHT_NIGHT = 4;          // on-time in 100 us ticks of an 18-tick window
static constexpr bool SEPARATOR_RIGHT_COMMAS = true;             // true: right commas of tubes 2+4, false: left of 3+5

// ----------------------------------------------------------------------------- display state (ISR side)
static constexpr int SLOT_TICKS = 20;                            // 20 x 100 us = 2 ms per tube
static constexpr int BLANK_TICKS = 2;                            // first 200 us of a slot: everything off
static volatile uint8_t dispDigit[6] = {0, 0, 0, 0, 0, 0};       // 0..9, 10 = blank
static volatile bool dispDpL[6], dispDpR[6];
static volatile uint8_t brightness = BRIGHT_DAY;                 // ticks the tube is lit per slot
static volatile bool displayOn = true;

static hw_timer_t *muxTimer = nullptr;

// bit positions in the 24-bit word (bit 0 = U301.QA ... bit 23 = U303.QH)
static constexpr uint32_t BIT_K(int d) { return 1u << d; }                            // K0..K9 = bits 0..9
static constexpr uint32_t BIT_DL = 1u << 10, BIT_DR = 1u << 11;
static constexpr uint32_t BIT_A(int tube) { return 1u << (tube < 4 ? 12 + tube : 16 + (tube - 4)); }  // tube 0..5

static inline void IRAM_ATTR gpioSet(int pin) { REG_WRITE(GPIO_OUT_W1TS_REG, 1u << pin); }
static inline void IRAM_ATTR gpioClr(int pin) { REG_WRITE(GPIO_OUT_W1TC_REG, 1u << pin); }

// Shift 24 bits MSB first (bit 23 first, it travels to U303.QH), then latch.
static void IRAM_ATTR shiftOut24(uint32_t w) {
  for (int i = 23; i >= 0; --i) {
    if (w & (1u << i)) gpioSet(PIN_SER); else gpioClr(PIN_SER);
    gpioSet(PIN_SRCLK);
    gpioClr(PIN_SRCLK);
  }
  gpioSet(PIN_RCLK);
  gpioClr(PIN_RCLK);
}

static void IRAM_ATTR onMuxTick() {
  static int tube = 0, tick = 0;
  if (tick == 0) {
    shiftOut24(0);                                               // blank: anode and cathodes off
  } else if (tick == BLANK_TICKS) {
    uint32_t w = 0;
    if (displayOn) {
      uint8_t d = dispDigit[tube];
      if (d <= 9) w |= BIT_K(d) | BIT_A(tube);
      if (dispDpL[tube]) w |= BIT_DL | BIT_A(tube);
      if (dispDpR[tube]) w |= BIT_DR | BIT_A(tube);
    }
    shiftOut24(w);
  } else if (tick == BLANK_TICKS + brightness) {
    shiftOut24(0);                                               // end of the lit part (dimming)
  }
  if (++tick >= SLOT_TICKS) {
    tick = 0;
    tube = (tube + 1) % 6;
  }
}

// ----------------------------------------------------------------------------- helpers
static void showNumber(int hh, int mm, int ss) {
  int v[6] = {hh / 10, hh % 10, mm / 10, mm % 10, ss / 10, ss % 10};
  for (int i = 0; i < 6; ++i) dispDigit[i] = v[i];
}

static void setSeparators(bool on) {
  for (int i = 0; i < 6; ++i) dispDpL[i] = dispDpR[i] = false;
  if (SEPARATOR_RIGHT_COMMAS) {
    dispDpR[1] = dispDpR[3] = on;
  } else {
    dispDpL[2] = dispDpL[4] = on;
  }
}

static float readVin() {
  return analogReadMilliVolts(PIN_VIN_SNS) * VIN_DIVIDER / 1000.0f;
}

// Enable the boost only with enough input voltage (PD 9 V or the terminal), drop it again below 6.5 V.
static void updateHV() {
  static bool hvOn = false;
  float vin = readVin();
  if (!hvOn && vin > VIN_HV_ON) hvOn = true;
  if (hvOn && vin < VIN_HV_OFF) hvOn = false;
  digitalWrite(PIN_HV_OFF, hvOn ? LOW : HIGH);
}

static void setHV(bool on) {
  digitalWrite(PIN_HV_OFF, on ? LOW : HIGH);
}

// Anti cathode poisoning: run every digit through all tubes ("slot machine").
static void cathodeExercise(int rounds) {
  setSeparators(false);
  for (int r = 0; r < rounds; ++r)
    for (int d = 0; d < 10; ++d) {
      for (int i = 0; i < 6; ++i) dispDigit[i] = (d + i) % 10;
      delay(60);
    }
}

static bool timeValid() {
  return time(nullptr) > 1700000000;                             // after Nov 2023 -> SNTP has answered
}

// ----------------------------------------------------------------------------- setup / loop
static Preferences prefs;
static char tzBuf[64];
static WiFiManager wm;
static WiFiManagerParameter *tzParam;

void setup() {
  // outputs off and HV off before anything else (the pull-ups already hold them there)
  pinMode(PIN_HV_OFF, OUTPUT);
  setHV(false);
  pinMode(PIN_OE_N, OUTPUT);
  digitalWrite(PIN_OE_N, HIGH);
  for (int p : {PIN_SER, PIN_SRCLK, PIN_RCLK}) {
    pinMode(p, OUTPUT);
    digitalWrite(p, LOW);
  }
  pinMode(PIN_BOOT, INPUT_PULLUP);
  Serial.begin(115200);
  shiftOut24(0);
  digitalWrite(PIN_OE_N, LOW);

  muxTimer = timerBegin(1000000);                                // 1 MHz timer clock
  timerAttachInterrupt(muxTimer, &onMuxTick);
  timerAlarm(muxTimer, 100, true, 0);                            // 100 us tick
  pinMode(PIN_PD_OK_N, INPUT_PULLUP);                            // CH221K PG is open drain, no pull-up on the board
  analogSetPinAttenuation(PIN_VIN_SNS, ADC_11db);
  updateHV();

  // BOOT held for 5 s at power-up: forget WiFi + settings
  uint32_t t0 = millis();
  while (digitalRead(PIN_BOOT) == LOW) {
    showNumber(0, 0, (millis() - t0) / 1000);
    if (millis() - t0 > 5000) {
      wm.resetSettings();
      prefs.begin("nixi", false);
      prefs.clear();
      prefs.end();
      break;
    }
    delay(20);
  }

  prefs.begin("nixi", false);
  String tz = prefs.getString("tz", DEFAULT_TZ);
  strlcpy(tzBuf, tz.c_str(), sizeof(tzBuf));

  // WiFi: stored credentials, or a captive portal "NixiClock-Setup" (tubes cycle while it is open)
  tzParam = new WiFiManagerParameter("tz", "POSIX time zone (e.g. CET-1CEST,M3.5.0,M10.5.0/3)", tzBuf,
                                     sizeof(tzBuf) - 1);
  wm.addParameter(tzParam);
  wm.setConfigPortalBlocking(false);
  wm.setSaveParamsCallback([]() {
    strlcpy(tzBuf, tzParam->getValue(), sizeof(tzBuf));
    prefs.putString("tz", tzBuf);
    setenv("TZ", tzBuf, 1);
    tzset();
  });
  wm.autoConnect("NixiClock-Setup");

  setenv("TZ", tzBuf, 1);
  tzset();
  sntp_set_sync_interval(60 * 60 * 1000);                        // re-sync every hour
  configTzTime(tzBuf, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  WiFi.setSleep(true);                                           // modem sleep between beacons
  cathodeExercise(2);
}

void loop() {
  static uint32_t lastExercise = 0;
  wm.process();                                                  // serves the setup portal while it is open
  updateHV();

  if (!timeValid()) {                                            // no time yet: slow digit cycle
    static uint32_t last = 0;
    if (millis() - last > 300) {
      last = millis();
      for (int i = 0; i < 6; ++i) dispDigit[i] = (dispDigit[i] + 1) % 10;
    }
    delay(10);
    return;
  }

  struct timeval tv;
  gettimeofday(&tv, nullptr);
  struct tm now;
  localtime_r(&tv.tv_sec, &now);

  bool night = (NIGHT_FROM > NIGHT_TO) ? (now.tm_hour >= NIGHT_FROM || now.tm_hour < NIGHT_TO)
                                       : (now.tm_hour >= NIGHT_FROM && now.tm_hour < NIGHT_TO);
  brightness = night ? BRIGHT_NIGHT : BRIGHT_DAY;

  // every 10 minutes (on minute x0, second 30) exercise all cathodes for ~1 s; longer at 03:00
  if (now.tm_sec == 30 && now.tm_min % 10 == 0 && millis() - lastExercise > 60000) {
    lastExercise = millis();
    cathodeExercise(now.tm_hour == 3 && now.tm_min == 0 ? 60 : 2);
    return;
  }

  showNumber(now.tm_hour, now.tm_min, now.tm_sec);
  setSeparators(tv.tv_usec < 500000);                            // commas blink at 1 Hz
  delay(5);
}
