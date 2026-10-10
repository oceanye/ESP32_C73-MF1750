"""Offline validator/header planner for the LH1 rebound campaign.

The rebound campaign uses a new cursor namespace and boot key while preserving
lhist_v1/cur_lh1=770 and boot_lh1=30a9e5989873f4e0. No device or network I/O is
performed by import or validation.
"""
from __future__ import annotations
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import mf1750_lh1_lh4_middle_once_v2 as core
PACKAGE=ROOT/'.test-output/offline/LH1_REBOUND_20260914_R4'
HEX=core.HEX; NONCE=core.NONCE
EXPECTED_ANCHOR_SHA256='3bbf1bfffe29bf51eca3f1d876161c4fdd37ec792b9175b250549aa88ed72f84'

def _string(src,key):
 m=re.findall(r'static constexpr const char \*'+re.escape(key)+r'\s*=\s*"([^"]*)";',src)
 if len(m)!=1 or not m[0]: raise core.MiddleRunnerError('compiled constant missing/duplicate: '+key)
 return m[0]

def validate_rebound_anchor(contract):
 anchor=contract.get('rebound_source_anchor')
 if not isinstance(anchor,dict): raise core.MiddleRunnerError('rebound source anchor missing')
 if anchor.get('sha256') != EXPECTED_ANCHOR_SHA256:
  raise core.MiddleRunnerError('rebound source anchor digest differs')
 if Path(anchor.get('path','')).resolve() != (ROOT/'.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1/close-review-v5.json').resolve():
  raise core.MiddleRunnerError('rebound source anchor path differs')
 value=core.parse_json(core.read_bound(anchor)); core.verify_integrity(value)
 if value.get('kind')!='mf1750-lh1-fault-white-close-review-v3' or value.get('protocol')!='PASS': raise core.MiddleRunnerError('white close-review is not PASS')
 if value.get('authorization')!='white recovery authorized and consumed; next lightness action requires its own fresh chain': raise core.MiddleRunnerError('white authorization text differs')
 terminal=value.get('terminal_report',{})
 if terminal.get('result') is not True or terminal.get('terminal_state')!='COMPLETE' or terminal.get('next_ordinal')!=2: raise core.MiddleRunnerError('white terminal incomplete')
 if terminal.get('contract_id')!=contract['source_white']['contract_id']: raise core.MiddleRunnerError('white source contract differs')
 return value

def validate_package(package=PACKAGE):
 package=Path(package).resolve(); manifest=core.read_record(package/'manifest.json'); build=core.read_record(package/'build-report.json'); contract=core.read_record(package/'contract.json')
 if manifest.get('contract_id')!=contract.get('contract_id') or build.get('result') not in ('PASS','PASS_OFFLINE_COMPILED_AND_BOUND'): raise core.MiddleRunnerError('rebound package identity mismatch')
 for item in manifest.get('inputs',[])+manifest.get('outputs',[]): core.read_bound(item)
 core._require(contract,{'action_count':3,'autochain':False,'retry':False,'white_or_repeat_action':False},'rebound contract')
 core._require(contract.get('nvs',{}),{'namespace':'lhist_lh1_rebound_v1','cursor':'cur_lh1_rebound','boot':'boot_lh1_rebound'},'rebound NVS')
 core._require(contract.get('old_fault_preservation',{}),{'namespace':'lhist_v1','cursor':'cur_lh1','boot':'boot_lh1','expected_cursor_raw':770,'must_remain_untouched':True},'old fault preservation')
 core._require(contract.get('source_white',{}),{'nvs_namespace':'lh1srcw_v1','nvs_key':'used_lh1sw1','complete_cursor':2},'white source anchor')
 validate_rebound_anchor(contract)
 cfg=next(package.glob('generated/*_main_config.inc')).read_text(encoding='utf-8')
 names={'build_tag':'kBuildTag','test_id':'kTestId','campaign_id':'kCampaignId','contract_id':'kContractId','nvs_namespace':'kNvsNamespace','nvs_key':'kNvsKey','nvs_boot':'kNvsBootKey','arm_intent':'kArmIntent','execute_intent':'kExecuteIntent'}
 identity={k:_string(cfg,v) for k,v in names.items()}
 if identity['contract_id']!=contract['contract_id'] or identity['nvs_namespace']!=contract['nvs']['namespace'] or identity['nvs_key']!=contract['nvs']['cursor'] or identity['nvs_boot']!=contract['nvs']['boot']: raise core.MiddleRunnerError('compiled rebound identity differs')
 actions=contract['actions']
 for i,a in enumerate(actions,1):
  if a.get('ordinal')!=i or not HEX.fullmatch(a.get('action_id','')) or not HEX.fullmatch(a.get('descriptor_id','')): raise core.MiddleRunnerError('rebound action identity differs')
  frame=package/(a['stage'].lower()+'.frame4bpp')
  if not frame.is_file() or core.digest(frame.read_bytes())!=a['frame']['sha256']: raise core.MiddleRunnerError('rebound frame differs')
 return {'package':package,'manifest':manifest,'build':build,'contract':contract,'identity':identity,'actions':actions,'source_anchor':contract['rebound_source_anchor']}

def headers(ctx,ordinal,boot,run_id,source_review,prior_review,arm_nonce=None):
 if ordinal not in (1,2,3) or not NONCE.fullmatch(boot) or not HEX.fullmatch(source_review) or not HEX.fullmatch(prior_review): raise core.MiddleRunnerError('invalid rebound header binding')
 if ordinal == 1 and (source_review != EXPECTED_ANCHOR_SHA256 or prior_review != EXPECTED_ANCHOR_SHA256):
  raise core.MiddleRunnerError('ordinal 1 review must bind the sealed R4 white close review')
 a=ctx['actions'][ordinal-1]; h={'X-EC5-Build-Tag':ctx['identity']['build_tag'],'X-EC5-Test-Id':ctx['identity']['test_id'],'X-EC5-Campaign-Id':ctx['identity']['campaign_id'],'X-EC5-Action-Id':a['action_id'],'X-EC5-Ordinal':str(ordinal),'X-EC5-Descriptor-Id':a['descriptor_id'],'X-EC5-Boot-Nonce':boot,'X-EC5-Intent':ctx['identity']['execute_intent'] if arm_nonce else ctx['identity']['arm_intent'],'X-LH-Run-Id':run_id,'X-LH-Source-Review':source_review,'X-LH-Prior-Review':prior_review}
 if arm_nonce: h['X-EC5-Arm-Nonce']=arm_nonce
 return h

if __name__=='__main__':
 c=validate_package(); print(c['contract']['contract_id'])
