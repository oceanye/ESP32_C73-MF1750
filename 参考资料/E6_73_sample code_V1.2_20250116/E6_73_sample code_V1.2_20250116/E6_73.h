#ifndef __E6_73_H__
#define __E6_73__
/*************************************************************************************
 * Copyright (C) 2023 E Ink Holdings Inc. (Ryan Liu, Tina Liu) All Rights Reserved   *
 *************************************************************************************/
/**********************************
Constant set
**********************************/
#define PSR         0x00
#define PWR         0x01
#define POF         0x02
#define POFS        0x03
#define PON         0x04
#define BTST1       0x05
#define BTST2       0x06
#define DSLP        0x07
#define BTST3       0x08
#define DTM         0x10
#define DRF         0x12
#define PLL         0x30
#define CDI         0x50
#define TCON        0x60
#define TRES        0x61
#define REV         0x70
#define VDCS        0x82
#define T_VDCS      0x84
#define PWS         0xE3

#endif 


#ifdef __E6_73_C__
#define __E6_73_EXTERN__
#else 
#define __E6_73_EXTERN__ extern
#endif

__E6_73_EXTERN__ void spi_9b_init(void);
__E6_73_EXTERN__ void EPD_Init();
__E6_73_EXTERN__ void SPI_COMMAND(unsigned char dat);
__E6_73_EXTERN__ void SPI_DATA(unsigned char dat);
__E6_73_EXTERN__ unsigned char SPI_GET_DATA(void);
__E6_73_EXTERN__ void EPD_Display_White();
__E6_73_EXTERN__ void EPD_Display_Black();
__E6_73_EXTERN__ void EPD_Display_Yellow();
__E6_73_EXTERN__ void EPD_Display_Red();
__E6_73_EXTERN__ void EPD_Display_Blue();
__E6_73_EXTERN__ void EPD_Display_Green();
__E6_73_EXTERN__ void check_busy_high(void);// If BUSYN=0 then waiting
__E6_73_EXTERN__ void check_busy_low(void);// If BUSYN=1 then waiting
__E6_73_EXTERN__ void reset(void);
__E6_73_EXTERN__ void EPD_Sleep(void);
__E6_73_EXTERN__ unsigned char get_Rev(void);

