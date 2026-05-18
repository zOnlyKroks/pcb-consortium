#include "driver/i2s_std.h"
#include "freertos/ringbuf.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_bt_device.h"
#include "esp_gap_bt_api.h"
#include "esp_a2dp_api.h"
#include "driver/i2c_master.h"
#include <cstring>

#include "../DSP/BoxV3-DSP_IC_1.h"

#define MODE_PIN 8
#define SCL 1
#define SDA 2
#define I2S_BCLK 4
#define I2S_LRCLK 5
#define BT_I2S_DATA 6
#define DSP_IN_SELECT 7
#define AMP_MUTE 48

#define DEBOUNCE 20

RingbufHandle_t audio_rb;

int current_mode;

i2c_master_dev_handle_t adau_handle;
i2s_chan_handle_t tx_handle;

void audio_data_callback(const uint8_t *data, uint32_t len)
{
    if (audio_rb) {
        xRingbufferSend(audio_rb, data, len, 0);
    }
}

void bt_app_a2d_cb(esp_a2d_cb_event_t event, esp_a2d_cb_param_t *param)
{
    switch (event) {
        case ESP_A2D_CONNECTION_STATE_EVT:
            // connected / disconnected
            break;

        case ESP_A2D_AUDIO_STATE_EVT:
            // started / stopped streaming
            break;

        default:
            break;
    }
}

void i2s_task(void *arg)
{   
  size_t item_size;
  uint8_t* item;
  while (1) {
    item = (uint8_t *)xRingbufferReceive(audio_rb, &item_size, portMAX_DELAY);

    if (item) {
        size_t written;
        i2s_channel_write(tx_handle, item, item_size, &written, portMAX_DELAY);

        vRingbufferReturnItem(audio_rb, item);
    }
  }
}

void SigmaWriteRegisterBlock(uint8_t devAddr, uint16_t regAddr, uint16_t length, uint8_t *data) {
  uint8_t buf[2+length];
  buf[0] = (uint8_t)(regAddr >> 8);
  buf[1] = (uint8_t)(regAddr & 0xff);
  std::memcpy(buf+2, data, length);

  i2c_master_transmit(adau_handle, buf, length+2, -1);
}

void i2c_send(i2c_master_dev_handle_t device, uint8_t reg_addr, uint8_t data) {
  uint8_t buf[] = {reg_addr, data};
  i2c_master_transmit(device, buf, 2, -1);
}

void BT_init() {
  esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
  digitalWrite(DSP_IN_SELECT, 0);
}

void AUX_init() {
  esp_bt_gap_set_scan_mode(ESP_BT_NON_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);
  digitalWrite(DSP_IN_SELECT, 1);
}

void setup() {
  //I²C setup
  i2c_master_bus_config_t i2c_bus_config = {
    .i2c_port = 1,
    .sda_io_num = GPIO_NUM_2,
    .scl_io_num = GPIO_NUM_1,
    .clk_source = I2C_CLK_SRC_DEFAULT,
  };

  i2c_master_bus_handle_t i2c_bus_handle;
  i2c_new_master_bus(&i2c_bus_config, &i2c_bus_handle);

  i2c_device_config_t adau_device_config = {
    .dev_addr_length = I2C_ADDR_BIT_LEN_7,
    .device_address = 0x34, //0x34; maybe try 0x68 if not working
    .scl_speed_hz = 100000, //100 khz
  };

//  i2c_master_dev_handle_t adau_handle; was moved to global scope
  i2c_master_bus_add_device(i2c_bus_handle, &adau_device_config, &adau_handle);

  i2c_device_config_t aux_device_config = {
    .dev_addr_length = I2C_ADDR_BIT_LEN_7,
    .device_address = 0x4a, //0x4a; maybe try 0x94 if not working
    .scl_speed_hz = 100000, //100 khz
  };

  i2c_master_dev_handle_t aux_handle;
  i2c_master_bus_add_device(i2c_bus_handle, &aux_device_config, &aux_handle);


  //PCM1862 Setup
  //maybe register 0x20 clock selection
  //maybe register 0x70 sleep modes
  //status registers in high page 0 registers
  
  //ADAU Setup
  default_download_IC_1();

  //I²S setup
//  i2s_chan_handle_t tx_handle; was moved to global scope

  i2s_chan_config_t chan_cfg{
    .id = I2S_NUM_0,
    .role = I2S_ROLE_MASTER,
    .dma_desc_num = 8,
    .dma_frame_num = 64,
    .auto_clear = true
  };

  i2s_new_channel(&chan_cfg, &tx_handle, NULL);

  i2s_std_config_t cfg = {
    .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(48000),
    .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(
        I2S_DATA_BIT_WIDTH_16BIT,
        I2S_SLOT_MODE_MONO
    ),
    .gpio_cfg = {
        .mclk = I2S_GPIO_UNUSED,
        .bclk = GPIO_NUM_4,
        .ws = GPIO_NUM_5,
        .dout = GPIO_NUM_6,
        .din = I2S_GPIO_UNUSED,
    },
  };

  i2s_channel_init_std_mode(tx_handle, &cfg);
  i2s_channel_enable(tx_handle);

  //Ringbuffer setup
  audio_rb = xRingbufferCreate(8 * 1024, RINGBUF_TYPE_BYTEBUF); //currently 8KB buffer size. If dropouts occur increase this.
  xTaskCreate(i2s_task, "i2s_task", 4096, NULL, 5, NULL);

  //Bluetooth setup
  esp_bt_controller_mem_release(ESP_BT_MODE_BLE);

  esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  esp_bt_controller_init(&bt_cfg);
  esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT);

  esp_bluedroid_init();
  esp_bluedroid_enable();

  esp_bt_dev_set_device_name("BoxV3");

  esp_a2d_sink_register_data_callback(audio_data_callback); //for audio
  esp_a2d_register_callback(bt_app_a2d_cb); //for events

  esp_a2d_sink_init();

  //general
  pinMode(MODE_PIN, INPUT);
  pinMode(DSP_IN_SELECT, OUTPUT);
  pinMode(AMP_MUTE, OUTPUT);

  current_mode = digitalRead(MODE_PIN);
  if (current_mode) {
    BT_init();
  } else {
    AUX_init();
  }
}

void loop() {
  //mode switch detect
  if (current_mode != digitalRead(MODE_PIN)) {
    delay(DEBOUNCE);
    if (current_mode != digitalRead(MODE_PIN)) {
      current_mode = !current_mode;
      if (current_mode) {
        BT_init();
      } else {
        AUX_init();
      }
    }
  }

  delay(100);
}
