/*------------------------------------------------------------------
//Purpose     : Sample configuration file
------------------------------------------------------------------*/
#ifndef _LCDCONFIG_H_
#define _LCDCONFIG_H_
//#include "pattern_api.h"
#include <stdio.h>
#include <string.h>
#include "./SYSTEM/sys/sys.h"

//typedef uint16_t


#define  define_pattern_max   40
#define  BUFFER_size          16

typedef struct
{
    void (*pt_pattern)(uint16_t,uint16_t);
    void (*pt_delays)(uint32_t);
    uint32_t delay_ms;
//    uint16_t delay_islock;
//    uint8_t bmp_id;
}Pattern_InitTypeDef;

extern Pattern_InitTypeDef Display_pattern[40];


//#define   type_name                    "M001F-H_OQC_RD0413_V01"      /* 产品型号         */
#define   LCD_XSIZE                    1024                      /* 水平大小         */
#define   LCD_YSIZE                    600                      /* 垂直大小         */
#define   IMAGE_YSIZE                    LCD_XSIZE * LCD_YSIZE /2
/******************************************************************/
#define   DisEnable                    0

#define   Enable                       1

#define   TRUE                         1
#define   FALSE                        0


#define   NO_OTP_Status                 0  //未OTP

#define   OTP_Status                    1  //已经OTP

#define   W_B_R_Y_Status                3   //黑白红电子纸 类型定义

#define   W_B_R_Status                  2   //黑白红电子纸 类型定义

#define   W_B_Status                    1   //黑白电子纸 类型定义

#define   EPD_All_refresh               0   // 全刷定义

#define   EPD_Part_refresh              1  // 局刷定义

#define   start_Is_play                 1           // 开机后，是否自动跑画面   0:不跑 1:跑

/******************************************************************/

#endif

