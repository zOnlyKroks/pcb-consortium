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
#include <WebServer.h>
#include <ArduinoOTA.h>
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
static constexpr bool SEPARATOR_RIGHT_COMMAS = true;             // true: right commas of tubes 2+4, false: left of 3+5
static const char *OTA_PASSWORD = "nixiclock";                   // ArduinoOTA password (LAN only)
static constexpr uint32_t SYNC_STALE_MS = 24UL * 3600 * 1000;    // no NTP answer for 24 h -> commas stop blinking
static constexpr uint32_t PORTAL_RETRY_MS = 3UL * 60 * 1000;     // setup AP open this long with saved WiFi -> reboot

// ----------------------------------------------------------------------------- display state (ISR side)
static constexpr int SLOT_TICKS = 20;                            // 20 x 100 us = 2 ms per tube
static constexpr int BLANK_TICKS = 2;                            // first 200 us of a slot: everything off
static constexpr int MAX_BRIGHT = SLOT_TICKS - BLANK_TICKS;      // lit ticks per slot at full brightness

// user settings, editable on the status page, stored in NVS
static int nightFrom = 23, nightTo = 7;                          // dimmed between these hours
static int brightDay = 16, brightNight = 4;                      // on-time in 100 us ticks (1..MAX_BRIGHT)
static volatile uint8_t dispDigit[6] = {0, 0, 0, 0, 0, 0};       // 0..9, 10 = blank
static volatile bool dispDpL[6], dispDpR[6];
static volatile uint8_t brightness = 16;                         // ticks the tube is lit per slot
static volatile bool displayOn = true;

// Hardware test mode (status page /test): the 24-bit word is driven as-is, but the anode bits stay time-multiplexed
// (one anode per slot) so no tube ever sees more than its normal duty cycle.
static constexpr uint32_t TEST_TIMEOUT_MS = 10UL * 60 * 1000;    // test mode ends by itself
static volatile bool testMode = false;
static volatile uint32_t testWord = 0;
static volatile int hvMode = 0;                                  // 0 auto, 1 forced off, 2 forced on (test mode only)
static volatile bool oeOff = false;                              // test mode: OE_N high (shift register outputs Hi-Z)
static uint32_t testSince = 0;

static hw_timer_t *muxTimer = nullptr;

// bit positions in the 24-bit word (bit 0 = U301.QA ... bit 23 = U303.QH)
static constexpr uint32_t BIT_K(int d) { return 1u << d; }                            // K0..K9 = bits 0..9
static constexpr uint32_t BIT_DL = 1u << 10, BIT_DR = 1u << 11;
static constexpr uint32_t BIT_A(int tube) { return 1u << (tube < 4 ? 12 + tube : 16 + (tube - 4)); }  // tube 0..5

static constexpr uint32_t ANODE_MASK = (0xFu << 12) | (0x3u << 16);                   // A1..A6

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
  // Test mode with no cathode/comma bit selected: no tube current can flow, so the selected anodes are held on
  // continuously (no blanking, no multiplexing) and can be measured as DC.
  const uint32_t t = testWord;
  if (displayOn && testMode && (t & ~ANODE_MASK) == 0) {
    if (tick == 0) shiftOut24(t);
  } else if (tick == 0) {
    shiftOut24(0);                                               // blank: anode and cathodes off
  } else if (tick == BLANK_TICKS) {
    uint32_t w = 0;
    if (displayOn && testMode) {
      w = t & ~ANODE_MASK;                                       // cathodes / commas as selected
      if (t & BIT_A(tube)) w |= BIT_A(tube);                     // this slot's anode only
    } else if (displayOn) {
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
  uint32_t sum = 0;
  for (int i = 0; i < 16; ++i) sum += analogReadMilliVolts(PIN_VIN_SNS);
  return (sum / 16.0f) * VIN_DIVIDER / 1000.0f;
}

// Enable the boost only with enough input voltage (PD 9 V or the terminal), drop it again below 6.5 V.
static void updateHV() {
  static bool hvOn = false;
  float vin = readVin();
  if (!hvOn && vin > VIN_HV_ON) hvOn = true;
  if (hvOn && vin < VIN_HV_OFF) hvOn = false;
  int m = testMode ? hvMode : 0;                                 // manual HV override only inside test mode
  bool on = m == 1 ? false : m == 2 ? true : hvOn;
  digitalWrite(PIN_HV_OFF, on ? LOW : HIGH);
}

static bool timeValid();

// NTP sync tracking (callback runs in the SNTP task)
static volatile uint32_t lastSyncMs = 0;
static volatile bool everSynced = false;
static bool syncStale() { return everSynced && millis() - lastSyncMs > SYNC_STALE_MS; }

// Repeat the IP + power status over serial every 2 s (USB CDC drops anything printed before the monitor opens).
static void serialStatus() {
  static uint32_t last = 0;
  if (millis() - last < 2000) return;
  last = millis();
  bool apMode = WiFi.getMode() & WIFI_AP;
  Serial.printf("[nixi] ip=%s%s  vin=%.2fV  pd_ok=%d  hv=%s  time=%s\n",
                WiFi.isConnected() ? WiFi.localIP().toString().c_str() : "(not connected)",
                apMode ? " (setup AP: 192.168.4.1)" : "", readVin(), digitalRead(PIN_PD_OK_N) == LOW,
                digitalRead(PIN_HV_OFF) == LOW ? "ON" : "OFF", timeValid() ? "ok" : "waiting");
}

// Anti cathode poisoning: run every digit through all tubes ("slot machine").
static void cathodeExercise(int rounds) {
  setSeparators(false);
  for (int r = 0; r < rounds; ++r)
    for (int d = 0; d < 10; ++d) {
      for (int i = 0; i < 6; ++i) dispDigit[i] = (d + i) % 10;
      updateHV();                                                // keep the HV supervision alive while blocking
      delay(60);
    }
}

static bool timeValid() {
  return time(nullptr) > 1700000000;                             // after Nov 2023 -> SNTP has answered
}

// ----------------------------------------------------------------------------- status page
static char tzBuf[64];
static WebServer web(80);
static bool webStarted = false;

static Preferences prefs;

static void saveSettings() {
  prefs.putInt("nf", nightFrom);
  prefs.putInt("nt", nightTo);
  prefs.putInt("bd", brightDay);
  prefs.putInt("bn", brightNight);
}

static void handleSet() {
  auto get = [&](const char *name, int lo, int hi, int &v) {
    if (web.hasArg(name)) v = constrain(web.arg(name).toInt(), lo, hi);
  };
  get("nf", 0, 23, nightFrom);
  get("nt", 0, 23, nightTo);
  get("bd", 1, MAX_BRIGHT, brightDay);
  get("bn", 1, MAX_BRIGHT, brightNight);
  saveSettings();
  web.sendHeader("Location", "/");
  web.send(303);
}

static const char *BIT_NAMES[18] = {"K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "KDL (left comma)",
                                    "KDR (right comma)", "A1 (tube 1)", "A2 (tube 2)", "A3 (tube 3)",
                                    "A4 (tube 4)", "A5 (tube 5)", "A6 (tube 6)"};

static void handleTest() {
  String h = F("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
               "<title>NixiClock test</title><style>body{font:16px sans-serif;margin:1.5em;max-width:28em}"
               "label{display:block;padding:.15em 0}button{margin:.3em .3em 0 0}.w{color:#c00}</style>"
               "<h2>Hardware test</h2><p class=w>HV is live when switched on. Test mode ends by itself after 10 min.</p>"
               "<form method=post action=/test>");
  h += String("<label><input type=checkbox name=tm") + (testMode ? " checked" : "") +
       "> Test mode (replaces the clock display)</label><h3>HV boost</h3>";
  const char *hvl[3] = {"Auto (VIN &gt; 7 V)", "Forced off", "Forced on"};
  for (int i = 0; i < 3; ++i)
    h += String("<label><input type=radio name=hv value=") + i + (hvMode == i ? " checked" : "") + "> " + hvl[i] + "</label>";
  h += String("<h3>74HC595 outputs</h3><label><input type=checkbox name=oe") + (oeOff ? " checked" : "") +
       "> Disable outputs (OE_N high)</label>";
  for (int i = 0; i < 18; ++i)
    h += String("<label><input type=checkbox name=b") + i + ((testWord >> i) & 1 ? " checked" : "") + "> " +
         BIT_NAMES[i] + "</label>";
  h += F("<button>Apply</button><button name=act value=off>All bits off</button>"
         "<button name=act value=cath>All cathodes</button><button name=act value=anodes>All anodes</button></form>"
         "<p><a href=/>Back to status</a>");
  web.send(200, "text/html", h);
}

static void handleTestPost() {
  String act = web.arg("act");
  uint32_t w = 0;
  if (act == "cath") w = 0xFFF;
  else if (act == "anodes") w = ANODE_MASK;
  else if (act != "off")
    for (int i = 0; i < 18; ++i)
      if (web.hasArg(String("b") + i)) w |= 1u << i;
  testWord = w;
  hvMode = constrain(web.arg("hv").toInt(), 0, 2);
  oeOff = web.hasArg("oe");
  testSince = millis();
  testMode = web.hasArg("tm");
  web.sendHeader("Location", "/test");
  web.send(303);
}

static void handleStatus() {
  char tbuf[32] = "waiting for NTP";
  if (timeValid()) {
    time_t t = time(nullptr);
    struct tm lt;
    localtime_r(&t, &lt);
    strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", &lt);
  }
  uint32_t up = millis() / 1000;
  bool hv = digitalRead(PIN_HV_OFF) == LOW;
  bool pd = digitalRead(PIN_PD_OK_N) == LOW;
  String h = F("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
               "<title>NixiClock</title>"
               "<style>body{font:16px sans-serif;margin:1.5em;max-width:28em}td{padding:.2em 1em .2em 0}"
               "input{width:4em}.on{color:#090}.off{color:#c00}</style><h2>NixiClock</h2><table>");
  auto row = [&](const char *k, const String &v, const char *cls = "") {
    h += "<tr><td>"; h += k; h += "<td class='"; h += cls; h += "'>"; h += v; h += "</tr>";
  };
  row("Time", tbuf);
  row("Time zone", tzBuf);
  row("VIN", String(readVin(), 2) + " V");
  row("PD 9 V OK", pd ? "yes" : "no", pd ? "on" : "off");
  row("HV (185 V)", hv ? "ON" : "OFF", hv ? "on" : "off");
  row("Brightness", String(brightness) + " / " + String(MAX_BRIGHT));
  row("Last NTP sync", everSynced ? String((millis() - lastSyncMs) / 60000) + " min ago" : String("never"),
      syncStale() ? "off" : "");
  row("WiFi", WiFi.SSID() + " (" + String(WiFi.RSSI()) + " dBm)");
  row("IP", WiFi.localIP().toString());
  row("Uptime", String(up / 3600) + "h " + String(up / 60 % 60) + "m " + String(up % 60) + "s");
  row("Free heap", String(ESP.getFreeHeap()) + " B");
  h += F("</table><h3>Settings</h3><form method=post action=/set><table>");
  auto field = [&](const char *label, const char *name, int v, int lo, int hi) {
    h += "<tr><td>"; h += label; h += "<td><input type=number name="; h += name; h += " value="; h += v;
    h += " min="; h += lo; h += " max="; h += hi; h += "></tr>";
  };
  field("Night from (hour)", "nf", nightFrom, 0, 23);
  field("Night to (hour)", "nt", nightTo, 0, 23);
  field("Day brightness", "bd", brightDay, 1, MAX_BRIGHT);
  field("Night brightness", "bn", brightNight, 1, MAX_BRIGHT);
  h += F("</table><p><button>Save</button></form><p><a href=/test>Hardware test</a>");
  web.send(200, "text/html", h);
}

// Start once WiFi is up and the setup portal (which owns port 80) is closed.
static void webLoop(bool portalActive) {
  if (!webStarted && WiFi.isConnected() && !portalActive) {
    web.on("/", handleStatus);
    web.on("/set", HTTP_POST, handleSet);
    web.on("/test", HTTP_GET, handleTest);
    web.on("/test", HTTP_POST, handleTestPost);
    web.begin();

    ArduinoOTA.setHostname("nixiclock");
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { displayOn = false; });             // dark tubes while flashing
    ArduinoOTA.onEnd([]() { displayOn = true; });
    ArduinoOTA.onError([](ota_error_t) { displayOn = true; });
    ArduinoOTA.begin();

    webStarted = true;
    Serial.println("[nixi] status page on http://" + WiFi.localIP().toString() + "/, OTA host nixiclock");
  }
  if (webStarted) {
    web.handleClient();
    ArduinoOTA.handle();
  }
}

// ----------------------------------------------------------------------------- setup / loop
static WiFiManager wm;
static WiFiManagerParameter *tzParam;

void setup() {
  // outputs off and HV off before anything else (the pull-ups already hold them there)
  pinMode(PIN_HV_OFF, OUTPUT);
  digitalWrite(PIN_HV_OFF, HIGH);
  pinMode(PIN_OE_N, OUTPUT);
  digitalWrite(PIN_OE_N, HIGH);
  for (int p : {PIN_SER, PIN_SRCLK, PIN_RCLK}) {
    pinMode(p, OUTPUT);
    digitalWrite(p, LOW);
  }
  pinMode(PIN_BOOT, INPUT_PULLUP);
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);                                      // never stall when no monitor is attached
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
  nightFrom = prefs.getInt("nf", nightFrom);
  nightTo = prefs.getInt("nt", nightTo);
  brightDay = constrain(prefs.getInt("bd", brightDay), 1, MAX_BRIGHT);
  brightNight = constrain(prefs.getInt("bn", brightNight), 1, MAX_BRIGHT);
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

  sntp_set_time_sync_notification_cb([](struct timeval *) {
    lastSyncMs = millis();
    everSynced = true;
  });
  sntp_set_sync_interval(60 * 60 * 1000);                        // re-sync every hour
  configTzTime(tzBuf, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  WiFi.setSleep(true);                                           // modem sleep between beacons
  cathodeExercise(2);
}

void loop() {
  static uint32_t lastExercise = 0;
  static uint32_t portalSince = 0;
  wm.process();                                                  // serves the setup portal while it is open
  updateHV();
  serialStatus();
  bool portal = wm.getConfigPortalActive();
  webLoop(portal);

  // Router slower than the clock after a power cut: the setup AP would stay open forever. With saved WiFi and
  // nobody connected to the AP, reboot after a while to try the saved network again.
  if (!portal) portalSince = 0;
  else if (!portalSince) portalSince = millis();
  else if (wm.getWiFiIsSaved() && millis() - portalSince > PORTAL_RETRY_MS && WiFi.softAPgetStationNum() == 0)
    ESP.restart();

  if (testMode && millis() - testSince > TEST_TIMEOUT_MS) testMode = false;
  digitalWrite(PIN_OE_N, (testMode && oeOff) ? HIGH : LOW);
  if (testMode) {                                              // hardware test: the ISR drives testWord
    delay(10);
    return;
  }

  if (!timeValid()) {                                          // no time yet: slow digit cycle
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

  bool night = (nightFrom > nightTo) ? (now.tm_hour >= nightFrom || now.tm_hour < nightTo)
                                     : (now.tm_hour >= nightFrom && now.tm_hour < nightTo);
  brightness = night ? brightNight : brightDay;

  // every 10 minutes (on minute x0, second 30) exercise all cathodes for ~1 s; longer at 03:00
  if (now.tm_sec == 30 && now.tm_min % 10 == 0 && millis() - lastExercise > 60000) {
    lastExercise = millis();
    cathodeExercise(now.tm_hour == 3 && now.tm_min == 0 ? 60 : 2);
    return;
  }

  showNumber(now.tm_hour, now.tm_min, now.tm_sec);
  setSeparators(syncStale() || tv.tv_usec < 500000);             // commas blink at 1 Hz; steady = no NTP for 24 h
  delay(5);
}
