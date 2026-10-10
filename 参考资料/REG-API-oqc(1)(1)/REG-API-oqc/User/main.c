#include "./stm32f1xx_it.h"
#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/LED/led.h"
#include "stmflash.h"
#include "iap.h"
#include "usart.h"
#include "UartDataDeal.h"
#include "EPD_init.h"
#include "key.h"
#include "LCDConfig.h"
#include "pattern.h"
#include "./BSP/NORFLASH/norflash.h"
#include "./BSP/TIMER/gtim.h"



#include <stdio.h>
#include <stdlib.h>
#include <string.h>


#include "pindefine.h"
#include "comm.h"
#include "E28xx.h"
//#include "usbcdc.h"

//#if OTP_API_Mod
//#include "OTP.h" //Generate File From H File Conversion AP
//#elif REG_API_Mode_From_File
#include "WF20_25.h" //Generate File From WF Tunning Tool AP

//#endif

static void Display(uint8_t* value)
{
//	data.pt_pattern
  
	ENABLE_LED0_FAST_FLASH();
	switch(value[0])
	{
		case COLOR_BLACK:Display_Black(0,0) ;break;
		case COLOR_WHITE:Display_White(0,0) ;break;
		case COLOR_RED:Display_Red(0,0) ;break;
		case COLOR_YELLOW:Display_Yellow(0,0) ;break;
		case COLOR_PIC:Display_Picture(0,0) ;break;
		case COLOR_A:Display_B_W_R_Y_A(0,0) ;break;
		case COLOR_B:Display_B_W_R_Y_B(0,0) ;break;
	}
	DISABLE_LED0_FAST_FLASH();
	delay_s(value[1]*256+value[2]);
}
static void EPD_initial_noOTP(void)
{
	
	unsigned long int Gate,Source;
	Gate=428;
	Source=428;
	
	EPD_Rest=0;
	delay_ms(100);
	EPD_Rest=1;
	delay_ms(100);
	EPD_Check_Busy(); 

		EPD_WriteCMD(0xAA);  //Access full function of user command
		EPD_WriteDATA(0x49); //访问用户命令的全部功能
		EPD_WriteDATA(0x55); 
		EPD_WriteDATA(0x20); 
		EPD_WriteDATA(0x08); 
		EPD_WriteDATA(0x09); 
		EPD_WriteDATA(0x18); 
	
		EPD_WriteCMD(0x06);   //Set VPH booster soft start setting
		EPD_WriteDATA(0x6F); 	//设置VPH增压器软启动参数
		EPD_WriteDATA(0x15); 
		EPD_WriteDATA(0x26); 
		EPD_WriteDATA(0x36); 

    EPD_WriteCMD(0x00);     //PSR寄存器   
    EPD_WriteDATA(0x0F); 
		EPD_WriteDATA(0x89);    //高8bit:1  MCU发送LUT模式，高8bit:0 调用OTP模式  要使用E9指令绕过CRC
    EPD_Check_Busy();
		
    EPD_WriteCMD(0x01);    //PWR Power setting Register 电压设置 
    EPD_WriteDATA(0x0F);    //	
	  EPD_WriteDATA(0xF8);    //	
    EPD_WriteDATA(WF20_25[1]);    //0x1E
    EPD_WriteDATA(WF20_25[2]);    
    EPD_WriteDATA(WF20_25[3]);    //0x78
		EPD_WriteDATA(WF20_25[4]);    //0x1E
		
		EPD_WriteCMD(0x50);     //CDI Booder 设置   POR:97
    EPD_WriteDATA(0x37); 
			
	  EPD_WriteCMD(0x30);     //Frame 频率设置
    EPD_WriteDATA(WF20_25[6]);
	 
  	EPD_WriteCMD(0x82);     //DC_VCOM
   // EPD_WriteDATA(WF24_24[5]); 	/*********注意：此处设置的电压请根据waveform设置的电压进行对应设置***********/
    EPD_WriteDATA(0x14); 	/*********注意：此处设置的电压请根据waveform设置的电压进行对应设置***********/	
		 
  	 EPD_WriteCMD(0x61); 					//TRES  Panel分辨率设置
     EPD_WriteDATA(Source/256);		// Source_BITS_H
     EPD_WriteDATA(Source%256);		// Source_BITS_L		 
     EPD_WriteDATA(Gate/256);			// Gate_BITS_H
     EPD_WriteDATA(Gate%256); 		// Gate_BITS_L	
		 EPD_Check_Busy();

     EPD_WriteCMD(0xE9);  /*注意，如果Panel已经OTP使用MCU点亮必须打开此指令绕过CRC校验*/
     EPD_WriteDATA(0x01);
     EPD_Check_Busy(); 
		 
     EPD_Check_Busy(); 
//		 printf(" 发送 SSD2693_Init_MCU_Code OK !");		 
}





int main(void)
{
	
	
	unsigned char otpflg = 0xFF;
		unsigned char uidflg = 0xFF;
		unsigned char vcomflg = 0xFF;
		/* 设置中断向量表偏移量为0X4800 */
//	sys_nvic_set_vector_table(FLASH_BASE,0x4800);	
	int i;
	HAL_Init();                             /* 初始化HAL库 */
	sys_stm32_clock_init(RCC_PLL_MUL9);     /* 设置时钟为72Mhz */
	delay_init(72);                         /* 延时初始化 */
	Uart1_Init();
	Key_init();
	init_global_pata();
	EPD_interface_init();
//	norflash_init();
	led_init();                             /* 初始化LED */
	gtim_timx_int_init(10000 - 1, 720 - 1); /* 100Khz的计数频率，计数5K次为50ms */
//	HAL_NVIC_EnableIRQ(GTIM_TIMX_INT_IRQn);   
	LED0(0);  
	delay_ms(500);
	LED0(1); 
	
		
		
	
//Wait_key_press();
	ENABLE_LED0_FAST_FLASH();
//	epdInitial();
//	display_Black();
	//DISABLE_LED0_FAST_FLASH();

////	


//while(1)
//	
//{


//	epdInitial();
//	display_Black();
////	
//		for(i=0;i<120;i++)
//	{
//	
//		delay_ms(1000);
//	}
////	
////	
////	
//		epdInitial();
//	display_White();
////	
////	
////	
//		for(i=0;i<150;i++)
//	{
//	
//		delay_ms(1000);
//	}
//	
//	
//	
//		epdInitial();
//	display_Red();
//	
//	
//			for(i=0;i<150;i++)
//	{
//	
//		delay_ms(1000);
//	}
//	
//	epdInitial();
//	display_Yellow();
//	
//	
//			for(i=0;i<150;i++)
//	{
//	
//		delay_ms(1000);
//	}
//	
//		epdInitial();
//	display_G();
//	
//			for(i=0;i<150;i++)
//	{
//	
//		delay_ms(1000);
//	}
//	
//		epdInitial();
//	display_B();
//	
//			for(i=0;i<10;i++)
//	{
//	
//		delay_ms(1000);
//	}
//	
//	
	
	


//}

//Wait_key_press();
//ENABLE_LED0_FAST_FLASH();
//		epdInitial();
//	display_White();
	//DISABLE_LED0_FAST_FLASH();

//	for(i=0;i<1200;i++)
//	{
//	
//		delay_ms(1000);
//	}、
//Wait_key_press();


//ENABLE_LED0_FAST_FLASH();
		epdInitial();
	Display_Picture(0,0);	
//	DISABLE_LED0_FAST_FLASH();


		
		

	while(1)
	{
		if (usart_cmd == USART_CMD_PLAY_PIC)
		{
			usart_cmd = USART_CMD_NULL;
//			if(usart_cmd_buff[0]==0) break;
			for(i = 0;i < usart_cmd_buff[3];i++)
			{
				Display(&usart_cmd_buff[0]);
			}

//			if(usart_cmd_buff[4]==0) break;
			for(i = 0;i < usart_cmd_buff[7];i++)
			{
				Display(&usart_cmd_buff[4]);
			}

//			if(usart_cmd_buff[8]==0) break;
			for(i = 0;i < usart_cmd_buff[11];i++)
			{
				Display(&usart_cmd_buff[8]);
			}

//			if(usart_cmd_buff[12]==0) break;
			for(i = 0;i < usart_cmd_buff[15];i++)
			{
				Display(&usart_cmd_buff[12]);
			}

//			if(usart_cmd_buff[16]==0) break;
			for(i = 0;i < usart_cmd_buff[19];i++)
			{
				Display(&usart_cmd_buff[16]);
			}
		}
		else if (usart_cmd == USART_CMD_GET_VCOM)
		{
			usart_cmd = USART_CMD_NULL;
			get_vcom();
			Uart_ask_vcom();
		}
	  else if (usart_cmd == USART_CMD_SET_VCOM)
		{
			usart_cmd = USART_CMD_NULL;
			Uart_ask_set_vcom();
//			EPD_setting.VCOM = vcom;
		}
//		if (usart_cmd_play_enable)
//		{
//			usart_cmd_play_enable = 0;
//			
//		}
		
	};
}
