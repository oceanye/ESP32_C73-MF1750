#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include <string.h>
#include "UartDataDeal.h"
#include "stmflash.h"
#include "iap.h"
#include "norflash.h"
#include "IC_drive_code.h"
#include "EPD_init.h"



uint16_t table[256];
const uint16_t poly = 4129;
uint8_t USART1_RData[USART1_RData_length];

struct uart_cmd_struct uart_cmd;
uint8_t usart_cmd_play_enable;
uint8_t usart_cmd = USART_CMD_NULL;

static void initialCRC(void);

/******************************************************************************************/


UART_HandleTypeDef huart1;
DMA_HandleTypeDef hdma_USART1_rx;
 
void Uart1_Init(void)
{
	__HAL_RCC_GPIOA_CLK_ENABLE();
	__HAL_RCC_AFIO_CLK_ENABLE();
  __HAL_RCC_PWR_CLK_ENABLE();
	__HAL_RCC_USART1_CLK_ENABLE();
	__HAL_RCC_DMA1_CLK_ENABLE();
	HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
	
//	HAL_NVIC_SetPriority(DMA1_Channel5_IRQn, 0, 0);
//  HAL_NVIC_EnableIRQ(DMA1_Channel5_IRQn);
	
	GPIO_InitTypeDef GPIO_InitStruct = {0};
	GPIO_InitStruct.Pin = GPIO_PIN_9;
	GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
	GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
	HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
 
	GPIO_InitStruct.Pin = GPIO_PIN_10;
	GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
	GPIO_InitStruct.Pull = GPIO_PULLUP;
	HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
	
	/* USART1 DMA Init */
    /* USART2_rx Init */
	hdma_USART1_rx.Instance = DMA1_Channel5;
	hdma_USART1_rx.Init.Direction = DMA_PERIPH_TO_MEMORY;
	hdma_USART1_rx.Init.PeriphInc = DMA_PINC_DISABLE;
	hdma_USART1_rx.Init.MemInc = DMA_MINC_ENABLE;
	hdma_USART1_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
	hdma_USART1_rx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
	hdma_USART1_rx.Init.Mode = DMA_NORMAL;
	hdma_USART1_rx.Init.Priority = DMA_PRIORITY_LOW;
	if (HAL_DMA_Init(&hdma_USART1_rx) != HAL_OK)
	{
		//Error_Handler();
	}
 
	__HAL_LINKDMA(&huart1,hdmarx,hdma_USART1_rx);
 

	HAL_NVIC_SetPriority(USART1_IRQn, 0, 0);
	HAL_NVIC_EnableIRQ(USART1_IRQn);	
	
	huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    //Error_Handler();
  }
	__HAL_UART_ENABLE_IT(&huart1, UART_IT_IDLE);

	HAL_UART_Receive_DMA(&huart1, (uint8_t*)USART1_RData, USART1_RData_length); 	
		/* USART1 interrupt Init */

  initialCRC();  
	memset(USART1_RData, 0, sizeof(USART1_RData)); 
}


/**
  * @brief This function handles USART2 global interrupt.
  */
uint8_t data_length;
void USART1_IRQHandler(void)
{
	if(RESET != __HAL_UART_GET_FLAG(&huart1, UART_FLAG_IDLE))   //判断是否是空闲中断
	{
		__HAL_UART_CLEAR_IDLEFLAG(&huart1);                       //清除空闲中断标志
		HAL_UART_DMAStop(&huart1);                                //停止本次DMA传输    
		data_length  = USART1_RData_length - __HAL_DMA_GET_COUNTER(&hdma_USART1_rx);   //计算接收到的数据长度
//		HAL_UART_Transmit(&huart1,receive_buff2,data_length,0x200);             //测试函数：将接收到的数据打印出去
		USART1_receiveDataNnalyse();
		memset(USART1_RData,0,USART1_RData_length);                                            
		HAL_UART_Receive_DMA(&huart1, (uint8_t*)USART1_RData, USART1_RData_length);                    //重启开始DMA传输
	}
}

void reboot_system(void) {
    NVIC_SystemReset();
}

static void initialCRC(void)
{
    uint16_t temp, a,j,i;
	
    for ( i = 0; i < 256; ++i)
    {
      temp = 0;
       a = (uint16_t)(i << 8);
       for ( j = 0; j < 8; ++j)
       {
            if (((temp ^ a) & 0x8000) != 0)
            {
                temp = (uint16_t)((temp << 1) ^ poly);
            }
            else
            {
                temp <<= 1;
            }
            a <<= 1;
        }
        table[i] = temp;
    } 
}
static uint16_t  ComputeChecksumBytes(uint8_t* byte,uint16_t byte_size)
{
  uint16_t i;
  uint16_t crc = 0;
  for ( i = 0; i < byte_size; ++i)
  {
     crc = (uint16_t)((crc << 8) ^ table[((crc >> 8) ^ (0xff & byte[i]))]);
  }
  return crc;    
}

     //0x41 + 0x41 + 'number_sum_H' + 'number_sum_L' +  'cmd_type' + cmd' + 'para' + 'crc_H' + 'CRC_L' + '0X0D'
        // 0     1          2               3                4           5      6+n     6+n+1     6+n+2      6+n+3

void USART1_receiveDataNnalyse(void)
{
	uint8_t    cmd_type;
	uint16_t   number_sum;
	uint16_t   crc_value;

	number_sum = USART1_RData[2]<<8|USART1_RData[3];
	if((USART1_RData[0]==0x41)&&(USART1_RData[1]==0x41)&&(USART1_RData[number_sum-1]==0x0D))
	{
	}
	else
	{
		return;
	}
	cmd_type   = USART1_RData[4];
	crc_value  = (USART1_RData[number_sum-3]<<8) + USART1_RData[number_sum-2];
	//check crc
	if(crc_value !=ComputeChecksumBytes(USART1_RData,number_sum-3))
		{
				memset(USART1_RData, 0, sizeof(USART1_RData)); 
				return ;
		}
		switch(cmd_type)
		{
			case 1:  //开始升级
				erase_Mult_sec(FLASH_DATA_ADDR,1);
				test_write(FLASH_DATA_ADDR,0x0055);
			  reboot_system();break;  //开始升级

			case 4:  //接受图片

			break;
					
			case 5:  //接受波形数据
				Uart_save_wf_data(&USART1_RData[6],number_sum - 9);
			break;
				
			case 6:  //存储配置
				usart_cmd = USART_CMD_PLAY_PIC;
				write_group_setting(&USART1_RData[6],number_sum - 9);				
			break;
			
			case 7:  //测量VCOM
				usart_cmd = USART_CMD_GET_VCOM;
			break;
			case 8:  //设置VCOM
				usart_cmd = USART_CMD_SET_VCOM;
			  vcom = USART1_RData[6];
			break;
		}
		
}


void usart_send(uint8_t*buff,uint16_t buff_len)
{
	uint16_t i;
	for (i = 0;i < buff_len;i++)
	{
		while ((USART1->SR & 0X40) == 0);     /* 等待上一个字符发送完成 */
    USART1->DR = buff[i];             /* 将要发送的字符 ch 写入到DR寄存器 */
	}

}


