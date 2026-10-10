#ifndef _UARTDATADEAL_H
#define _UARTDATADEAL_H
#include "./SYSTEM/sys/sys.h"

#define SINGLE_BAG_SIZE  512
#define SINGLE_PIC_BAG_SIZE  1024

#define FLASH_PIC_HEAD_ADDR  0
#define FLASH_PIC_DATA_ADDR  256

#define INTERNAL_FALSH_PIC_HEAD_ADDR  0x08011000
#define INTERNAL_FALSH_PIC_SETTING_ADDR  0x08011400
#define INTERNAL_FALSH_PIC_ADDR 0x08011800

extern uint16_t rec_bag_count;
extern uint8_t usart_cmd_buff[50];
void Uart_UpgradeData_deal(uint8_t* dat_buff,uint16_t buff_len);
void send_cmd(void);
void write_pic_head(uint8_t* dat_buff,uint16_t buff_len);
void Uart_PicData_Write(uint8_t* dat_buff,uint16_t buff_len);
void Uart_request_picdata(void);
void write_group_setting(uint8_t* dat_buff,uint16_t buff_len);
void Uart_save_wf_data(uint8_t* dat_buff,uint16_t buff_len);
void Uart_ask_vcom(void);
void Uart_ask_set_vcom(void);

#endif

