#pragma once

#include <Arduino.h>

// User-confirmed full panel resolution. MF-17506-M009F-T contains two
// SPD1657/E2802 controllers, each driving one 512 x 600 half.
static constexpr uint16_t EPD_WIDTH = 1024;
static constexpr uint16_t EPD_HEIGHT = 600;
static constexpr size_t EPD_FRAME_BYTES = (static_cast<size_t>(EPD_WIDTH) * EPD_HEIGHT) / 2;
static constexpr uint16_t EPD_CONTROLLER_WIDTH = EPD_WIDTH / 2;
static constexpr size_t EPD_CONTROLLER_FRAME_BYTES =
    (static_cast<size_t>(EPD_CONTROLLER_WIDTH) * EPD_HEIGHT) / 2;
static_assert((EPD_WIDTH % 4) == 0 && (EPD_HEIGHT > 0),
              "EPD frame and two half-row byte layout require width divisible by 4");

// ESP32-S3 SPI wiring to the MF-1750 Rev A1 driver board.
// Keep all signals at 3.3 V. Do not drive e-paper logic with 5 V GPIO.
static constexpr int EPD_PIN_BUSY = 4;
static constexpr int EPD_PIN_RST = 5;
static constexpr int EPD_PIN_DC = 6; // Unused in 3-wire mode; kept available for 4-wire experiments.
static constexpr int EPD_PIN_CS = 7;
// R16 independent-CS diagnostic configuration. Hardware precondition:
// R15 removed, R16 fitted as 0 ohm, and J2-9 connected to GPIO10.
// Never populate R15 and R16 at the same time.
static constexpr int EPD_PIN_CS2 = 10;
static constexpr int EPD_PIN_SCK = 12;
static constexpr int EPD_PIN_MOSI = 11;
static constexpr int EPD_PIN_BS = -1; // Rev A1 fixes BS0/BS1 low with R12/R13 for 4-wire SPI.
static constexpr int EPD_PIN_SWC = -1; // Optional panel VDD switch control. Set to -1 if not connected.
// Keep 4-wire mode for the current DESPI-C73 wiring. In 3-wire 9-bit mode the
// panel did not enter a real refresh cycle: BUSY stayed idle through PON/DRF.
static constexpr bool EPD_USE_3WIRE_9BIT = false;
static constexpr int EPD_BUSY_IDLE_LEVEL = HIGH; // Sample code waits until BUSYN becomes HIGH.
static constexpr uint32_t EPD_SPI_DEFAULT_HZ = 1000000;
static constexpr uint32_t EPD_SPI_DIAGNOSTIC_HZ = 100000;

// Canonical application-frame mapping. Applications always provide a
// 1024x600 row-major frame with x=0/y=0 at logical top-left, even x in the
// high nibble and odd x in the low nibble. The driver alone owns any physical
// controller routing/orientation compensation.
// 2026-08-04 global bars verified CS1=physical left, CS2=physical right and
// no horizontal flip. MAP_ORIENT_V1 will close the remaining vertical check.
static constexpr uint8_t EPD_CS1_SOURCE_HALF = 0; // 0=logical left, 1=logical right
static constexpr bool EPD_CS1_FLIP_X = false;
static constexpr bool EPD_CS1_FLIP_Y = false;
static constexpr bool EPD_CS1_NIBBLE_SWAP = false;
static constexpr uint8_t EPD_CS2_SOURCE_HALF = 1;
static constexpr bool EPD_CS2_FLIP_X = false;
static constexpr bool EPD_CS2_FLIP_Y = false;
static constexpr bool EPD_CS2_NIBBLE_SWAP = false;

static constexpr uint8_t EPD_COLOR_BLACK = 0x0;
static constexpr uint8_t EPD_COLOR_WHITE = 0x1;
static constexpr uint8_t EPD_COLOR_YELLOW = 0x2;
static constexpr uint8_t EPD_COLOR_RED = 0x3;
static constexpr uint8_t EPD_COLOR_BLUE = 0x5;
static constexpr uint8_t EPD_COLOR_GREEN = 0x6;

// Wi-Fi credentials are deliberately local-only and excluded from Git.
// Copy wifi_secrets.example.h to wifi_secrets.h and edit it for the device.
#if __has_include("wifi_secrets.h")
#include "wifi_secrets.h"
#else
static constexpr const char *WIFI_STA_SSID = "";
static constexpr const char *WIFI_STA_PASSWORD = "";
static constexpr const char *WIFI_AP_SSID = "ESP32-S3-EINK";
static constexpr const char *WIFI_AP_PASSWORD = "change-me";
#endif
