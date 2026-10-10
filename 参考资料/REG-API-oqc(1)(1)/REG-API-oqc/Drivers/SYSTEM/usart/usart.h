#ifndef EPD_USART_H
#define EPD_USART_H


#include "stdio.h"
#include "./SYSTEM/sys/sys.h"

#define USART_CMD_NULL        0  
#define USART_CMD_PLAY_PIC    1
#define USART_CMD_GET_VCOM    2
#define USART_CMD_SET_VCOM    3
//#define USART_CMD_FLASH_GROUP     4


#define    USART1_RData_length  1500
extern uint8_t USART1_RData[USART1_RData_length];
extern uint8_t usart_cmd_play_enable;
extern uint8_t usart_cmd;



struct uart_cmd_struct{
	
	uint8_t  epd_type;
	uint8_t  cmd_type;
	uint8_t  color_type;
	uint8_t  pic1;
	uint16_t delay_second1;
	uint8_t  play_cnt1;
	uint8_t  pic2;
	uint16_t delay_second2;
	uint8_t  play_cnt2;
	uint8_t  pic3;
	uint16_t delay_second3;
	uint8_t  play_cnt3;
	uint8_t  pic4;
	uint16_t delay_second4;
	uint8_t  play_cnt4;
	uint8_t  pic5;
	uint16_t delay_second5;
	uint8_t  play_cnt5;
	uint8_t  circul_play;
};

extern struct uart_cmd_struct uart_cmd;

void usart_init(uint32_t bound);                /* 串口初始化函数 */
void USART1_receiveDataNnalyse(void);
void reboot_system(void);
void usart_send(uint8_t*buff,uint16_t buff_len);
void Uart1_Init(void);

#endif

