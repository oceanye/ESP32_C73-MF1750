//=================================================================================================
//                   Pin Define for MCU Board V3 of HULK-II
//
// File Name : pindefine.h
// Author : Electronic Design Dept. II
// Data : 2024.09.01
// Version : 1.0
// Copyright : E Ink Holdings Inc.
//=================================================================================================
//#include "stm32f1xx.h"
#include "./SYSTEM/sys/sys.h"
#include "GPIOLIKE51.h"

#ifndef __PINDEFINE_H__
#define __PINDEFINE_H__
//#define E_Paper_BUSY          PEin(13)
//#define EPD_Rest 							PEout(14)		
//#define E_Paper_DC            PEout(15)	
//#define E_Paper_CS            PDout(8)
//#define E_Paper_SCK           PDout(9)
//#define E_Paper_SDI           PDout(10)


//==============  Standard SPI Setting   ==============//
#define SPI_CS0		8
#define SPI_CS1		8
#define SPI_CLK		  9
#define SPI_Data0	 10
#define SPI_Data1	40
#define SPI_Data2	39
#define SPI_Data3	38

//==============  I2C Setting   ==============//
//Please modify the pin number
#define I2C_SDA		10
#define I2C_SCL		11

//==============  SD Card Setting   ==============//
#define SD_CS		46
#define SD_DI		21
#define SD_DO		14
#define SD_CLK		12

//==============   GPIO Setting   ==============//
//For EPD Module
#define EPD_DC		15   // Please set it as output pin
#define EPD_RST		14   // Please set it as output pin
#define EPD_BUSY	13  // Please set it as input pin
#define EPD_BS		17  // Please set it as output pin

//For Button Switch Function
#define SW1     	48  // Please set it as input pin
#define SW2     	47  // Please set it as input pin
#define SW3			45  // Please set it as input pin
#define SW4			42  // Please set it as input pin

//For Other Function
#define IO1     	1
#define IO2_LED		2  // Please set it as output pin
#define IO13_SW_CTL	13 // Please set it as output pin
#define IO16     	16

//For EPD Power Setting
#define IO5_3V3_CTL		5	// Please set it as output pin
#define IO15_3V0_CTL	15  // Please set it as output pin

//===============================================

#define GPIO_LOW	0
#define GPIO_HIGH	1

#endif //#ifndef __PINDEFINE_H__
