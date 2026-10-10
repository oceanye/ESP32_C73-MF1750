//=============================================================================
//                   E6 13 inch Customer FW Reference Code 
//
// File Name : main.h
// Author : Electronic Design Dept. II
// Data : 2024.08.08
// Version : 1.0
// Copyright : E Ink Holdings Inc.
//=============================================================================
#ifndef __MAIN_H__
#define __MAIN_H__

typedef unsigned char u8;
typedef unsigned short u16;

//====== App command list ======
#define _getFirmware 0x01
#define _loadWF 0x20
#define _setVCOMDC 0x80
#define _getVCOMDC 0x81
#define _testPattern 0xEF

//====== Feedback message list ======
#define _msgActionSucces 0x00
#define _msgActionSuccesAndFreedbackData 0x01
#define _msgUnknownError 0xE0
#define _msgCheckSumError 0xE1
#define _msgNoVCOMError 0xE2

#endif

//=============================================================================

#ifdef __MAIN_C__
#define __MAIN_EXTERN__
#else 
#define __MAIN_EXTERN__ extern
#endif

__MAIN_EXTERN__ void fillFeedback(unsigned char msgType, unsigned int dataLen);
