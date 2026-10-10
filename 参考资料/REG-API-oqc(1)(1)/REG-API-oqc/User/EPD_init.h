#ifndef EPD_INIT_H
#define EPD_INIT_H

#include "stm32f1xx.h"
#include "./SYSTEM/sys/sys.h"
#include "GPIOLIKE51.h"


#define    EPD_White   0xFF
#define    EPD_Black   0x00
#define    EPD_Red     0xFF


#define R00_PSR         0x00
#define R01_PWR         0x01
#define R02_POF         0x02
#define R03_POFS        0x03
#define R04_PON         0x04
#define R06_BTST        0x06
#define R07_DSLP        0x07
#define R10_DTM         0x10
#define R11_DSP         0x11
#define R12_DRF         0x12
#define R17_AUTO        0x17
#define R20_LUT0        0x20

#define IMAGE_SIZE (LCD_XSIZE*LCD_YSIZE/4) //
#define WF_DATA_LENGTH 535
#define COLOR_BLACK   1
#define COLOR_WHITE   2
#define COLOR_RED     3
#define COLOR_YELLOW  4
#define COLOR_PIC     5
#define COLOR_A       6
#define COLOR_B       7

#define E_Paper_BUSY          PEin(13)

#define EPD_Rest 							PEout(14)		
#define E_Paper_DC            PEout(15)	
#define E_Paper_CS            PDout(8)
#define E_Paper_SCK           PDout(9)
#define E_Paper_SDI           PDout(10)

#define E_Paper_SLAVE_CS      PDout(11)   // 从机CS（从设备片选）

#define E_READ_SDI  PDin(10)                                            //READ SDA

typedef struct
{
	unsigned int   LCM_LCD_XSIZE ;
	unsigned int   LCM_LCD_YSIZE ;
	unsigned char  LCM_OTP_Status;		
	unsigned char  LCM_Type_Status;

	unsigned char  LCM_refresh_Staus;	
	unsigned int   LCM_X_Start ;
	unsigned int   LCM_Y_Start ;
	unsigned int   LCM_X_Size ;
	unsigned int   LCM_Y_Size ;
	  	
	
} LCM_InitTypeDef;

extern LCM_InitTypeDef LCM;

typedef struct 
{  	
	unsigned  char   VCOM;
	unsigned  char   V1;
  unsigned  char   V2;	
	unsigned  char   V3;	
	unsigned  char   V4;			
	unsigned  char   Frame;	
}EPD_InitTypeDef;

extern EPD_InitTypeDef EPD_setting;

extern uint8_t wf_data[535];
extern uint8_t vcom;

void init_global_pata(void);
void EPD_interface_OFF(void);
void EPD_SPI_Write(unsigned char value);
void E_SDI_IN(void);
void E_SDI_OUT(void);
void EPD_WriteCMD(unsigned char command);
void EPD_WriteDATA(unsigned char data);
void EPD_display_White(void);
void EPD_display_Black(void);
void EPD_display_Red(void);

void EPD_Check_Busy(void);
void EPD_refresh(void);
void EPD_initial(void);	
void EPD_interface_init(void);
void EPD_sleep(void);
unsigned char  EPD_Read_VCOM(void);
void EDP_Write_reg(unsigned char reg,unsigned char *pbuf,unsigned int len);
void EPD_Read_reg(unsigned char reg,unsigned char *pbuf,unsigned int len);

void Display_Black(uint16_t x, uint16_t y);
void Display_White(uint16_t x, uint16_t y);
void Display_Red(uint16_t x, uint16_t y);
void Display_Picture(uint16_t x, uint16_t y);
void Display_Yellow(uint16_t x, uint16_t y);
void Display_VRedKBlack(uint16_t x, uint16_t y);
void Display_HRedKBlack(uint16_t x, uint16_t y);
void Display_VBlackKRed(uint16_t x, uint16_t y);
void Display_HBlackKRed(uint16_t x, uint16_t y);
unsigned char EPD_SPI_Read(void);
void EPD_Write_LUT(unsigned char *LUTbuf,unsigned int len);

void EPD_display_yellow(void);
void Display_B_W_R_Y_A(uint16_t x, uint16_t y);
void Display_B_W_R_Y_B(uint16_t x, uint16_t y);
void EPD_display_B_W_R_Y_B(void);
void EPD_display_B_W_R_Y_A(void);
void get_vcom(void);
void Display_Picture_1(uint16_t x, uint16_t y);


typedef enum {
    TARGET_MASTER = 0,   /**< 目标：主机设备 */
    TARGET_SLAVE  = 1,   /**< 目标：从机设备 */
    TARGET_BOTH   = 2    /**< 目标：两个设备（广播） */
} EP_Target_t;


/* 写入函数 - 分开写入 */
void EPD_WriteCMD_ToMaster(unsigned char command);
void EPD_WriteCMD_ToSlave(unsigned char command);
void EPD_WriteDATA_ToMaster(unsigned char data);
void EPD_WriteDATA_ToSlave(unsigned char data);
void EPD_WriteMultiData_ToMaster(unsigned char *data, unsigned int len);
void EPD_WriteMultiData_ToSlave(unsigned char *data, unsigned int len);

/* 写入函数 - 同时写入（广播）*/
void EPD_WriteCMD_ToBoth(unsigned char command);
void EPD_WriteDATA_ToBoth(unsigned char data);
void EPD_WriteMultiData_ToBoth(unsigned char *data, unsigned int len);

/* 写入函数 - 灵活目标选择 */
void EPD_WriteCMD_Target(EP_Target_t target, unsigned char command);
void EPD_WriteDATA_Target(EP_Target_t target, unsigned char data);
void EPD_WriteMultiData_Target(EP_Target_t target, unsigned char *data, unsigned int len);

/* 读取函数 - 必须分开读取 */
void EPD_Read_reg_FromMaster(unsigned char reg, unsigned char *pbuf, unsigned int len);
void EPD_Read_reg_FromSlave(unsigned char reg, unsigned char *pbuf, unsigned int len);
unsigned char EPD_ReadByte_FromMaster(unsigned char reg);
unsigned char EPD_ReadByte_FromSlave(unsigned char reg);

/* 设备控制函数 */
void EPD_ResetBoth(void);
void EPD_InitBoth(void);
void EPD_ClearBothScreens(unsigned char color);
void EPD_DisplaySameImage(unsigned char *image_data, unsigned int data_len);

#endif
