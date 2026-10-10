#include "EPD_init.h"
#include <stdio.h>
#include <string.h>
#include "LCDConfig.h"
#include "EPD_DATA.h"
#include "./SYSTEM/delay/delay.h"
#include "./SYSTEM/usart/usart.h"

LCM_InitTypeDef LCM;
uint8_t vcom= 0x1E;
EPD_InitTypeDef EPD_setting;
uint8_t wf_data[535]={ 
//0x00,0x24,0x78,0x27,0x20,0x14,0x03,//VGHL,VSHL_0,VSH_1,VSL_1,VSHL_1,VCOM,PLL
//0xEF,0x7F,0xFF,0xA8,0xFF,0xFF,0xEF,0xFF,0xFF,0xFF,0xFF,//VCOM-GROUP1
//0xEF,0x7F,0xFF,0xBF,0x7F,0xFF,0xBE,0x7F,0x7F,0xFF,0x7D,//VCOM-GROUP2
//0xEF,0x7F,0xFF,0xFF,0xFF,0xFF,0xEF,0x7F,0x7F,0xFF,0x2D,//VCOM-GROUP3
//0xEF,0x7F,0xFF,0x7F,0x7F,0xFF,0x3C,0x7F,0x7F,0xFF,0x3F,//VCOM-GROUP4
//0xFD,0x7F,0xFF,0xEF,0xAD,0x2D,0xEF,0xEC,0xAF,0x7F,0xEF,//VCOM-GROUP5
//0x6F,0x7F,0xFF,0xEF,0xAF,0xEF,0xEF,0xEF,0xFE,0x6F,0xEF,//VCOM-GROUP6
//0xEF,0x7F,0xFF,0xEF,0xEF,0xEF,0xEF,0x6F,0xBF,0xAF,0xEF,//VCOM-GROUP7
//0x7F,0x7F,0xFF,0xEF,0xEF,0xEF,0xEF,0xFF,0xFF,0xFF,0xEF,//VCOM-GROUP8
//0xEF,0xFB,0xF3,0x29,0xFF,0xFF,0xEF,0xEF,0xEF,0xFF,0x2F,//Black-GROUP1
//0xEF,0xDE,0xF3,0xBF,0x7F,0xFF,0xBE,0x7F,0x7F,0xFF,0x7D,//Black-GROUP2
//0xEF,0xFF,0xF3,0xFF,0xFF,0xFF,0xEF,0x7F,0x7F,0xFF,0x2D,//Black-GROUP3
//0xEF,0xDE,0xF3,0x7F,0x7F,0xFF,0x3C,0x7F,0x7F,0xFF,0x3F,//Black-GROUP4
//0xFD,0xFF,0xB7,0xEF,0xAD,0x2D,0xEF,0x7D,0xBE,0x7F,0xEF,//Black-GROUP5
//0x6F,0xFF,0xBF,0xEF,0x6F,0x6F,0xEF,0xEF,0x3D,0xAF,0xEF,//Black-GROUP6
//0xEF,0xFF,0xFF,0xEF,0xEF,0xEF,0xEF,0x6F,0xBF,0xAF,0xEF,//Black-GROUP7
//0xEF,0xBE,0xFF,0x6F,0x7F,0xEF,0xEF,0xFF,0xFF,0xFF,0xEF,//Black-GROUP8
//0xEF,0xFB,0xF3,0xA8,0xFF,0xFF,0xEF,0xFF,0xFF,0xFF,0xFF,//White-GROUP1
//0xEF,0xDE,0xF3,0xBF,0x7F,0xFF,0xBE,0x7F,0x7F,0xFF,0x7D,//White-GROUP2
//0xEF,0xFF,0xF3,0xFF,0xFF,0xFF,0xEF,0x7F,0x7F,0xFF,0x2D,//White-GROUP3
//0xEF,0xDE,0xF3,0x7F,0x7F,0xFF,0x3C,0x7F,0x7F,0xFF,0x3F,//White-GROUP4
//0xFD,0xFF,0xB7,0xEF,0xAD,0x2D,0xEF,0x2D,0x2D,0x7F,0xEF,//White-GROUP5
//0x6F,0xFF,0xF7,0xEF,0xAF,0xEF,0xEF,0xED,0xFD,0x6F,0xEF,//White-GROUP6
//0xEF,0xFF,0xFF,0xEF,0xEF,0xEF,0xEF,0x6F,0xFF,0xED,0xEF,//White-GROUP7
//0x7F,0xD5,0xFF,0xEF,0xEF,0xEF,0xEF,0xFF,0xFF,0xFF,0xEF,//White-GROUP8
//0xEF,0xFB,0xF3,0x6A,0xFF,0xFF,0xEF,0xEF,0xEF,0xFF,0xAF,//Yellow-GROUP1
//0xEF,0xDE,0xF3,0xBF,0x7F,0xFF,0xBE,0x7F,0x7F,0xFF,0x7D,//Yellow-GROUP2
//0xEF,0xFF,0xF3,0xFF,0xFF,0xFF,0xEF,0x7F,0x7F,0xFF,0x2D,//Yellow-GROUP3
//0xEF,0xDE,0xF3,0x7F,0x7F,0xFF,0x3C,0x7F,0x7F,0xFF,0x3F,//Yellow-GROUP4
//0xFD,0xF7,0xB5,0xEF,0xBF,0x2D,0xEF,0xF7,0xBF,0xAF,0xEF,//Yellow-GROUP5
//0x6F,0xF7,0xFF,0xEF,0x6F,0x6F,0xEF,0xEF,0xFE,0x6F,0xEF,//Yellow-GROUP6
//0xEF,0xFF,0xF7,0xEF,0xEF,0xEF,0xEF,0xBF,0xAF,0x6F,0xEF,//Yellow-GROUP7
//0x7F,0xF5,0xFF,0xEF,0xEF,0xEF,0xEF,0xFF,0xFF,0xFF,0xEF,//Yellow-GROUP8
//0xEF,0xF7,0xF3,0xEF,0x35,0xFF,0xEF,0xEF,0xEF,0xFF,0x2E,//Red-GROUP1
//0xEF,0xDE,0xF3,0xBF,0x7F,0xFF,0xBE,0x7F,0x7F,0xFF,0x7D,//Red-GROUP2
//0xEF,0xFF,0xF3,0xFF,0xFF,0xFF,0xEF,0x7F,0x7F,0xFF,0x2D,//Red-GROUP3
//0xEF,0xDE,0xF3,0x7F,0x7F,0xFF,0x3C,0x7F,0x7F,0xFF,0x3F,//Red-GROUP4
//0x6F,0xF7,0xD2,0xEF,0x7F,0x7F,0xEF,0xEF,0xEC,0x3C,0xEF,//Red-GROUP5
//0xAF,0xFD,0xF6,0xEF,0x7F,0xEF,0xEF,0x7F,0xEC,0x3C,0xEF,//Red-GROUP6
//0xEF,0xFF,0xBD,0xEF,0xEF,0xBF,0xEF,0xEF,0xEF,0x2D,0xEF,//Red-GROUP7
//0xEF,0xFF,0xB4,0xFF,0xF5,0xEF,0xEF,0xBE,0xBD,0x3F,0xEF,//Red-GROUP8
//0xEF,0xFF,0xFF,0xA8,0xFF,0xFF,0xEF,0xFF,0xFF,0xFF,0xFF,//Power-GROUP1
//0xEF,0xFF,0xFF,0xBF,0x7F,0xFF,0xBE,0x7F,0x7F,0xFF,0x7D,//Power-GROUP2
//0xEF,0xFF,0xFF,0xFF,0xFF,0xFF,0xEF,0x7F,0x7F,0xFF,0x2D,//Power-GROUP3
//0xEF,0xFF,0xFF,0x7F,0x7F,0xFF,0x3C,0x7F,0x7F,0xFF,0x3F,//Power-GROUP4
//0xFD,0xBF,0xBA,0xEF,0xBF,0xEF,0xEF,0x3C,0xBE,0xAF,0xEF,//Power-GROUP5
//0x6F,0xBF,0xBA,0xEF,0x6F,0x6F,0xEF,0xEF,0xFE,0x6F,0xEF,//Power-GROUP6
//0xEF,0xBF,0xBA,0xEF,0xEF,0xEF,0xEF,0x6F,0xBF,0xAF,0xEF,//Power-GROUP7
//0x7F,0xBA,0xFF,0xEF,0xEF,0xEF,0xEF,0xFF,0xFF,0xFF,0xEF,//Power-GROUP8    

0x00,0x1E,0x78,0x20,0x1E,0x14,0x02,//VGHL,VSHL_0,VSH_1,VSL_1,VSHL_1,VCOM,PLL
0xEF,0x7F,0xFF,0xFF,0xFF,0x3C,0x7F,0x76,0x76,0xFF,0xEF,//VCOM-GROUP1
0x7F,0x7F,0xFF,0x7F,0xAF,0xEF,0x3F,0xAF,0x7F,0xEF,0x3F,//VCOM-GROUP2
0xEF,0x7F,0xFF,0x7F,0x7F,0xFF,0xBE,0xBC,0xD5,0xFF,0xEF,//VCOM-GROUP3
0xEF,0x7F,0xFF,0x7F,0xFF,0xFF,0x00,0xBE,0xB4,0x3C,0xEF,//VCOM-GROUP4
0xEF,0x7F,0xFF,0xAF,0xEF,0xFF,0xEF,0xFF,0xFF,0xFF,0xFF,//VCOM-GROUP5
0xFF,0x7F,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//VCOM-GROUP6
0xFF,0x7F,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//VCOM-GROUP7
0xFF,0x7F,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//VCOM-GROUP8
0xEF,0xDF,0xDE,0x7D,0xFF,0x76,0xEF,0x76,0x76,0xFF,0xEF,//Black-GROUP1
0x7F,0xDE,0xDE,0x7F,0xAF,0xEF,0x3F,0xAF,0x7F,0xEF,0x3F,//Black-GROUP2
0xEF,0xDE,0xFE,0x7F,0x7F,0xFF,0xBE,0xEF,0x6C,0x7E,0xEF,//Black-GROUP3
0xEF,0xDE,0xDE,0x6F,0x7F,0xFF,0x7E,0x3D,0xEF,0xFE,0xED,//Black-GROUP4
0xEF,0xFF,0xFF,0x7D,0x3F,0xED,0x6F,0xBD,0xAE,0xFF,0x6F,//Black-GROUP5
0x6F,0xFB,0xFF,0x7F,0xBE,0xED,0xEF,0xFD,0xFF,0xFF,0xEF,//Black-GROUP6
0xEF,0xFF,0xFA,0x7E,0xFD,0x7A,0xEF,0x7F,0xAF,0xEF,0xEF,//Black-GROUP7
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//Black-GROUP8
0xEF,0xFB,0xDE,0xA9,0xFF,0x6A,0xEF,0xFF,0xFF,0xFF,0xEF,//White-GROUP1
0x7F,0xDE,0xDE,0x7F,0xAF,0xEF,0x3F,0xAF,0x7F,0xEF,0x3F,//White-GROUP2
0xEF,0xDE,0xFF,0x7F,0x7F,0xFF,0xBE,0xEF,0x6C,0x7F,0xEF,//White-GROUP3
0xEF,0xDE,0xDE,0xBF,0xEF,0xFF,0x3E,0xFE,0xEF,0x6F,0xFD,//White-GROUP4
0xEF,0xDF,0xFF,0xAF,0x7D,0xFF,0x2F,0x35,0x00,0xFF,0xEF,//White-GROUP5
0xEF,0xF7,0xF7,0xA3,0xEF,0x7F,0xEF,0xBF,0x3F,0x7F,0xEF,//White-GROUP6
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//White-GROUP7
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//White-GROUP8
0xEF,0xDF,0xDE,0x25,0xFF,0xAD,0xEF,0x76,0x76,0xFF,0xEF,//Yellow-GROUP1
0x7F,0xDE,0xDE,0x7F,0xAF,0xEF,0x3F,0xAF,0x7F,0xEF,0x3F,//Yellow-GROUP2
0xEF,0xDE,0xFE,0x7F,0x7F,0xFF,0xBE,0x37,0xBD,0xA6,0xBF,//Yellow-GROUP3
0xEF,0x9D,0xDF,0xBF,0x7F,0xFE,0xBF,0xEF,0x25,0x3F,0xAF,//Yellow-GROUP4
0xEF,0xFF,0xFD,0x6F,0xFF,0xFF,0xEF,0xBD,0xBE,0xBF,0xEF,//Yellow-GROUP5
0xEF,0xFD,0xFF,0xAF,0x7F,0x7F,0xEF,0xBF,0xFF,0xFF,0xEF,//Yellow-GROUP6
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//Yellow-GROUP7
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//Yellow-GROUP8
0xEF,0xDF,0xDE,0x0C,0xFF,0xEF,0xEF,0xFF,0xFF,0xFF,0xEF,//Red-GROUP1
0x7F,0xDE,0xDE,0x7F,0xAF,0xEF,0x3F,0xAF,0x7F,0xEF,0x3F,//Red-GROUP2
0xEF,0xDE,0xFF,0x7F,0x7F,0xFF,0xBE,0xEF,0x6C,0x7E,0xEF,//Red-GROUP3
0xEF,0xF2,0x9D,0xEF,0xED,0x7D,0x7E,0x6F,0x7D,0x2D,0x6F,//Red-GROUP4
0x6F,0x94,0xFF,0xEF,0x2D,0x7D,0xEF,0x2F,0xFF,0xFF,0xEF,//Red-GROUP5
0x6F,0x94,0xFF,0xEF,0xBE,0x7D,0xEF,0xFD,0xFF,0xFF,0xEF,//Red-GROUP6
0xEF,0xD6,0xB4,0xEF,0xBD,0xF8,0xEF,0x2F,0xBF,0xBF,0xEF,//Red-GROUP7
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//Red-GROUP8
0xEF,0xFF,0xFF,0xFF,0xFF,0x3C,0x7F,0x76,0x76,0xFF,0xEF,//Power-GROUP1
0x7F,0xFF,0xFF,0x7F,0xAF,0xEF,0x3F,0xAF,0x7F,0xEF,0x3F,//Power-GROUP2
0xEF,0xFF,0xBA,0x7F,0x7F,0xFF,0xBE,0xEF,0x00,0x30,0xEF,//Power-GROUP3
0xEF,0xFB,0xFF,0x2E,0x00,0xFF,0xEF,0xFF,0xFF,0xFF,0xFF,//Power-GROUP4
0xEF,0xFF,0xFF,0xBD,0xFF,0xEE,0xEF,0xED,0xFF,0xFF,0xEF,//Power-GROUP5
0xEF,0xFF,0xBF,0xBE,0xB4,0xBE,0xEF,0x2D,0xEF,0xFD,0xEF,//Power-GROUP6
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//Power-GROUP7
0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,//Power-GROUP8
};

void EPD_interface_init(void)
{

	 GPIO_InitTypeDef gpio_init_struct;  
    __HAL_RCC_GPIOE_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
                          
    // 修改这里：增加PD11作为从机CS引脚
    gpio_init_struct.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_11;  /* 增加PIN_11 */
    gpio_init_struct.Mode = GPIO_MODE_OUTPUT_PP;            /* 推挽输出 */
    gpio_init_struct.Pull = GPIO_PULLUP;                    /* 上拉 */
    gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;          /* 高速 */
    HAL_GPIO_Init(GPIOD, &gpio_init_struct);                /* 初始化引脚 */           
    
    gpio_init_struct.Pin = GPIO_PIN_14 | GPIO_PIN_15;       /* PE14, PE15 */
    HAL_GPIO_Init(GPIOE, &gpio_init_struct);                /* 初始化引脚 */           

    gpio_init_struct.Pin = GPIO_PIN_13;                     /* PE13 (BUSY) */
    gpio_init_struct.Mode = GPIO_MODE_INPUT;                /* 输入 */
    gpio_init_struct.Pull = GPIO_PULLUP;                    /* 上拉 */
    gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;          /* 高速 */
    HAL_GPIO_Init(GPIOE, &gpio_init_struct);                /* 设置引脚模式 */
    
    // 初始化所有输出引脚
    EPD_Rest          = 0;             
    E_Paper_DC        = 0;           
    E_Paper_CS        = 1;           // 默认不选中主机（CS高电平有效）
    E_Paper_SLAVE_CS  = 1;           // 默认不选中从机（CS高电平有效）
    E_Paper_SCK       = 0;           
    E_Paper_SDI       = 0;           
}

void E_SDI_IN(void)
{
	GPIO_InitTypeDef gpio_init_struct;  
	__HAL_RCC_GPIOD_CLK_ENABLE();
	gpio_init_struct.Pin = GPIO_PIN_10;                       /* KEY0引脚 */
	gpio_init_struct.Mode = GPIO_MODE_INPUT;                    /* 输入 */
	gpio_init_struct.Pull = GPIO_PULLUP;                        /* 上拉 */
	gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;              /* 高速 */
	HAL_GPIO_Init(GPIOD, &gpio_init_struct);           /* KEY0引脚模式设置,上拉输入 */
}	


void E_SDI_OUT(void)
{
	GPIO_InitTypeDef gpio_init_struct;  
	 __HAL_RCC_GPIOD_CLK_ENABLE();	                      
	gpio_init_struct.Pin = GPIO_PIN_10;                   /* LED0引脚 */
	gpio_init_struct.Mode = GPIO_MODE_OUTPUT_PP;            /* 推挽输出 */
	gpio_init_struct.Pull = GPIO_PULLUP;                    /* 上拉 */
	gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;          /* 高速 */
	HAL_GPIO_Init(GPIOD, &gpio_init_struct);       /* 初始化LED0引脚 */   	  			
}
void EPD_Check_Busy(void)
{
  while(1)
  {	 //=1 BUSY
     if(E_Paper_BUSY==1)
		 {
//			 delay_ms(500);
			 break;
		 }			 
  }  	
}


void init_global_pata(void)
{

	LCM.LCM_LCD_XSIZE   = LCD_XSIZE ;
	LCM.LCM_LCD_YSIZE   = LCD_YSIZE ;	
	LCM.LCM_Type_Status=W_B_R_Status;		
	LCM.LCM_OTP_Status = OTP_Status;	

	
	EPD_setting.V1 = wf_data[1];	
	EPD_setting.V2 = wf_data[2];
	EPD_setting.V3 = wf_data[3];
	EPD_setting.V4 = wf_data[4];
	EPD_setting.VCOM = wf_data[5];
	EPD_setting.Frame = wf_data[6];	
	
	memset((uint8_t*)Display_pattern,NULL,sizeof(Pattern_InitTypeDef));
	usart_cmd_play_enable = 0;
}




// ==================== CS控制函数 ====================
void EPD_Select_None(void)
{
    E_Paper_CS = 1;
    E_Paper_SLAVE_CS = 1;
}

void EPD_Select_Master(void)
{
    E_Paper_CS = 0;
    E_Paper_SLAVE_CS = 1;
}

void EPD_Select_Slave(void)
{
    E_Paper_CS = 1;
    E_Paper_SLAVE_CS = 0;
}

void EPD_Select_Both(void)
{
    E_Paper_CS = 0;
    E_Paper_SLAVE_CS = 0;
}

// ==================== 基础SPI函数 ====================
void EPD_SPI_Write(unsigned char value)
{
    unsigned char i;
    E_Paper_SCK = 0;
    for(i=0; i<8; i++)
    {
        E_Paper_SCK = 0;			 
        if(value & 0x80)
           E_Paper_SDI = 1;
        else
           E_Paper_SDI = 0;
        delay_us(1);
        E_Paper_SCK = 1;
        delay_us(1);
        value = (value << 1);
    }
    E_Paper_SCK = 0;
}

unsigned char EPD_SPI_Read(void)
{
    unsigned char rdata = 0;
    unsigned char i;
    for(i=0; i<8; i++)
    {
        E_Paper_SCK = 0;
        delay_us(4);
        E_Paper_SCK = 1;
        delay_us(4);
        rdata <<= 1;
        if(E_READ_SDI) rdata |= 0x01;
    }
    E_Paper_SCK = 0;
    return rdata;
}
// ==================== 基础写入函数（内部使用）====================
static void EPD_WriteCMD_PreSelected(unsigned char command)
{
    E_SDI_OUT();
    E_Paper_DC = 0;       // command write
    delay_us(10);
    EPD_SPI_Write(command);
}

static void EPD_WriteDATA_PreSelected(unsigned char data)
{
    E_SDI_OUT();
    E_Paper_DC = 1;       // data write
    delay_us(10);
    EPD_SPI_Write(data);
}

// ==================== 1. 分开写入函数 ====================
// 写入命令到主机
void EPD_WriteCMD_ToMaster(unsigned char command)
{
    EPD_Select_Master();
    EPD_WriteCMD_PreSelected(command);
    EPD_Select_None();
}

// 写入命令到从机
void EPD_WriteCMD_ToSlave(unsigned char command)
{
    EPD_Select_Slave();
    EPD_WriteCMD_PreSelected(command);
    EPD_Select_None();
}

// 写入数据到主机
void EPD_WriteDATA_ToMaster(unsigned char data)
{
    EPD_Select_Master();
    EPD_WriteDATA_PreSelected(data);
    EPD_Select_None();
}

// 写入数据到从机
void EPD_WriteDATA_ToSlave(unsigned char data)
{
    EPD_Select_Slave();
    EPD_WriteDATA_PreSelected(data);
    EPD_Select_None();
}

// 批量写入数据到主机
void EPD_WriteMultiData_ToMaster(unsigned char *data, unsigned int len)
{
    if(len == 0 || data == NULL) return;
    
    EPD_Select_Master();
    for(unsigned int i=0; i<len; i++)
    {
        EPD_WriteDATA_PreSelected(data[i]);
    }
    EPD_Select_None();
}

// 批量写入数据到从机
void EPD_WriteMultiData_ToSlave(unsigned char *data, unsigned int len)
{
    if(len == 0 || data == NULL) return;
    
    EPD_Select_Slave();
    for(unsigned int i=0; i<len; i++)
    {
        EPD_WriteDATA_PreSelected(data[i]);
    }
    EPD_Select_None();
}

// ==================== 2. 同时写入函数（广播）====================
// 同时写入命令到两个设备
void EPD_WriteCMD_ToBoth(unsigned char command)
{
    EPD_Select_Both();
    EPD_WriteCMD_PreSelected(command);
    EPD_Select_None();
}

// 同时写入数据到两个设备
void EPD_WriteDATA_ToBoth(unsigned char data)
{
    EPD_Select_Both();
    EPD_WriteDATA_PreSelected(data);
    EPD_Select_None();
}

// 同时批量写入数据到两个设备
void EPD_WriteMultiData_ToBoth(unsigned char *data, unsigned int len)
{
    if(len == 0 || data == NULL) return;
    
    EPD_Select_Both();
    for(unsigned int i=0; i<len; i++)
    {
        EPD_WriteDATA_PreSelected(data[i]);
    }
    EPD_Select_None();
}

// ==================== 3. 灵活的写入函数 ====================


// 写入命令到指定目标
void EPD_WriteCMD_Target(EP_Target_t target, unsigned char command)
{
    switch(target)
    {
        case TARGET_MASTER:
            EPD_WriteCMD_ToMaster(command);
            break;
        case TARGET_SLAVE:
            EPD_WriteCMD_ToSlave(command);
            break;
        case TARGET_BOTH:
            EPD_WriteCMD_ToBoth(command);
            break;
        default:
            break;
    }
}

// 写入数据到指定目标
void EPD_WriteDATA_Target(EP_Target_t target, unsigned char data)
{
    switch(target)
    {
        case TARGET_MASTER:
            EPD_WriteDATA_ToMaster(data);
            break;
        case TARGET_SLAVE:
            EPD_WriteDATA_ToSlave(data);
            break;
        case TARGET_BOTH:
            EPD_WriteDATA_ToBoth(data);
            break;
        default:
            break;
    }
}

// 批量写入数据到指定目标
void EPD_WriteMultiData_Target(EP_Target_t target, unsigned char *data, unsigned int len)
{
    if(len == 0 || data == NULL) return;
    
    switch(target)
    {
        case TARGET_MASTER:
            EPD_WriteMultiData_ToMaster(data, len);
            break;
        case TARGET_SLAVE:
            EPD_WriteMultiData_ToSlave(data, len);
            break;
        case TARGET_BOTH:
            EPD_WriteMultiData_ToBoth(data, len);
            break;
        default:
            break;
    }
}

// ==================== 4. 读取函数（必须分开读取）====================
// 从主机读取寄存器
void EPD_Read_reg_FromMaster(unsigned char reg, unsigned char *pbuf, unsigned int len)
{
    if(pbuf == NULL || len == 0) return;
    
    // 发送读取命令到主机
    EPD_Select_Master();
    EPD_WriteCMD_PreSelected(reg);
    
    // 切换为输入模式并读取数据
    E_SDI_IN();
    E_Paper_DC = 1;               // data read
    delay_ms(10);                 // 短暂延迟
    
    for(unsigned int i=0; i<len; i++)
    {
        pbuf[i] = EPD_SPI_Read();
    }
    
    EPD_Select_None();
    E_SDI_OUT();  // 恢复输出模式
}

// 从从机读取寄存器
void EPD_Read_reg_FromSlave(unsigned char reg, unsigned char *pbuf, unsigned int len)
{
    if(pbuf == NULL || len == 0) return;
    
    // 发送读取命令到从机
    EPD_Select_Slave();
    EPD_WriteCMD_PreSelected(reg);
    
    // 切换为输入模式并读取数据
    E_SDI_IN();
    E_Paper_DC = 1;               // data read
    delay_ms(10);                 // 短暂延迟
    
    for(unsigned int i=0; i<len; i++)
    {
        pbuf[i] = EPD_SPI_Read();
    }
    
    EPD_Select_None();
    E_SDI_OUT();  // 恢复输出模式
}

// 读取单个字节
unsigned char EPD_ReadByte_FromMaster(unsigned char reg)
{
    unsigned char data = 0;
    EPD_Read_reg_FromMaster(reg, &data, 1);
    return data;
}

unsigned char EPD_ReadByte_FromSlave(unsigned char reg)
{
    unsigned char data = 0;
    EPD_Read_reg_FromSlave(reg, &data, 1);
    return data;
}




//void EPD_SPI_Write(unsigned char value)
//{
//    unsigned char i;
//    E_Paper_SCK = 0;
//    for(i=0; i<8; i++)
//    {
//        E_Paper_SCK = 0;			 
//        if(value & 0x80)
//           E_Paper_SDI = 1;
//        else
//           E_Paper_SDI = 0;
//			  delay_us(1);
//        E_Paper_SCK = 1;
//				delay_us(1);
//        value = (value << 1);
//    }
//		 E_Paper_SCK = 0;
//}


void EPD_WriteCMD(unsigned char command)
{
    E_SDI_OUT();          //SDA out mode
    E_Paper_CS = 0;
    E_Paper_DC = 0;		// command write
    delay_us(10);
    EPD_SPI_Write(command);
    E_Paper_CS = 1;
}

void EPD_WriteDATA(unsigned char data)
{
   // E_Paper_CS = 1;
    E_Paper_CS = 0;
    E_Paper_DC = 1;		// data write
    delay_us(10);
    EPD_SPI_Write(data);
    E_Paper_CS = 1;
}

//unsigned char EPD_SPI_Read(void)
//{
//	unsigned char rdata =0;
//	unsigned char i;
//	for(i=0;i<8;i++)
//	{
//		E_Paper_SCK = 0;
//		delay_us(4);
//		E_Paper_SCK = 1;
//		delay_us(4);
//		rdata <<= 1;
//		if(E_READ_SDI) rdata |=0x01;
//		
//	}
//	E_Paper_SCK = 0;
//	return rdata;
//}

void  EPD_Read_reg(unsigned char  reg,unsigned char * pbuf,unsigned int len)
{
   unsigned int  i = 0;
	EPD_WriteCMD(reg);    
	E_SDI_IN();           //SDA  input mode
	E_Paper_DC = 1;		    //data read
	E_Paper_CS = 0;
	delay_ms(40);
	

	for(i=0;i<len;i++)
	{
		*(pbuf ++)= EPD_SPI_Read();
	}
	E_Paper_CS = 1;
	      
	  
}




void EPD_sleep(void)
{
   	EPD_WriteCMD(0X02);    	 //power off
	 	
		EPD_Check_Busy();        //waiting for the electronic paper IC to release the idle signal
	  delay_ms(100);
		EPD_WriteCMD(0X07);  	   //deep sleep
		EPD_WriteDATA(0xA5);
}

void EPD_refresh(void)
{
	
		EPD_WriteCMD(0x04); //R04H (PON): Power ON Command
		EPD_Check_Busy();        //waiting for the electronic paper IC to release the idle signal	
		EPD_WriteCMD(0x12);			//DISPLAY REFRESH 	
		EPD_Check_Busy();        //w
}	

void EPD_refresh_17H(void)
{
	  EPD_WriteCMD(0x17);
    EPD_WriteDATA(0xa5);	
		EPD_Check_Busy();
}

void EPD_display_White(void)
{
    unsigned long i;

    EPD_WriteCMD(R10_DTM);
    for(i=0;i<IMAGE_SIZE;i++)
    {
      EPD_WriteDATA(0x11);
    }
    
	EPD_refresh_17H();
	EPD_WriteCMD(0x07);
	EPD_WriteDATA(0xa5);		

}


void EPD_display_yellow(void)
{
	  unsigned long i;
    EPD_WriteCMD(R10_DTM);
    for(i=0;i<IMAGE_SIZE;i++)
    {
      EPD_WriteDATA(0xaa);
    }
	EPD_refresh_17H();
	EPD_WriteCMD(0x07);
	EPD_WriteDATA(0xa5);		
}	

void EPD_display_Black(void)
{
    unsigned long i;

    EPD_WriteCMD(R10_DTM);
    for(i=0;i<(IMAGE_SIZE);i++)
    {
      EPD_WriteDATA(0x00);
    }
	EPD_refresh_17H();
	EPD_WriteCMD(0x07);
	EPD_WriteDATA(0xa5);		
}

void EPD_display_RedKBlack_H(void)
{
    unsigned int EPD_X,EPD_Y;
	  unsigned int x_size=0;
  	x_size=(LCD_XSIZE%8)?(LCD_XSIZE/8+1):(LCD_XSIZE/8);
	 // EPD_BUSY_LED(EPD_state_busy);
    //write  black and white data
	//  EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x10);	      
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {	
       for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				  if(LCM.LCM_Type_Status==W_B_R_Status)
					{
				 
				     if(EPD_X<x_size/3)
               EPD_WriteDATA(EPD_White);
				     else if(EPD_X<x_size*2/3)
				       EPD_WriteDATA(EPD_White);
			  	   else 
					     EPD_WriteDATA(EPD_Black);
				 }
				else  //W_B_Status
				{
				
				 if(EPD_X<x_size*1/2)
				    EPD_WriteDATA(EPD_White);
			  	else 
					  EPD_WriteDATA(EPD_Black);					
				}
					
       }
		}		
		 //write  red and white data
		//EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x13);		   
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {
      for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				 
				  if(LCM.LCM_Type_Status==W_B_R_Status)
					{
				     if(EPD_X<x_size/3)
               EPD_WriteDATA(EPD_Red);
			      else 
				      EPD_WriteDATA(0x00);
				  }
					else
					  EPD_WriteDATA(0x00);
					
       }
		}
    //Refresh
		EPD_refresh();//EPD_refresh		
		EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}



void EPD_display_RedKBlack_V(void)
{
    unsigned int EPD_X,EPD_Y;
	  unsigned int x_size=0;
  	x_size=(LCD_XSIZE%8)?(LCD_XSIZE/8+1):(LCD_XSIZE/8);
   //	EPD_BUSY_LED(EPD_state_busy);
    //write  black and white data
	  //EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x10);	      
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {	
       for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				 
				  if(LCM.LCM_Type_Status==W_B_R_Status)
					{
				 
				    if(EPD_Y<=LCD_YSIZE/3)
              EPD_WriteDATA(EPD_White);
				    else if(EPD_Y<=LCD_YSIZE*2/3)
				      EPD_WriteDATA(EPD_White);
			  	  else 
					    EPD_WriteDATA(EPD_Black);
				  }
				 else
				 {
				 
					  if(EPD_Y<=LCD_YSIZE*1/2)
				      EPD_WriteDATA(EPD_White);
			  	  else 
					    EPD_WriteDATA(EPD_Black);
				 
				 }
				 	
       }
		}		
		 //write  red and white data
		//EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x13);		   
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {
      for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				  if(LCM.LCM_Type_Status==W_B_R_Status)
				  {
				 
				    if(EPD_Y<=LCD_YSIZE/3)
              EPD_WriteDATA(EPD_Red);
			  	   else 
					     EPD_WriteDATA(0x00);
					}
          else
       		  EPD_WriteDATA(0x00);				
       }
		}
    //Refresh
		EPD_refresh();//EPD_refresh		
		EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}


void EPD_display_BlackKRed_H(void)
{
    unsigned int EPD_X,EPD_Y;
	  unsigned int x_size=0;
  	x_size=(LCD_XSIZE%8)?(LCD_XSIZE/8+1):(LCD_XSIZE/8);
	 // EPD_BUSY_LED(EPD_state_busy);
    //write  black and white data
	 // EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x10);	      
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {	
			
       for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				  if(LCM.LCM_Type_Status==W_B_R_Status)
				  {
				 
				     if(EPD_X<x_size/3)
               EPD_WriteDATA(EPD_Black);
			  	   else 
					     EPD_WriteDATA(EPD_White);
				  }
					else
					{
				     if(EPD_X<x_size/2)
               EPD_WriteDATA(EPD_Black);
			  	   else 
					     EPD_WriteDATA(EPD_White);			
					
          }
       }
		}		
		 //write  red and white data
		//EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x13);		   
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {
      for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				  if(LCM.LCM_Type_Status==W_B_R_Status)
				  {
				 
				    if(EPD_X<x_size*2/3)
              EPD_WriteDATA(0x00);
			  	   else 
					    EPD_WriteDATA(EPD_Red);
				   }
					else
					 EPD_WriteDATA(0x00);	
       }
		}
    //Refresh
		EPD_refresh();//EPD_refresh		
		EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}



void EPD_display_BlackKRed_V(void)
{
    unsigned int EPD_X,EPD_Y;
	  unsigned int x_size=0;
  	x_size=(LCD_XSIZE%8)?(LCD_XSIZE/8+1):(LCD_XSIZE/8);
	 // EPD_BUSY_LED(EPD_state_busy);
    //write  black and white data
	  //EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x10);	      
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {	
       for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				  if(LCM.LCM_Type_Status==W_B_R_Status)
				  {
				    
				     if(EPD_Y<=LCD_YSIZE/3)
               EPD_WriteDATA(EPD_Black);
				     else if(EPD_Y<=LCD_YSIZE*2/3)
				       EPD_WriteDATA(EPD_White);
			       else 
				       EPD_WriteDATA(EPD_White);
					}
					else
					{
						 if(EPD_Y<=LCD_YSIZE/2)
               EPD_WriteDATA(EPD_Black);
				     else 
				       EPD_WriteDATA(EPD_White);																
					}	
       }
		}		
		 //write  red and white data
	//	EPD_RAM_XY_address_counter();
    EPD_WriteCMD(0x13);		   
	  for(EPD_Y=0; EPD_Y<LCD_YSIZE; EPD_Y++)
    {
      for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
         if(LCM.LCM_Type_Status==W_B_R_Status)
				  { 
				     if(EPD_Y<=LCD_YSIZE*2/3)
               EPD_WriteDATA(0x00);
			  	    else 
					      EPD_WriteDATA(EPD_Red);
					}
					else
						 EPD_WriteDATA(0x00);
					
       }
		}
    //Refresh
		EPD_refresh();//EPD_refresh		
		EPD_sleep();//EPD_sleep,Sleep instruction is necessary, please do not delete!!!	
}


void EPD_display_Red(void)
{
	  unsigned long i;
    EPD_WriteCMD(R10_DTM);
    for(i=0;i<IMAGE_SIZE;i++)
    {
      EPD_WriteDATA(0xff);
    }
	EPD_refresh_17H();
	EPD_WriteCMD(0x07);
	EPD_WriteDATA(0xa5);		

}


#define BLOCK_SIZE      256
   
void EPD_display_BMP(const unsigned char* WK_data,const unsigned char* R_data)
{
    unsigned long i;
	 unsigned long block_idx;
    unsigned long a_index = 0, b_index = 0;

    EPD_WriteCMD_ToBoth(0x10);  	
    for(i=0;i<IMAGE_YSIZE;i++)
    {
			 block_idx = i / BLOCK_SIZE;
			
			  if((block_idx & 0x01) == 0)  // 偶数块 -> Master
        {
          
       
      EPD_WriteDATA_ToMaster(gImage_BW[i]);

		 }

   else  // 奇数块 -> Slave
        {
      EPD_WriteDATA_ToSlave(gImage_BW[i]);
			
				}
			
			
    }
    
    EPD_WriteCMD_ToBoth(0x04);
		delay_ms(100);
    EPD_Check_Busy();
		

//    
    EPD_WriteCMD_ToBoth(0x12);
    EPD_WriteDATA_ToBoth(0x00);
		delay_ms(100);
    EPD_Check_Busy();
   
  
    EPD_WriteCMD_ToBoth(R02_POF);
    EPD_WriteDATA_ToBoth(0x00);
			delay_ms(100);
    EPD_Check_Busy();
	
 }

void Display_Black(uint16_t x, uint16_t y)
{
  EPD_initial();
	EPD_display_Black();
}

void Display_White(uint16_t x, uint16_t y)
{
  EPD_initial();
	EPD_display_White();
}

void Display_Red(uint16_t x, uint16_t y)
{
	EPD_initial();
	EPD_display_Red();
   
}

void Display_Yellow(uint16_t x, uint16_t y)
{
	EPD_initial();
	EPD_display_yellow();
   
}

void Display_Picture(uint16_t x, uint16_t y)
{
//  EPD_initial();
	EPD_display_BMP(gImage_BW,gImage_R);
	
}

void Display_Picture_1(uint16_t x, uint16_t y)
{
//  EPD_initial();
	//EPD_display_BMP(Image_BWRY,gImage_R);
	
}

void EPD_Write_LUT(unsigned char *LUTbuf,unsigned int len)
{	
	 unsigned int i;
	 for(i=0;i<len;i++)
     EPD_WriteDATA(*(LUTbuf++));
}
 
void Display_VRedKBlack(uint16_t x, uint16_t y)
{
  EPD_initial();
	EPD_display_RedKBlack_V();
}
void Display_HRedKBlack(uint16_t x, uint16_t y)
{
  EPD_initial();
	EPD_display_RedKBlack_H();
}
void Display_VBlackKRed(uint16_t x, uint16_t y)
{
  EPD_initial();
	EPD_display_BlackKRed_V();
}
void Display_HBlackKRed(uint16_t x, uint16_t y)
{
  EPD_initial();
	EPD_display_BlackKRed_H();
}





void EPD_display_B_W_R_Y_B(void)
{
    unsigned long i;

    EPD_WriteCMD(R10_DTM);
    for(i=0;i<(IMAGE_SIZE/4);i++)
    {
      EPD_WriteDATA(0x00);
    }
		for(i=0;i<(IMAGE_SIZE/4);i++)
    {
      EPD_WriteDATA(0x55);
    }
		for(i=0;i<(IMAGE_SIZE/4);i++)
    {
      EPD_WriteDATA(0xff);
    }
		for(i=0;i<(IMAGE_SIZE/4);i++)
    {
      EPD_WriteDATA(0xaa);
    }
    
	EPD_refresh_17H();
	EPD_WriteCMD(0x07);
	EPD_WriteDATA(0xa5);		
}


void EPD_display_B_W_R_Y_A(void)
{
    EPD_WriteCMD(0x10); //DTM1

	  unsigned int EPD_X,EPD_Y;
	  unsigned int x_size=0;
  	x_size=(LCM.LCM_LCD_XSIZE%8)?(LCM.LCM_LCD_XSIZE/8+1):(LCM.LCM_LCD_XSIZE/8);
		x_size=x_size*2;
   
	  for(EPD_Y=0; EPD_Y<LCM.LCM_LCD_YSIZE*2; EPD_Y++)
    {	
       for(EPD_X=0; EPD_X<x_size; EPD_X++)
       {
				
				 
				     if(EPD_X<x_size/4)
               EPD_WriteDATA(0x00);
				     else if(EPD_X<x_size*2/4)
				       EPD_WriteDATA(0x55);
						  else if(EPD_X<x_size*3/4)
				       EPD_WriteDATA(0xaa);
			  	   else 
					     EPD_WriteDATA(0xff);
					 }
				 }
	EPD_refresh_17H();
	EPD_WriteCMD(0x07);
	EPD_WriteDATA(0xa5);		
}

void Display_B_W_R_Y_A(uint16_t x, uint16_t y)
{
	EPD_initial();
	EPD_display_B_W_R_Y_A();	
}

void Display_B_W_R_Y_B(uint16_t x, uint16_t y)
{
	EPD_initial();
	EPD_display_B_W_R_Y_B();	
}

void get_vcom(void)
{	
  if(vcom == 0)
  {
			
		EPD_Rest=0;
		delay_ms(10);
		EPD_Rest=1;
		delay_ms(10);
		EPD_Check_Busy();
		EPD_WriteCMD(0x4D);
		EPD_WriteDATA(0x78);

		EPD_WriteCMD(0xb4);
		EPD_WriteDATA(0xd0);

		EPD_WriteCMD(R00_PSR);
		EPD_WriteDATA(0x2F);
		EPD_WriteDATA(0xB9); 

		EPD_WriteCMD(0x06);
		EPD_WriteDATA(0x0f);  
		EPD_WriteDATA(0x2a);
		EPD_WriteDATA(0x2F);  
		EPD_WriteDATA(0x25);
		EPD_WriteDATA(0x22);
		EPD_WriteDATA(0x2e);  
		EPD_WriteDATA(0x21);

		EPD_WriteCMD(0x82);//AMV
		EPD_WriteDATA(0x80);

		EPD_WriteCMD(R04_PON);//PON
		EPD_Check_Busy();

		EPD_WriteCMD(0x80);//AMV
		EPD_WriteDATA(0xC1);
		EPD_Check_Busy();
		delay_s(2);		
		EPD_Read_reg(0x81,&vcom,1);
		EPD_WriteCMD(R02_POF);//POF
		EPD_WriteDATA(0x00);  
		EPD_Check_Busy();
//		vcom=vcom&0x7F;
  }
}

void EPD_initial(void)
{	
	uint16_t i;
	EPD_Rest=0;
	delay_ms(50);
	EPD_Rest=1;
	delay_ms(50);		
	EPD_Check_Busy(); 

	EPD_WriteCMD(0x4D);			//PWD After OTP
	EPD_WriteDATA(0x78);
	
	EPD_WriteCMD(0xae);			
	EPD_WriteDATA(0x0f);

	EPD_WriteCMD(0xBd);			
	EPD_WriteDATA(0x00);	
	
	EPD_WriteCMD(0xad);			
	EPD_WriteDATA(0x17);

	EPD_WriteCMD(0xB6);			
	EPD_WriteDATA(0x0f);

	
	EPD_WriteCMD(0x00);			
	EPD_WriteDATA(0x0f);
	EPD_WriteDATA(0xa9);



	EPD_WriteCMD(0x01);    //PWR Power setting Register 电压设置       
	EPD_WriteDATA(0x07);    //
	EPD_WriteDATA(0x00);//
	EPD_WriteDATA(EPD_setting.V1); //
	EPD_WriteDATA(EPD_setting.V2);//
	EPD_WriteDATA(EPD_setting.V3);//
	EPD_WriteDATA(EPD_setting.V4);//
	EPD_Check_Busy();
	
	EPD_WriteCMD(0x03);			//Power off Sequence Setting
	EPD_WriteDATA(0x10);
	EPD_WriteDATA(0x54);
	EPD_WriteDATA(0x44);
//	

	EPD_WriteCMD(R06_BTST);
	EPD_WriteDATA(0x0f);
	EPD_WriteDATA(0x0a);
	EPD_WriteDATA(0x2f);
	EPD_WriteDATA(0x25);
	EPD_WriteDATA(0x22);
	EPD_WriteDATA(0x2e);
	EPD_WriteDATA(0x21);	
	
	EPD_WriteCMD(0x30);     //CDI Booder 设置   POR:97
	EPD_WriteDATA(0x08);
	
	EPD_WriteCMD(0x50);			//CDI Setting
	EPD_WriteDATA(0x37);
	
	EPD_WriteCMD(0xf0);			//CDI Setting
	EPD_WriteDATA(0x5f);
	
	EPD_WriteCMD(0x61); //TRES
	EPD_WriteDATA(LCD_XSIZE/256);
	EPD_WriteDATA(LCD_XSIZE%256);
	EPD_WriteDATA(LCD_YSIZE/256);
	EPD_WriteDATA(LCD_YSIZE%256);
	
	EPD_WriteCMD(0x65);	    //resolution setting		
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x00);
	EPD_WriteDATA(0x00);
	
	EPD_WriteCMD(0xe3);			//CDI Setting
	EPD_WriteDATA(0x22);
	
//	EPD_WriteCMD(0xe7);			//CDI Setting
//	EPD_WriteDATA(0x1c);
	
	EPD_WriteCMD(0x82); 
	EPD_WriteDATA(vcom|0x80);

	EPD_WriteCMD(0xe9);			//CDI Setting
	EPD_WriteDATA(0x01);
	EPD_Check_Busy(); 
	
	EPD_WriteCMD(0x20);                            //LUT 注册
	for(i=0;i<535;i++)                               //循环次数根据不同的芯片规格有所不同
	EPD_WriteDATA(wf_data[i]);    
}
 

