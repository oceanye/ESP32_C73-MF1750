#include "IC_drive_code.h"
#include "epd_type.h"
#include "IC_drive_code.h"
#include "EPD_init.h"
#include <stdio.h>
#include <string.h>
#include "./SYSTEM/delay/delay.h"
#include "./BSP/NORFLASH/norflash.h"
#include "UartDataDeal.h"
#include "./BSP/STMFLASH/stmflash.h"
#include "./BSP/LED/led.h"
#include "./BSP/TIMER/gtim.h"


void IC_display_image(uint8_t edp_type)
{
	uint8_t i;
	for(i = 0;i<MAX_EPD_NUM;i++)
	  {
			if (edp_type == epd_list[i].epd_type) break;
	  }	
	ENABLE_LED0_FAST_FLASH();
	epd_list[i].initial_code(epd_list[i].epd_x,epd_list[i].epd_y);
	epd_list[i].display_pic(epd_list[i].epd_x,epd_list[i].epd_y);
	DISABLE_LED0_FAST_FLASH();
}

void IC_display_color(uint8_t edp_type,uint8_t color)
{
	uint8_t i;
	for(i = 0;i<MAX_EPD_NUM;i++)
	  {
			if (edp_type == epd_list[i].epd_type) break;
	  }	
	ENABLE_LED0_FAST_FLASH();
	epd_list[i].initial_code(epd_list[i].epd_x,epd_list[i].epd_y);
	epd_list[i].display_single_color(epd_list[i].epd_x,epd_list[i].epd_y,color);
	DISABLE_LED0_FAST_FLASH();
}

void IC_display_tiaowen(uint8_t edp_type,uint8_t color)
{
	uint8_t i;
	for(i = 0;i<MAX_EPD_NUM;i++)
	  {
			if (edp_type == epd_list[i].epd_type) break;
	  }	
	ENABLE_LED0_FAST_FLASH();
	epd_list[i].initial_code(epd_list[i].epd_x,epd_list[i].epd_y);
	epd_list[i].display_single_tiaowen(epd_list[i].epd_x,epd_list[i].epd_y,color);
	DISABLE_LED0_FAST_FLASH();
}

void IC_79656_EPD_Check_Busy(void)
{
  while(1)
  {	 //=1 BUSY
     if(E_Paper_BUSY==1) break;;
  }  	
}

void IC_79656_initialCode(uint16_t epd_x,uint16_t epd_y)
{
	EPD_Rest=0;
	delay_ms(10);
	EPD_Rest=1;
	delay_ms(10);
	IC_79656_EPD_Check_Busy();        //ic entern  normal

	//PWD
	EPD_WriteCMD(0x4D);			// PWD Cmd
	EPD_WriteDATA(0x55);

	EPD_WriteCMD(0xF3);			// PWD Cmd
	EPD_WriteDATA(0x0A);
	
	EPD_WriteCMD(0x00);
	EPD_WriteDATA(0xcf);	
	EPD_WriteDATA(0x08);	

	EPD_WriteCMD(0xE3);
	EPD_WriteDATA(0x88);

	EPD_WriteCMD(0xA8);
	EPD_WriteDATA(0x3D);

	EPD_WriteCMD(0xE9);
	EPD_WriteDATA(0x02);
	EPD_WriteCMD(0xF8);
	EPD_WriteDATA(0x80);

	EPD_WriteCMD(0xB4);
	EPD_WriteDATA(0x28);

	EPD_WriteCMD(0xAA);
	EPD_WriteDATA(0xB7);

	EPD_WriteCMD(0xB6);
	EPD_WriteDATA(0x11);		

	EPD_WriteCMD(0xB3);
	EPD_WriteDATA(0x57);		
}


void IC_79656_EPD_sleep(void)
{
   	EPD_WriteCMD(0X02);    	 //power off
	 	
		IC_79656_EPD_Check_Busy();        //waiting for the electronic paper IC to release the idle signal
	  delay_ms(100);
		EPD_WriteCMD(0X07);  	   //deep sleep
		EPD_WriteDATA(0xA5);
}

void IC_79656_EPD_refresh(void)
{
	
		EPD_WriteCMD(0x04); //R04H (PON): Power ON Command
		IC_79656_EPD_Check_Busy();        //waiting for the electronic paper IC to release the idle signal	
		EPD_WriteCMD(0x12);			//DISPLAY REFRESH 	
		IC_79656_EPD_Check_Busy();        //w
}	

void IC_79656_display_image(uint16_t epd_x,uint16_t epd_y)
{
	  uint32_t image_size = epd_x*epd_y/8;
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  uint8_t image_buff[200];
	  EPD_WriteCMD(0x10);	       //Transfer old data
	  for (i = 0;i < epd_y;i++)
	    {
//				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR),x_size);
				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*x_size, (uint16_t*)image_buff, x_size/2);
				for (j = 0;j < x_size;j++)
				  {
						EPD_WriteDATA(image_buff[j]);
					}
			}
			
	  EPD_WriteCMD(0x13);	       //Transfer old data
	  for (i = 0;i < epd_y;i++)
	    {
//				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR+image_size),x_size);
				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*x_size+image_size, (uint16_t*)image_buff, x_size/2);
				for (j = 0;j < x_size;j++)
				  {
						EPD_WriteDATA(image_buff[j]);
					}
			}

		IC_79656_EPD_refresh();//EPD_refresh		
		IC_79656_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}

void IC_79656_display_single_color(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  EPD_WriteCMD(0x10);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_BLACK:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_WHITE:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0xff);
							}
					}
			break;
			case COLOR_RED:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
		}

			
	  EPD_WriteCMD(0x13);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_BLACK:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_WHITE:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_RED:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0xff);
							}
					}
			break;
		}

		IC_79656_EPD_refresh();//EPD_refresh		
		IC_79656_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}

void IC_79656_display_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  EPD_WriteCMD(0x10);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_A:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(j<x_size/3)
									EPD_WriteDATA(EPD_White);
								else if(j<x_size*2/3)
									EPD_WriteDATA(EPD_White);
								else 
									EPD_WriteDATA(EPD_Black);
							}
					}
			break;
			case COLOR_B:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(i<=epd_y/3)
									EPD_WriteDATA(EPD_White);
								else if(i<=epd_y*2/3)
									EPD_WriteDATA(EPD_White);
								else 
									EPD_WriteDATA(EPD_Black);
							}
					}
			break;
		}
			
	  EPD_WriteCMD(0x13);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_A:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(j<x_size/3)
									EPD_WriteDATA(EPD_Red);
								else 
									EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_B:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(i<=epd_y/3)
									EPD_WriteDATA(EPD_Red);
								else 
									EPD_WriteDATA(0x00);
							}
					}
			break;
		}

		IC_79656_EPD_refresh();//EPD_refresh		
		IC_79656_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}



void IC_SSD1683_EPD_Check_Busy(void)
{
  while(1)
  {	 //=1 BUSY
     if(E_Paper_BUSY==0) break;;
  }  	
}


void IC_SSD1683_initialCode(uint16_t epd_x,uint16_t epd_y)
{
  unsigned 	int x_size=(epd_x%8)?(epd_x/8):(epd_x/8-1);		
	EPD_Rest=0;
	delay_ms(100);
	EPD_Rest=1;
	delay_ms(100);
	IC_SSD1683_EPD_Check_Busy();        //ic entern  normal
	EPD_WriteCMD(0x12);       //sw rest 
	delay_ms(20);
	IC_SSD1683_EPD_Check_Busy(); 			

	EPD_WriteCMD(0x01);              //Driver output control
	EPD_WriteDATA(LCM.LCM_LCD_YSIZE-1);          //Gate setting_A[8:0]= 0x127 [POR], 296 MUX 208:
	EPD_WriteDATA((LCM.LCM_LCD_YSIZE-1)>>8);         //296:0127 208:00CF   152:0097 250:00F9   
	EPD_WriteDATA(0x00);         //Gate scanning sequence and direction  00:[POR]


	EPD_WriteCMD(0x11);	    		//数据进入模式设置	
	EPD_WriteDATA(0x03);       //01  //数据更新方向，以及递增递减(建议固定使用01)                     

	EPD_WriteCMD(0x44);          //设置Source范围--开始、结束		
	EPD_WriteDATA(0x00);   //00      //Source 起点		
	EPD_WriteDATA(x_size);  //0x31       //128:0f Source 终点（起始点根据数据进入模式选择）
													 // 数值0x((Source/8)-1) 128:0f 122:0f   152：12  160:13   176：15

	EPD_WriteCMD(0x45);          //设置Gate范围--开始、结束	
	EPD_WriteDATA(0x00);      //2b   		
	EPD_WriteDATA(0x00);      //01   //Gate 终点（起始点根据数据进入模式选择）  	 	          
	EPD_WriteDATA(epd_y-1);  //00       //Gate 起点 数值0x(Gate-1)  //296:0127 152:0097  250:00F9
	EPD_WriteDATA((epd_y-1)>>8);//00        //数值  0x(Gate-1) 


																
	EPD_WriteCMD(0x3C);          //边界控制		
	EPD_WriteDATA(0x01); 


	EPD_WriteCMD(0x4E);	//Set RAM X address counter
	EPD_WriteDATA(0x00);
	EPD_WriteCMD(0x4F);	//Set RAM Y address counter
	EPD_WriteDATA(0x00);         
	EPD_WriteDATA(0x00); 
	IC_SSD1683_EPD_Check_Busy();    
				
}

void IC_SSD1683_EPD_sleep(void)
{
		EPD_WriteCMD(0X02);    	 //power off
	 	delay_ms(100);
		IC_SSD1683_EPD_Check_Busy();        //waiting for the electronic paper IC to release the idle signal
		EPD_WriteCMD(0X07);  	   //deep sleep
		EPD_WriteDATA(0xA5);
}

void IC_SSD1683_EPD_refresh(void)
{
	
	EPD_WriteCMD(0x18);         //温度传感器选择
	EPD_WriteDATA(0X80);        //0x80:内部  0x48:外部 
	EPD_WriteCMD(0x22);
	EPD_WriteDATA(0XF7);     //不同的值不同操作执行流程    
	EPD_WriteCMD(0x20);      //主动激活
	delay_ms(10);
	IC_SSD1683_EPD_Check_Busy();               //读取工作状态
}	

void IC_SSD1683_display_image(uint16_t epd_x,uint16_t epd_y)
{
	  uint32_t image_size = epd_x*epd_y/8;
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  uint8_t image_buff[200];
	  EPD_WriteCMD(0x24);	       //Transfer old data
//	  for (i = 0;i < epd_y;i++)
//	    {
////				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR),x_size);
//				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*x_size, (uint16_t*)image_buff, x_size/2);
//				for (j = 0;j < x_size;j++)
//				  {
//						EPD_WriteDATA(image_buff[j]);
//					}
//			}
	  for (i = 0;i < image_size/4;i++)
	    {
//				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR),x_size);
				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*4, (uint16_t*)image_buff,2);
				EPD_WriteDATA(image_buff[0]);
				EPD_WriteDATA(image_buff[1]);
				EPD_WriteDATA(image_buff[2]);
				EPD_WriteDATA(image_buff[3]);
			}
			
	  EPD_WriteCMD(0x26);	       //Transfer old data
//	  for (i = 0;i < epd_y;i++)
//	    {
////				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR+image_size),x_size);
//				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*x_size+image_size, (uint16_t*)image_buff, x_size/2);
//				for (j = 0;j < x_size;j++)
//				  {
//						EPD_WriteDATA(image_buff[j]);
//					}
//			}
	  for (i = 0;i < image_size/4;i++)
	    {
//				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR),x_size);
				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*4+image_size, (uint16_t*)image_buff,2);
				EPD_WriteDATA(image_buff[0]);
				EPD_WriteDATA(image_buff[1]);
				EPD_WriteDATA(image_buff[2]);
				EPD_WriteDATA(image_buff[3]);
			}
		IC_SSD1683_EPD_refresh();//EPD_refresh		
		IC_SSD1683_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}

void IC_SSD1683_display_single_color(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  EPD_WriteCMD(0x24);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_BLACK:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_WHITE:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0xff);
							}
					}
			break;
			case COLOR_RED:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
		}

			
	  EPD_WriteCMD(0x26);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_BLACK:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_WHITE:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_RED:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0xff);
							}
					}
			break;
		}

		IC_SSD1683_EPD_refresh();//EPD_refresh		
		IC_SSD1683_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}

void IC_SSD1683_display_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  EPD_WriteCMD(0x24);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_A:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(j<x_size/3)
									EPD_WriteDATA(EPD_White);
								else if(j<x_size*2/3)
									EPD_WriteDATA(EPD_White);
								else 
									EPD_WriteDATA(EPD_Black);
							}
					}
			break;
			case COLOR_B:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(i<=epd_y/3)
									EPD_WriteDATA(EPD_White);
								else if(i<=epd_y*2/3)
									EPD_WriteDATA(EPD_White);
								else 
									EPD_WriteDATA(EPD_Black);
							}
					}
			break;
		}
			
	  EPD_WriteCMD(0x26);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_A:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(j<x_size/3)
									EPD_WriteDATA(EPD_Red);
								else 
									EPD_WriteDATA(0x00);
							}
					}
			break;
			case COLOR_B:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(i<=epd_y/3)
									EPD_WriteDATA(EPD_Red);
								else 
									EPD_WriteDATA(0x00);
							}
					}
			break;
		}

		IC_SSD1683_EPD_refresh();//EPD_refresh		
		IC_SSD1683_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}


void IC_JD79667_initialCode(uint16_t epd_x,uint16_t epd_y)
{	
	uint8_t res = 0;
	if (epd_x<= 168) 
		res =0x80;
	else if(epd_x<= 184) 
		res = 0x40;
	else if((epd_x<= 200) && (epd_y<= 384)) 
		res = 0;
	else if((epd_x<= 200) && (epd_y<= 200)) 
		res = 0xc0;
	EPD_Rest=0;
	delay_ms(50);
	EPD_Rest=1;
	delay_ms(50);
	//		
	IC_79656_EPD_Check_Busy(); 

	EPD_WriteCMD(0x4D);			//PWD After OTP
	EPD_WriteDATA(0x78);

	EPD_WriteCMD(0xB4);			//PWD After OTP
	EPD_WriteDATA(0xd0);

	EPD_WriteCMD(0xB7);			
	EPD_WriteDATA(0x7c);

	EPD_WriteCMD(0x00);			
	EPD_WriteDATA(0x0f|res);      //PSR setting
	EPD_WriteDATA(0X29);

	EPD_WriteCMD(0x01);			
	EPD_WriteDATA(0x07);      //PWR setting
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x22);      //PWR setting
	EPD_WriteDATA(0x78);
	EPD_WriteDATA(0x0a);      //PWR setting
	EPD_WriteDATA(0x22);
				
	EPD_WriteCMD(0x03);			//Power off Sequence Setting
	EPD_WriteDATA(0x10);
	EPD_WriteDATA(0x54);
	EPD_WriteDATA(0x44);				 

	EPD_WriteCMD(0x06);			//Booster Soft Start	Setting			
	EPD_WriteDATA(0x0f);
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x3F);
	EPD_WriteDATA(0x0A);
	EPD_WriteDATA(0x25);
	EPD_WriteDATA(0x1a);
	EPD_WriteDATA(0x17);	

	EPD_WriteCMD(0x30);			//CDI Setting
	EPD_WriteDATA(0x02);				 

	EPD_WriteCMD(0x41);			//CDI Setting
	EPD_WriteDATA(0x00);

	EPD_WriteCMD(0x50);			//CDI Setting
	EPD_WriteDATA(0x37);

	EPD_WriteCMD(0x60);			//TCON Setting
	EPD_WriteDATA(0x02);
	EPD_WriteDATA(0x02);

	EPD_WriteCMD(0x61);	    //resolution setting		
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(epd_x);
	EPD_WriteDATA(epd_y>>8);
	EPD_WriteDATA(epd_y);

	EPD_WriteCMD(0x65);	    			
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x00);

	EPD_WriteCMD(0xE7);	    			
	EPD_WriteDATA(0x1C);

	EPD_WriteCMD(0xE3);	    //PWS setting   			
	EPD_WriteDATA(0x22);
					 
	EPD_WriteCMD(0xe0);			
	EPD_WriteDATA(0x00);

	EPD_WriteCMD(0xE9);			
	EPD_WriteDATA(0x01);			
}

void IC_JD79667_display_image(uint16_t epd_x,uint16_t epd_y)
{
		uint16_t i,j;
		uint16_t x_size=epd_x>>2;
	  uint8_t image_buff[200];
	  EPD_WriteCMD(0x10);	       //Transfer old data
	  for (i = 0;i < epd_y;i++)
	    {
//				norflash_read(image_buff, (i*x_size+FLASH_PIC_DATA_ADDR),x_size);
				stmflash_read(INTERNAL_FALSH_PIC_ADDR+i*x_size, (uint16_t*)image_buff, x_size/2);
				for (j = 0;j < x_size;j++)
				  {
						EPD_WriteDATA(image_buff[j]);
					}
			}			

    EPD_WriteCMD(0x04);
    IC_79656_EPD_Check_Busy();
    
    EPD_WriteCMD(0x12);
    EPD_WriteDATA(0x00);
    IC_79656_EPD_Check_Busy();
   
  
//    EPD_WriteCMD(R02_POF);
//    EPD_WriteDATA(0x00);
//		delay_ms(50);
//    EPD_Check_Busy();
//		delay_ms(50);
    EPD_WriteCMD(0x07);
    EPD_WriteDATA(0xa5);			
}

void IC_JD79667_display_single_color(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=epd_x>>2;
	  EPD_WriteCMD(0x10);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_BLACK:		
				for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x00);
							}
					}							
			break;
			case COLOR_WHITE:		
				for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0x55);
							}
					}											
			break;
			case COLOR_RED:		
				for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0xff);
							}
					}											
			break;
			case COLOR_YELLOW:		
				for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								EPD_WriteDATA(0xaa);
							}
					}											
			break;
		}


    EPD_WriteCMD(0x04);
    IC_79656_EPD_Check_Busy();
    
    EPD_WriteCMD(0x12);
    EPD_WriteDATA(0x00);
    IC_79656_EPD_Check_Busy();
   
  
//    EPD_WriteCMD(R02_POF);
//    EPD_WriteDATA(0x00);
//		delay_ms(50);
//    EPD_Check_Busy();
//		delay_ms(50);
    EPD_WriteCMD(0x07);
    EPD_WriteDATA(0xa5);			
}


void IC_JD79667_display_single_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=epd_x>>2;
	  EPD_WriteCMD(0x10);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_A:		
				for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(j<x_size/4)
									EPD_WriteDATA(0x00);
								else if(j<x_size*2/4)
									EPD_WriteDATA(0x55);
								else if(j<x_size*3/4)
									EPD_WriteDATA(0xaa);
								else 
									EPD_WriteDATA(0xff);
							}
					}							
			break;
			case COLOR_B:		
				for(i=0;i<((epd_x*epd_y)/4);i++)
				{
					EPD_WriteDATA(0x00);
				}
				for(i=0;i<(epd_x*epd_y/4);i++)
				{
					EPD_WriteDATA(0x55);
				}
				for(i=0;i<(epd_x*epd_y/4);i++)
				{
					EPD_WriteDATA(0xff);
				}
				for(i=0;i<(epd_x*epd_y/2);i++)
				{
					EPD_WriteDATA(0xaa);
				}
			break;
		}


    EPD_WriteCMD(0x04);
    IC_79656_EPD_Check_Busy();
    
    EPD_WriteCMD(0x12);
    EPD_WriteDATA(0x00);
    IC_79656_EPD_Check_Busy();
   
  
//    EPD_WriteCMD(R02_POF);
//    EPD_WriteDATA(0x00);
//		delay_ms(50);
//    EPD_Check_Busy();
//		delay_ms(50);
    EPD_WriteCMD(0x07);
    EPD_WriteDATA(0xa5);			
}

void IC_SSD1680_BW_initialCode(uint16_t epd_x,uint16_t epd_y)
{	   
	unsigned 	int x_size=(epd_x%8)?(epd_x/8):(epd_x/8-1);
  
	EPD_Rest=0;
	delay_ms(100);
	EPD_Rest=1;
	delay_ms(100);					
	IC_SSD1683_EPD_Check_Busy();        //ic entern  normal

	EPD_WriteCMD(0x12);       //sw rest 
	delay_ms(20);
	IC_SSD1683_EPD_Check_Busy(); 			


	EPD_WriteCMD(0x01);           //Driver output control
	EPD_WriteDATA(epd_y-1);          //Gate setting_A[8:0]= 0x127 [POR], 296 MUX 208:
	EPD_WriteDATA((epd_y-1)>>8);         //296:0127 208:00CF   152:0097 250:00F9   
	EPD_WriteDATA(0x00);         //Gate scanning sequence and direction  00:[POR]


	EPD_WriteCMD(0x11);	    		//数据进入模式设置	
	EPD_WriteDATA(0x03);         //数据更新方向，以及递增递减(建议固定使用01)                     

	EPD_WriteCMD(0x44);          //设置Source范围--开始、结束		
	EPD_WriteDATA(0x00);         //Source 起点		
	EPD_WriteDATA(x_size);         //128:0f Source 终点（起始点根据数据进入模式选择）
														 // 数值0x((Source/8)-1) 128:0f 122:0f   152：12  160:13   176：15

	EPD_WriteCMD(0x45);          //设置Gate范围--开始、结束	
	EPD_WriteDATA(0x00);         		
	EPD_WriteDATA(0x00);         //Gate 终点（起始点根据数据进入模式选择）  	 	          
	EPD_WriteDATA(epd_y-1);         //Gate 起点 数值0x(Gate-1)  //296:0127 152:0097  250:00F9
	EPD_WriteDATA((epd_y-1)>>8);        //数值  0x(Gate-1) 

																	
	EPD_WriteCMD(0x3C);          //边界控制		
	EPD_WriteDATA(0x05); 


	EPD_WriteCMD(0x21);          //Display Update Control 1显示更新控制1//	
	EPD_WriteDATA(0x00);         //0000：常用
	EPD_WriteDATA(0x80);        //source的输出模式 00:s0 to s175 80：S8 to S167     


	EPD_WriteCMD(0x4E);	//Set RAM X address counter
	EPD_WriteDATA(0x00);
	EPD_WriteCMD(0x4F);	//Set RAM Y address counter
	EPD_WriteDATA(0x00);         
	EPD_WriteDATA(0x00); 
	IC_SSD1683_EPD_Check_Busy();   
}

void IC_SSD1680_BW_display_tiaowen(uint16_t epd_x,uint16_t epd_y,uint8_t color_type)
{
		uint16_t i,j;
		uint16_t x_size=(epd_x%8)?(epd_x/8+1):(epd_x/8);
	  EPD_WriteCMD(0x24);	       //Transfer old data
		switch(color_type)
		{
			case COLOR_A:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								 if(j<x_size*1/2)
										EPD_WriteDATA(0xff);
									else 
										EPD_WriteDATA(0x00);					
							}
					}
			break;
			case COLOR_B:
			  for (i = 0;i < epd_y;i++)
					{
						for (j = 0;j < x_size;j++)
							{
								if(i<=epd_y*1/2)
									EPD_WriteDATA(0xff);
								else 
									EPD_WriteDATA(0x00);
							}
					}
			break;
		}
			
	  EPD_WriteCMD(0x26);	       //Transfer old data
		for (i = 0;i < epd_y;i++)
			{
				for (j = 0;j < x_size;j++)
					{
							EPD_WriteDATA(0x00);
					}
			}

		IC_SSD1683_EPD_refresh();//EPD_refresh		
		IC_SSD1683_EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}


void IC_79650_initialCode(uint16_t epd_x,uint16_t epd_y)
{	   
	EPD_Rest=0;
	delay_ms(10);
	EPD_Rest=1;
	delay_ms(10);
	IC_79656_EPD_Check_Busy();        //ic entern  normal

	//PWD
	EPD_WriteCMD(0x4D);			// PWD Cmd
	EPD_WriteDATA(0x55);

	EPD_WriteCMD(0xF3);			// PWD Cmd
	EPD_WriteDATA(0x0A);
	
//	EPD_WriteCMD(0x04); //POWER ON
//	EPD_Check_Busy();        //waiting for the electronic paper IC to release the idle signal
}

