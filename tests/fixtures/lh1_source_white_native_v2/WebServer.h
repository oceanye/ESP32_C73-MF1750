#pragma once
#include "Arduino.h"
#include <map>
#include <functional>
enum {HTTP_GET=0,HTTP_POST=1};
class WebServer {
 public:
  using Handler=std::function<void()>;
  std::map<std::string,String> headers;
  std::map<std::pair<std::string,int>,Handler> routes;
  Handler notFound;
  int code=0, argumentCount=0, methodValue=HTTP_GET;
  String body;
  explicit WebServer(int) {}
  int args() const { return argumentCount; }
  bool hasArg(const char *) const { return argumentCount!=0; }
  bool hasHeader(const char *k) const { return headers.count(k)!=0; }
  String header(const char *k) const { auto i=headers.find(k); return i==headers.end()?String():i->second; }
  void send(int c,const char *,const String &b) { code=c; body=b; }
  void collectHeaders(const char **,size_t) {}
  void on(const char *route,int method,Handler h) { routes[{route,method}]=h; }
  void onNotFound(Handler h) { notFound=h; }
  int method() const { return methodValue; }
  void begin() {}
  void stop() {}
  void handleClient() {}
  void request(const char *path,int method) {
    methodValue=method; code=0;
    auto i=routes.find({path,method});
    if(i!=routes.end()) i->second(); else notFound();
  }
};
