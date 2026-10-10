"""Offline tests for corrected MIDDLE v2 identity/review binding."""
from pathlib import Path
import pytest
from tools import mf1750_lh1_lh4_middle_once_v2 as m
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'.test-output/offline/LH1_LH4_20260912_R1'

def seal_write(p,v): p.write_bytes(m.canonical(m.seal(v))); return p

def source(tmp,ctx):
    boot='0123456789abcdef'; sr='a'*64
    return seal_write(tmp/'source.json', {'kind':'mf1750-lh1-lh4-middle-source-binding-v1','contract_id':ctx['contract_id'],'boot_nonce':boot,'source_review_sha256':sr,'terminal_report':{'terminal_state':'COMPLETE','result':True,'next_ordinal':2,'boot_nonce':boot,'source_review_sha256':sr,'contract_id':ctx['contract_id'],'build_tag':ctx['contract']['build_tag'],'test_id':ctx['contract']['algorithm_id'],'campaign_id':ctx['contract']['campaign_id']},'terminal_status':{'cursor_raw':2,'next_ordinal':2,'boot_nonce':boot,'source_review_sha256':sr,'contract_id':ctx['contract_id'],'build_tag':ctx['contract']['build_tag'],'test_id':ctx['contract']['algorithm_id'],'campaign_id':ctx['contract']['campaign_id']},'source_replayed':False,'claim_created':False})

def stage(tmp,ctx,s):
    payload={'stage':'MIDDLE','ordinal':2,'method':'offline-structured-review','source_terminal_sha256':'a'*64}
    return seal_write(tmp/'stage.json', {'kind':'mf1750-lh1-middle-new-stage-review-v1','ordinal':2,'contract_id':ctx['contract_id'],'source_review_sha256':s['source_review_sha256'],'prior_review_is_distinct_from_source':True,'source_review_is_white_reuse':False,'prior_review_sha256':m.digest(m.canonical(payload)),'boot_nonce':s['boot_nonce'],'review_payload':payload})

class T:
    def __init__(self,ctx): self.ctx=ctx; self.n=0; self.calls=[]
    def __call__(self,method,url,headers,timeout):
        r=url.rsplit('/',1)[-1]; self.calls.append((method,r,headers))
        c=self.ctx; b='0123456789abcdef'
        if r=='arm': return 201,m.canonical({'accepted':True,'armed':True,'phase':1,'arm_nonce':'fedcba9876543210','boot_nonce':b,'ordinal':2,'build_tag':self.ctx['contract']['build_tag'],'test_id':self.ctx['contract']['algorithm_id'],'campaign_id':self.ctx['contract']['campaign_id'],'contract_id':self.ctx['contract_id']})
        if r=='execute': return 202,m.canonical({'accepted':True,'execute_consumed':True,'phase':2,'job_id':2,'boot_nonce':b,'ordinal':2,'build_tag':self.ctx['contract']['build_tag'],'test_id':self.ctx['contract']['algorithm_id'],'campaign_id':self.ctx['contract']['campaign_id'],'contract_id':self.ctx['contract_id']})
        if r=='status':
            self.n+=1; x=3 if self.n>2 else 2
            return 200,m.canonical({'cursor_raw':x,'next_ordinal':x,'phase':0 if self.n==1 or x==3 else 2,'state':'ready' if self.n==1 else 'running','cursor_valid':True,'arm_request_count':2,'execute_request_count':2,'total_driver_call_count':2,'boot_nonce':b,'build_tag':self.ctx['contract']['build_tag'],'test_id':self.ctx['contract']['algorithm_id'],'campaign_id':self.ctx['contract']['campaign_id'],'contract_id':self.ctx['contract_id']})
        if r=='report': return 200,m.canonical({'ordinal':2,'action_id':c['middle']['action_id'],'terminal_state':'COMPLETE','result':True,'driver_call_count_for_action':1,'total_driver_call_count':2,'no_retry':True,'boot_nonce':b,'build_tag':self.ctx['contract']['build_tag'],'test_id':self.ctx['contract']['algorithm_id'],'campaign_id':self.ctx['contract']['campaign_id'],'contract_id':self.ctx['contract_id'],'driver':{'valid':True,'running':False,'input_fnv1a':c['middle']['frame']['fnv1a'],'cs1_dtm_fnv1a':c['middle']['cs1_dtm']['fnv1a'],'cs2_dtm_fnv1a':c['middle']['cs2_dtm']['fnv1a'],'sequence_ok':True,'mapping_applied':True,'pon_busy_seen':True,'drf_busy_seen':True,'pof_busy_seen':True,'safe_finish':{'busy_before_pins_low':1,'busy_after_pins_low':1,'busy_after_5ms':1}}})
        return 200,m.canonical({'boot_nonce':b,'build_tag':self.ctx['contract']['build_tag'],'test_id':self.ctx['contract']['algorithm_id'],'campaign_id':self.ctx['contract']['campaign_id'],'contract_id':self.ctx['contract_id']})

def test_source_raw_review_rejected_without_digest(tmp_path):
    c=m.validate_package(PACKAGE); p=source(tmp_path,c); v=m.read_record(p); v.pop('source_review_sha256'); v['terminal_report'].pop('source_review_sha256'); v['terminal_status'].pop('source_review_sha256'); seal_write(p,{k:x for k,x in v.items() if k!='integrity'})
    with pytest.raises(m.MiddleRunnerError,match='device SOURCE review digest missing'): m.validate_source_reconciliation(p,c)

def test_photo_hash_cannot_be_stage_authority(tmp_path):
    c=m.validate_package(PACKAGE); s=m.read_record(source(tmp_path,c)); p=stage(tmp_path,c,s); v=m.read_record(p); v['review_payload']={'photo':'x'}; v['prior_review_sha256']=m.digest(m.canonical(v['review_payload'])); seal_write(p,{k:x for k,x in v.items() if k!='integrity'})
    with pytest.raises(m.MiddleRunnerError,match='photo hash'): m.validate_stage_review(p,s,c)

def test_v2_headers_and_single_action(tmp_path):
    c=m.validate_package(PACKAGE); sp=source(tmp_path,c); s=m.read_record(sp); st=stage(tmp_path,c,s); t=T(c)
    r=m.run_middle(PACKAGE,sp,tmp_path/'run',transport=t,sleeper=lambda _:None,initial_wait=60,stage_review=st)
    assert r['outcome']=='complete_pass'; posts=[x for x in t.calls if x[0]=='POST']; assert len(posts)==2
    assert posts[0][2]['X-EC5-Build-Tag']==c['contract']['build_tag']; assert posts[0][2]['X-LH-Source-Review']=='a'*64; assert posts[0][2]['X-LH-Prior-Review']!=posts[0][2]['X-LH-Source-Review']

def test_stage_required(tmp_path):
    c=m.validate_package(PACKAGE); sp=source(tmp_path,c)
    with pytest.raises(m.MiddleRunnerError,match='stage review is required'): m.run_middle(PACKAGE,sp,tmp_path/'run',transport=T(c),sleeper=lambda _:None,initial_wait=60)

def test_initial_wait_rejected_before_transport(tmp_path):
    c=m.validate_package(PACKAGE); sp=source(tmp_path,c); s=m.read_record(sp); st=stage(tmp_path,c,s); t=T(c)
    with pytest.raises(m.MiddleRunnerError,match='at least 60'): m.run_middle(PACKAGE,sp,tmp_path/'run',transport=t,sleeper=lambda _:None,initial_wait=59,stage_review=st)
    assert t.calls == []

def test_fault_locked_preflight_stops_before_arm(tmp_path):
    c=m.validate_package(PACKAGE); sp=source(tmp_path,c); s=m.read_record(sp); st=stage(tmp_path,c,s)
    class Fault(T):
        def __call__(self,method,url,headers,timeout):
            out=super().__call__(method,url,headers,timeout)
            if url.endswith('/status'):
                import json
                v=json.loads(out[1]); v['state']='fault_locked'; v['phase']=3; return out[0],m.canonical(v)
            return out
    t=Fault(c)
    with pytest.raises(m.MiddleRunnerError,match='not READY'): m.run_middle(PACKAGE,sp,tmp_path/'run',transport=t,sleeper=lambda _:None,initial_wait=60,stage_review=st)
    assert not any(x[0]=='POST' for x in t.calls)
