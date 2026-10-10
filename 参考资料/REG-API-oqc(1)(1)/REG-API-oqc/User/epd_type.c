#include "epd_type.h"
#include "IC_drive_code.h"
#include "EPD_init.h"
#include <stdio.h>
#include <string.h>
#include "./SYSTEM/delay/delay.h"

struct epd_struct epd_list[MAX_EPD_NUM];

void epd_list_initial(void)
{
	memset((uint8_t*)epd_list,0,sizeof(epd_list));
	epd_list[0].epd_type     = JD79656_122X250;
	epd_list[0].epd_x        = JD79656_122X250_X;
	epd_list[0].epd_y        = JD79656_122X250_Y;
	epd_list[0].epd_color    = JD79656_122X250_COLOR;
	epd_list[0].initial_code = IC_79656_initialCode;
	epd_list[0].display_pic  = IC_79656_display_image;
	epd_list[0].display_single_color = IC_79656_display_single_color;
	epd_list[0].display_single_tiaowen = IC_79656_display_tiaowen;
	
	epd_list[1].epd_type     = SSD1683_400X300;
	epd_list[1].epd_x        = SSD1683_400X300_X;
	epd_list[1].epd_y        = SSD1683_400X300_Y;
	epd_list[1].epd_color    = SSD1683_400X300_COLOR;
	epd_list[1].initial_code = IC_SSD1683_initialCode;
	epd_list[1].display_pic  = IC_SSD1683_display_image;
	epd_list[1].display_single_color = IC_SSD1683_display_single_color;
	epd_list[1].display_single_tiaowen = IC_SSD1683_display_tiaowen;
	
	
	epd_list[2].epd_type     = JD79667_184X360;
	epd_list[2].epd_x        = JD79667_184X360_X;
	epd_list[2].epd_y        = JD79667_184X360_Y;
	epd_list[2].epd_color    = JD79667_184X360_COLOR;
	epd_list[2].initial_code = IC_JD79667_initialCode;
	epd_list[2].display_pic  = IC_JD79667_display_image;
	epd_list[2].display_single_color = IC_JD79667_display_single_color;
	epd_list[2].display_single_tiaowen = IC_JD79667_display_single_tiaowen;

	epd_list[3].epd_type     = SSD1680_152X296_BW;
	epd_list[3].epd_x        = SSD1680_152X296_BW_X;
	epd_list[3].epd_y        = SSD1680_152X296_BW_Y;
	epd_list[3].epd_color    = SSD1680_152X296_BW_COLOR;
	epd_list[3].initial_code = IC_SSD1680_BW_initialCode;
	epd_list[3].display_pic  = IC_SSD1683_display_image;
	epd_list[3].display_single_color = IC_SSD1683_display_single_color;
	epd_list[3].display_single_tiaowen = IC_SSD1680_BW_display_tiaowen;
	
	epd_list[4].epd_type     = JD79650_200X200;
	epd_list[4].epd_x        = JD79650_200X200_X;
	epd_list[4].epd_y        = JD79650_200X200_Y;
	epd_list[4].epd_color    = JD79650_200X200_COLOR;
	epd_list[4].initial_code = IC_79650_initialCode;
	epd_list[4].display_pic  = IC_79656_display_image;
	epd_list[4].display_single_color = IC_79656_display_single_color;
	epd_list[4].display_single_tiaowen = IC_79656_display_tiaowen;
}


