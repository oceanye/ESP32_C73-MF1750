#ifndef IC_DRIVE_CODE_H
#define IC_DRIVE_CODE_H

#include "./SYSTEM/sys/sys.h"

#define COLOR_NULL    0
#define COLOR_BLACK   1
#define COLOR_WHITE   2
#define COLOR_RED     3
#define COLOR_YELLOW  4
#define COLOR_PIC     5
#define COLOR_A       6
#define COLOR_B       7


void IC_display_image(uint8_t edp_type);
void IC_display_color(uint8_t edp_type,uint8_t color);
void IC_display_tiaowen(uint8_t edp_type,uint8_t color);
	


void IC_79656_initialCode(uint16_t epd_x,uint16_t epd_y);
void IC_79656_display_image(uint16_t epd_x,uint16_t epd_y);
void IC_79656_EPD_sleep(void);
void IC_79656_EPD_refresh(void);
void IC_79656_EPD_Check_Busy(void);
void IC_79656_display_single_color(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);
void IC_79656_display_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);

void IC_SSD1683_EPD_Check_Busy(void);
void IC_SSD1683_initialCode(uint16_t epd_x,uint16_t epd_y);
void IC_SSD1683_EPD_sleep(void);
void IC_SSD1683_EPD_refresh(void);
void IC_SSD1683_display_image(uint16_t epd_x,uint16_t epd_y);
void IC_SSD1683_display_single_color(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);
void IC_SSD1683_display_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);

void IC_JD79667_initialCode(uint16_t epd_x,uint16_t epd_y);
void IC_JD79667_display_image(uint16_t epd_x,uint16_t epd_y);
void IC_JD79667_display_single_color(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);
void IC_JD79667_display_single_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);

void IC_SSD1680_BW_initialCode(uint16_t epd_x,uint16_t epd_y);
void IC_SSD1680_BW_display_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type);

void IC_79650_initialCode(uint16_t epd_x,uint16_t epd_y);

#endif



