//=============================================================================
// E5 3-bit Development Environment
//
// File Name : E2802-SPD1657_OTP.c
// Author : Electronic Design Dept. II
// Date : 2023.11.22
// Version : 1.1 (Support 2nd OTP Burn)
// Copyright : E Ink Holdings Inc.
//=============================================================================
#define __E28xx_C__

#include "E28xx.h"
#include "otp.h"
#include "pindefine.h"
#include "EPD_init.h"
#include "LCDConfig.h"


//=============== Delay Function ============================================================

//void delay_s(unsigned long time)
//{

//  int j,k;
//  for(j = 0;j<time;j++)
//  {
//    for(k=0;k<210;k++)
//    {
//      // Please check that the delay meets 1 second.
//    }
//  }
//}

//void delay_ms(unsigned long time)
//{

//  int j;
//  for(j = 0;j<time;j++)
//  {
//      // Please check that the delay meets 1ms.
//  }
//}



//===========================================================================================

//=============== Global Variable ===========================================================
unsigned char vcomExist=1;
unsigned char vcomBuf=0;
unsigned char opt_write_status=WRITE_OTP_FAIL_NO_VCOM;

//=== Please place your security key below ===
const char customer_key[] = "0f5445f92132b6ef57466f274d3b6b2d47d79356";
//=============== Function ==================================================================
static void checkBusyHigh(void);
static void checkBusyLow(void);
static void sendSPICommand(unsigned char dat);
static void sendSPIData(unsigned char dat);
static unsigned char getSPIData(void);
static void sendMutipleSPIData(unsigned char *data, unsigned int counter);
static void getMutipleSPIData(unsigned int counter);
static void reset(void);


//=============== Function ==================================================================
static void checkBusyHigh(void);
static void checkBusyLow(void);
static void sendSPICommand(unsigned char dat);
static void sendSPIData(unsigned char dat);
static unsigned char getSPIData(void);
static void sendMutipleSPIData(unsigned char *data, unsigned int counter);
static void getMutipleSPIData(unsigned int counter);
static void reset(void);


void initEPDSPI(void) // Different Driver ICs require maintenance.
{
// Please design according to the respective driver board

//    E_Paper_SCK= 0;
//   E_Paper_SDI= 1;
//  E_Paper_CS = 1;
//  BS1_L;
//  BS0_H;
	  E_Paper_SCK= 0; 
	  E_Paper_SDI= 1;
	E_Paper_CS = 1;      
	
//	E_Paper_DC = 0;           
//  E_Paper_CS = 1;           
//          
//  E_Paper_SDI= 0;   
 
}

static void sendSPICommand(unsigned char dat)
{
// Please design according to the respective driver board

EPD_WriteCMD(dat);
}

static void sendSPIData(unsigned char dat)
{
// Please design according to the respective driver board
	EPD_WriteDATA(dat);		

}

static unsigned char getSPIData(void)
{
	unsigned char rdata =0;
	unsigned char i;
	for(i=0;i<8;i++)
	{
		E_Paper_SCK = 0;
		delay_us(4);
		E_Paper_SCK = 1;
		delay_us(4);
		rdata <<= 1;
		if(E_READ_SDI) rdata |=0x01;
		
	}
	E_Paper_SCK = 0;
	return rdata;

}

static void sendMutipleSPIData(unsigned char *data, unsigned int counter)
{
  unsigned int i;
  
  for(i=0;i<counter;i++)
  {
    sendSPIData(*data);
    data++;
  }
}

static void getMutipleSPIData(unsigned int counter)
{
  unsigned int i;
  
  for(i=0;i<counter;i++)
  {
    epdSPI.buf[i] = getSPIData();
  }
  
  epdSPI.len=counter;
  epdSPI.status=1;
}

static void reset(void)
{
	EPD_Rest=0;
	delay_ms(100);
	EPD_Rest=1;
	delay_ms(100);


}


void epdInitial(void)
{
	// Please modify the seeting according to your module design.
 // Please modify the seeting according to your module design.
 
	// Please modify the seeting according to your module design.
  reset();

  EPD_WriteCMD_ToBoth(0xAA);
  EPD_WriteDATA_ToBoth(0x49);
  EPD_WriteDATA_ToBoth(0x55);
  EPD_WriteDATA_ToBoth(0x20);
  EPD_WriteDATA_ToBoth(0x08);
	EPD_WriteDATA_ToBoth(0x09);
  EPD_WriteDATA_ToBoth(0x18);
	
	EPD_WriteCMD_ToBoth(R00_PSR);
  EPD_WriteDATA_ToBoth(0x5F);
  EPD_WriteDATA_ToBoth(0x69); 
	
	    EPD_Check_Busy();
	
	EPD_WriteCMD_ToBoth(0xe0);
  EPD_WriteDATA_ToBoth(0x01);
	
	    EPD_Check_Busy();
  
  
  EPD_WriteCMD_ToBoth(R01_PWR);
  EPD_WriteDATA_ToBoth(0x3F);


 EPD_WriteCMD_ToBoth(R03_POFS);
  EPD_WriteDATA_ToBoth(0x00);  
  EPD_WriteDATA_ToBoth(0x54);  
  EPD_WriteDATA_ToBoth(0x00);
  EPD_WriteDATA_ToBoth(0x44);

  EPD_WriteCMD_ToBoth(R05_BTST1);
  EPD_WriteDATA_ToBoth(0x40);  
  EPD_WriteDATA_ToBoth(0x1F);
  EPD_WriteDATA_ToBoth(0x1F);  
  EPD_WriteDATA_ToBoth(0x2C);

  EPD_WriteCMD_ToBoth(R06_BTST2);
  EPD_WriteDATA_ToBoth(0x6F);  
  EPD_WriteDATA_ToBoth(0x1F);
  EPD_WriteDATA_ToBoth(0x16);  
  EPD_WriteDATA_ToBoth(0x25);

  EPD_WriteCMD_ToBoth(R08_BTST3);
  EPD_WriteDATA_ToBoth(0x6F);  
  EPD_WriteDATA_ToBoth(0x1F);
  EPD_WriteDATA_ToBoth(0x1f);  
  EPD_WriteDATA_ToBoth(0x22);

  EPD_WriteCMD_ToBoth(R13_IPC);
  EPD_WriteDATA_ToBoth(0x00); 
  EPD_WriteDATA_ToBoth(0x04); 
	
	  EPD_WriteCMD_ToBoth(0x30);
  EPD_WriteDATA_ToBoth(0x08);

  EPD_WriteCMD_ToBoth(R41_TSE);
  EPD_WriteDATA_ToBoth(0x00);

 
   EPD_WriteCMD_ToBoth(R50_CDI);
  EPD_WriteDATA_ToBoth(0x3F);
  
  

  
  
 EPD_WriteCMD_ToBoth(R60_TCON);
  EPD_WriteDATA_ToBoth(0x02);
  EPD_WriteDATA_ToBoth(0x00);

   EPD_WriteCMD_ToBoth(R61_TRES);//EPD Resolution
  EPD_WriteDATA_ToBoth(0x02);// Source Line
  EPD_WriteDATA_ToBoth(0x00);
  EPD_WriteDATA_ToBoth(0x02);// Gate Line
  EPD_WriteDATA_ToBoth(0x58);
    EPD_Check_Busy();
		
		
  EPD_WriteCMD_ToBoth(0x84);
  EPD_WriteDATA_ToBoth(0x01);
  

  EPD_WriteCMD_ToBoth(R86_AGID);
  EPD_WriteDATA_ToBoth(0x00);
  
  EPD_WriteCMD_ToBoth(RE3_PWS);
  EPD_WriteDATA_ToBoth(0x2F);
  



  EPD_WriteCMD_ToBoth(0xe5);
  EPD_WriteDATA_ToBoth(0x00);
	


 
	
	
  

  
  
}

void writeEPD(unsigned char spi_c, unsigned char * spi_d, unsigned int len) {
  
  // LED_D1_ON;
  
  sendSPICommand(spi_c);
  sendMutipleSPIData(spi_d, len);

  // LED_D1_OFF;  
}

unsigned char getVCOMDC(void){
  unsigned char readBuf;
  
  if(vcomBuf == 0)
  {
 
    sendSPICommand(R04_PON);
    EPD_Check_Busy();
    
    sendSPICommand(R80_AMV);
    sendSPIData(0xC1);
    sendSPIData(0x02);
    EPD_Check_Busy();
    sendSPICommand(R02_POF);
    sendSPIData(0x00);  
    EPD_Check_Busy();
    delay_s(2);
    
    
    sendSPICommand(R81_VV);
    readBuf=getSPIData();
    
    

    if(readBuf!=0)
    {
    	vcomBuf = readBuf;
    	vcomExist=1; // VCOM is effective.
    }
    else
    {
    	vcomBuf = 0;
    	vcomExist=0; // VCOM is invalid.
    }
  }  
//  printf("(0x%02X)",vcomBuf);
  return vcomExist;
  
}
unsigned char setVCOMDC(unsigned char vcom){
    if(vcom!=0)
    {
        vcomBuf = vcom;
        vcomExist=1; // VCOM is effective.
    }
    else
    {
        vcomBuf = 0;
        vcomExist=0; // VCOM is invalid.
    }
  return vcomExist;

}

void readOTP(unsigned char * rxBuf, unsigned int add, unsigned int len)
{
  unsigned int i=0;
  reset();
    
  sendSPICommand(0xF0);
  sendSPIData(0x10);
  
  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x03);//internal VPP, raw mode
  
  sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
  
  sendSPICommand(0xF6);
  sendSPIData(0x01);     //read address  first byte must setting to 0x01
  sendSPIData(add/256);
  sendSPIData(add%256);
  
  sendSPICommand(R92_ROTP);
  getSPIData();
  
  for(i=0;i<len;i++)
  {
    rxBuf[i]=getSPIData();
  }
  
}

void readOTP_VCOM(unsigned char * rxBuf)
{
  unsigned int i=0;
  reset();
    
  sendSPICommand(0xF0);
  sendSPIData(0x10);
  
  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x02);//internal VPP, raw mode
  
  sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
  
  sendSPICommand(0xF6);
  sendSPIData(0x01);     //read address  first byte must setting to 0x01
  sendSPIData(0x00);
  sendSPIData(0x00);
  
  sendSPICommand(R92_ROTP);
  getSPIData();//dummy
  
  for(i=0;i<11;i++)
  {
    getSPIData();
  }
  rxBuf[0]=getSPIData();//12
  
}

void  EPD_Read_reg_lut(unsigned char * pbuf,unsigned int len)
{
     unsigned int  i = 0;
    
	E_SDI_IN();           //SDA  input mode
	E_Paper_DC = 1;		    //data read
	E_Paper_CS = 0;
	delay_ms(40);
	

	for(i=0;i<len;i++)
	{
		*(pbuf ++)= EPD_SPI_Read();
	}
	E_Paper_CS = 1;
	
		E_SDI_OUT();           //SDA  output mode

}

static char OTP_Data_Cheak(const uint8_t *buffer1,const uint8_t *buffer2,int len)
{
	int i;
	for (i = 0;i < len; i++)
	{
		if (buffer1[i] != buffer2[i])
		{
			return 0;
		}
	}
	return 1;
}

unsigned char writeUserData(unsigned char *data, unsigned char len)
{
  unsigned int i=0;
  reset();
  sendSPICommand(0xAA);
  sendSPIData(0x49); 
  sendSPIData(0x55); 
  sendSPIData(0x20); 
  sendSPIData(0x08); 
  sendSPIData(0x09); 
  sendSPIData(0x18); 

  sendSPICommand(R05_BTST1);
  sendSPIData(0x40); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x2C);

  sendSPICommand(R06_BTST2);
  sendSPIData(0x6F); 
  sendSPIData(0x15); 
  sendSPIData(0x26); 
  sendSPIData(0x36);

  sendSPICommand(R08_BTST3);
  sendSPIData(0x70); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x22);

  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x13);
  sendSPIData(0x40);
  sendSPIData(0xC0);
  sendSPIData(0x00);
  sendSPIData(0xE0);


  sendSPICommand(R10_DTM);
  for(i=0;i<224;i++)
  {
    if(i<len) sendSPIData(data[i]);
    else sendSPIData(0x00);
  }  
  
  sendSPICommand(R04_PON);

  EPD_Check_Busy();
  
  delay_ms(10);
          
  sendSPICommand(R91_APG);
  EPD_Check_Busy();
          
  delay_ms(50);
  
  sendSPICommand(R02_POF);
  sendSPIData(0x00);
  EPD_Check_Busy();

  delay_ms(50);
  
 
}


//#define R00_PSR         0x00
//#define R01_PWR         0x01
//#define R02_POF         0x02
//#define R03_POFS        0x03
//#define R04_PON         0x04
//#define R06_BTST        0x06
//#define R07_DSLP        0x07
//#define R10_DTM         0x10
//#define R11_DSP         0x11
//#define R12_DRF         0x12
//#define R17_AUTO        0x17
//#define R20_LUT0        0x20




/***********************vcom value table****************
0000000 00h  0    0011100 1Ch -1.4  0111000 38h -2.8
0000001 01h -0.05 0011101 1Dh -1.45 0111001 39h -2.85
0000010 02h -0.1  0011110 1Eh -1.5  0111010 3Ah -2.9
0000011 03h -0.15 0011111 1Fh -1.55 0111011 3Bh -2.95
0000100 04h -0.2  0100000 20h -1.6  0111100 3Ch -3
0000101 05h -0.25 0100001 21h -1.65 0111101 3Dh -3.05
0000110 06h -0.3  0100010 22h -1.7  0111110 3Eh -3.1
0000111 07h -0.35 0100011 23h -1.75 0111111 3Fh -3.15
0001000 08h -0.4  0100100 24h -1.8  1000000 40h -3.2
0001001 09h -0.45 0100101 25h -1.85 1000001 41h -3.25
0001010 0Ah -0.5  0100110 26h -1.9  1000010 42h -3.3
0001011 0Bh -0.55 0100111 27h -1.95 1000011 43h -3.35
0001100 0Ch -0.6  0101000 28h -2    1000100 44h -3.4
0001101 0Dh -0.65 0101001 29h -2.05 1000101 45h -3.45
0001110 0Eh -0.7  0101010 2Ah -2.1  1000110 46h -3.5
0001111 0Fh -0.75 0101011 2Bh -2.15 1000111 47h -3.55
0010000 10h -0.8  0101100 2Ch -2.2  1001000 48h -3.6
0010001 11h -0.85 0101101 2Dh -2.25 1001001 49h -3.65
0010010 12h -0.9  0101110 2Eh -2.3  1001010 4Ah -3.7
0010011 13h -0.95 0101111 2Fh -2.35 1001011 4Bh -3.75
0010100 14h -1    0110000 30h -2.4  1001100 4Ch -3.8
0010101 15h -1.05 0110001 31h -2.45 1001101 4Dh -3.85
0010110 16h -1.1  0110010 32h -2.5  1001110 4Eh -3.9
0010111 17h -1.15 0110011 33h -2.55 1001111 4Fh -3.95
0011000 18h -1.2  0110100 34h -2.6  1010000 50h -4
0011001 19h -1.25 0110101 35h -2.65 other -4
0011010 1Ah -1.3  0110110 36h -2.7
0011011 1Bh -1.35 0110111 37h -2.75
******************************************************/
#define USER_SETTING_SIZE  72
#define VCOM_VALUE          0x10
#define USERID_SETTING_SIZE  16
//static unsigned char user_setting[USER_SETTING_SIZE] = {		  
//	//烧录的Init_Code  需要根据不同尺寸的Panel调整相关参数 比如：分辨率 BTST VCOM等
//		0x07,0xAA,0x49,0x55,0x20,0x08,0x09,0x18,      //CMDH
//		0x03,0x00,0x5f,0x69,   													//PSR
//		0x02,0x01,0x3f,											//PWR
//		0x05,0x03,0x00,0x54,0x00,0x44,								//Pofs
//		0x05,0x05,0x40,0x1F,0x1F,0x2c,								//BTST1
//		0x05,0x06,0x6f,0x1F,0x16,0x25,								//BTST2
//		0x05,0x08,0x6f,0x1F,0x1F,0x22,								//BTST3
//		0x02,0x50,0x90,											//CDI
//		0x03,0x60,0xc1,0x00,			//TCON
//		0x05,0x61,0x01,0xad,0x01,0xad,					//TRES   Rsolution
//		0x02,0x82,VCOM_VALUE, 		//vdcs
//		0x02,0x84,0x01,   //t-vdcs
//		0x02,0xe0,0x01,   //ccset
//		0x02,0xe3,0x40,   //pws-2
//		0x03,0xf0,0x14,0x80,    //rsv0
//		0x12,0xf6,0x31,   //rsv1
//		0x00,									};

static unsigned char userID_setting[USERID_SETTING_SIZE] = {0x45,'J','1','5','8',0x01,0,0,0,0,0,0,0,0,0,0};
unsigned char Ra4_buf_read[4];
unsigned char Ra3_buf_read[1];
unsigned char default_buf_read[73];
		
		
		
unsigned char  program_int()
	 
{
	
	opt_write_status = WRITE_OTP_FAIL_WRONG_OPERATION;
	int i;
	
	writeUserData(userID_setting, USERID_SETTING_SIZE);
	

	
	// read
	  reset();
    
  sendSPICommand(0xF0);
  sendSPIData(0x10);
  
  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x03);
  
  sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
  
  sendSPICommand(0xF6);
  sendSPIData(0x01);     
  sendSPIData(0x40);
  sendSPIData(0xC0);

  sendSPICommand(R92_ROTP);
 
	EPD_Read_reg_lut(default_buf_read,USERID_SETTING_SIZE);
	
	
	
	
	 if(OTP_Data_Cheak(&default_buf_read[1],userID_setting,USERID_SETTING_SIZE))
  {
    opt_write_status = WRITE_OTP_OK;
  }
  else
  {
    opt_write_status = WRITE_OTP_FAIL_WRONG_OPERATION;
  }
  return opt_write_status;
	 

	
}





static unsigned char OTP_buf_read[SIZE+5];
static unsigned char VCOM_buf_read[15];
unsigned char programOTP(void)
{
	
	
  unsigned int i=0;
  unsigned char otp_1st_cnt, otp_address_A,otp_address_B;
  unsigned int otp_1st_data_size=0;
	
	opt_write_status = WRITE_OTP_FAIL_WRONG_OPERATION;
  reset();
  
  sendSPICommand(0xF0);
  sendSPIData(0x10);
  
  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x03);//internal VPP, raw mode
  
  sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
  
  sendSPICommand(0xF6);
  sendSPIData(0x01);     //read address  first byte must setting to 0x01
  sendSPIData(0x00);
  sendSPIData(0x00);
  
  sendSPICommand(R92_ROTP);

//  EPD_SPI_Read();//Dummy
//  EPD_SPI_Read();       //0x01
//  EPD_SPI_Read();       //0xA5
//  otp_1st_cnt = EPD_SPI_Read();
  otp_1st_cnt = 0x00;

  if(otp_1st_cnt == 0x00){
    otp_1st_data_size = 0;
    otp_address_A = 0x00;
    otp_address_B = 0x00;
    
  }else{
    otp_1st_data_size =  (otp_1st_cnt * 384);
    otp_address_A = otp_1st_data_size/256;
    otp_address_B = otp_1st_data_size%256;

  }    
  
  reset();
  sendSPICommand(0xAA);
  sendSPIData(0x49); 
  sendSPIData(0x55); 
  sendSPIData(0x20); 
  sendSPIData(0x08); 
  sendSPIData(0x09); 
  sendSPIData(0x18); 

  sendSPICommand(R05_BTST1);
  sendSPIData(0x40); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x2C);

  sendSPICommand(R06_BTST2);
  sendSPIData(0x6F); 
  sendSPIData(0x15); 
  sendSPIData(0x26); 
  sendSPIData(0x36);

  sendSPICommand(R08_BTST3);
  sendSPIData(0x70); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x22);


  sendSPICommand(R90_PGM);
  EPD_Check_Busy();


  if(otp_1st_data_size == 0){ //1st burn
    sendSPICommand(RA2_PGM_CFG);
    sendSPIData(0x13);
    sendSPIData(0x00);
    sendSPIData(0x00);
    sendSPIData(SIZE/256);
    sendSPIData(SIZE%256);

    

  }else{ //2nd burn
    sendSPICommand(RA2_PGM_CFG);
    sendSPIData(0x13);
    sendSPIData(0x00);
    sendSPIData(0x01);
    sendSPIData(0x00);
    sendSPIData(0x01);

    sendSPICommand(R10_DTM);
    sendSPIData(0xFF);

    sendSPICommand(R04_PON);
    EPD_Check_Busy();
    delay_ms(10);

    sendSPICommand(R91_APG);
    EPD_Check_Busy();
    delay_ms(50);

    sendSPICommand(R02_POF);
    sendSPIData(0x00);
    EPD_Check_Busy();
    delay_ms(50);

    reset();
    sendSPICommand(0xAA);
    sendSPIData(0x49); 
    sendSPIData(0x55); 
    sendSPIData(0x20); 
    sendSPIData(0x08); 
    sendSPIData(0x09); 
    sendSPIData(0x18); 

    sendSPICommand(R05_BTST1);
    sendSPIData(0x40); 
    sendSPIData(0x1F); 
    sendSPIData(0x1F); 
    sendSPIData(0x2C);

    sendSPICommand(R06_BTST2);
    sendSPIData(0x6F); 
    sendSPIData(0x15); 
    sendSPIData(0x26); 
    sendSPIData(0x36);

    sendSPICommand(R08_BTST3);
    sendSPIData(0x70); 
    sendSPIData(0x1F); 
    sendSPIData(0x1F); 
    sendSPIData(0x22);


    sendSPICommand(R90_PGM);
    EPD_Check_Busy();
    sendSPICommand(RA2_PGM_CFG);
    sendSPIData(0x13);
    sendSPIData(otp_address_A);
    sendSPIData(otp_address_B);
    sendSPIData(SIZE/256);
    sendSPIData(SIZE%256); 


  }
  sendSPICommand(R10_DTM);
  for(i=0 ; i < SIZE ; i++)
  {
    sendSPIData(OTP_DATA[i]);
  }
  sendSPICommand(R04_PON);
  EPD_Check_Busy();
  delay_ms(10);
          
  sendSPICommand(R91_APG);
  EPD_Check_Busy();
  delay_ms(50);
  
  sendSPICommand(R02_POF);
  sendSPIData(0x00);
  EPD_Check_Busy();
  delay_ms(50);


  reset();
    
  sendSPICommand(0xF0);
  sendSPIData(0x10);
  
  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x03);//internal VPP, raw mode
  
  sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
  sendSPICommand(0xF6);
  sendSPIData(0x01);     //read address  first byte must setting to 0x01
  if(otp_1st_data_size == 0){ //check 1st 
    sendSPIData(0x00);
    sendSPIData(0x00);
  } else { //check 2nd 
    sendSPIData(otp_address_A);
    sendSPIData(otp_address_B);
  }
  

	
	  reset();
	EPD_Check_Busy();
	delay_ms(50);
	
			sendSPICommand(R90_PGM);
    EPD_Check_Busy();
			delay_ms(50);
	
	
	sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
			delay_ms(50);



  sendSPICommand(R92_ROTP);
//  EPD_SPI_Read();
		EPD_Read_reg_lut(OTP_buf_read,(SIZE+1));
  unsigned char da_tt;
  for(i=0;i<SIZE;i++)
  {
     da_tt = OTP_buf_read[i+1];
    if(OTP_DATA[i] == da_tt)
    {
      opt_write_status = WRITE_OTP_OK;
    }
    else
    {
      opt_write_status = WRITE_OTP_FAIL_WRONG_OPERATION;
      i = SIZE;
    }
    delay_ms(2);

  }

  return opt_write_status;

}

unsigned char programOTP_VCOM(void)
{
  unsigned int i=0;
opt_write_status = WRITE_OTP_FAIL_WRONG_OPERATION;
	
  reset();
  epdInitial(); 
  sendSPICommand(0xAA);
  sendSPIData(0x49); 
  sendSPIData(0x55); 
  sendSPIData(0x20); 
  sendSPIData(0x08); 
  sendSPIData(0x09); 
  sendSPIData(0x18); 
  sendSPICommand(R05_BTST1);
  sendSPIData(0x40); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x2C); 

  sendSPICommand(R06_BTST2);
  sendSPIData(0x60); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x45); 

  sendSPICommand(R08_BTST3);
  sendSPIData(0x70); 
  sendSPIData(0x1F); 
  sendSPIData(0x1F); 
  sendSPIData(0x22);

  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x12);
  sendSPIData(0x00);
  sendSPIData(0x00);
  sendSPIData(0x00);
  sendSPIData(0x0C);

  sendSPICommand(R10_DTM);

  sendSPIData(0x25);  
  sendSPIData(0xF4);
  sendSPIData(0x78);
  sendSPIData(0x78);
  sendSPIData(0x7F);
  sendSPIData(0x3F);
  sendSPIData(0x12);
  sendSPIData(0xF6);
  sendSPIData(0x31);
  sendSPIData(0x02);
  sendSPIData(0x82);
  
  if(vcomExist==1){
    sendSPIData(VCOM_VALUE);
  }else{
    sendSPIData(0x00);
  }

  sendSPICommand(R04_PON);
  EPD_Check_Busy();
  delay_ms(10);
          
  sendSPICommand(R91_APG);
  EPD_Check_Busy();
  delay_ms(50);
  
  sendSPICommand(R02_POF);
  sendSPIData(0x00);
  EPD_Check_Busy();
  delay_ms(50);
  reset();
    
  sendSPICommand(0xF0);
  sendSPIData(0x10);
  
  sendSPICommand(R90_PGM);
  EPD_Check_Busy();
  
  sendSPICommand(RA2_PGM_CFG);
  sendSPIData(0x02);//internal VPP, raw mode
  
  sendSPICommand(RA0_LOTP);
  EPD_Check_Busy();
  
  sendSPICommand(0xF6);
  sendSPIData(0x01);     //read address  first byte must setting to 0x01
  sendSPIData(0x00);
  sendSPIData(0x00);
  
  sendSPICommand(R92_ROTP);
//  getSPIData();//dummy
//  for(i=0;i<11;i++)
//  {
//   getSPIData();
//  }
		EPD_Read_reg_lut(VCOM_buf_read,15);
  if(VCOM_VALUE == VCOM_buf_read[12])
  {
    opt_write_status = WRITE_OTP_OK;
  }
  else
  {
    opt_write_status = WRITE_OTP_FAIL_WRONG_OPERATION;
  }
  return opt_write_status;
}


void showImage(unsigned char *imageData)
{
    unsigned long i;
    
    sendSPICommand(R10_DTM);
    for(i=0;i<_imageSize;i++)
    {
      sendSPIData(imageData[i]);
    }
    
    sendSPICommand(R04_PON);
    EPD_Check_Busy();
    
    sendSPICommand(R12_DRF);
    sendSPIData(0x00);
    EPD_Check_Busy();

    sendSPICommand(R02_POF);  
    sendSPIData(0x00);
    EPD_Check_Busy();
}

void display_Black(void)
{
   unsigned long i;

    EPD_WriteCMD_ToMaster(0x10);  		//Master image
    for(i=0;i<IMAGE_YSIZE/2;i++)
    {
      EPD_WriteDATA_ToMaster(0x00);
    }
		
		    EPD_WriteCMD_ToSlave(0x10);    	//Slave image
 for(i=0;i<IMAGE_YSIZE/2;i++)
    {
      EPD_WriteDATA_ToSlave(0x00);
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

void display_White(void)
{
    unsigned long i;

    EPD_WriteCMD_ToMaster(0x10);  		//Master image
    for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToMaster(0x11);
    }
		
		    EPD_WriteCMD_ToSlave(0x10);    	//Slave image
		for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToSlave(0x11);
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

void display_Red(void)
{
    unsigned long i;

    EPD_WriteCMD_ToMaster(0x10);  		//Master image
    for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToMaster(0x22);
    }
		
		    EPD_WriteCMD_ToSlave(0x10);    	//Slave image
		for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToSlave(0x22);
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

void display_Yellow(void)
{
    unsigned long i;

    EPD_WriteCMD_ToMaster(0x10);  		//Master image
    for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToMaster(0x33);
    }
		
		    EPD_WriteCMD_ToSlave(0x10);    	//Slave image
		for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToSlave(0x33);
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


void display_B(void)
{
    unsigned long i;

    EPD_WriteCMD_ToMaster(0x10);  		//Master image
    for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToMaster(0x55);
    }
		
		    EPD_WriteCMD_ToSlave(0x10);    	//Slave image
		for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToSlave(0x55);
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

void display_G(void)
{
   unsigned long i;

    EPD_WriteCMD_ToMaster(0x10);  		//Master image
    for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToMaster(0x66);
    }
		
		    EPD_WriteCMD_ToSlave(0x10);    	//Slave image
		for(i=0;i<(IMAGE_YSIZE/2);i++)
    {
      EPD_WriteDATA_ToSlave(0x66);
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

void display_KWRY(void)
{
    unsigned long i;
    unsigned int imageSize = _imageSize/4;
    
    sendSPICommand(R10_DTM);
    for(i=0;i<imageSize;i++)
    {
      sendSPIData(0x00);
    }
    
    for(i=0;i<imageSize;i++)
    {
      sendSPIData(0x11);
    }
    
    for(i=0;i<imageSize;i++)
    {
      sendSPIData(0x22);
    }
    
    for(i=0;i<imageSize;i++)
    {
      sendSPIData(0x33);
    }
    
    sendSPICommand(R04_PON);
    EPD_Check_Busy();
    
    sendSPICommand(R12_DRF);
    sendSPIData(0x00);
    EPD_Check_Busy();
    
    sendSPICommand(R02_POF);  
    sendSPIData(0x00);
    EPD_Check_Busy();

}

static void checkBusyHigh(void) // If BUSYN=0 then waiting
{
 EPD_Check_Busy();

}

static void checkBusyLow(void) // If BUSYN=1 then waiting
{
  while(E_Paper_BUSY);
}
