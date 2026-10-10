#pragma once
#include <map>
#include <string>
#include <cstdint>
class Preferences {
 public:
  inline static std::map<std::string,uint64_t> values;
  inline static bool failWrite=false, failBegin=false;
  std::string ns;
  bool readOnly=false;
  bool begin(const char *n,bool r=false) { ns=n; readOnly=r; return !failBegin; }
  void end() {}
  std::string key(const char *k) const { return ns+"/"+k; }
  bool isKey(const char *k) const { return values.count(key(k))!=0; }
  uint16_t getUShort(const char *k,uint16_t fallback=0) const {
    return isKey(k)?static_cast<uint16_t>(values.at(key(k))):fallback;
  }
  uint64_t getULong64(const char *k,uint64_t fallback=0) const {
    return isKey(k)?values.at(key(k)):fallback;
  }
  size_t putUShort(const char *k,uint16_t v) {
    if(failWrite||readOnly) return 0; values[key(k)]=v; return 2;
  }
  size_t putULong64(const char *k,uint64_t v) {
    if(failWrite||readOnly) return 0; values[key(k)]=v; return 8;
  }
};
