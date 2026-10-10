#ifndef _KEY_H
#define _KEY_H
#include "./SYSTEM/sys/sys.h"



#define KEY0_GPIO_PORT                  GPIOE
#define KEY0_GPIO_PIN                   GPIO_PIN_11
#define KEY0_GPIO_CLK_ENABLE()          do{ __HAL_RCC_GPIOE_CLK_ENABLE(); }while(0)   /* PE口时钟使能 */



#define KEY_PIN_READ  HAL_GPIO_ReadPin(KEY0_GPIO_PORT, KEY0_GPIO_PIN)


void Key_init(void);
void Wait_key_press(void); 



#endif



