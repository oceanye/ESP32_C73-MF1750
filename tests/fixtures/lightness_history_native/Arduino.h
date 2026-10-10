#pragma once
// Desktop-only substitutes. No GPIO, USB, socket or serial operations exist.
#include <cstdint>
#include <cstddef>
#include <string>
#include <type_traits>
class String {
 public:
  std::string value;
  String()=default;
  String(const char *v):value(v?v:""){}
  String(std::string v):value(v){}
  template<class T, typename std::enable_if<std::is_integral<T>::value,int>::type=0>
  String(T v):value(std::to_string(v)){}
  const char *c_str() const { return value.c_str(); }
  size_t length() const { return value.size(); }
  bool isEmpty() const { return value.empty(); }
  char operator[](size_t i) const { return value[i]; }
  String &operator+=(const String &s) { value+=s.value; return *this; }
  String &operator+=(char c) { value+=c; return *this; }
  friend String operator+(const String &a,const String &b) { return a.value+b.value; }
  friend bool operator==(const String &a,const String &b) { return a.value==b.value; }
  friend bool operator!=(const String &a,const String &b) { return !(a==b); }
};
inline uint32_t testMillis=0;
inline uint32_t millis() { return testMillis; }
inline void delay(unsigned ms) { testMillis+=ms; }
inline int digitalRead(int) { return 1; }
struct TestSerial {
  void begin(unsigned) {}
  void println(const char *) {}
  template<class... T> void printf(const char *,T...) {}
};
inline TestSerial Serial;
