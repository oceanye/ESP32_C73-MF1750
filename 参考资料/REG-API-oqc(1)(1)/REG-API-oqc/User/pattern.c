#include "LCDConfig.h"
#include "EPD_init.h"
#include "pattern.h"
#include "key.h"
#include "./BSP/LED/led.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/TIMER/gtim.h"
//int X,Y;
/*********************************************************************
*
*                    display pattern configuration
*
*********************************************************************/
Pattern_InitTypeDef Display_pattern[define_pattern_max];// =
//{
// Pattern名称,    延时, 时间(s)	
//	{Display_Black, delay_s ,1},
//	{Display_White, delay_s ,1},
//	{Display_Red, delay_s ,1},	 
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_HRedKBlack, delay_s ,3},
//	{Display_VRedKBlack, delay_s ,3},
//	{Display_Picture, delay_s ,3},
//	{Display_Black, delay_s ,3},
//	{Display_White, delay_s ,3},

//};


static uint8_t lcd_calculate_pattern(void)
{
    uint8_t i = 0;
    uint8_t size_pattern = 0;

    while(Display_pattern[i].pt_pattern != NULL)
    {
        i++;
        size_pattern++;
    }
		return size_pattern;
}

void lcd_display_pattern(void)
{
	uint8_t pattern_num = 0,i;
	pattern_num = lcd_calculate_pattern();
a:	for (i = 0; i < pattern_num;i++)
	{
#if !start_Is_play
		Wait_key_press();
#endif
		ENABLE_LED0_FAST_FLASH();
		Display_pattern[i].pt_pattern(0,0);
		DISABLE_LED0_FAST_FLASH();
		Display_pattern[i].pt_delays(Display_pattern[i].delay_ms);
	}	
#if IS_Circle_Run
	goto a;
#else

#endif
}


