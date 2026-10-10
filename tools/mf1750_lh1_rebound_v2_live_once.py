"""QUARANTINED historical V2 SOURCE runner; no further device access.

The caller must provide the already sealed app-only flash and fresh IPv4/MAC
binding. This runner does four read-only GETs before each gate, sends exactly
one ARM and one EXECUTE, polls to terminal once, and never retries a request.
It does not operate the relay; relay receipts are recorded separately.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, time
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'.test-output/offline/LH1_REBOUND_20260916_V2_R1'
ANCHOR='3bbf1bfffe29bf51eca3f1d876161c4fdd37ec792b9175b250549aa88ed72f84'
HEX=re.compile(r'^[0-9a-f]{64}$'); NONCE=re.compile(r'^[0-9a-f]{16}$')

def canon(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def seal(v): return {**v,'integrity':{'algorithm':'sha256-canonical-json-without-integrity','sha256':sha(canon(v))}}
def now(): return datetime.now(timezone.utc).isoformat()
def readj(p): return json.loads(Path(p).read_text(encoding='utf8'))
def write_new(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f: f.write((canon(v)+b'\n') if isinstance(v,dict) else v); f.flush(); os.fsync(f.fileno())
def require(ok,msg):
    if not ok: raise RuntimeError(msg)

def cfg():
    c=readj(PKG/'contract.json'); cfg=(next((PKG/'generated').glob('*_main_config.inc'))).read_text(encoding='utf8')
    def s(k):
        m=re.search(r'static constexpr const char \*'+re.escape(k)+r'\s*=\s*"([^"]*)";',cfg); require(m,'missing '+k); return m.group(1)
    art={Path(x['path']).suffix:x for x in readj(PKG/'build-report.json')['artifacts']}
    return c,{k:s(k) for k in ('kBuildTag','kTestId','kCampaignId','kContractId','kArmIntent','kExecuteIntent','kVersionRoute','kManifestRoute','kStatusRoute','kReportRoute','kArmRoute','kExecuteRoute')},art

class Once:
    def __init__(self,base,out,headers):
        u=urlsplit(base); require(u.scheme=='http' and u.port in (None,80) and u.hostname,'bad base url'); self.host=u.hostname; self.base='http://'+self.host; self.out=Path(out); self.headers=headers; self.n=0; self.boot=None; self.count={'GET':0,'POST':0}
    def req(self,method,route,status):
        self.n+=1; stem=f'{self.n:03d}-{method.lower()}-{route.strip("/").replace("/","_")}'; h={'Connection':'close',**self.headers.get('common',{})}; h.update(self.headers.get(method,{}));
        conn=HTTPConnection(self.host,80,timeout=8)
        try:
            conn.request(method,route,headers=h); r=conn.getresponse(); raw=r.read(2*1024*1024+1)
        finally: conn.close()
        self.count[method]+=1; write_new(self.out/(stem+'.body.bin'),raw); write_new(self.out/(stem+'.json'),seal({'method':method,'route':route,'status':r.status,'headers':h,'response_sha256':sha(raw),'recorded_at':now()})); require(r.status==status,f'{method} {route} status {r.status}, expected {status}');
        try: return json.loads(raw.decode('utf8'))
        except Exception as e: raise RuntimeError('invalid JSON '+route) from e
    def get4(self,busy):
        vals={k:self.req('GET',self.routes[k],200) for k in ('version','manifest','status','report')}
        st=vals['status']; require(st.get('busy')==busy,f'BUSY={st.get("busy")} expected {busy}'); require(st.get('phase')==0 and st.get('next_ordinal')==1,'fresh cursor not ordinal 1'); require(st.get('state')=='ready','device not ready'); require(vals['report'].get('total_driver_call_count')==0,'driver already called');
        if self.boot is None: self.boot=st.get('boot_nonce')
        require(isinstance(self.boot,str) and NONCE.fullmatch(self.boot),'invalid boot'); require(st.get('boot_nonce')==self.boot and vals['report'].get('boot_nonce')==self.boot,'boot mismatch')
        return vals

def run(base,out,relay_off,relay_on):
    raise RuntimeError('QUARANTINED: SOURCE already consumed; historical runner has admission/claim/polling defects. See STATUS_HANDOFF.md.')
    c,i,art=cfg(); require(c['contract_id']==i['kContractId'],'contract identity mismatch'); require(c['nvs']=={'namespace':'lh1reb_v2','cursor':'cur_lh1r','boot':'boot_lh1r'},'NVS contract mismatch'); require(c['actions'][0]['source_state']=='R4_RETAINED_CLEAN_WHITE_HOST_CONFIRMED','source semantics mismatch')
    common={'X-EC5-Build-Tag':i['kBuildTag'],'X-EC5-Test-Id':i['kTestId'],'X-EC5-Campaign-Id':i['kCampaignId'],'X-EC5-Action-Id':c['actions'][0]['action_id'],'X-EC5-Ordinal':'1','X-EC5-Descriptor-Id':c['actions'][0]['descriptor_id'],'X-EC5-Boot-Nonce':'','X-EC5-Intent':i['kArmIntent'],'X-LH-Run-Id':'LH1_REBOUND_V2_SOURCE_20260916','X-LH-Source-Review':ANCHOR,'X-LH-Prior-Review':ANCHOR}
    o=Once(base,out,{'common':common,'GET':{},'POST':{}}); o.routes={'version':i['kVersionRoute'],'manifest':i['kManifestRoute'],'status':i['kStatusRoute'],'report':i['kReportRoute'],'arm':i['kArmRoute'],'execute':i['kExecuteRoute']}
    # First GET discovers the boot; subsequent headers must bind this boot.
    vals=o.get4(0); common['X-EC5-Boot-Nonce']=o.boot
    write_new(Path(out)/'j2-off-result.json',seal({'kind':'mf1750-lh1-rebound-v2-j2-off','result':'PASS','boot_nonce':o.boot,'network':o.count,'relay':relay_off,'responses':vals,'recorded_at':now()}))
    vals=o.get4(1); write_new(Path(out)/'j2-on-result.json',seal({'kind':'mf1750-lh1-rebound-v2-j2-on','result':'PASS','boot_nonce':o.boot,'network':o.count,'relay':relay_on,'responses':vals,'recorded_at':now()}))
    arm=o.req('POST',o.routes['arm'],201); require(arm.get('accepted') is True and arm.get('phase')==1,'ARM response invalid'); an=arm.get('arm_nonce'); require(isinstance(an,str) and NONCE.fullmatch(an),'ARM nonce invalid')
    common['X-EC5-Intent']=i['kExecuteIntent']; common['X-EC5-Arm-Nonce']=an
    exe=o.req('POST',o.routes['execute'],202); require(exe.get('accepted') is True and exe.get('phase')==2,'EXECUTE response invalid')
    terminal=None; status=None
    for n in range(90):
        time.sleep(2); status=o.req('GET',o.routes['status'],200); require(status.get('boot_nonce')==o.boot,'boot changed');
        if status.get('phase')==3 or status.get('state')=='fault_locked': raise RuntimeError('device fault locked; no retry')
        if status.get('phase')==0 and status.get('next_ordinal')==2:
            terminal=o.req('GET',o.routes['report'],200); break
    require(terminal is not None,'terminal deadline exceeded; no retry'); require(terminal.get('result') is True and terminal.get('driver_called') is True and terminal.get('driver_call_count_for_action')==1,'terminal action not complete'); require(status.get('total_driver_call_count')==1,'driver count differs')
    result=seal({'kind':'mf1750-lh1-rebound-v2-source-result-v1','outcome':'complete_pass','contract_id':c['contract_id'],'boot_nonce':o.boot,'ordinal':1,'action_id':c['actions'][0]['action_id'],'driver_calls':1,'visible_refreshes':1,'qualified_count':0,'stop_and_review_required':True,'no_retry':True,'network':o.count,'terminal':terminal,'status':status,'relay_off':relay_off,'relay_on':relay_on,'recorded_at':now()}); write_new(Path(out)/'result.json',result); return result

def run_on_only(base,out,relay_on,boot):
    raise RuntimeError('QUARANTINED: SOURCE already consumed; historical runner has admission/claim/polling defects. See STATUS_HANDOFF.md.')
    c,i,art=cfg(); require(NONCE.fullmatch(boot),'invalid sealed boot')
    common={'X-EC5-Build-Tag':i['kBuildTag'],'X-EC5-Test-Id':i['kTestId'],'X-EC5-Campaign-Id':i['kCampaignId'],'X-EC5-Action-Id':c['actions'][0]['action_id'],'X-EC5-Ordinal':'1','X-EC5-Descriptor-Id':c['actions'][0]['descriptor_id'],'X-EC5-Boot-Nonce':boot,'X-EC5-Intent':i['kArmIntent'],'X-LH-Run-Id':'LH1_REBOUND_V2_SOURCE_20260916','X-LH-Source-Review':ANCHOR,'X-LH-Prior-Review':ANCHOR}
    o=Once(base,out,{'common':common,'GET':{},'POST':{}}); o.routes={k:i['k'+k.capitalize()+'Route'] for k in ('version','manifest','status','report','arm','execute')}; o.boot=boot
    vals=o.get4(1); write_new(Path(out)/'j2-on-result.json',seal({'kind':'mf1750-lh1-rebound-v2-j2-on','result':'PASS','boot_nonce':o.boot,'network':o.count,'relay':relay_on,'responses':vals,'recorded_at':now()}))
    arm=o.req('POST',o.routes['arm'],201); require(arm.get('accepted') is True and arm.get('phase')==1,'ARM response invalid'); an=arm.get('arm_nonce'); require(isinstance(an,str) and NONCE.fullmatch(an),'ARM nonce invalid')
    common['X-EC5-Intent']=i['kExecuteIntent']; common['X-EC5-Arm-Nonce']=an
    exe=o.req('POST',o.routes['execute'],202); require(exe.get('accepted') is True and exe.get('phase')==2,'EXECUTE response invalid')
    terminal=None; status=None
    for _ in range(90):
        time.sleep(2); status=o.req('GET',o.routes['status'],200); require(status.get('boot_nonce')==o.boot,'boot changed')
        if status.get('phase')==3 or status.get('state')=='fault_locked': raise RuntimeError('device fault locked; no retry')
        if status.get('phase')==0 and status.get('next_ordinal')==2: terminal=o.req('GET',o.routes['report'],200); break
    require(terminal is not None,'terminal deadline exceeded; no retry'); require(terminal.get('result') is True and terminal.get('driver_called') is True and terminal.get('driver_call_count_for_action')==1,'terminal action not complete'); require(status.get('total_driver_call_count')==1,'driver count differs')
    result=seal({'kind':'mf1750-lh1-rebound-v2-source-result-v1','outcome':'complete_pass','contract_id':c['contract_id'],'boot_nonce':o.boot,'ordinal':1,'action_id':c['actions'][0]['action_id'],'driver_calls':1,'visible_refreshes':1,'qualified_count':0,'stop_and_review_required':True,'no_retry':True,'network':o.count,'terminal':terminal,'status':status,'relay_on':relay_on,'recorded_at':now()}); write_new(Path(out)/'result.json',result); return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',required=True); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--relay-off',type=Path); ap.add_argument('--relay-on',type=Path,required=True); ap.add_argument('--on-only',action='store_true'); ap.add_argument('--boot'); a=ap.parse_args(); value=run_on_only(a.base_url,a.output,readj(a.relay_on),a.boot) if a.on_only else run(a.base_url,a.output,readj(a.relay_off) if a.relay_off else None,readj(a.relay_on)); print(json.dumps(value,ensure_ascii=False,indent=2))
