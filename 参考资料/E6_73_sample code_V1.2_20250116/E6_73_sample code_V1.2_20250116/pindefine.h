/*******************************************
 * Copyright (C) 2021, Ryan Liu, Tina Liu  *
 *******************************************/
//==============================================
//            MSP430f550x pin define
//==============================================

#ifndef __PINDEFINE_H__
#define __PINDEFINE_H__

#include <msp430f5502.h>

/**********************************
MSP430f550x port define
**********************************/
//OUTPUT
//#define DC 	P5OUT_bit.P5OUT0
#define DC_L    P5OUT&=0xFE
#define DC_H    P5OUT|=0x01
//#define RSTN  P6OUT_bit.P6OUT1
#define RSTN_L  P6OUT&=0xFD
#define RSTN_H  P6OUT|=0x02
//#define CSB   P6OUT_bit.P6OUT3 
#define CSB_L  	P6OUT&=0xF7
#define CSB_H  	P6OUT|=0x08
//#define SCL  	P4OUT_bit.P4OUT7
#define SCL_L  	P4OUT&=0x7F
#define SCL_H  	P4OUT|=0x80
//#define SDA(SI0)  P4OUT_bit.P4OUT6
#define SDA_L 	P4OUT&=0xBF
#define SDA_H 	P4OUT|=0x40

//#define BS 	P5OUT_bit.P5OUT1
#define BS_L    P5OUT&=0xFD
#define BS_H    P5OUT|=0x02

//#define Switch control  P6OUT_bit.P6OUT0
#define SWC_L    P6OUT&=0xFE
#define SWC_H    P6OUT|=0x01

//========= Input ==========
// UC8154
//#define SDA_IN  P4IN_bit.P4IN6
#define SDA_IN  (P4IN&0x40)>>6
#define BUSYN 	P6IN_bit.P6IN2   
// MCU Board Button Switch
#define SW2    	P1IN_bit.P1IN5
#define SW3    	P1IN_bit.P1IN4  
#define SW4    	P1IN_bit.P1IN3
#define SW5    	P1IN_bit.P1IN2


#endif //#ifndef __PINDEFINE_H__


