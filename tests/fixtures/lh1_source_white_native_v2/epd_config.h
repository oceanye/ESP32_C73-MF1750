#pragma once
#include "Arduino.h"
// Only main's geometry/GPIO label declarations. Actual hardware uses src/epd_config.h.
constexpr uint16_t EPD_WIDTH=1024,EPD_HEIGHT=600;
constexpr size_t EPD_FRAME_BYTES=307200,EPD_CONTROLLER_FRAME_BYTES=153600;
constexpr int EPD_CS1_SOURCE_HALF=0,EPD_CS2_SOURCE_HALF=1;
constexpr bool EPD_CS1_FLIP_X=false,EPD_CS1_FLIP_Y=false,EPD_CS1_NIBBLE_SWAP=false;
constexpr bool EPD_CS2_FLIP_X=false,EPD_CS2_FLIP_Y=false,EPD_CS2_NIBBLE_SWAP=false;
constexpr int EPD_PIN_RST=5,EPD_PIN_CS=7,EPD_PIN_CS2=10;
constexpr const char *WIFI_STA_SSID="",*WIFI_STA_PASSWORD="",*WIFI_AP_SSID="",*WIFI_AP_PASSWORD="";
constexpr int EPD_PIN_BUSY=4,EPD_PIN_SCK=6,EPD_PIN_DC=8,EPD_PIN_MOSI=9,EPD_PIN_SWC=-1; constexpr int EPD_BUSY_IDLE_LEVEL=1; constexpr unsigned EPD_SPI_DEFAULT_HZ=1000000;
