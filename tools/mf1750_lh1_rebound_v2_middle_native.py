"""Offline native MIDDLE wire-schema test; synthetic GPIO/NVS/driver only."""
from pathlib import Path
import argparse
import subprocess

from tools import mf1750_lh1_rebound_v2_native_audit as native
from tools import mf1750_lh1_rebound_v2_review as review
from tools import mf1750_lh1_rebound_v2_middle_once as host
from tools.mf1750_lh1_lh4_once import canonical, file_binding, seal, write_new, parse_json, _require


def audit(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    ctx = review.validate_package()
    fixture = native.prepare_fixture(out)
    arduino = (native.FIXTURES / 'Arduino.h').read_text(encoding='utf8')
    arduino = arduino.replace('inline int digitalRead(int) { return 1; }',
                              'inline int digitalRead(int) { return 0; }')
    write_new(fixture / 'Arduino.h', arduino.encode())
    # Quoted includes in WebServer/WiFi must resolve this same Arduino stub.
    for header in native.FIXTURES.glob('*.h'):
        if not (fixture / header.name).exists():
            write_new(fixture / header.name, header.read_bytes())
    cpp = (fixture / 'protocol.cpp').read_text(encoding='utf8')
    cpp = cpp.replace('TEST_FIXTURE_LH1', review.RUN)
    cpp = cpp.replace('  setup();', '''  setup();
  // Deterministic test-only boot fixture. No physical NVS is accessed.
  bootNonceHigh=0x7274e005; bootNonceLow=0xc8833ca1;
  Preferences::values["lh1reb_v2/boot_lh1r"]=0x7274e005c8833ca1ULL;
  check(initializeOrValidateCampaignBootBinding(),"test boot setup failed");''', 1)
    cpp = cpp.replace('  if(testFailOnComplete)', '''  // Synthetic report fields exercise host validation; no physics model.
  testReport.spiHz=1000000;
  for(auto p:{&testReport.ponBusy,&testReport.drfBusy,&testReport.pofBusy}) {
    p->gateEntryLevel=1;p->preCommandLevel=1;p->waitEntryLevel=0;p->waitExitLevel=1;
    p->preCommandIdleOk=true;p->assertionAfterIdle=true;p->waitMs=1;
  }
  testReport.resetBusy.waitEntryLevel=0;testReport.resetBusy.waitExitLevel=1;
  testReport.postPsrBusy.preCommandLevel=1;testReport.postPsrBusy.preCommandIdleOk=true;
  testReport.postPsrBusy.waitEntryLevel=1;testReport.postPsrBusy.waitExitLevel=1;
  testReport.safeFinishBusyBeforePinsLow=1;testReport.safeFinishBusyAfterPinsLow=1;
  testReport.safeFinishBusyAfter5Ms=1;testReport.finalBusyLevel=1;
  testReport.finalRstLevel=0;testReport.finalCs1Level=0;testReport.finalCs2Level=0;
  delay(10);
  if(testFailOnComplete)''', 1)
    cpp = cpp.replace('    if(scenario=="chain") {', '''    if(scenario=="middle_wire") {
      queue(1);loop();
      for(const auto route:{kVersionRoute,kManifestRoute,kStatusRoute,kReportRoute}) {
        server.headers.clear();server.request(route,HTTP_GET);
        check(server.code==200,"SOURCE GET failed");std::cout<<server.body.c_str()<<'\\n';
      }
      const String prior=std::string(64,'b');
      arm(2,prior);std::cout<<server.body.c_str()<<'\\n';
      requestHeaders(2,true,prior);server.request(kExecuteRoute,HTTP_POST);
      check(server.code==202,"MIDDLE EXEC failed");std::cout<<server.body.c_str()<<'\\n';
      loop();
      for(const auto route:{kStatusRoute,kReportRoute}) {
        server.headers.clear();server.request(route,HTTP_GET);
        check(server.code==200,"MIDDLE GET failed");std::cout<<server.body.c_str()<<'\\n';
      }
      check(testCalls==2 && nextOrdinal==3,"unexpected driver count/ordinal");
      for(int i=0;i<10;++i) loop();
      check(testCalls==2,"unexpected automatic TARGET");
    } else if(scenario=="chain") {''', 1)
    source = out / 'middle-wire.cpp'
    write_new(source, cpp.encode())
    compiler, env, msvc = native.compiler_environment()
    includes = [fixture, native.FIXTURES, review.PACKAGE / 'generated', review.ROOT / 'src']
    macros = ['MF1750_ENABLE_CHROMA_GRID=1', 'MF1750_LIGHTNESS_LH1_REBOUND_V2_BUILD=1',
              'EPD_ENABLE_TEST_PATTERN=0', 'MF1750_RUNTIME_LUT_PARTIAL_HOLD_BUILD=1']
    exe = out / ('middle-wire.exe' if msvc else 'middle-wire')
    if msvc:
        args = [compiler, '/nologo', '/std:c++17', '/EHsc', '/utf-8', '/D_CRT_SECURE_NO_WARNINGS']
        args += ['/I' + str(p) for p in includes] + ['/D' + p for p in macros]
        args += [str(source), '/Fe:' + str(exe), '/Fo:' + str(out / 'middle-wire.obj')]
    else:
        args = [compiler, '-std=c++17'] + ['-I' + str(p) for p in includes] + ['-D' + p for p in macros]
        args += [str(source), '-o', str(exe)]
    compiled = subprocess.run(args, cwd=out, env=env, capture_output=True)
    write_new(out / 'compile.log', compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError('native compile failed; inspect compile.log')
    result = subprocess.run([str(exe), 'middle_wire'], cwd=out, capture_output=True)
    write_new(out / 'middle-wire.log', result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('native case failed')
    rows = [parse_json(line) for line in result.stdout.splitlines() if line.startswith(b'{')]
    if len(rows) != 8:
        raise RuntimeError('expected 8 actual generated wire documents')
    host.validate_preflight(ctx, dict(zip(('version', 'manifest', 'status', 'report'), rows[:4])))
    prior = 'b' * 64
    for row, flag, phase in ((rows[4], 'armed', 1), (rows[5], 'execute_consumed', 2)):
        host.identity(ctx, row, prior)
        _require(row, {**host.gates.expected_action(ctx, 1), 'accepted': True, flag: True,
                      'phase': phase}, 'native ACK')
    host.validate_terminal(ctx, rows[6], rows[7], prior)
    report = seal({'kind': 'mf1750-lh1-rebound-v2-middle-native-v1', 'recorded_at': review.now(),
        'result': 'PASS', 'native_wire_documents': 8, 'host_preflight_ack_terminal': 'PASS',
        'hardware_accessed': False, 'physical_waveform_simulated': False,
        'driver_is_synthetic': True, 'qualified_count': 0,
        'host': host.dependencies(), 'package_manifest': file_binding(review.PACKAGE / 'manifest.json'),
        'source': file_binding(source), 'compile_command': args,
        'wire_log': file_binding(out / 'middle-wire.log'),
        'limitations': 'Actual generated main with desktop Arduino/WebServer/Preferences/GPIO and synthetic driver reports; no electrical or optical proof.'})
    write_new(out / 'native-audit.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    value = audit(parser.parse_args().output)
    print(canonical({'result': value['result'], 'wire_documents': 8, 'hardware_accessed': False}).decode())
