//=============================================================================
// E5 3-bit Development Environment
//
// File Name : E2802-SPD1657_OTP.h
// Author : Electronic Design Dept. II
// Date : 2023.11.22
// Version : 1.1 (Support 2nd OTP Burn)
// Copyright : E Ink Holdings Inc.
//=============================================================================

#include "./SYSTEM/delay/delay.h"
#ifndef __E28xx_H__
#define __E28xx_H__


//================================
//       Constant set
//===============================

#define R00_PSR         0x00
#define R01_PWR         0x01
#define R02_POF         0x02
#define R03_POFS        0x03
#define R04_PON         0x04
#define R05_BTST1       0x05
#define R06_BTST2       0x06
#define R07_DSLP        0x07
#define R08_BTST3       0x08 
#define R09_PSAVE       0x09
#define R10_DTM         0x10
#define R11_DSP         0x11
#define R12_DRF         0x12
#define R13_IPC         0x13
#define R17_AUTO        0x17
#define R20_LUT0        0x20
#define R21_LUT1        0x21


#define R30_PLL         0x30
#define R40_TSC         0x40
#define R41_TSE         0x41
#define R42_TSW         0x42
#define R43_TSR         0x43
#define R44_GPIO        0x44
#define R50_CDI         0x50
#define R51_LPD         0x51
#define R60_TCON        0x60
#define R61_TRES        0x61
#define R70_REV         0x70
#define R71_FLG         0x71
#define R80_AMV         0x80
#define R81_VV          0x81
#define R82_VDCS        0x82
#define R83_PTLW        0x83
#define R84_TVDCS       0x84
#define R86_AGID        0x86

#define R90_PGM         0x90
#define R91_APG         0x91
#define R92_ROTP        0x92
#define R93_RSRAM       0x93

#define RA0_LOTP	    0xA0
#define RA2_PGM_CFG     0xA2
#define RA3_PGM_STAT    0xA3

#define RE0_CCSET       0xE0
#define RE3_PWS         0xE3
#define RE4_LVSEL       0xE4
#define RE5_SPIM        0xE5
#define RE6_TSSET       0xE6


//================================
//    Write OTP status
//================================
#define WRITE_OTP_OK                    0
#define WRITE_OTP_FAIL_NO_VCOM          1
#define WRITE_OTP_FAIL_HAS_Written      2
#define WRITE_OTP_FAIL_WRONG_OPERATION  3
#define WRITE_OTP_FAIL_CRC_FAIL         4
#define WRITE_OTP_OK_WITH_DATA          5
#define OTP_DATA_ADD          12

#define _imageSize   800*480/2   // Please modify the value according to your needs


#endif 

struct _epdSPI
{
	unsigned char status; // 1 : ����Ʀ^�� App ; 0 : �L��Ʀ^�� App
	unsigned char buf[10];
	unsigned char len;
};


#ifdef __E28xx_C__
#define __E28xx_EXTERN__
#else 
#define __E28xx_EXTERN__ extern
#endif
unsigned char  program_int();
//=============== Global Variable ===========================================================
__E28xx_EXTERN__ struct _epdSPI epdSPI;
extern const char customer_key[];
//=============== Function ==================================================================
//spi
__E28xx_EXTERN__ void initEPDSPI(void);

//utils
//__E28xx_EXTERN__ void delay_s(unsigned long time);
//__E28xx_EXTERN__  void delay_ms(unsigned long time);

//EPD
__E28xx_EXTERN__  void epdInitial(void);

//=============== Application ==================================================================
//main to driver ic

__E28xx_EXTERN__  void writeEPD(unsigned char spi_c, unsigned char * spi_d, unsigned int len);
__E28xx_EXTERN__  unsigned char getVCOMDC(void);
__E28xx_EXTERN__  unsigned char setVCOMDC(unsigned char vcom);
__E28xx_EXTERN__  void readOTP(unsigned char * rxBuf, unsigned int add, unsigned int len);
__E28xx_EXTERN__  void readOTP_VCOM(unsigned char * rxBuf);
__E28xx_EXTERN__  unsigned char programOTP(void);
__E28xx_EXTERN__  unsigned char programOTP_VCOM(void);
__E28xx_EXTERN__  unsigned char writeUserData(unsigned char *data, unsigned char len);
__E28xx_EXTERN__  void loadWF(const unsigned char* wf_buffer);

__E28xx_EXTERN__  void showImage(unsigned char *imageData);
__E28xx_EXTERN__  void display_Black(void);
__E28xx_EXTERN__  void display_White(void);
__E28xx_EXTERN__  void display_Red(void);
__E28xx_EXTERN__  void display_Yellow(void);
__E28xx_EXTERN__  void display_KWRY(void);

__E28xx_EXTERN__ void display_G(void);
__E28xx_EXTERN__ void display_B(void);


