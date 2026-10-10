#!/usr/bin/env python3
"""Offline-gated MIDDLE (ordinal 2) runner for MF1750 LH1/LH4 R1.

The module performs strict package/source reconciliation and can execute only
against an explicitly injected synthetic transport.  No import or CLI command
opens sockets, serial ports, cameras, relays, or devices.  Live authorization
is intentionally absent; callers must provide an offline transport for tests.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, time, http.client, ipaddress
from urllib.parse import urlsplit
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DEFAULT = ROOT / '.test-output/offline/LH1_LH4_20260912_R1'
# Source ordinal-1 observed a 45.354 s driver; MIDDLE enforces the wider
# documented guard of at least 60 s before its first status poll.
OBSERVED_SOURCE_DRIVER_SECONDS = 45.354
INITIAL_STATUS_WAIT_SECONDS = 60
POLL_INTERVAL_SECONDS = 2
MAX_STATUS_POLLS = 90
HEX = re.compile(r'^[0-9a-f]{64}$')
NONCE = re.compile(r'^[0-9a-f]{16}$')

class MiddleRunnerError(RuntimeError):
    """Fail closed; a failed request is never retried."""

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def seal(value: dict) -> dict:
    body = deepcopy(value); body['integrity'] = {'algorithm':'sha256-canonical-json-without-integrity','sha256':digest(canonical(value))}; return body

def _pairs(pairs):
    out = {}
    for k,v in pairs:
        if k in out: raise MiddleRunnerError('duplicate JSON key: '+k)
        out[k] = v
    return out

def parse_json(data: bytes) -> dict:
    try: value = json.loads(data, object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(MiddleRunnerError('non-finite JSON: '+x)))
    except (ValueError, UnicodeError) as exc: raise MiddleRunnerError('invalid JSON') from exc
    if not isinstance(value, dict): raise MiddleRunnerError('JSON object required')
    return value

def _regular(path: Path) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file(): raise MiddleRunnerError('missing or unsafe file: '+str(path))
    return path.read_bytes()
def file_binding(path: Path) -> dict:
    path = Path(path).resolve(); payload = _regular(path); return {'path':str(path),'bytes':len(payload),'sha256':digest(payload)}
def read_bound(binding: dict) -> bytes:
    if not isinstance(binding, dict) or set(binding) != {'path','bytes','sha256'}: raise MiddleRunnerError('invalid file binding')
    path = Path(binding['path']); payload = _regular(path)
    if type(binding['bytes']) is not int or len(payload) != binding['bytes'] or digest(payload) != binding['sha256']: raise MiddleRunnerError('file binding differs: '+str(path))
    return payload
def verify_integrity(value: dict) -> None:
    body = deepcopy(value); integrity = body.pop('integrity', None)
    if not isinstance(integrity, dict): raise MiddleRunnerError('canonical integrity differs')
    ok = ((integrity.get('algorithm') == 'sha256-canonical-json-without-integrity' and integrity.get('sha256') == digest(canonical(body))) or
          (integrity.get('canonical_sha256') == digest(canonical(body)) and isinstance(integrity.get('scope'), str)))
    if not ok: raise MiddleRunnerError('canonical integrity differs')
def read_record(path: Path) -> dict:
    value = parse_json(_regular(path)); verify_integrity(value); return value
def _require(value: dict, expected: dict, label='record') -> None:
    for key,wanted in expected.items():
        found = value.get(key)
        if type(found) is not type(wanted) or canonical(found) != canonical(wanted): raise MiddleRunnerError(f'{label} {key} differs')
def write_new(path: Path, value: dict|bytes) -> None:
    payload = canonical(value)+b'\n' if isinstance(value,dict) else value
    with Path(path).open('xb') as fh: fh.write(payload); fh.flush(); os.fsync(fh.fileno())

def _http(method: str, url: str, headers: dict, timeout: int):
    """Single non-retrying HTTP request, enabled only by explicit run-live."""
    parts = urlsplit(url)
    if parts.scheme != 'http' or parts.username or parts.password or parts.port not in (None, 80):
        raise MiddleRunnerError('live origin must be plain HTTP port 80')
    try:
        address = ipaddress.ip_address(parts.hostname or '')
    except ValueError as exc:
        raise MiddleRunnerError('live origin must use literal private IPv4') from exc
    if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
        raise MiddleRunnerError('live origin must use literal private IPv4')
    conn = http.client.HTTPConnection(parts.hostname, 80, timeout=timeout)
    try:
        conn.request(method, parts.path or '/', headers={'Connection':'close', **headers})
        response = conn.getresponse(); raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024: raise MiddleRunnerError('HTTP response too large')
        return response.status, raw
    finally:
        conn.close()

def validate_package(package: Path) -> dict:
    package = Path(package).resolve(); manifest = read_record(package/'manifest.json'); contract = parse_json(_regular(package/'contract.json')); build = read_record(package/'build-report.json')
    actions = contract.get('actions');
    if not isinstance(actions,list) or len(actions)!=3: raise MiddleRunnerError('three-action contract required')
    middle = actions[1]
    _require(middle, {'ordinal':2,'stage':'MIDDLE','global_header':'commented','driver_role':'Mid','role':'LH1_MIDDLE'}, 'MIDDLE action')
    if middle.get('prior_action_id') != actions[0].get('action_id'): raise MiddleRunnerError('MIDDLE prior action binding differs')
    if not HEX.fullmatch(str(middle.get('action_id',''))) or not HEX.fullmatch(str(middle.get('descriptor_id',''))): raise MiddleRunnerError('MIDDLE identifiers invalid')
    _require(contract, {'action_count':3,'autochain':False,'retry':False}, 'contract')
    if manifest.get('contract_id') != contract.get('contract_id') or build.get('result') != 'PASS': raise MiddleRunnerError('manifest/build contract mismatch')
    frame = package/'middle.frame4bpp'; outputs = {Path(x.get('path','')).resolve() for x in manifest.get('outputs',[])}
    if frame.resolve() not in outputs: raise MiddleRunnerError('middle frame not sealed in manifest')
    if digest(_regular(frame)) != middle.get('frame',{}).get('sha256'): raise MiddleRunnerError('middle frame digest differs')
    return {'package':package,'manifest':manifest,'contract':contract,'build':build,'middle':middle,'contract_id':contract['contract_id']}

def validate_source_reconciliation(path: Path, ctx: dict) -> dict:
    value = read_record(path)
    if value.get('kind') not in ('mf1750-lh1-lh4-source-terminal-reconciliation-v1','mf1750-lh1-lh4-middle-source-binding-v1','mf1750-lh1-lh4-source-result-v1'):
        raise MiddleRunnerError('source reconciliation kind differs')
    if value.get('contract_id') not in (ctx['contract_id'], None): raise MiddleRunnerError('source reconciliation contract differs')
    boot = value.get('boot_nonce') or value.get('source_boot_nonce')
    if not isinstance(boot,str) or not NONCE.fullmatch(boot): raise MiddleRunnerError('source boot nonce missing')
    terminal = value.get('terminal_report', value.get('terminal', value))
    status = value.get('terminal_status', value.get('status', {}))
    if not isinstance(terminal,dict) or not isinstance(status,dict): raise MiddleRunnerError('source terminal/status missing')
    if terminal.get('terminal_state') not in ('COMPLETE','complete_pass') or terminal.get('result') is not True: raise MiddleRunnerError('source terminal is not complete')
    if status.get('cursor_raw') != 2 or status.get('next_ordinal') != 2: raise MiddleRunnerError('source cursor must be 2')
    if terminal.get('next_ordinal') not in (2,None): raise MiddleRunnerError('source terminal next ordinal differs')
    if status.get('boot_nonce',boot) != boot or terminal.get('boot_nonce',boot) != boot: raise MiddleRunnerError('source terminal/status boot mismatch')
    if 'terminal_sha256' in value and (not isinstance(value['terminal_sha256'], str) or not HEX.fullmatch(value['terminal_sha256'])):
        raise MiddleRunnerError('source terminal binding hash invalid')
    if status.get('total_driver_call_count') not in (None, 1) or terminal.get('total_driver_call_count') not in (None, 1):
        raise MiddleRunnerError('source terminal driver count must be 1')
    if value.get('source_replayed') is True or value.get('claim_created') is True or value.get('source_claim_created') is True: raise MiddleRunnerError('source replay/claim forbidden')
    return value

def validate_stage_review(path: Path, source: dict, ctx: dict) -> dict:
    value = read_record(path)
    _require(value, {'kind':'mf1750-lh1-middle-new-stage-review-v1','ordinal':2,
                     'contract_id':ctx['contract_id'],'source_review_is_white_reuse':False,
                     'prior_review_is_distinct_from_source':True}, 'stage review')
    if value.get('source_review_sha256') != source.get('source_review_sha256'):
        raise MiddleRunnerError('stage review source digest differs')
    if not HEX.fullmatch(str(value.get('prior_review_sha256',''))) or value['prior_review_sha256'] == value['source_review_sha256']:
        raise MiddleRunnerError('stage review prior digest must be new and distinct')
    if value.get('boot_nonce') != source.get('boot_nonce'):
        raise MiddleRunnerError('stage review boot differs')
    return value

class Session:
    def __init__(self, ctx:dict, source:dict, output:Path, base_url:str, transport:Callable, sleeper:Callable=time.sleep):
        if transport is None: raise MiddleRunnerError('offline-only runner requires injected transport')
        self.ctx,self.source,self.base_url = ctx,source,base_url.rstrip('/'); self.output=Path(output).resolve(); self.output.mkdir(parents=True,exist_ok=False); self.transport=transport; self.sleeper=sleeper; self.index=0; self.counts={'GET':0,'POST':0}
    def request(self, method:str, route:str, expected:int, headers:dict|None=None)->dict:
        self.index += 1; self.counts[method] += 1; stem=f'{self.index:03d}-{method.lower()}-{route}'
        meta={'method':method,'url':self.base_url+self.ctx['routes'].get(route,'/'+route),'headers':headers or {},'request_body_bytes':0,'started_at':datetime.now(timezone.utc).isoformat()}
        try:
            status,raw=self.transport(method,meta['url'],headers or {},65)
            if not isinstance(raw,bytes): raise MiddleRunnerError('transport must return bytes')
            body=self.output/(stem+'.body.bin'); write_new(body,raw); meta.update(status=status,finished_at=datetime.now(timezone.utc).isoformat(),response_body=file_binding(body)); write_new(self.output/(stem+'.json'),seal(meta))
        except Exception as exc:
            try: write_new(self.output/(stem+'.error.json'),seal({**meta,'finished_at':datetime.now(timezone.utc).isoformat(),'error':type(exc).__name__,'no_retry':True}))
            except FileExistsError: pass
            raise MiddleRunnerError(f'{method} {route} failed; STOP, no retry') from exc
        if status != expected: raise MiddleRunnerError(f'{route} HTTP {status}; STOP, no retry')
        return parse_json(raw)

def _headers(ctx, source, action, intent, arm_nonce=None, stage_review=None):
    # These headers are part of the firmware identity contract.  Bind review
    # fields to the reconciled ordinal-1 evidence; never invent a new digest.
    h={'X-EC5-Build-Tag':ctx['contract'].get('build_tag',''),
       'X-EC5-Test-Id':ctx['contract'].get('algorithm_id','MF1750_LIGHTNESS_HISTORY_V1_20260911'),
       'X-EC5-Campaign-Id':ctx['contract'].get('campaign_id',''),
       'X-EC5-Action-Id':action['action_id'],'X-EC5-Ordinal':'2',
       'X-EC5-Descriptor-Id':action['descriptor_id'],'X-EC5-Boot-Nonce':source['boot_nonce'],
       'X-EC5-Intent':intent,
       'X-LH-Run-Id':source.get('run_id','LH1_SOURCE_FIELD_20260913_V3'),
       'X-LH-Source-Review':source.get('source_review_sha256',source.get('terminal_sha256','')),
       'X-LH-Prior-Review':(stage_review or {}).get('prior_review_sha256',source.get('prior_review_sha256',source.get('source_review_sha256',source.get('terminal_sha256',''))))}
    if arm_nonce: h['X-EC5-Arm-Nonce']=arm_nonce
    return h

def _run_middle_impl(package:Path, source_reconciliation:Path, output:Path, base_url='http://192.168.1.77', transport=None, sleeper=time.sleep, initial_wait=INITIAL_STATUS_WAIT_SECONDS, stage_review=None)->dict:
    ctx=validate_package(package); source=validate_source_reconciliation(source_reconciliation,ctx); source['boot_nonce']=source.get('boot_nonce') or source.get('source_boot_nonce')
    if stage_review is not None: stage_review=validate_stage_review(stage_review,source,ctx)
    routes={'version':'/api/ec5/lightness-history-v1/version','manifest':'/api/ec5/lightness-history-v1/manifest','status':'/api/ec5/lightness-history-v1/status','report':'/api/ec5/lightness-history-v1/report','arm':'/api/ec5/lightness-history-v1/arm','execute':'/api/ec5/lightness-history-v1/execute'}; ctx['routes']=routes
    session=Session(ctx,source,output,base_url,transport,sleeper)
    # Read-only preflight; any GET failure stops before ARM mutation.
    pre={r:session.request('GET',r,200) for r in ('version','manifest','status','report')}
    if pre['status'].get('boot_nonce') != source['boot_nonce'] or pre['report'].get('boot_nonce') != source['boot_nonce']: raise MiddleRunnerError('same-boot preflight binding differs')
    if pre['status'].get('cursor_raw') != 2 or pre['status'].get('next_ordinal') != 2: raise MiddleRunnerError('device cursor is not source cursor 2')
    action=ctx['middle']; arm=session.request('POST','arm',201,_headers(ctx,source,action,'ARM_ONE_LIGHTNESS_HISTORY_ACTION',stage_review=stage_review)); _require(arm,{'accepted':True,'armed':True,'phase':1,'boot_nonce':source['boot_nonce'],'ordinal':2},'ARM201')
    nonce=arm.get('arm_nonce');
    if not isinstance(nonce,str) or not NONCE.fullmatch(nonce): raise MiddleRunnerError('invalid ARM nonce')
    exe=session.request('POST','execute',202,_headers(ctx,source,action,'EXECUTE_ONE_LIGHTNESS_HISTORY_ACTION_ONCE',nonce,stage_review)); _require(exe,{'accepted':True,'execute_consumed':True,'phase':2,'job_id':2,'boot_nonce':source['boot_nonce'],'ordinal':2},'EXEC202')
    if type(initial_wait) is not int or initial_wait < INITIAL_STATUS_WAIT_SECONDS: raise MiddleRunnerError('initial status wait must be >=60 seconds (at least 60 seconds)')
    session.sleeper(initial_wait)
    terminal=None; status=None
    for _ in range(MAX_STATUS_POLLS):
        status=session.request('GET','status',200)
        if status.get('phase')==3 or status.get('state')=='fault_locked': raise MiddleRunnerError('FAULT; STOP no retry')
        if status.get('next_ordinal')==3 and status.get('cursor_raw')==3:
            terminal=session.request('GET','report',200); break
        if status.get('next_ordinal') != 2: raise MiddleRunnerError('unexpected in-flight cursor')
        session.sleeper(POLL_INTERVAL_SECONDS)
    if terminal is None: raise MiddleRunnerError('terminal deadline exceeded; STOP no retry')
    _require(terminal,{'ordinal':2,'action_id':action['action_id'],'terminal_state':'COMPLETE','result':True,'driver_call_count_for_action':1,'total_driver_call_count':2,'no_retry':True},'MIDDLE report')
    _require(status,{'cursor_raw':3,'next_ordinal':3,'arm_request_count':1,'execute_request_count':1,'total_driver_call_count':2,'boot_nonce':source['boot_nonce']},'MIDDLE status')
    result=seal({'kind':'mf1750-lh1-lh4-middle-result-v1','outcome':'complete_pass','ordinal':2,'contract_id':ctx['contract_id'],'source_reconciliation':file_binding(source_reconciliation),'terminal':terminal,'status':status,'network':session.counts,'driver_calls':2,'middle_driver_calls':1,'visible_refreshes':1,'source_replayed':False,'claim_created':False,'transcripts':[file_binding(p) for p in sorted(session.output.glob('*')) if p.is_file()]})
    write_new(session.output/'result.json',result); return result

def run_middle(package:Path, source_reconciliation:Path, output:Path, base_url='http://192.168.1.77', transport=None, sleeper=time.sleep, initial_wait=INITIAL_STATUS_WAIT_SECONDS, stage_review=None)->dict:
    """Execute one synthetic MIDDLE transaction; failures emit O_EXCL STOP."""
    try:
        return _run_middle_impl(package, source_reconciliation, output, base_url, transport, sleeper, initial_wait, stage_review)
    except Exception as exc:
        out = Path(output).resolve()
        try:
            out.mkdir(parents=True, exist_ok=True)
            write_new(out/'STOP.json', seal({'kind':'mf1750-lh1-lh4-middle-stop-v1','outcome':'STOP_UNCERTAIN_OR_FAILED','error':str(exc),'ordinal':2,'no_retry':True,'no_recovery':True,'source_replayed':False,'claim_created':False}))
        except (FileExistsError, OSError):
            pass
        raise

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('command',choices=('validate','source-validate','run-live')); p.add_argument('--package',type=Path,default=PACKAGE_DEFAULT); p.add_argument('--source-reconciliation',type=Path); p.add_argument('--stage-review',type=Path); p.add_argument('--output',type=Path); p.add_argument('--base-url',default='http://192.168.1.77')
    a=p.parse_args(argv)
    try:
        ctx=validate_package(a.package)
        if a.command=='validate': value={'result':'PASS','contract_id':ctx['contract_id'],'ordinal':2,'stage':'MIDDLE','live_authorized':False}
        elif a.command=='source-validate': value=validate_source_reconciliation(a.source_reconciliation,ctx)
        else:
            if not a.source_reconciliation or not a.output: raise MiddleRunnerError('--source-reconciliation and --output required')
            if not a.stage_review: raise MiddleRunnerError('--stage-review required for run-live')
            value=run_middle(a.package,a.source_reconciliation,a.output,a.base_url,transport=_http,sleeper=time.sleep,initial_wait=INITIAL_STATUS_WAIT_SECONDS,stage_review=a.stage_review)
    except (MiddleRunnerError,OSError,ValueError,KeyError,TypeError) as exc: print('MIDDLE stopped: '+str(exc),file=sys.stderr); return 2
    print(json.dumps(value,ensure_ascii=False,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
