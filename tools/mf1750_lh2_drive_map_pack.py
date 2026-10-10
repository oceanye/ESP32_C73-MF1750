"""Isolated LH2 drive-map package; no device access or profile changes.

LH2 = 8 measured middle histories x 8 map codes per side. SOURCE (active C7
white) -> MIDDLE (commented M0..M7 rebuilds the histories) -> MAP (commented;
each history's four quadrant cells carry the four codes of its code half, so
every (history, code) pair appears exactly once per side). The MAP action must
select the commented profile for the Target role as well: the level-producing
mechanism lives in the commented tuples (see the design document).

The source-white anchor is the LH2 factory-OTP white successor terminal state
(lh2srcw_v1/used_lh2sw1==2). prepare() refuses to seal until the real white run
records exist and their digests are pinned below; tests inject synthetic sealed
records through configured().
"""
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
from host.static_photo import lightness_history_lh2 as lh2
from tools import mf1750_lh1_lh4_middle_once_v2 as record
from tools import mf1750_lh1_rebound_v2_review as v2review

PREFIX = 'ec5_lightness_lh2_drive_map_v1'
MACRO = 'MF1750_LIGHTNESS_LH2_DRIVE_MAP_V1_BUILD'
CPP_NAMESPACE = 'mf1750_lh2_drive_map_v1'
NVS = {'namespace': 'lh2map_v1', 'cursor': 'cur_lh2m', 'boot': 'boot_lh2m'}
CAMPAIGN = 'EC5_LIGHTNESS_HISTORY_LH2_DRIVE_MAP_V1_20260917'
SOURCE_STATE = 'LH2_WHITE_COMPLETE_PLUS_CURRENT_HOST_CLEAN_WHITE_REVIEW_REQUIRED'
DEFAULT = ROOT / '.test-output/offline/LH2_DRIVE_MAP_20260917_R1'
# Sealed after the LH2 white-successor field run of 2026-09-18 (batch
# LH2_SOURCE_WHITE_20260918_V1: 1 ARM / 1 EXECUTE / 1 driver / 1 refresh,
# terminal COMPLETE, uniform white field on camera).
WHITE = ROOT / '.test-output/hardware/LH2_SOURCE_WHITE_20260918_V1'
ANCHOR_SHA = '99078ff932313f89aa2af0b02fa38d25dee23e42fbcc7505dfc7c2edf0702a47'
WHITE_RECORD_NAMES = {
    'close_review': 'close-review-v1.json',
    'optical_review': 'postwhite-optical-review-v1.json',
    'app_flash': 'app-flash-raw-v2.json',
    'terminal': 'live-white-v1/result.json',
}


def module():
    spec = importlib.util.spec_from_file_location('_lh2_drive_map_base', ROOT/'tools/mf1750_lightness_history_firmware.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base


def configured(white_records: dict, anchor_sha: str):
    base = module()
    close_binding = base.bind(white_records['close_review'])
    if close_binding['sha256'] != anchor_sha:
        raise ValueError('LH2 white close-review differs')
    close = record.read_record(white_records['close_review'])
    terminal = close['terminal_report']
    if terminal['terminal_state'] != 'COMPLETE' or terminal['result'] is not True:
        raise ValueError('LH2 white not complete')
    flash = json.loads(Path(white_records['app_flash']).read_text(encoding='utf-8'))
    for name in NVS.values():
        if not 1 <= len(name.encode('ascii')) <= 15:
            raise ValueError('ESP32 NVS names must fit 15 bytes')
    base.algorithm = lh2
    base.SOURCE_WHITE = {
        'campaign_id': terminal['campaign_id'], 'action_id': terminal['action_id'],
        'contract_id': terminal['contract_id'], 'firmware_sha256': flash['binary']['observed_sha256'],
        'nvs_namespace': 'lh2srcw_v1', 'nvs_key': 'used_lh2sw1', 'complete_cursor': 2,
        'terminal_evidence': base.bind(white_records['terminal']),
        'clean_white_review': base.bind(white_records['optical_review']),
        'close_review': close_binding, 'nvs_is_not_optical_or_electrical_proof': True,
    }
    base.CAMPAIGN = CAMPAIGN
    base.BUILD_TAG = 'MF1750_EC5_LIGHTNESS_HISTORY_LH2_DRIVE_MAP_V1_2026-09-17'
    base.PREFIX, base.MACRO, base.NAMESPACE = PREFIX, MACRO, CPP_NAMESPACE
    original_contract, original_config = base.contract, base.config_source
    original_frame, original_identity = base.frame_source, base.identity_source
    original_gate, original_render = base.source_gate_code, base.render

    def contract():
        c = original_contract()
        c.pop('contract_id')
        c['nvs'] = deepcopy(NVS)
        c['lh2_white_source_anchor'] = close_binding
        c['old_fault_preservation'] = {'namespace':'lhist_v1', 'cursor':'cur_lh1', 'boot':'boot_lh1',
            'expected_cursor_raw':770, 'expected_boot':'30a9e5989873f4e0', 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['rebound_v2_terminal_preservation'] = {'namespace':'lh1reb_v2', 'cursor':'cur_lh1r', 'boot':'boot_lh1r',
            'expected_cursor_raw':4, 'expected_boot':'7274e005c8833ca1', 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch',
            'v2_contract': v2review.CONTRACT}
        c['implementation_sha256']['tools/mf1750_lh2_drive_map_pack.py'] = base.bind(Path(__file__))['sha256']
        c['implementation_sha256']['host/static_photo/lightness_history_lh2.py'] = base.bind(ROOT/'host/static_photo/lightness_history_lh2.py')['sha256']
        c['protocol_compatibility'] = 'Existing lightness-history-v1 API/test algorithm; new campaign/build/actions/NVS; MAP stage replaces TARGET'
        c['optical_source_authority'] = {'historical_anchor': close_binding, 'fresh_host_confirmation_required':True,
            'panel_optical_self_report':False, 'state':SOURCE_STATE}
        c['level_counts'] = None
        c['level_count_is_refresh_count'] = False
        c['drive_map'] = {'map_codes': list(range(8)), 'histories_per_map_code_per_side': 8,
            'cells_per_side': 64, 'frame_rule': 'code=4*code_half+quadrant(TL0,TR1,BL2,BR3)',
            'commented_profile_for_middle_and_map': True,
            'note': 'MAP enumerates 8 commented codes x 8 measured histories per side; recipes are candidates, not encoded lightness ranks.'}
        prior = None
        for a in c['actions']:
            a.pop('action_id'); a.pop('descriptor_id')
            a['prior_action_id'] = prior
            for key in ('role', 'branch', 'target_state'):
                a[key] = a[key].replace('LH1_', 'LH2_')
            if a['ordinal'] == 1:
                a['source_state'] = SOURCE_STATE
            else:
                a['source_state'] = a['source_state'].replace('LH1_', 'LH2_')
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
        text = text.replace('\\"target_codes\\":[3,7]', '\\"target_codes\\":[0,1,2,3,4,5,6,7]')
        text = text.replace('\\"symmetric_tuple_sequence\\":[\\"AA\\",\\"CC\\",\\"AA\\"]',
            '\\"symmetric_tuple_sequence\\":[\\"AA\\",\\"CC\\",\\"CC\\"]')
        text = text.replace('\\"level_counts\\":[3,5,10]', '\\"level_counts\\":null')
        text = text.replace('"LH1_HISTORY_POSITION_BALANCED_8X8"', '"LH2_DRIVE_MAP_8X8"')
        text = text.replace('"MF1750 Lightness History V1"', '"MF1750 Lightness LH2 Drive Map"')
        text = text.replace('static constexpr const char *kIdentityRevision="lightness-history-v1";',
            'static constexpr const char *kIdentityRevision="lightness-lh2-drive-map-v1";')
        text = text.replace('"LH1_SOURCE"', '"LH2_SOURCE"')
        text = text.replace('MF1750_LH1_COMPILED|CONTRACT=', 'MF1750_LH2_COMPILED|CONTRACT=')
        text += '\n' + '\n'.join(f'static_assert(sizeof("{v}") <= 16, "NVS name too long");' for v in NVS.values()) + '\n'
        return text

    def gate():
        text = original_gate().replace('p2catwsv1','lh2srcw_v1').replace('used_p2cw1','used_lh2sw1')
        preserved = '''bool oldFaultPreserved() {
  Preferences old;
  if (!old.begin("lhist_v1", true)) return false;
  const bool ok = old.isKey("cur_lh1") && old.getUShort("cur_lh1",0)==770 &&
      old.isKey("boot_lh1") && old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL;
  old.end(); return ok;
}
bool reboundV2TerminalPreserved() {
  Preferences source;
  if (!source.begin("lh1reb_v2", true)) return false;
  const bool ok = source.isKey("cur_lh1r") && source.getUShort("cur_lh1r",0)==4 &&
      source.isKey("boot_lh1r") && source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL;
  source.end(); return ok;
}
'''
        text = text.replace('bool whiteSourceReady() {', preserved+'bool whiteSourceReady() {\n  if (!oldFaultPreserved() || !reboundV2TerminalPreserved()) return false;')
        text = text.replace('  if(action.ordinal==1 && prior!=source)',
            f'  if(source!="{anchor_sha}") return "source_review_anchor_mismatch";\n  if(action.ordinal==1 && prior!=source)')
        return text

    def identity(c):
        return original_identity(c).replace('mf1750_lightness_history_v1',CPP_NAMESPACE).replace(
            'kTargetCodes[2]={3,7}', 'kTargetCodes[8]={0,1,2,3,4,5,6,7}')

    def frame():
        text = original_frame().replace('ec5_lightness_history_v1_identity.inc',PREFIX+'_identity.inc').replace('mf1750_lightness_history_v1',CPP_NAMESPACE)
        old_rule = '    const uint8_t code=role==1 ? 7 : role==2 ? recipe%8 : kTargetCodes[recipe/8];'
        new_rule = '    const uint8_t code=role==1 ? 7 : role==2 ? recipe%8 : (uint8_t)(4*(recipe/8)+((i/8)>=4?2:0)+((i%8)>=4?1:0));'
        if text.count(old_rule) != 1:
            raise ValueError('frame rule anchor changed')
        return text.replace(old_rule, new_rule)

    base.contract, base.config_source, base.source_gate_code = contract, config, gate
    base.identity_source, base.frame_source = identity, frame
    def render(c):
        sources = original_render(c)
        name = PREFIX+'_main.cpp'
        main = sources[name]
        for old, new in (('P2_WHITE_SUCCESSOR_COMPLETE_PLUS_FRESH_REVIEW_REQUIRED_NOT_YET_OBSERVED', SOURCE_STATE),
                         ('LH1 forbids in-campaign white recovery', 'LH2 drive-map forbids in-campaign white recovery')):
            if main.count(old) != 1:
                raise ValueError('main label anchor changed: ' + old[:60])
            main = main.replace(old, new)
        if 'single-pixel lightness history V1' not in main:
            raise ValueError('main label anchor changed: lightness history label')
        main = main.replace('single-pixel lightness history V1', 'LH2 drive-map history V1')
        if 'FRESH_P2_FACTORY_WHITE' in main:
            raise ValueError('stale source-state compiled')
        lines = main.split('\n')
        hits = [i for i, line in enumerate(lines) if 'if(action.ordinal==3) return String(' in line]
        if len(hits) != 1 or lines[hits[0]].count('\\"controller_tuple_dispatch\\":\\"AA\\"') != 1:
            raise ValueError('transport dispatch anchor changed')
        lines[hits[0]] = lines[hits[0]].replace('\\"controller_tuple_dispatch\\":\\"AA\\"', '\\"controller_tuple_dispatch\\":\\"CC\\"')
        sources[name] = '\n'.join(lines)
        driver = sources[PREFIX+'_driver.inc']
        old_branch = '#if defined('+MACRO+')\n  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;'
        new_branch = '#if defined('+MACRO+')\n  if (role == EpdChromaGridRole::Mid || role == EpdChromaGridRole::Target) useCommentedGlobal = true;'
        if driver.count(old_branch) != 1:
            raise ValueError('commented-profile branch anchor changed')
        sources[PREFIX+'_driver.inc'] = driver.replace(old_branch, new_branch).replace(
            '// Isolated LH1 full-frame history driver, symmetric complete tuples.',
            '// Isolated LH2 full-frame drive-map driver, symmetric complete tuples; MAP also uses commented tuples.')
        driver = sources[PREFIX+'_driver.inc']
        # phLayoutValid pins the LH1 target-code pair; LH2 enumerates all eight
        # codes, so the layout gate must pin the new array's endpoints instead.
        old_layout = ('      ph::kSeparatorCode != 7 || ph::kSourceCode != 7 ||\n'
                      '          ph::kTargetCodes[0] != 3 || ph::kTargetCodes[1] != 7 ||')
        new_layout = ('      ph::kSeparatorCode != 7 || ph::kSourceCode != 7 ||\n'
                      '          ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7 ||')
        if driver.count(old_layout) != 1:
            raise ValueError('phLayoutValid target-code anchor changed')
        sources[PREFIX+'_driver.inc'] = driver.replace(old_layout, new_layout)
        return sources
    base.render = render
    return base


def prepare(out=DEFAULT):
    if ANCHOR_SHA is None or not WHITE.is_dir():
        raise ValueError('LH2 white successor terminal evidence not sealed; prepare stays closed')
    records = {k: WHITE / n for k, n in WHITE_RECORD_NAMES.items()}
    return configured(records, ANCHOR_SHA).prepare(Path(out))

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
