#include "key.h"
#include "delay.h"
#include "./BSP/LED/led.h"
#include "./SYSTEM/usart/usart.h"

void Key_init(void)
{
	GPIO_InitTypeDef gpio_init_struct;
	KEY0_GPIO_CLK_ENABLE();                                     /* KEY0时钟使能 */
//	gpio_init_struct.Pin = KEY0_GPIO_PIN;                       /* KEY0引脚 */
//	gpio_init_struct.Mode = GPIO_MODE_INPUT;                    /* 输入 */
//	gpio_init_struct.Pull = GPIO_PULLDOWN;                        /* 上拉 */
//	gpio_init_struct.Speed = GPIO_SPEED_FREQ_HIGH;              /* 高速 */
//	HAL_GPIO_Init(KEY0_GPIO_PORT, &gpio_init_struct);           /* KEY0引脚模式设置,上拉输入 */
	
	gpio_init_struct.Pin = KEY0_GPIO_PIN;
	gpio_init_struct.Mode = GPIO_MODE_IT_RISING;            /* 上升沿触发 */
	gpio_init_struct.Pull = GPIO_PULLDOWN;
	HAL_GPIO_Init(KEY0_GPIO_PORT, &gpio_init_struct);    /* KEY0配置为上升沿触发中断 */
	
	HAL_NVIC_SetPriority(EXTI15_10_IRQn, 0, 2);               /* 抢占0，子优先级2 */
	HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);                       /* 使能中断线4 */
}


void EXTI15_10_IRQHandler(void)
{
    HAL_GPIO_EXTI_IRQHandler(KEY0_GPIO_PIN);         /* 调用中断处理公用函数 清除KEY0所在中断线 的中断标志位 */
    __HAL_GPIO_EXTI_CLEAR_IT(KEY0_GPIO_PIN);         /* HAL库默认先清中断再处理回调，退出时再清一次中断，避免按键抖动误触发 */	
}



void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
//	delay_ms(10);
//	if (KEY_PIN_READ)
//	{
////		uart_cmd.cmd_type = USART_CMD_FLASH_GROUP;
//		LED0_TOGGLE();
//	}
	
	
}

void Wait_key_press(void) 
{
	while(1)
	{
		if (1 == KEY_PIN_READ)
		{
			delay_ms(10);
			if (1 == KEY_PIN_READ) break;
		}
	}	
}	

