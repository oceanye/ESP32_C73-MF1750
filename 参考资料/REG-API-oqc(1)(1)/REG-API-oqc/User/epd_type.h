#ifndef EPD_TYPE_H
#define EPD_TYPE_H

#include "LCDConfig.h"

#define MAX_EPD_NUM  20

#define JD79656_122X250          0
#define JD79656_122X250_X        128
#define JD79656_122X250_Y        250
#define JD79656_122X250_COLOR    W_B_R_Status

#define SSD1683_400X300          1
#define SSD1683_400X300_X        400
#define SSD1683_400X300_Y        300
#define SSD1683_400X300_COLOR    W_B_R_Status

#define JD79667_184X360          2
#define JD79667_184X360_X        184
#define JD79667_184X360_Y        360
#define JD79667_184X360_COLOR    W_B_R_Y_Status

#define SSD1680_152X296_BW        3
#define SSD1680_152X296_BW_X      152
#define SSD1680_152X296_BW_Y      296
#define SSD1680_152X296_BW_COLOR  W_B_Status

#define JD79650_200X200           4
#define JD79650_200X200_X          200
#define JD79650_200X200_Y          200
#define JD79650_200X200_COLOR      W_B_R_Status

#define MF_12802_M037F            8
#define MF_12802_M037F_X          152
#define MF_12802_M037F_Y          296
#define MF_12802_M037F_COLOR      W_B_R_Status

#define MF_12132_M037F_L          9
#define MF_12132_M037F_L_X        128
#define MF_12132_M037F_L_Y        250
#define MF_12132_M037F_L_COLOR    W_B_R_Status

#define MF_12602_M036F            10
#define MF_12602_M036F_X          152
#define MF_12602_M036F_Y          296
#define MF_12602_M036F_COLOR      W_B_R_Status



struct epd_struct{
	uint8_t epd_type;
	uint16_t epd_x;
	uint16_t epd_y;
	uint8_t epd_color;
	void(*initial_code)(uint16_t x_size,uint16_t y_size);
	void(*display_pic)(uint16_t x_size,uint16_t y_size);
	void(*display_single_color)(uint16_t x_size,uint16_t y_size,uint8_t color_type);
	void(*display_single_tiaowen)(uint16_t x_size,uint16_t y_size,uint8_t color_type);
	
};


extern struct epd_struct epd_list[MAX_EPD_NUM];
void epd_list_initial(void);

#endif

