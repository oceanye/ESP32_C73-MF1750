#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "string.h"
#include "UartDataDeal.h"
#include "./BSP/STMFLASH/stmflash.h"
#include "iap.h"
#include "./BSP/NORFLASH/norflash.h"
#include "EPD_init.h"
#include "LCDConfig.h"
#include "EPD_init.h"
#include "pattern.h"
#include "./SYSTEM/delay/delay.h"

uint8_t usart_cmd_buff[50];
uint16_t rec_bag_count = 0;

void Uart_UpgradeData_deal(uint8_t* dat_buff,uint16_t buff_len)
{
	stmflash_write_nocheck((FLASH_APP1_ADDR+rec_bag_count*SINGLE_BAG_SIZE), (uint16_t*)dat_buff, (buff_len>>1));
	rec_bag_count++;
}

void send_cmd(void)
{
	uint8_t data[15];
	data[0] = 0x41;
	data[1] = 0x41;
	data[2] = 0;
	data[3] = 10;
	data[4] = 2;
	data[5] = 0;
	data[6] = 0;
	data[7] = 0;
	data[8] = 0;
	data[9] = 0x0d;
	usart_send(data,10);
}

uint16_t temp_t = 0;
void write_pic_head(uint8_t* dat_buff,uint16_t buff_len)
{
//	norflash_erase_chip();  //清空图片区域 
//	norflash_write(dat_buff, FLASH_PIC_HEAD_ADDR, buff_len);      /* 从倒数第100个地址处开始,写入SIZE长度的数据 */
//	Uart_request_picdata();
	rec_bag_count = 0;
	erase_Mult_sec(INTERNAL_FALSH_PIC_HEAD_ADDR,51);
//	HAL_FLASH_Unlock(); 
	stmflash_write(INTERNAL_FALSH_PIC_HEAD_ADDR, (uint16_t*)dat_buff, (buff_len>>1));
//	HAL_FLASH_Lock();   /* 上锁 */
	temp_t=stmflash_read_halfword(INTERNAL_FALSH_PIC_HEAD_ADDR);
	Uart_request_picdata();
}


void Uart_request_picdata(void)
{
	uint8_t data[15];
	data[0] = 0x41;
	data[1] = 0x41;
	data[2] = 0;
	data[3] = 10;
	data[4] = 4;
	data[5] = 0;
	data[6] = 0;
	data[7] = 0;
	data[8] = 0;
	data[9] = 0x0d;
	usart_send(data,10);
}

void Uart_PicData_Write(uint8_t* dat_buff,uint16_t buff_len)
{
//	norflash_write(dat_buff, (FLASH_PIC_DATA_ADDR+rec_bag_count*SINGLE_PIC_BAG_SIZE),buff_len);
	HAL_FLASH_Unlock(); 
	stmflash_write_nocheck((INTERNAL_FALSH_PIC_ADDR+rec_bag_count*SINGLE_PIC_BAG_SIZE), (uint16_t*)dat_buff, (buff_len>>1));
	HAL_FLASH_Lock();   /* 上锁 */
	
	rec_bag_count++;
	Uart_request_picdata();
}


static void Uart_wf_ack(void)
{
	uint8_t data[15];
	data[0] = 0x41;
	data[1] = 0x41;
	data[2] = 0;
	data[3] = 10;
	data[4] = 5;
	data[5] = 0;
	data[6] = 0;
	data[7] = 0;
	data[8] = 0;
	data[9] = 0x0d;
	usart_send(data,10);
}
void Uart_save_wf_data(uint8_t* dat_buff,uint16_t buff_len)
{
	memset(wf_data,0,sizeof(wf_data));
	memcpy(wf_data,dat_buff,WF_DATA_LENGTH);
	EPD_setting.V1 = wf_data[1];	
	EPD_setting.V2 = wf_data[2];
	EPD_setting.V3 = wf_data[3];
	EPD_setting.V4 = wf_data[4];
	EPD_setting.VCOM = wf_data[5];
	EPD_setting.Frame = wf_data[6];	
	Uart_wf_ack();
}



void Uart_ask_setting(void)
{
	uint8_t data[15];
	data[0] = 0x41;
	data[1] = 0x41;
	data[2] = 0;
	data[3] = 10;
	data[4] = 6;
	data[5] = 0;
	data[6] = 0;
	data[7] = 0;
	data[8] = 0;
	data[9] = 0x0d;
	usart_send(data,10);
}
//uint8_t temp_setting[50];
static void Display_pattern_add(Pattern_InitTypeDef *data,uint8_t* value)
{
//	data.pt_pattern
	data->pt_delays = delay_s;
	data->delay_ms = value[1]*256+value[2];
	switch(value[0])
	{
		case COLOR_BLACK:data->pt_pattern = Display_Black ;break;
		case COLOR_WHITE:data->pt_pattern = Display_White ;break;
		case COLOR_RED:data->pt_pattern = Display_Red ;break;
		case COLOR_YELLOW:data->pt_pattern = Display_Yellow ;break;
		case COLOR_PIC:data->pt_pattern = Display_Picture ;break;
		case COLOR_A:data->pt_pattern = Display_B_W_R_Y_A ;break;
		case COLOR_B:data->pt_pattern = Display_B_W_R_Y_B ;break;
	}
}

void write_group_setting(uint8_t* dat_buff,uint16_t buff_len)
{
//	uint8_t i = 0,j = 0;
	usart_cmd_play_enable = 1;	
	Uart_wf_ack();
//	for (i = 0;i<define_pattern_max;i++)
//	  {
//			Display_pattern[i].pt_pattern = NULL;
//		},
	memcpy(usart_cmd_buff,dat_buff,buff_len);
//	if(dat_buff[0]==0) return;
//	for(i = 0;i < dat_buff[3];i++)
//	{
//		Display_pattern_add(&Display_pattern[j++],&dat_buff[0]);
//	}
//	
//	if(dat_buff[4]==0) return;
//	for(i = 0;i < dat_buff[7];i++)
//	{
//		Display_pattern_add(&Display_pattern[j++],&dat_buff[4]);
//	}
//	
//	if(dat_buff[8]==0) return;
//	for(i = 0;i < dat_buff[11];i++)
//	{
//		Display_pattern_add(&Display_pattern[j++],&dat_buff[8]);
//	}
//	
//	if(dat_buff[12]==0) return;
//	for(i = 0;i < dat_buff[15];i++)
//	{
//		Display_pattern_add(&Display_pattern[j++],&dat_buff[12]);
//	}
//	
//	if(dat_buff[16]==0) return;
//	for(i = 0;i < dat_buff[19];i++)
//	{
//		Display_pattern_add(&Display_pattern[j++],&dat_buff[16]);
//	}

}


void Uart_ask_vcom(void)
{
	uint8_t data[15];
	data[0] = 0x41;
	data[1] = 0x41;
	data[2] = 0;
	data[3] = 10;
	data[4] = 7;
	data[5] = 0;
	data[6] = vcom;
	data[7] = 0;
	data[8] = 0;
	data[9] = 0x0d;
	usart_send(data,10);
}

void Uart_ask_set_vcom(void)
{
	uint8_t data[15];
	data[0] = 0x41;
	data[1] = 0x41;
	data[2] = 0;
	data[3] = 10;
	data[4] = 8;
	data[5] = 0;
	data[6] = 0;
	data[7] = 0;
	data[8] = 0;
	data[9] = 0x0d;
	usart_send(data,10);
}
