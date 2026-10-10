#include <stdexcept>
#include <iostream>
#include <fstream>
#include <vector>
#include "ec5_lightness_history_v1_main.cpp"
#include "lh_frame_fill.hpp"

int testBusy=1,testCalls=0,testBeginCalls=0;
bool testDriverResult=true,testDriverEvidence=true,testFixtureResult=true,testFailOnComplete=false;
EpdOperationReport testReport;
void epdBegin() { ++testBeginCalls; }
int epdReadBusy() { return testBusy; }
const EpdOperationReport &epdGetLastOperationReport() { return testReport; }
bool epdValidateCompiledChromaGridFixtures() { return testFixtureResult; }
bool epdDisplayCompiledChromaGrid(EpdChromaGridRole role) {
  ++testCalls;
  const auto &a=kActions[static_cast<unsigned>(role)-1];
  testReport={};
  testReport.operationId=testCalls;
  testReport.valid=true; testReport.sequenceOk=true;
  testReport.mappingApplied=true;
  testReport.ponBusySeen=true; testReport.drfBusySeen=testDriverEvidence; testReport.pofBusySeen=true;
  testReport.inputFrameFnv1a=a.frameFnv1a;
  testReport.cs1DtmFnv1a=a.cs1DtmFnv1a;
  testReport.cs2DtmFnv1a=a.cs2DtmFnv1a;
  if(testFailOnComplete) Preferences::failWrite=true;
  return testDriverResult;
}
void check(bool condition,const char *message) { if(!condition) throw std::runtime_error(message); }
const String sourceReview=std::string(64,'a');
void requestHeaders(unsigned ordinal,bool executing,const String &prior=sourceReview) {
  server.headers.clear(); server.argumentCount=0;
  const auto &a=kActions[ordinal-1];
  server.headers={{kBuildHeader,kBuildTag},{kTestHeader,kTestId},{kCampaignHeader,kCampaignId},
    {kActionHeader,a.actionId},{kOrdinalHeader,String(ordinal)},{kDescriptorHeader,a.descriptorId},
    {kBootNonceHeader,bootNonce()},{kIntentHeader,executing?kExecuteIntent:kArmIntent},
    {"X-LH-Run-Id","TEST_FIXTURE_LH1"},{"X-LH-Source-Review",sourceReview},{"X-LH-Prior-Review",prior}};
  if(executing) server.headers[kArmNonceHeader]=armNonce();
}
void arm(unsigned ordinal,const String &prior=sourceReview) {
  requestHeaders(ordinal,false,prior); server.request(kArmRoute,HTTP_POST);
  check(server.code==201,"ARM did not return 201");
}
void queue(unsigned ordinal,const String &prior=sourceReview) {
  arm(ordinal,prior); requestHeaders(ordinal,true,prior); server.request(kExecuteRoute,HTTP_POST);
  check(server.code==202,"EXECUTE did not return 202");
  check(persistentPhase==kPhaseConsumed,"not consumed before dispatch");
}
void stopped(int calls=0) {
  for(int i=0;i<3;++i) loop();
  check(state==RuntimeState::FaultLocked,"must fault lock");
  check(testCalls==calls,"unexpected driver call or retry");
  check(!executePending,"pending action survives stop");
}
int main(int argc,char **argv) {
 try {
  check(argc==2,"one case required"); const std::string scenario=argv[1];
  Preferences::values["p2catwsv1/used_p2cw1"]=2;
  if(scenario=="fixture_failure") testFixtureResult=false;
  if(scenario=="nvs_open_failure") Preferences::failBegin=true;
  if(scenario=="boot_write_failure") Preferences::failWrite=true;
  if(scenario=="invalid_cursor") Preferences::values["lhist_v1/cur_lh1"]=0xffff;
  setup();
  if(scenario=="fixture_failure"||scenario=="nvs_open_failure"||scenario=="boot_write_failure"||scenario=="invalid_cursor") {
    check(state==RuntimeState::FaultLocked&&testCalls==0&&testBeginCalls==0,"startup failure touched driver");
  } else {
    check(state==RuntimeState::Ready&&testCalls==0,"startup must be ready without refresh");
    if(scenario=="chain") {
      for(unsigned n=1;n<=3;++n) {
        const String review=std::string(64,char('a'+n-1)); queue(n,review);
        check(testCalls==int(n-1),"ACK called driver directly");
        loop(); check(testCalls==int(n),"one driver per stage");
        for(int i=0;i<10;++i) loop(); check(testCalls==int(n),"automatic chaining");
        check(nextOrdinal==n+1,"wrong following ordinal");
        std::cout<<publishedReport.c_str()<<'\n';
      }
      check(state==RuntimeState::Complete,"campaign not complete");
      requestHeaders(3,false,std::string(64,'d')); server.request(kArmRoute,HTTP_POST); stopped(3);
    } else if(scenario=="frames") {
      std::vector<uint8_t> frame(307200); uint32_t histogram[8];
      check(!lh_frame::build(0,frame.data(),histogram)&&!lh_frame::build(4,frame.data(),histogram),"white/repeat admitted");
      for(unsigned n=1;n<=3;++n) {
        check(lh_frame::build(n,frame.data(),histogram),"frame build failed");
        std::ofstream f("native-frame-"+std::to_string(n)+".bin",std::ios::binary); f.write(reinterpret_cast<char *>(frame.data()),frame.size());
        for(unsigned i=0;i<8;++i) check(histogram[i]==kActions[n-1].histogram[i],"histogram differs");
      }
    } else if(scenario=="read_only") {
      for(const auto route:{kVersionRoute,kManifestRoute,kStatusRoute,kReportRoute}) {
        server.request(route,HTTP_GET); check(server.code==200,"GET failed"); std::cout<<server.body.c_str()<<'\n';
      }
      server.argumentCount=1; server.request(kStatusRoute,HTTP_GET); check(server.code==400,"GET body admitted");
      check(state==RuntimeState::Ready&&testCalls==0,"read-only mutated");
    } else if(scenario=="reboot") {
      queue(1); loop(); bootNonceLow+=100; check(!initializeOrValidateCampaignBootBinding(),"reboot admitted");
      setup(); stopped(1);
    } else if(scenario=="duplicate_execute") {
      queue(1); server.request(kExecuteRoute,HTTP_POST); stopped();
    } else if(scenario=="duplicate_arm") {
      arm(1); server.request(kArmRoute,HTTP_POST); stopped();
    } else if(scenario=="changed_review_execute") {
      arm(1); requestHeaders(1,true); server.headers["X-LH-Run-Id"]="different_run"; server.request(kExecuteRoute,HTTP_POST); stopped();
    } else if(scenario=="reused_stage_review") {
      queue(1); loop(); requestHeaders(2,false); server.request(kArmRoute,HTTP_POST); stopped(1);
    } else if(scenario=="driver_failure"||scenario=="bad_driver_report"||scenario=="complete_write_failure") {
      queue(1); testDriverResult=scenario!="driver_failure"; testDriverEvidence=scenario!="bad_driver_report";
      testFailOnComplete=scenario=="complete_write_failure"; loop(); stopped(1);
    } else if(scenario=="busy_execute"||scenario=="consume_write_failure") {
      arm(1); requestHeaders(1,true);
      testBusy=scenario=="busy_execute"?0:1; Preferences::failWrite=scenario=="consume_write_failure";
      server.request(kExecuteRoute,HTTP_POST); stopped();
    } else if(scenario=="busy_dispatch"||scenario=="source_lost_dispatch"||scenario=="cursor_changed_dispatch") {
      queue(1);
      if(scenario=="busy_dispatch") testBusy=0;
      if(scenario=="source_lost_dispatch") Preferences::values.erase("p2catwsv1/used_p2cw1");
      if(scenario=="cursor_changed_dispatch") Preferences::values["lhist_v1/cur_lh1"]=encodeCursor(kPhaseConsumed,2);
      loop(); stopped();
    } else {
      requestHeaders(1,false);
      if(scenario=="missing_white") Preferences::values.erase("p2catwsv1/used_p2cw1");
      else if(scenario=="busy_arm") testBusy=0;
      else if(scenario=="arm_write_failure") Preferences::failWrite=true;
      else if(scenario=="wrong_boot") server.headers[kBootNonceHeader]="stale";
      else if(scenario=="wrong_action") server.headers[kActionHeader]="stale";
      else if(scenario=="body") server.argumentCount=1;
      else if(scenario=="invalid_review") server.headers["X-LH-Source-Review"]="invalid";
      else if(scenario=="ordinal_skip") server.headers[kOrdinalHeader]="3";
      else check(scenario=="unknown_mutation","unknown case");
      server.request(scenario=="unknown_mutation"?"/api/reset":kArmRoute,HTTP_POST); stopped();
    }
  }
  std::cout<<"PASS "<<scenario<<'\n'; return 0;
 } catch(const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
