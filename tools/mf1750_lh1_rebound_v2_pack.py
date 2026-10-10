"""Isolated retained-white LH1 package; no device access or profile changes."""
from __future__ import annotations
import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import mf1750_lh1_lh4_middle_once_v2 as record

PREFIX = 'ec5_lightness_lh1_rebound_v2'
MACRO = 'MF1750_LIGHTNESS_LH1_REBOUND_V2_BUILD'
CPP_NAMESPACE = 'mf1750_lh1_rebound_v2'
NVS = {'namespace': 'lh1reb_v2', 'cursor': 'cur_lh1r', 'boot': 'boot_lh1r'}
CAMPAIGN = 'EC5_LIGHTNESS_HISTORY_LH1_REBOUND_V2_20260916'
SOURCE_STATE = 'R4_RETAINED_CLEAN_WHITE_HOST_CONFIRMED'
ANCHOR_SHA = '3bbf1bfffe29bf51eca3f1d876161c4fdd37ec792b9175b250549aa88ed72f84'
WHITE = ROOT / '.test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1'
DEFAULT = ROOT / '.test-output/offline/LH1_REBOUND_20260916_V2_R1'


def module():
    spec = importlib.util.spec_from_file_location('_lh1_rebound_v2_base', ROOT/'tools/mf1750_lightness_history_firmware.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base


def configured():
    base = module()
    close_binding = base.bind(WHITE/'close-review-v5.json')
    if close_binding['sha256'] != ANCHOR_SHA:
        raise ValueError('R4 close-review differs')
    close = record.read_record(WHITE/'close-review-v5.json')
    terminal = close['terminal_report']
    if close['protocol'] != 'PASS' or terminal['terminal_state'] != 'COMPLETE' or terminal['result'] is not True:
        raise ValueError('R4 white not complete')
    for name in NVS.values():
        if not 1 <= len(name.encode('ascii')) <= 15:
            raise ValueError('ESP32 NVS names must fit 15 bytes')
    flash = json.loads((WHITE/'app-flash-raw.json').read_text(encoding='utf-8'))
    base.SOURCE_WHITE = {
        'campaign_id': terminal['campaign_id'], 'action_id': terminal['action_id'],
        'contract_id': terminal['contract_id'], 'firmware_sha256': flash['binary']['observed_sha256'],
        'nvs_namespace': 'lh1srcw_v1', 'nvs_key': 'used_lh1sw1', 'complete_cursor': 2,
        'terminal_evidence': base.bind(WHITE/'live-reopen-v2/result.json'),
        'clean_white_review': base.bind(WHITE/'postwhite-optical-review-v4.json'),
        'close_review': close_binding, 'nvs_is_not_optical_or_electrical_proof': True,
    }
    base.CAMPAIGN = CAMPAIGN
    base.BUILD_TAG = 'MF1750_EC5_LIGHTNESS_HISTORY_LH1_REBOUND_V2_2026-09-16'
    base.PREFIX, base.MACRO, base.NAMESPACE = PREFIX, MACRO, CPP_NAMESPACE
    original_contract, original_config = base.contract, base.config_source
    original_frame, original_identity = base.frame_source, base.identity_source
    original_gate, original_render = base.source_gate_code, base.render

    def contract():
        c = original_contract()
        c.pop('contract_id')
        c['nvs'] = deepcopy(NVS)
        c['rebound_source_anchor'] = close_binding
        c['old_fault_preservation'] = {'namespace':'lhist_v1', 'cursor':'cur_lh1', 'boot':'boot_lh1',
            'expected_cursor_raw':770, 'expected_boot':'30a9e5989873f4e0', 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['implementation_sha256']['tools/mf1750_lh1_rebound_v2_pack.py'] = base.bind(Path(__file__))['sha256']
        c['protocol_compatibility'] = 'Existing lightness-history-v1 API/test algorithm; new campaign/build/actions/NVS'
        c['optical_source_authority'] = {'historical_anchor': close_binding, 'fresh_host_confirmation_required':True,
            'panel_optical_self_report':False, 'state':SOURCE_STATE}
        prior = None
        for a in c['actions']:
            a.pop('action_id'); a.pop('descriptor_id')
            a['prior_action_id'] = prior
            if a['ordinal'] == 1:
                a['source_state'] = SOURCE_STATE
            a['descriptor_id'] = base.algorithm.digest(base.algorithm.canonical({
                'campaign':CAMPAIGN, 'action':a, 'source_white':base.SOURCE_WHITE,
                'implementation':c['implementation_sha256']}))
            a['action_id'] = base.algorithm.digest(f"{CAMPAIGN}|{a['ordinal']}|{a['descriptor_id']}".encode())
            prior = a['action_id']
        c['contract_id'] = base.algorithm.digest(base.algorithm.canonical(c))
        return c

    def config(c):
        text = original_config(c)
        for old,new in (('lhist_v1',NVS['namespace']),('cur_lh1',NVS['cursor']),('boot_lh1',NVS['boot'])):
            text = text.replace('"'+old+'"','"'+new+'"')
        text = text.replace('\\"source_white_observed\\":false',
            '\\"source_white_observation_authority\\":\\"HOST_REVIEW_REQUIRED\\",\\"source_white_is_panel_self_report\\":false')
        text += '\n' + '\n'.join(f'static_assert(sizeof("{v}") <= 16, "NVS name too long");' for v in NVS.values()) + '\n'
        return text

    def gate():
        text = original_gate().replace('p2catwsv1','lh1srcw_v1').replace('used_p2cw1','used_lh1sw1')
        old_gate = '''bool oldFaultPreserved() {
  Preferences old;
  if (!old.begin("lhist_v1", true)) return false;
  const bool ok = old.isKey("cur_lh1") && old.getUShort("cur_lh1",0)==770 &&
      old.isKey("boot_lh1") && old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL;
  old.end(); return ok;
}
'''
        text = text.replace('bool whiteSourceReady() {', old_gate+'bool whiteSourceReady() {\n  if (!oldFaultPreserved()) return false;')
        text = text.replace('  if(action.ordinal==1 && prior!=source)',
            f'  if(source!="{ANCHOR_SHA}") return "source_review_anchor_mismatch";\n  if(action.ordinal==1 && prior!=source)')
        return text

    base.contract, base.config_source, base.source_gate_code = contract, config, gate
    base.identity_source = lambda c: original_identity(c).replace('mf1750_lightness_history_v1',CPP_NAMESPACE)
    base.frame_source = lambda: original_frame().replace('ec5_lightness_history_v1_identity.inc',PREFIX+'_identity.inc').replace('mf1750_lightness_history_v1',CPP_NAMESPACE)
    def render(c):
        sources = original_render(c)
        name = PREFIX+'_main.cpp'
        sources[name] = sources[name].replace('P2_WHITE_SUCCESSOR_COMPLETE_PLUS_FRESH_REVIEW_REQUIRED_NOT_YET_OBSERVED',
            'R4_WHITE_COMPLETE_PLUS_CURRENT_HOST_RETAINED_CLEAN_WHITE_REVIEW_REQUIRED')
        if 'FRESH_P2_FACTORY_WHITE' in sources[name]:
            raise ValueError('stale source-state compiled')
        return sources
    base.render = render
    return base


def prepare(out=DEFAULT):
    return configured().prepare(Path(out))

def build(out=DEFAULT):
    return module().build(Path(out))

def verify(out=DEFAULT):
    return module().verify_package(Path(out))

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','build','verify'))
    parser.add_argument('--package',type=Path,default=DEFAULT)
    args=parser.parse_args()
    result=globals()[args.command](args.package)
    print(json.dumps(result,ensure_ascii=False,indent=2))
