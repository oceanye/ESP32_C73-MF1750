#pragma once
#include "Arduino.h"
enum {WIFI_STA=0,WIFI_AP=1,WL_CONNECTED=3};
struct TestIP { String toString() { return "DESKTOP_STUB_NO_NETWORK"; } };
struct TestWiFi {
  void mode(int) {}
  void begin(const char *,const char *) {}
  int status() { return WL_CONNECTED; }
  TestIP localIP() { return {}; }
  TestIP softAPIP() { return {}; }
  void softAP(const char *,const char *) {}
};
inline TestWiFi WiFi;
