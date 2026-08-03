#define __E6_73_C__
/*************************************************************************************
 * Copyright (C) 2023 E Ink Holdings Inc. (Ryan Liu, Tina Liu) All Rights Reserved   *
 *************************************************************************************/
#include "pindefine.h"
#include "E6_73.h"
#include "delay.h"


//Check Busy
//==============================================================================

void check_busy_high(void)// If BUSYN=0 then waiting
{
delay(2000);
while(!(BUSYN));
}

void check_busy_low(void)// If BUSYN=1 then waiting
{
delay(2000);
while(BUSYN);
}

//==============================================================================
//EPD initial
//==============================================================================

void spi_9b_init(void)
{
  SCL_L;
  SDA_H;
  CSB_H;
  BS_H;//3
  DC_L;
  RSTN_H;
  SWC_H;
  delay(10);
}

void reset(void)
{
  //20220330
  //dual reset
  RSTN_L; // Reset
  delay(42000);
  delay(42000);
  delay(42000);//at least 30ms
  RSTN_H;
  delay(42000);
  delay(42000);
  delay(42000);//at least 30ms
  RSTN_L; // Reset
  delay(42000);
  delay(42000);
  delay(42000);//at least 30ms
  RSTN_H;
}


//IC initialization (parameters from Host)
void EPD_Init()
{
  reset();
  check_busy_high();
  delay(42000);
  
  //20211212
  SPI_COMMAND(0xAA);
  SPI_DATA(0x49);
  SPI_DATA(0x55);
  SPI_DATA(0x20);
  SPI_DATA(0x08);
  SPI_DATA(0x09);
  SPI_DATA(0x18);

  SPI_COMMAND(PWR);
  SPI_DATA(0x3F);
  
  SPI_COMMAND(PSR);
  SPI_DATA(0x5F);
  SPI_DATA(0x69);
 
  
  SPI_COMMAND(BTST1);
  SPI_DATA(0x40);
  SPI_DATA(0x1F);
  SPI_DATA(0x1F);
  SPI_DATA(0x2C);
  
  SPI_COMMAND(BTST3);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x1F);
  SPI_DATA(0x22);
 
  //===================
  //20211212
  //First setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x17);
  //===================
  
  SPI_COMMAND(POFS);
  SPI_DATA(0x00);
  SPI_DATA(0x54);
  SPI_DATA(0x00);
  SPI_DATA(0x44);
  
  SPI_COMMAND(TCON);
  SPI_DATA(0x02);
  SPI_DATA(0x00);
  //Please notice that PLL must be set for version 2 IC
  SPI_COMMAND(PLL);
  SPI_DATA(0x08);


  
  
  SPI_COMMAND(CDI);
  SPI_DATA(0x3F);
  
  SPI_COMMAND(TRES);
  SPI_DATA(0x03);
  SPI_DATA(0x20);
  SPI_DATA(0x01); 
  SPI_DATA(0xE0); 
  
  SPI_COMMAND(PWS);
  SPI_DATA(0x2F);
 
  SPI_COMMAND(T_VDCS);
  SPI_DATA(0x01);
  
}


//Not use now. Reserve for dither image in future
//It depends on dithering area on image
void Enable_Interlace() 
{
  SPI_COMMAND(0x86);
  SPI_DATA(0x01);
}

void Disable_Interlace() 
{
  SPI_COMMAND(0x86);
  SPI_DATA(0x00);
}

//==============================================================================
//EPD Display
//==============================================================================

void EPD_Display_White()
{
  unsigned long i;
 

  
  SPI_COMMAND(DTM);
  {
    for(i=0;i<192000;i++)
    {
      SPI_DATA(0x11);
    }
  }
  SPI_COMMAND(PON);
  check_busy_high();
  
  //20211212
  //Second setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x49);
    
  
  SPI_COMMAND(DRF);
  SPI_DATA(0x00);
  check_busy_high();
  
 
  SPI_COMMAND(POF);
  SPI_DATA(0x00);
  check_busy_high();
  delay(42000);//At least 10ms
  
//20250116//////////////
  delay_1s(6);
  SPI_COMMAND(PSR);
  SPI_DATA(0x4F); 
  SPI_DATA(0x6E); 
  check_busy_high();
  delay_1s(1);  
  CSB_L;
  RSTN_L;
  SDA_L;  
  SWC_L;//VDD SW off 
////////////////////////
}

void EPD_Display_Black()
{
  unsigned long i;

  
  SPI_COMMAND(DTM);
  for(i=0;i<192000;i++)
  {
    SPI_DATA(0x00);
  }
  
  SPI_COMMAND(PON);
  check_busy_high();  
  
  //20211212
  //Second setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x49);
  
  SPI_COMMAND(DRF);
  SPI_DATA(0x00);
  check_busy_high();
 
  
  SPI_COMMAND(POF);
  SPI_DATA(0x00);
  check_busy_high();
  delay(42000);//At least 10ms
  
//20250116//////////////
  delay_1s(6);
  SPI_COMMAND(PSR);
  SPI_DATA(0x4F); 
  SPI_DATA(0x6E); 
  check_busy_high();
  delay_1s(1);  
  CSB_L;
  RSTN_L;
  SDA_L;  
  SWC_L;//VDD SW off 
////////////////////////
}
                 
void EPD_Display_Yellow()
{
  unsigned long i;
 
  SPI_COMMAND(DTM);
  for(i=0;i<192000;i++)
  {
    SPI_DATA(0x22);
  }
  
  SPI_COMMAND(PON);
  check_busy_high();
  
  //20211212
  //Second setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x49);
  
  SPI_COMMAND(DRF);
  SPI_DATA(0x00);
  check_busy_high();
 
  
  SPI_COMMAND(POF);
  SPI_DATA(0x00);
  check_busy_high();
  delay(42000);//At least 10ms
  
//20250116////////////// 
  delay_1s(6);
  SPI_COMMAND(PSR);
  SPI_DATA(0x4F); 
  SPI_DATA(0x6E); 
  check_busy_high();
  delay_1s(1);  
  CSB_L;
  RSTN_L;
  SDA_L;  
  SWC_L;//VDD SW off 
////////////////////////
}
                 
                 
void EPD_Display_Red()
{
  unsigned long i;


  
  SPI_COMMAND(DTM);
  for(i=0;i<192000;i++)
  {
    SPI_DATA(0x33);
  }
  SPI_COMMAND(PON);
  check_busy_high();  
  
  //20211212
  //Second setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x49);
  
  SPI_COMMAND(DRF);
  SPI_DATA(0x00);
  check_busy_high();
 
   
  SPI_COMMAND(POF);
  SPI_DATA(0x00);
  check_busy_high();
  delay(42000);//At least 10ms
  
//20250116////////////// 
  delay_1s(6);
  SPI_COMMAND(PSR);
  SPI_DATA(0x4F); 
  SPI_DATA(0x6E); 
  check_busy_high();
  delay_1s(1);  
  CSB_L;
  RSTN_L;
  SDA_L;  
  SWC_L;//VDD SW off 
////////////////////////
 
}

void EPD_Display_Blue()
{
  unsigned long i;


  
  SPI_COMMAND(DTM);
  for(i=0;i<192000;i++)
  {
    SPI_DATA(0x55);
  }
  SPI_COMMAND(PON);
  check_busy_high();  
  
  //20211212
  //Second setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x49);
  
  SPI_COMMAND(DRF);
  SPI_DATA(0x00);
  check_busy_high();
 
   
  SPI_COMMAND(POF);
  SPI_DATA(0x00);
  check_busy_high();
  delay(42000);//At least 10ms
  
//20250116////////////// 
  delay_1s(6);
  SPI_COMMAND(PSR);
  SPI_DATA(0x4F); 
  SPI_DATA(0x6E); 
  check_busy_high();
  delay_1s(1);  
  CSB_L;
  RSTN_L;
  SDA_L;  
  SWC_L;//VDD SW off 
////////////////////////
 
}

void EPD_Display_Green()
{
  unsigned long i;


  
  SPI_COMMAND(DTM);
  for(i=0;i<192000;i++)
  {
    SPI_DATA(0x66);
  }
  SPI_COMMAND(PON);
  check_busy_high();  
  
  //20211212
  //Second setting
  SPI_COMMAND(BTST2);
  SPI_DATA(0x6F);
  SPI_DATA(0x1F);
  SPI_DATA(0x17);
  SPI_DATA(0x49);
  
  SPI_COMMAND(DRF);
  SPI_DATA(0x00);
  check_busy_high();
 
   
  SPI_COMMAND(POF);
  SPI_DATA(0x00);
  check_busy_high();
  delay(42000);//At least 10ms
  
//20250116////////////// 
  delay_1s(6);
  SPI_COMMAND(PSR);
  SPI_DATA(0x4F); 
  SPI_DATA(0x6E); 
  check_busy_high();
  delay_1s(1);  
  CSB_L;
  RSTN_L;
  SDA_L;  
  SWC_L;//VDD SW off 
////////////////////////
 
}


void EPD_Sleep(void)
{
  SPI_COMMAND(DSLP);
  SPI_DATA(0xA5);
}

unsigned char get_Rev(void)
{
  unsigned char num=0;
  reset();
  check_busy_high();
  
  SPI_COMMAND(REV);
  SPI_GET_DATA();
  SPI_GET_DATA();
  num = SPI_GET_DATA();
  
  return num;
}
//==============================================================================
//3-wire SPI transmission Protocol
//==============================================================================
void SPI_COMMAND(unsigned char dat)
{
  unsigned char i;

  CSB_L;
  
  delay(1);
  SDA_L; //0 for DCX_CMD
  SCL_H;
  delay(1);
  SCL_L;
  delay(1);    
  for(i=0;i<8;i++)
  {
    if(dat & 0x80) 
    {SDA_H;}
    else 
    {SDA_L;}
    delay(1);
    SCL_H;
    delay(1);    
    SCL_L;  
    dat=dat<<1;
  }
  SDA_L;
  delay(1);  
  
  CSB_H;
  
  delay(1);  
}

void SPI_DATA(unsigned char dat)
{
  unsigned char i;
  
  CSB_L;
  
  delay(1);
  SDA_H; //1 for DCX_DATA
  SCL_H;
  delay(1);
  SCL_L;
  delay(1);    
  for(i=0;i<8;i++)
  {
    if(dat & 0x80) 
    {SDA_H;}
    else 
    {SDA_L;}
    delay(1);
    SCL_H;
    delay(1);    
    SCL_L;  
    dat=dat<<1;
  }
  SDA_L;
  delay(1);  
  
  CSB_H;
  
  delay(1);  
}

unsigned char SPI_GET_DATA(void)
{
  int i;
  unsigned char DATA_BUF=0x00;

  CSB_L;

  delay(1);
  SDA_H; //1 for data
  delay(1);
  SCL_H;
  delay(1);
  SCL_L;
  delay(1);
  P4DIR = 0x80;// SDA input
  delay(3);   
  for(i=0;i<8;i++)
  {
    DATA_BUF=DATA_BUF<<1;
    SCL_H;
    if(SDA_IN) DATA_BUF|=0x01;     
    SCL_L;
    delay(1);
  }
  P4DIR = 0xC0;// SDA output
  SDA_L;
  
  delay(1);  
  
  CSB_H;
  
  delay(1);
  return DATA_BUF;
}

//==============================================================================
