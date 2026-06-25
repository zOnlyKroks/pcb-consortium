#include <Arduino.h>
#include <cstring>

#include "BluetoothSerial.h"

#include "driver/i2s_std.h"
#include "freertos/ringbuf.h"

#include "esp_system.h"
#include "esp_chip_info.h"
#include "nvs_flash.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp_a2dp_api.h"
#include "esp_avrc_api.h"

#include "driver/i2c_master.h"
#include "../DSP/BoxV3_IC_1.h"

// ================= PINS =================
#define SDA_PIN 14
#define SCL_PIN 26

#define I2S_BCLK 13
#define I2S_LRCLK 23
#define I2S_DOUT 25

#define MODE_PIN 19
#define DSP_IN_SELECT 18
#define AMP_MUTE_PIN 4  // PAM8620TR mute pin (LOW = mute, HIGH = unmute)

// ================= GLOBALS =================
RingbufHandle_t audio_rb;

i2c_master_dev_handle_t adau_handle;
i2s_chan_handle_t tx_handle;
i2c_master_bus_handle_t i2c_bus;

int current_mode = 0;

// ================= AUDIO CALLBACK =================
static uint32_t audio_byte_count = 0;
void audio_data_callback(const uint8_t *data, uint32_t len)
{
    if (!audio_rb) return;
    xRingbufferSend(audio_rb, data, len, 0);

    // Debug: print every ~100KB of audio received
    audio_byte_count += len;
    if (audio_byte_count > 100000) {
        Serial.printf("Audio data flowing: %d bytes\n", audio_byte_count);
        audio_byte_count = 0;
    }
}

// ================= BT CALLBACK =================
void bt_app_a2d_cb(esp_a2d_cb_event_t event, esp_a2d_cb_param_t *param)
{
    Serial.printf("A2DP Event: %d\n", event);

    switch (event) {
        case ESP_A2D_CONNECTION_STATE_EVT:
            Serial.printf("  Connection state: %d\n", param->conn_stat.state);
            if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_CONNECTED) {
                Serial.println("  -> A2DP Connected!");
            } else if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_DISCONNECTED) {
                Serial.println("  -> A2DP Disconnected");
                digitalWrite(AMP_MUTE_PIN, LOW);
            } else if (param->conn_stat.state == ESP_A2D_CONNECTION_STATE_CONNECTING) {
                Serial.println("  -> A2DP Connecting...");
            }
            break;

        case ESP_A2D_AUDIO_STATE_EVT:
            Serial.printf("  Audio state: %d\n", param->audio_stat.state);
            if (param->audio_stat.state == ESP_A2D_AUDIO_STATE_STARTED) {
                Serial.println("  -> Audio Started");
                // Force BT mode when audio starts (select I2S input on DSP)
                digitalWrite(DSP_IN_SELECT, LOW);
                Serial.println("  -> DSP set to I2S input");
                delay(50);
                digitalWrite(AMP_MUTE_PIN, HIGH);
                Serial.println("  -> Amp unmuted");
            } else if (param->audio_stat.state == ESP_A2D_AUDIO_STATE_STOPPED) {
                Serial.println("  -> Audio Stopped - Muting");
                digitalWrite(AMP_MUTE_PIN, LOW);
            } else if (param->audio_stat.state == ESP_A2D_AUDIO_STATE_REMOTE_SUSPEND) {
                Serial.println("  -> Audio Suspended");
            }
            break;

        case ESP_A2D_AUDIO_CFG_EVT:
            Serial.println("  -> Audio Config received");
            Serial.printf("     Codec: %d\n", param->audio_cfg.mcc.type);
            break;

        case ESP_A2D_PROF_STATE_EVT:
            Serial.printf("  -> Profile state: %d\n", param->a2d_prof_stat.init_state);
            break;

        default:
            break;
    }
}

// ================= AVRCP CALLBACK =================
void bt_app_avrc_cb(esp_avrc_ct_cb_event_t event, esp_avrc_ct_cb_param_t *param)
{
    Serial.printf("AVRC Event: %d\n", event);

    switch (event) {
        case ESP_AVRC_CT_CONNECTION_STATE_EVT:
            Serial.printf("  AVRC connection: %d\n", param->conn_stat.connected);
            break;
        case ESP_AVRC_CT_PASSTHROUGH_RSP_EVT:
            Serial.printf("  AVRC passthrough response\n");
            break;
        default:
            break;
    }
}

// ================= I2S TASK =================
void i2s_task(void *arg)
{
    size_t item_size;
    uint8_t *item;

    while (1)
    {
        item = (uint8_t *)xRingbufferReceive(audio_rb, &item_size, portMAX_DELAY);

        if (item)
        {
            size_t written;
            i2s_channel_write(tx_handle, item, item_size, &written, portMAX_DELAY);
            vRingbufferReturnItem(audio_rb, item);
        }
    }
}

// ================= ADAU WRITE =================
void SigmaWriteRegisterBlock(uint8_t devAddr,
                             uint16_t regAddr,
                             uint16_t length,
                             uint8_t *data)
{
    uint8_t *buf = (uint8_t*)malloc(length + 2);
    if (!buf) return;

    buf[0] = regAddr >> 8;
    buf[1] = regAddr & 0xFF;
    memcpy(buf + 2, data, length);

    i2c_master_transmit(
        adau_handle,
        buf,
        length + 2,
        pdMS_TO_TICKS(50)
    );

    free(buf);
}

// ================= BT INIT =================
bool BT_start()
{
    Serial.println("BT init");

    // btStart() should work now that BluetoothSerial.h is included
    if (!btStart()) {
        Serial.println("btStart() FAILED!");
        return false;
    }
    Serial.println("btStart() OK");

    esp_err_t err;

    // Initialize Bluedroid stack
    err = esp_bluedroid_init();
    if (err != ESP_OK) {
        Serial.printf("Bluedroid init FAIL: %d\n", err);
        return false;
    }
    Serial.println("Bluedroid init OK");

    err = esp_bluedroid_enable();
    if (err != ESP_OK) {
        Serial.printf("Bluedroid enable FAIL: %d\n", err);
        return false;
    }
    Serial.println("Bluedroid enable OK");

    // Set device name
    esp_bt_gap_set_device_name("BoxV3");

    // Make device discoverable and connectable
    esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);

    // Initialize A2DP sink
    esp_a2d_register_callback(bt_app_a2d_cb);
    esp_a2d_sink_register_data_callback(audio_data_callback);
    err = esp_a2d_sink_init();
    if (err != ESP_OK) {
        Serial.printf("A2DP sink init FAIL: %d\n", err);
        return false;
    }
    Serial.println("A2DP sink init OK");

    // Initialize AVRCP controller (for media control)
    esp_avrc_ct_register_callback(bt_app_avrc_cb);
    err = esp_avrc_ct_init();
    if (err != ESP_OK) {
        Serial.printf("AVRC init FAIL: %d\n", err);
        // Continue anyway, AVRCP is optional
    } else {
        Serial.println("AVRC init OK");
    }

    Serial.println("BT READY - Device visible as 'BoxV3'");
    return true;
}

// ================= MODE =================
void BT_init()
{
    Serial.println("Switched to BT mode");
    digitalWrite(DSP_IN_SELECT, 0);  // Select I2S input on DSP
    // Amp will be unmuted by A2DP callback when audio starts
}

void AUX_init()
{
    Serial.println("Switched to AUX mode");
    digitalWrite(DSP_IN_SELECT, 1);  // Select AUX input on DSP
    // Unmute amp for AUX mode (no A2DP callback in this mode)
    digitalWrite(AMP_MUTE_PIN, HIGH);
}

// ================= SETUP =================
void setup()
{
    Serial.begin(115200);
    delay(2000);

    Serial.println("\nBOOT");

    // Print IDF version
    Serial.printf("IDF Version: %s\n", esp_get_idf_version());

    // ================= NVS INIT (required for BT) =================
    Serial.println("NVS init...");
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        Serial.println("NVS erase/reinit");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        Serial.printf("NVS init FAIL: %d\n", ret);
        while(1) delay(1000);
    }
    Serial.println("NVS OK");

    pinMode(MODE_PIN, INPUT);
    pinMode(DSP_IN_SELECT, OUTPUT);
    pinMode(AMP_MUTE_PIN, OUTPUT);

    // Start muted until audio is ready
    digitalWrite(AMP_MUTE_PIN, LOW);
    digitalWrite(DSP_IN_SELECT, 1);

    // ================= BT MUST BE FIRST =================
    if (!BT_start()) {
        Serial.println("BT NOT AVAILABLE (continuing)");
    }

    // ================= I2C =================
    Serial.println("I2C init");

    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.i2c_port = I2C_NUM_0;
    bus_cfg.sda_io_num = (gpio_num_t)SDA_PIN;
    bus_cfg.scl_io_num = (gpio_num_t)SCL_PIN;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;

    if (i2c_new_master_bus(&bus_cfg, &i2c_bus) != ESP_OK) {
        Serial.println("I2C FAIL");
        while (1) delay(1000);
    }

    i2c_device_config_t adau_cfg = {};
    adau_cfg.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    adau_cfg.device_address = 0x34;
    adau_cfg.scl_speed_hz = 100000;

    if (i2c_master_bus_add_device(i2c_bus, &adau_cfg, &adau_handle) != ESP_OK) {
        Serial.println("ADAU FAIL");
        while (1) delay(1000);
    }

    Serial.println("ADAU init...");
    default_download_IC_1();
    Serial.println("ADAU done");

    // ================= I2S =================
    Serial.println("I2S init");

    i2s_chan_config_t chan_cfg = {
        .id = I2S_NUM_0,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 8,
        .dma_frame_num = 240,
        .auto_clear = true
    };

    i2s_new_channel(&chan_cfg, &tx_handle, NULL);

    // A2DP audio is 44100Hz 16-bit stereo
    i2s_std_config_t cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(44100),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(
            I2S_DATA_BIT_WIDTH_16BIT,
            I2S_SLOT_MODE_STEREO
        ),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)I2S_BCLK,
            .ws   = (gpio_num_t)I2S_LRCLK,
            .dout = (gpio_num_t)I2S_DOUT,
            .din  = I2S_GPIO_UNUSED
        }
    };

    i2s_channel_init_std_mode(tx_handle, &cfg);
    i2s_channel_enable(tx_handle);

    // ================= RINGBUFFER =================
    // Larger buffer for smooth audio playback
    audio_rb = xRingbufferCreate(32 * 1024, RINGBUF_TYPE_BYTEBUF);

    xTaskCreate(i2s_task, "i2s_task", 4096, NULL, 5, NULL);

    // ================= MODE =================
    current_mode = digitalRead(MODE_PIN);
    Serial.printf("MODE_PIN state: %d\n", current_mode);

    if (current_mode) BT_init();
    else AUX_init();

    Serial.println("READY");
}

// ================= LOOP =================
void loop()
{
    delay(200);

    int m = digitalRead(MODE_PIN);

    if (m != current_mode)
    {
        delay(30);
        if (digitalRead(MODE_PIN) == m)
        {
            current_mode = m;

            if (current_mode) BT_init();
            else AUX_init();
        }
    }
}
