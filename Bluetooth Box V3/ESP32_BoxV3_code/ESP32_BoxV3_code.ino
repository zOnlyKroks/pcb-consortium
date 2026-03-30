#include "driver/i2s_std.h"

void setup() {

  //I²S setup
  i2s_chan_handle_t tx_handle;

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

}

void loop() {
  // put your main code here, to run repeatedly:

}
