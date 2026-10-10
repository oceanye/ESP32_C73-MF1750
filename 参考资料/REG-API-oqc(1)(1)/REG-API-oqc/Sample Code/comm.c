//=================================================================================================
//                   E6 13 inch Customer FW Reference Code 
//
// File Name : comm.c
// Author : Electronic Design Dept. II
// Data : 2025.11.07
// Version : 1.0
// Copyright : E Ink Holdings Inc.
//=================================================================================================

#define __COMM_C__

#include <string.h>
#include <stdio.h>
#include "EPD_init.h"
//======= Please modify the h files according to your MCU API ========
// #include "spi.h"
// #include "gpio.h"
// #include "delay.h"
//================================================================

#include "./SYSTEM/delay/delay.h"
#include "comm.h"
#include "pindefine.h"


#define SPI_MAX_BUFFER_SIZE	32768

//spi_device_handle_t spi;


static const struct {
    unsigned char logicalPin;
    GPIO_TypeDef *port;
    uint16_t halPin;
} pinMap[] = {
    {1, GPIOE, GPIO_PIN_14},   // 逻辑引脚0 -> PA0
    {2, GPIOE, GPIO_PIN_15},   // 逻辑引脚1 -> PA1
//    {2, GPIOB, GPIO_PIN_0},   // 逻辑引脚2 -> PB0
    // ... 添加其他引脚映射
};
unsigned char initialSpi(void)
{
	unsigned char status= 0;
	
	
	GPIO_InitTypeDef gpio_init_struct;  
	 __HAL_RCC_GPIOE_CLK_ENABLE();
	 __HAL_RCC_GPIOD_CLK_ENABLE();
	                      
	gpio_init_struct.Pin = GPIO_PIN_8|GPIO_PIN_9|GPIO_PIN_10;                   /* LED0引脚 */
	gpio_init_struct.Mode = GPIO_MODE_OUTPUT_PP;            /* 推挽输出 */
	gpio_init_struct.Pull = GPIO_PULLUP;                    /* 上拉 */
	gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;          /* 高速 */
	HAL_GPIO_Init(GPIOD, &gpio_init_struct);       /* 初始化LED0引脚 */   	  		
	
	gpio_init_struct.Pin = GPIO_PIN_14|GPIO_PIN_15;                   /* LED0引脚 */
	HAL_GPIO_Init(GPIOE, &gpio_init_struct);       /* 初始化LED0引脚 */   	  		

	gpio_init_struct.Pin = GPIO_PIN_13;                       /* KEY0引脚 */
	gpio_init_struct.Mode = GPIO_MODE_INPUT;                    /* 输入 */
	gpio_init_struct.Pull = GPIO_PULLUP;                        /* 上拉 */
	gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;              /* 高速 */
	HAL_GPIO_Init(GPIOE, &gpio_init_struct);           /* KEY0引脚模式设置,上拉输入 */
	
  EPD_Rest   = 0;             
  E_Paper_DC = 0;           
  E_Paper_CS = 0;           
  E_Paper_SCK= 0;           
  E_Paper_SDI= 0;          
	//======= Please modify the h files according to your MCU API ========
	// SPI Communication Initial
	// Use Stand SPI Without CS Pin(Controlled By GPIO)
	return status;

}


unsigned char initialGpio(void)
{
	unsigned char status = 0;
	
	
	initialSpi();
	//======= Please modify the h files according to your MCU API ========
	// GPIO PIN Initial
	/*
    gpio_config_t ioConfig = {};
nitialSpi(void)
	ioConfig.pin_bit_mask = ((1ULL<<EPD_RST) | (1ULL<<SPI_CS0) | (1ULL<<SPI_CS1) );    
	ioConfig.mode = GPIO_MODE_OUTPUT;
    ioConfig.pull_up_en = GPIO_PULLUP_ENABLE;
    status = gpio_config(&ioConfig);
	ioConfig.pin_bit_mask = (1ULL<<EPD_BUSY);
    ioConfig.intr_type = GPIO_INTR_NEGEDGE;
    ioConfig.mode = GPIO_MODE_INPUT;
    ioConfig.pull_down_en = GPIO_PULLDOWN_DISABLE;
    ioConfig.pull_up_en = GPIO_PULLUP_DISABLE;
    status = gpio_config(&ioConfig);
	*/
	return status;

}


void delayms(unsigned int delayTime)
{
	//======= Please modify the h files according to your MCU API ========
	// Delay Function
	// vTaskDelay(delayTime/portTICK_PERIOD_MS);
	delay_ms(delayTime);
	
}

unsigned char spiTransmitCommand(unsigned char commandBuf)
{
	
	
	 EPD_WriteCMD(commandBuf);			//PWD After OTP
	unsigned char status = 0;
	//======= Please modify the h files according to your MCU API ========
	/*
	spi_transaction_t trans;

	memset(&trans, 0, sizeof(trans));
    trans.cmd = commandBuf;

    trans.length = 0;
    trans.tx_buffer = NULL;
    status = spi_device_transmit(spi, &trans);
    assert(status==ESP_OK);
	*/
	

	return status;

}

unsigned char spiTransmitData(const unsigned char *dataBuffer, unsigned long dataLength)
{
	
	     // 直接按照 EPD_WriteDATA 的逻辑实现
    
    // 设置DC为数据模式
    E_Paper_DC = 1;
    
    // 使能片选
    E_Paper_CS = 0;
    
    // 短暂延迟
    delay_us(10);
    
    // 发送所有数据
    for (unsigned long i = 0; i < dataLength; i++) {
        EPD_SPI_Write(dataBuffer[i]);
    }
    
    // 禁用片选
    E_Paper_CS = 1;
    
    return 0;  // 总是返回成功
	unsigned char status = 0;
	//======= Please modify the h files according to your MCU API ========
	/*
	spi_transaction_ext_t trans_ext;

	while(dataLength >= SPI_MAX_BUFFER_SIZE)
	{
		memset(&trans_ext, 0, sizeof(trans_ext));
		trans_ext.command_bits = 0;
		trans_ext.base.length = SPI_MAX_BUFFER_SIZE * 8;
		// The trans_ext.base.length unit is bit, so the SPI_MAX_BUFFER_SIZE must be multiplied by 8.
		trans_ext.base.tx_buffer =  dataBuffer;
		trans_ext.base.flags   = SPI_TRANS_VARIABLE_CMD;
		status = spi_device_transmit(spi, &trans_ext);
		dataLength -= SPI_MAX_BUFFER_SIZE;
		dataBuffer += SPI_MAX_BUFFER_SIZE;
	}

	if(dataLength > 0)
	{
		memset(&trans_ext, 0, sizeof(trans_ext));
		trans_ext.command_bits = 0;
		trans_ext.base.length = dataLength * 8;
		// The trans_ext.base.length unit is bit, so the dataLength must be multiplied by 8.
		trans_ext.base.tx_buffer =  dataBuffer;
		trans_ext.base.flags   = SPI_TRANS_VARIABLE_CMD;
		status = spi_device_transmit(spi, &trans_ext);
	}
	*/
	return status;

}



unsigned char spiReceiveData(unsigned char *dataBuffer, unsigned long dataLength)
{
	
	  unsigned char status = 0;
    
    // 直接调用原始的 EPD_SPI_Read 函数
    for (unsigned long i = 0; i < dataLength; i++) {
        dataBuffer[i] = EPD_SPI_Read();
    }
    
    return status;

	//======= Please modify the h files according to your MCU API ========
	/*
	spi_transaction_ext_t trans_ext;

	while(dataLength > SPI_MAX_BUFFER_SIZE)
	{
		memset(&trans_ext, 0, sizeof(trans_ext));

		trans_ext.command_bits = 0;
		trans_ext.base.length = SPI_MAX_BUFFER_SIZE * 8;
		// The trans_ext.base.length unit is bit, so the SPI_MAX_BUFFER_SIZE must be multiplied by 8.
		trans_ext.base.rx_buffer =  dataBuffer;
		trans_ext.base.rxlength = dataLength * 8;
		trans_ext.base.flags   = SPI_TRANS_VARIABLE_CMD;
		status = spi_device_transmit(spi, &trans_ext);
		dataLength -= SPI_MAX_BUFFER_SIZE;
		dataBuffer += SPI_MAX_BUFFER_SIZE;
	}

	if(dataLength > 0)
	{
		memset(&trans_ext, 0, sizeof(trans_ext));

		trans_ext.command_bits = 0;
		trans_ext.base.length = dataLength * 8;
		// The trans_ext.base.length unit is bit, so the dataLength must be multiplied by 8.
		trans_ext.base.rx_buffer =  dataBuffer;
		trans_ext.base.rxlength = dataLength * 8;
		trans_ext.base.flags   = SPI_TRANS_VARIABLE_CMD;
		status = spi_device_transmit(spi, &trans_ext);
	}
	*/


}

unsigned char spiTransmitLargeData(unsigned char commandBuf, unsigned char *dataBuffer, unsigned long dataLength)
{
unsigned char status = 0;
    
    // 参数检查
    if (dataBuffer == NULL && dataLength > 0) {
        return 1;  // 参数错误
    }
    
    // 发送命令字节
    status = spiTransmitData(&commandBuf, 1);
    if (status != 0) {
        return status;  // 命令发送失败
    }
    
    // 如果数据长度大于0，发送数据
    if (dataLength > 0 && dataBuffer != NULL) {
        status = spiTransmitData(dataBuffer, dataLength);
    }
    
    return status;

}

unsigned char spiTransmit(unsigned char commandBuf,const unsigned char *dataBuffer, unsigned int dataLength)
{
unsigned char status = 0;
    
    // 参数检查
    if (dataBuffer == NULL && dataLength > 0) {
        return 1;  // 参数错误
    }
    
    // 发送命令字节
    status = spiTransmitData(&commandBuf, 1);
    if (status != 0) {
        return status;  // 命令发送失败
    }
    
    // 如果数据长度大于0，发送数据
    if (dataLength > 0 && dataBuffer != NULL) {
        status = spiTransmitData(dataBuffer, dataLength);
    }
    
    return status;

}

unsigned char spiReceive(unsigned char commandBuf, unsigned char *dataBuffer, unsigned int dataLength)
{
	  unsigned char status = 0;
    
    // 参数验证
    if (dataBuffer == NULL) {
        return 1;  // 缓冲区为空
    }
    
    if (dataLength == 0) {
        return 2;  // 数据长度为0
    }
    
    // 发送命令（使用现有的spiTransmitData函数）
    status = spiTransmitData(&commandBuf, 1);
    if (status != 0) {
        return status;  // 命令发送失败
    }
    
    // 接收数据（使用现有的spiReceiveData函数）
    status = spiReceiveData(dataBuffer, dataLength);
    
    return status;

}

void setGpioLevel(unsigned char pinNumber, unsigned char voltageLevel)
{
	//======= Please modify the h files according to your MCU API ========
	//Set GPIO voltage level
	// gpio_set_level(pinNumber, voltageLevel);
	if (pinNumber ==8){
		 if (voltageLevel != 0) {
        PDout(8) = 1;
    } else {
        PDout(8) = 0;
    }
	}
		
	    if (voltageLevel != 0) {
        PEout(pinNumber) = 1;
    } else {
        PEout(pinNumber) = 0;
    }
    
}

unsigned char getGpioLevel(unsigned char pinNumber)
{
	unsigned char voltageLevel = 0;
	//======= Please modify the h files according to your MCU API ========
	//Get GPIO voltage level ====
	// voltageLevel = gpio_get_level(pinNumber);
  voltageLevel = PEin(pinNumber);
	return voltageLevel;
}