"""Isolated LH3 dose-axis package V2; no device access or profile changes.

LH3 dose = 8 code columns x 8 row repeats per side. SOURCE (active C7 white)
-> DOSE1 (commented; column c carries code c in all 8 rows) -> DOSE2
(commented; frame byte-identical to DOSE1, so the only independent variable is
one extra same-code application). Both dose actions must select the commented
profile for the Target role as well: the level-producing mechanism lives in
the commented tuples (same finding as the LH2 drive-map chain).

V2 rebuild (2026-09-24): the V1 campaign (namespace lh3dose_v1) was bricked
before its first ARM by an esptool read_mac RTS hard reset — the campaign boot
binding is written at first boot, so the reboot latched
campaign_boot_binding_mismatch_at_boot with cursor_raw=769 (phase FAULT |
ordinal 1), zero ARM/EXECUTE/driver/refresh. Erasing NVS is forbidden (it
would destroy the lh2map_v1/lhist_v1/lh1reb_v2/lh3srcw_v1 preservation
evidence), so V2 moves the campaign to a fresh namespace lh3dose_v2 and its
device gate additionally pins the V1 namespace at exactly the bricked cursor
769 as untouchable historical evidence. Layout, frames and action definitions
are unchanged; the white anchor is unchanged.

The source-white anchor is the LH3 factory-OTP white successor terminal state
(lh3srcw_v1/used_lh3sw1==2), which itself requires the LH2 drive-map campaign
terminal (lh2map_v1 cur_lh2m=4, boot ac92bb9e25c374ef) plus the preserved
lhist_v1/lh1reb_v2/lh2srcw_v1 namespaces. prepare() refuses to seal until the
real LH3 white run records exist and their digests are pinned below; tests and
the synthetic build inject synthetic sealed records through configured().
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
from host.static_photo import lightness_history_lh3_dose as lh3dose
from tools import mf1750_lh1_lh4_middle_once_v2 as record
from tools import mf1750_lh1_rebound_v2_review as v2review

PREFIX = 'ec5_lightness_lh3_dose_v2'
MACRO = 'MF1750_LIGHTNESS_LH3_DOSE_V2_BUILD'
CPP_NAMESPACE = 'mf1750_lh3_dose_v2'
NVS = {'namespace': 'lh3dose_v2', 'cursor': 'cur_lh3d2', 'boot': 'boot_lh3d2'}
CAMPAIGN = 'EC5_LIGHTNESS_HISTORY_LH3_DOSE_V2_20260924'
SOURCE_STATE = 'LH3_WHITE_COMPLETE_PLUS_CURRENT_HOST_CLEAN_WHITE_REVIEW_REQUIRED'
DEFAULT = ROOT / '.test-output/offline/LH3_DOSE_20260924_R2'
# Sealed after the LH3 source-white field run of 2026-09-22 (batch
# LH3_SOURCE_WHITE_20260922_V1: 1 ARM / 1 EXECUTE / 1 driver / 1 refresh,
# terminal COMPLETE, uniform white field on camera, MAP matrix fully erased,
# claim lh3srcw_v1/used_lh3sw1 permanently consumed). Unchanged for V2.
# ANCHOR_SHA is the close-review FILE sha256 (the value base.bind pins and the
# firmware/host review chain carries), exactly as the LH2 real seal did. The
# close-review record's own integrity canonical sha256 is
# 17dc2fed63eef7943510e0678f184b8d267fbcfc22450a69f6490d9e058d025e (verified).
WHITE = ROOT / '.test-output/hardware/LH3_SOURCE_WHITE_20260922_V1'
ANCHOR_SHA = '5dd81034bd9a963d89b91fc4ce9e7a01d8eaf4f99fc883e8ce0a3bc8f77dc9b0'
WHITE_RECORD_NAMES = {
    'close_review': 'close-review-v1.json',
    'optical_review': 'postwhite-optical-review-v1.json',
    'app_flash': 'app-flash-raw-v2.json',
    'terminal': 'live-white-v1/result.json',
}
# Real 2026-09-22 field-batch layout (differs from the synthetic recipe).
REAL_RECORD_NAMES = {
    'close_review': 'close-review-v1.json',
    'optical_review': 'postwhite-optical-review-v1.json',
    'app_flash': 'app-flash-raw.json',
    'terminal': 'live-white-v2/result.json',
}
LH2_MAP_TERMINAL = {'namespace': 'lh2map_v1', 'cursor': 'cur_lh2m', 'boot': 'boot_lh2m',
    'expected_cursor_raw': 4, 'expected_boot': 'ac92bb9e25c374ef'}
# V1 campaign bricked before its first ARM (2026-09-24 incident, see module
# docstring): cursor_raw=(kPhaseFault<<8)|1=769, zero driver calls. V2 treats
# the bricked namespace as untouchable historical evidence and pins the exact
# cursor value; the V1 boot key value is not pinned (not needed for the gate).
V1_BRICKED = {'namespace': 'lh3dose_v1', 'cursor': 'cur_lh3d', 'boot': 'boot_lh3d',
    'expected_cursor_raw': 769, 'expected_phase': 'FAULT', 'expected_ordinal': 1,
    'driver_call_count_at_brick': 0, 'recoverable': False,
    'must_remain_untouched': True,
    'incident': 'esptool read_mac RTS hard reset after campaign boot binding '
                'was written; campaign_boot_binding_mismatch_at_boot latched '
                'before any ARM/EXECUTE/driver/refresh'}


def module():
    spec = importlib.util.spec_from_file_location('_lh3_dose_base', ROOT/'tools/mf1750_lightness_history_firmware.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base


def configured(white_records: dict, anchor_sha: str):
    base = module()
    close_binding = base.bind(white_records['close_review'])
    if close_binding['sha256'] != anchor_sha:
        raise ValueError('LH3 white close-review differs')
    close = record.read_record(white_records['close_review'])
    # Synthetic records embed the terminal report in the close-review; the real
    # 2026-09-22 batch carries it in the live-white result record instead.
    if 'terminal_report' in close:
        terminal = close['terminal_report']
    else:
        terminal = record.read_record(white_records['terminal'])['terminal_report']
    if terminal['terminal_state'] != 'COMPLETE' or terminal['result'] is not True:
        raise ValueError('LH3 white not complete')
    flash = json.loads(Path(white_records['app_flash']).read_text(encoding='utf-8'))
    for name in NVS.values():
        if not 1 <= len(name.encode('ascii')) <= 15:
            raise ValueError('ESP32 NVS names must fit 15 bytes')
    base.algorithm = lh3dose
    base.SOURCE_WHITE = {
        'campaign_id': terminal['campaign_id'], 'action_id': terminal['action_id'],
        'contract_id': terminal['contract_id'], 'firmware_sha256': flash['binary']['observed_sha256'],
        'nvs_namespace': 'lh3srcw_v1', 'nvs_key': 'used_lh3sw1', 'complete_cursor': 2,
        'terminal_evidence': base.bind(white_records['terminal']),
        'clean_white_review': base.bind(white_records['optical_review']),
        'close_review': close_binding, 'nvs_is_not_optical_or_electrical_proof': True,
    }
    base.CAMPAIGN = CAMPAIGN
    base.BUILD_TAG = 'MF1750_EC5_LIGHTNESS_HISTORY_LH3_DOSE_V2_2026-09-24'
    base.PREFIX, base.MACRO, base.NAMESPACE = PREFIX, MACRO, CPP_NAMESPACE
    original_contract, original_config = base.contract, base.config_source
    original_frame, original_identity = base.frame_source, base.identity_source
    original_gate, original_render = base.source_gate_code, base.render

    def contract():
        c = original_contract()
        c.pop('contract_id')
        c['nvs'] = deepcopy(NVS)
        c['lh3_white_source_anchor'] = close_binding
        c['old_fault_preservation'] = {'namespace':'lhist_v1', 'cursor':'cur_lh1', 'boot':'boot_lh1',
            'expected_cursor_raw':770, 'expected_boot':'30a9e5989873f4e0', 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['rebound_v2_terminal_preservation'] = {'namespace':'lh1reb_v2', 'cursor':'cur_lh1r', 'boot':'boot_lh1r',
            'expected_cursor_raw':4, 'expected_boot':'7274e005c8833ca1', 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch',
            'v2_contract': v2review.CONTRACT}
        c['lh2_map_terminal_preservation'] = {**deepcopy(LH2_MAP_TERMINAL),
            'must_remain_untouched':True, 'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['lh2_white_preservation'] = {'namespace':'lh2srcw_v1', 'key':'used_lh2sw1',
            'expected_cursor_raw':2, 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['lh3_dose_v1_bricked_preservation'] = {**deepcopy(V1_BRICKED),
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['implementation_sha256']['tools/mf1750_lh3_dose_pack.py'] = base.bind(Path(__file__))['sha256']
        c['implementation_sha256']['host/static_photo/lightness_history_lh3_dose.py'] = base.bind(ROOT/'host/static_photo/lightness_history_lh3_dose.py')['sha256']
        c['protocol_compatibility'] = 'Existing lightness-history-v1 API/test algorithm; V2 campaign/build/NVS namespace after the 2026-09-24 V1 brick incident; DOSE1/DOSE2 stages replace MIDDLE/TARGET and share one byte-identical frame'
        c['optical_source_authority'] = {'historical_anchor': close_binding, 'fresh_host_confirmation_required':True,
            'panel_optical_self_report':False, 'state':SOURCE_STATE}
        c['level_counts'] = None
        c['level_count_is_refresh_count'] = False
        c.pop('recipes_per_target', None)
        c['dose_axis'] = {'dose_codes': list(range(8)), 'columns_per_side': 8, 'rows_per_code_per_side': 8,
            'cells_per_side': 64, 'frame_rule': 'code=column index 0..7; rows are spatial repeats',
            'dose2_frame_byte_identical_to_dose1': True,
            'commented_profile_for_dose1_and_dose2': True,
            'note': 'DOSE1/DOSE2 carry identical frames; the only independent variable is one extra same-code application. Code 7 column is the commented white reference.'}
        prior = None
        for a in c['actions']:
            a.pop('action_id'); a.pop('descriptor_id')
            a['prior_action_id'] = prior
            for key in ('role', 'branch', 'target_state'):
                a[key] = a[key].replace('LH1_', 'LH3_')
            if a['ordinal'] == 1:
                a['source_state'] = SOURCE_STATE
            else:
                a['source_state'] = a['source_state'].replace('LH1_', 'LH3_')
            a['descriptor_id'] = base.algorithm.digest(base.algorithm.canonical({
                'campaign':CAMPAIGN, 'action':a, 'source_white':base.SOURCE_WHITE,
                'implementation':c['implementation_sha256']}))
            a['action_id'] = base.algorithm.digest(f"{CAMPAIGN}|{a['ordinal']}|{a['descriptor_id']}".encode())
            prior = a['action_id']
        if c['actions'][1]['frame']['sha256'] != c['actions'][2]['frame']['sha256']:
            raise ValueError('DOSE2 frame must be byte-identical to DOSE1')
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
        text = text.replace('"LH1_HISTORY_POSITION_BALANCED_8X8"', '"LH3_DOSE_COLUMNS_8X8"')
        text = text.replace('"MF1750 Lightness History V1"', '"MF1750 Lightness LH3 Dose V2"')
        text = text.replace('static constexpr const char *kIdentityRevision="lightness-history-v1";',
            'static constexpr const char *kIdentityRevision="lightness-lh3-dose-v2";')
        text = text.replace('"LH1_SOURCE"', '"LH3_SOURCE"')
        text = text.replace('MF1750_LH1_COMPILED|CONTRACT=', 'MF1750_LH3_DOSE_V2_COMPILED|CONTRACT=')
        text += '\n' + '\n'.join(f'static_assert(sizeof("{v}") <= 16, "NVS name too long");' for v in NVS.values()) + '\n'
        return text

    def gate():
        text = original_gate().replace('p2catwsv1','lh3srcw_v1').replace('used_p2cw1','used_lh3sw1')
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
bool lh2DriveMapTerminalComplete() {
  Preferences source;
  if (!source.begin("lh2map_v1", true)) return false;
  const bool ok = source.isKey("cur_lh2m") && source.getUShort("cur_lh2m",0)==4 &&
      source.isKey("boot_lh2m") && source.getULong64("boot_lh2m",0)==0xac92bb9e25c374efULL;
  source.end(); return ok;
}
bool lh2WhitePreserved() {
  Preferences white;
  if (!white.begin("lh2srcw_v1", true)) return false;
  const bool ok = white.isKey("used_lh2sw1") && white.getUShort("used_lh2sw1",0)==2;
  white.end(); return ok;
}
bool lh3DoseV1BrickedPreserved() {
  Preferences old;
  if (!old.begin("lh3dose_v1", true)) return false;
  const bool ok = old.isKey("cur_lh3d") && old.getUShort("cur_lh3d",0)==769;
  old.end(); return ok;
}
'''
        text = text.replace('bool whiteSourceReady() {', preserved+'bool whiteSourceReady() {\n  if (!oldFaultPreserved() || !reboundV2TerminalPreserved() || !lh2DriveMapTerminalComplete() || !lh2WhitePreserved() || !lh3DoseV1BrickedPreserved()) return false;')
        text = text.replace('  if(action.ordinal==1 && prior!=source)',
            f'  if(source!="{anchor_sha}") return "source_review_anchor_mismatch";\n  if(action.ordinal==1 && prior!=source)')
        return text

    def identity(c):
        return original_identity(c).replace('mf1750_lightness_history_v1',CPP_NAMESPACE).replace(
            'kTargetCodes[2]={3,7}', 'kTargetCodes[8]={0,1,2,3,4,5,6,7}')

    def frame():
        text = original_frame().replace('ec5_lightness_history_v1_identity.inc',PREFIX+'_identity.inc').replace('mf1750_lightness_history_v1',CPP_NAMESPACE)
        old_rule = '    const uint8_t code=role==1 ? 7 : role==2 ? recipe%8 : kTargetCodes[recipe/8];'
        new_rule = '    const uint8_t code=role==1 ? 7 : (uint8_t)(i%8);'
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
                         ('LH1 forbids in-campaign white recovery', 'LH3 dose forbids in-campaign white recovery')):
            if main.count(old) != 1:
                raise ValueError('main label anchor changed: ' + old[:60])
            main = main.replace(old, new)
        if 'single-pixel lightness history V1' not in main:
            raise ValueError('main label anchor changed: lightness history label')
        main = main.replace('single-pixel lightness history V1', 'LH3 dose history V2')
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
            '// Isolated LH3 full-frame dose-axis driver, symmetric complete tuples; DOSE1/DOSE2 both use commented tuples with byte-identical frames.')
        driver = sources[PREFIX+'_driver.inc']
        # phLayoutValid pins the LH1 target-code pair; LH3 dose enumerates all
        # eight codes as columns, so the layout gate must pin the new array's
        # endpoints instead (same defect class as LH2-DM-D1).
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


def real_records():
    return {k: WHITE / n for k, n in REAL_RECORD_NAMES.items()}


def prepare(out=DEFAULT):
    if ANCHOR_SHA is None or not WHITE.is_dir():
        raise ValueError('LH3 white successor terminal evidence not sealed; prepare stays closed')
    return configured(real_records(), ANCHOR_SHA).prepare(Path(out))

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
