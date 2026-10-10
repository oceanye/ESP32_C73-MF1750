"""Isolated PAL1 measured-palette calibration package V3; no device access.

PAL1 = single action, active global header (the production render path, same
electrical path as the LH3 SOURCE action), 8 code columns x 8 row repeats per
side. One ARM / one EXECUTE / one driver call / one visible refresh; the
campaign completes at next_ordinal=2. The action's driver role is Source
(active profile; the commented-tuple Mid branch stays untouched) and the frame
rule is code=column for role 1.

V2 (2026-09-24) fixed defect PAL1-R1-D1 (fixture role loop indexed
kActions[2] out of bounds): kRoles={Source}, phRoleValid Source-only. V3
(2026-09-24 evening) fixes defect PAL1-R2-D2: the V2 gate demanded
pal1_v1/cur_pal1 == 1 with isKey, but the boot path writes ONLY the campaign
boot key — the cursor key is first written at the ARM transition — so the
gate never held on the real device (source_nvs_complete=false, preflight
refused; the read-only NVS dump's RTS reset then killed the fresh pal1_v2
boot binding before any ARM). V3 moves to namespace pal1_v3 and the dead
namespaces are pinned to the NVS-dump ground truth (NVS_DUMP_PARSE_20260924_V1):
pal1_v1 and pal1_v2 each have their boot key present and their cursor key
absent-or-1. The V2 audit additionally cross-checks every gate constant
against the sealed NVS dump parse report.

Device gate: the LH3 dose V2 campaign must be at its terminal
(lh3dose_v2 cur_lh3d2=4, boot 4d53de6fe4b39d3b, campaign complete), the bricked
V1 dose namespace must still read cursor 769, the dead PAL1 V1/V2 namespaces
must read boot-key-present + cursor absent-or-1, the LH3 white allowance stays
consumed (lh3srcw_v1 used_lh3sw1==2), the LH2 drive-map terminal stays
(lh2map_v1 cur_lh2m=4/boot ac92bb9e25c374ef), and lhist_v1/lh1reb_v2 stay
preserved. The white anchor is the unchanged 2026-09-22 LH3 white close-review
file sha256.

Operational warning (2026-09-24 incidents): after flashing, the first boot
writes the campaign boot binding — no MCU reset of any kind is allowed until
the action completes; a read-only esptool read_mac/NVS dump also resets.
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
from host.static_photo import palette_cal_pal1 as pal1
from tools import mf1750_lh1_lh4_middle_once_v2 as record
from tools import mf1750_lh1_rebound_v2_review as v2review
from tools import mf1750_lh3_dose_pack as dose_pack

PREFIX = 'pal1_cal_v5'
MACRO = 'MF1750_PALETTE_CAL_PAL1_V5_BUILD'
CPP_NAMESPACE = 'mf1750_pal1_cal_v5'
NVS = {'namespace': 'pal1_v5', 'cursor': 'cur_pal5', 'boot': 'boot_pal5'}
CAMPAIGN = 'EC5_PALETTE_CAL_PAL1_V5_20260925'
SOURCE_STATE = 'LH3_DOSE_V2_COMPLETE_PLUS_CURRENT_HOST_REVIEW_REQUIRED'
DEFAULT = ROOT / '.test-output/offline/PAL1_CAL_20260925_R2'
# White anchor: the 2026-09-22 LH3 white close-review FILE sha256 (unchanged,
# same anchor as the LH3 dose packages). The record's own integrity canonical
# sha256 is 17dc2fed63eef7943510e0678f184b8d267fbcfc22450a69f6490d9e058d025e.
WHITE = dose_pack.WHITE
ANCHOR_SHA = dose_pack.ANCHOR_SHA
WHITE_RECORD_NAMES = dose_pack.WHITE_RECORD_NAMES
REAL_RECORD_NAMES = dose_pack.REAL_RECORD_NAMES
LH2_MAP_TERMINAL = dose_pack.LH2_MAP_TERMINAL
V1_BRICKED = dose_pack.V1_BRICKED
# LH3 dose V2 terminal (2026-09-24 field chain, live-s3 result):
# campaign complete, cursor_raw=4, boot nonce 4d53de6fe4b39d3b.
LH3_DOSE_V2_TERMINAL = {'namespace': 'lh3dose_v2', 'cursor': 'cur_lh3d2', 'boot': 'boot_lh3d2',
    'expected_cursor_raw': 4, 'expected_boot': '4d53de6fe4b39d3b'}
# PAL1 V1 (package PAL1_CAL_20260924_R1) died at first boot with
# compiled_fixture_self_check_failed (PAL1-R1-D1, see module docstring).
# PAL1 V2 (package PAL1_CAL_20260924_R2) then died before its first ARM when
# its own gate demanded a pal1_v1 cursor key that was never written
# (PAL1-R2-D2, gate-vs-NVS-ground-truth mismatch): the boot path writes ONLY
# the campaign boot key; the cursor key is first written at the ARM
# transition. Ground truth (NVS_DUMP_PARSE_20260924_V1, captured read-only):
# pal1_v1 has boot_pal1 only, pal1_v2 has boot_pal2 only, no cursor keys.
# Both namespaces are dead in practice (their boot bindings exist, so any
# reset latches a persistent FAULT) with zero ARM/EXECUTE/driver/refresh.
PAL1_V1_DEAD = {'namespace': 'pal1_v1', 'cursor': 'cur_pal1', 'boot': 'boot_pal1',
    'expected_cursor_raw': 1, 'cursor_key_may_be_absent': True,
    'cursor_absent_means_fresh_value_1': True,
    'boot_key_present_required': True,
    'boot_value_pinned': False, 'fault_persisted': False,
    'driver_call_count_at_failure': 0, 'visible_refresh_count_at_failure': 0,
    'recoverable': False, 'must_remain_untouched': True,
    'incident': 'PAL1-R1-D1 compiled_fixture_self_check_failed at first boot: '
                'fixture role loop {Source,Mid,Target} indexed kActions[2] out '
                'of bounds (identity slot count 1+1 < role index 3)',
    'ground_truth': 'NVS_DUMP_PARSE_20260924_V1: pal1_v1 has boot_pal1 only, '
                    'no cur_pal1 key (boot writes only the boot key; the '
                    'cursor is first written at the ARM transition)'}
PAL1_V2_DEAD = {'namespace': 'pal1_v2', 'cursor': 'cur_pal2', 'boot': 'boot_pal2',
    'expected_cursor_raw': 1, 'cursor_key_may_be_absent': True,
    'cursor_absent_means_fresh_value_1': True,
    'boot_key_present_required': True,
    'boot_value_pinned': False, 'fault_persisted': False,
    'driver_call_count_at_failure': 0, 'visible_refresh_count_at_failure': 0,
    'recoverable': False, 'must_remain_untouched': True,
    'incident': 'PAL1-R2-D2: V2 gate demanded a pal1_v1 cursor key that the '
                'boot path never writes (cursor first written at ARM); '
                'whiteSourceReady was false on the real device, preflight '
                'refused, and the read-only NVS dump RTS reset killed the '
                'fresh pal1_v2 boot binding before any ARM',
    'inferred_cursor_fault_769': True,
    'inference': 'the dump was captured BEFORE the dump operation\'s own RTS '
                 'reset; the V2 firmware\'s only possible cursor write before '
                 'any ARM is the persistent boot-fault cursor 769 '
                 '(phase FAULT | ordinal 1). The V4 gate bitmap confirmed '
                 'pal1_v2=false on device. The gate therefore accepts '
                 'cursor absent, 1, or 769.',
    'ground_truth': 'NVS_DUMP_PARSE_20260924_V1: pal1_v2 has boot_pal2 only, '
                    'no cur_pal2 key'}
# PAL1 V4 (package PAL1_CAL_20260925_R1) booted with gate_detail all-true
# except pal1_v2=false (the inferred 769). Its boot binding (f434e324f1bca44f)
# was written at the V4 first boot; flashing V5 kills it like the others.
PAL1_V4_DEAD = {'namespace': 'pal1_v4', 'cursor': 'cur_pal4', 'boot': 'boot_pal4',
    'expected_cursor_raw': 1, 'cursor_key_may_be_absent': True,
    'cursor_absent_means_fresh_value_1': True,
    'boot_key_present_required': True,
    'boot_value_pinned': False, 'fault_persisted': False,
    'driver_call_count_at_failure': 0, 'visible_refresh_count_at_failure': 0,
    'recoverable': False, 'must_remain_untouched': True,
    'incident': 'V4 diagnosed PAL1-R3-D3 via gate_detail (pal1_v2=false); '
                'V4 never ARMed; flashing V5 strands its boot binding '
                '(device boot f434e324f1bca44f, field-reported)',
    'ground_truth': 'pal1_v4 boot binding written at the V4 first boot; no '
                    'cursor key (cursor is first written at ARM)'}
# PAL1 V3 (package PAL1_CAL_20260924_R3) booted clean (fixture fix worked) but
# the runner preflight still saw source_nvs_complete=false even though every
# gate pin was verified against the NVS dump. The read-only dump's RTS reset
# had already killed the fresh pal1_v3 boot binding (zero ARM/EXECUTE/driver/
# refresh). V4 adds a per-segment gate_detail bitmap to the identity JSON so
# the next field session pinpoints the failing segment directly; the dead
# pal1_v3 namespace is pinned like V1/V2 (boot 09665a142b77a580 was written at
# the V3 first boot, after the dump — its value comes from the field report,
# not the dump).
PAL1_V3_DEAD = {'namespace': 'pal1_v3', 'cursor': 'cur_pal3', 'boot': 'boot_pal3',
    'expected_cursor_raw': 1, 'cursor_key_may_be_absent': True,
    'cursor_absent_means_fresh_value_1': True,
    'boot_key_present_required': True,
    'boot_value_pinned': False, 'fault_persisted': False,
    'driver_call_count_at_failure': 0, 'visible_refresh_count_at_failure': 0,
    'recoverable': False, 'must_remain_untouched': True,
    'incident': 'PAL1-R3-D3: all gate pins verified against the NVS dump yet '
                'source_nvs_complete stayed false; the read-only dump RTS '
                'reset killed the fresh pal1_v3 boot binding (device boot '
                '09665a142b77a580) before any ARM',
    'ground_truth': 'pal1_v3 boot binding written at the V3 first boot '
                    '(post-dump; field-reported device boot 09665a142b77a580); '
                    'no cursor key (cursor is first written at ARM)'}


def module():
    spec = importlib.util.spec_from_file_location('_pal1_base', ROOT/'tools/mf1750_lightness_history_firmware.py')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    return base


def real_records():
    return dose_pack.real_records()


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
    base.algorithm = pal1
    base.SOURCE_WHITE = {
        'campaign_id': terminal['campaign_id'], 'action_id': terminal['action_id'],
        'contract_id': terminal['contract_id'], 'firmware_sha256': flash['binary']['observed_sha256'],
        'nvs_namespace': 'lh3srcw_v1', 'nvs_key': 'used_lh3sw1', 'complete_cursor': 2,
        'terminal_evidence': base.bind(white_records['terminal']),
        'clean_white_review': base.bind(white_records['optical_review']),
        'close_review': close_binding, 'nvs_is_not_optical_or_electrical_proof': True,
    }
    base.CAMPAIGN = CAMPAIGN
    base.BUILD_TAG = 'MF1750_EC5_PALETTE_CAL_PAL1_V5_2026-09-25'
    base.PREFIX, base.MACRO, base.NAMESPACE = PREFIX, MACRO, CPP_NAMESPACE
    original_contract, original_config = base.contract, base.config_source
    original_frame, original_identity = base.frame_source, base.identity_source
    original_gate, original_render = base.source_gate_code, base.render

    def contract():
        c = original_contract()
        c.pop('contract_id')
        c['nvs'] = deepcopy(NVS)
        c['action_count'] = 1
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
        c['lh3_dose_v2_terminal_preservation'] = {**deepcopy(LH3_DOSE_V2_TERMINAL),
            'campaign_complete':True, 'must_remain_untouched':True,
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['pal1_v1_fixture_defect_preservation'] = {**deepcopy(PAL1_V1_DEAD),
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['pal1_v2_gate_mismatch_preservation'] = {**deepcopy(PAL1_V2_DEAD),
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['pal1_v3_dead_preservation'] = {**deepcopy(PAL1_V3_DEAD),
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['pal1_v4_dead_preservation'] = {**deepcopy(PAL1_V4_DEAD),
            'device_gate':'read_only_before_ARM_EXECUTE_and_dispatch'}
        c['implementation_sha256']['tools/mf1750_pal1_pack.py'] = base.bind(Path(__file__))['sha256']
        c['implementation_sha256']['host/static_photo/palette_cal_pal1.py'] = base.bind(ROOT/'host/static_photo/palette_cal_pal1.py')['sha256']
        c['implementation_sha256']['tools/mf1750_lh3_dose_pack.py'] = base.bind(ROOT/'tools/mf1750_lh3_dose_pack.py')['sha256']
        c['protocol_compatibility'] = 'Existing lightness-history-v1 API/test algorithm; single PAL1 action, active header (production render path); V3 campaign/build/NVS after PAL1-R1-D1 (fixture defect) and PAL1-R2-D2 (gate vs NVS ground truth)'
        c['optical_source_authority'] = {'historical_anchor': close_binding, 'fresh_host_confirmation_required':True,
            'panel_optical_self_report':False, 'state':SOURCE_STATE}
        c['level_counts'] = None
        c['level_count_is_refresh_count'] = False
        c.pop('recipes_per_target', None)
        c['palette_calibration'] = {'pal1_codes': list(range(8)), 'columns_per_side': 8,
            'rows_per_code_per_side': 8, 'cells_per_side': 64,
            'frame_rule': 'code=column index 0..7; rows are spatial repeats',
            'physical_palette_codes': [0, 1, 2, 3, 5, 6], 'record_only_codes': [4, 7],
            'active_header_production_render_path': True,
            'code7_column_is_session_white_reference': True,
            'note': 'Single active action paints every code column once; measured Lab feeds palette schema v2 (calibrated=true).'}
        prior = None
        for a in c['actions']:
            a.pop('action_id'); a.pop('descriptor_id')
            a['prior_action_id'] = prior
            a['role'] = 'PAL1_CAL'
            a['branch'] = 'PAL1_SYMMETRIC_ACTIVE'
            a['driver_role'] = 'Source'
            a['source_state'] = SOURCE_STATE
            a['target_state'] = 'PAL1_CAL'
            a['descriptor_id'] = base.algorithm.digest(base.algorithm.canonical({
                'campaign':CAMPAIGN, 'action':a, 'source_white':base.SOURCE_WHITE,
                'implementation':c['implementation_sha256']}))
            a['action_id'] = base.algorithm.digest(f"{CAMPAIGN}|{a['ordinal']}|{a['descriptor_id']}".encode())
            prior = a['action_id']
        if len(c['actions']) != 1:
            raise ValueError('PAL1 is a single-action chain')
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
            '\\"symmetric_tuple_sequence\\":[\\"AA\\"]')
        text = text.replace('\\"level_counts\\":[3,5,10]', '\\"level_counts\\":null')
        text = text.replace('"LH1_HISTORY_POSITION_BALANCED_8X8"', '"PAL1_COLUMNS_8X8"')
        text = text.replace('"MF1750 Lightness History V1"', '"MF1750 PAL1 Measured Palette V5"')
        text = text.replace('static constexpr const char *kIdentityRevision="lightness-history-v1";',
            'static constexpr const char *kIdentityRevision="palette-cal-pal1-v5";')
        text = text.replace('"LH1_SOURCE"', '"PAL1_CAL"')
        text = text.replace('MF1750_LH1_COMPILED|CONTRACT=', 'MF1750_PAL1_V5_COMPILED|CONTRACT=')
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
bool lh3DoseV2TerminalComplete() {
  Preferences source;
  if (!source.begin("lh3dose_v2", true)) return false;
  const bool ok = source.isKey("cur_lh3d2") && source.getUShort("cur_lh3d2",0)==4 &&
      source.isKey("boot_lh3d2") && source.getULong64("boot_lh3d2",0)==0x4d53de6fe4b39d3bULL;
  source.end(); return ok;
}
bool pal1V1DeadPreserved() {
  Preferences old;
  if (!old.begin("pal1_v1", true)) return false;
  // Boot writes only the boot key; the cursor is first written at ARM, so the
  // dead V1 namespace has boot_pal1 and no cur_pal1 (NVS_DUMP_PARSE_20260924_V1).
  const bool ok = old.isKey("boot_pal1") &&
      (!old.isKey("cur_pal1") || old.getUShort("cur_pal1",0)==1);
  old.end(); return ok;
}
bool pal1V2DeadPreserved() {
  Preferences old;
  if (!old.begin("pal1_v2", true)) return false;
  // The dump predates its own RTS reset: V2's only possible cursor write
  // before any ARM is the persistent boot-fault cursor 769 (V4 gate bitmap
  // confirmed pal1_v2=false on device). Accept absent, 1, or 769.
  const uint16_t cur = old.getUShort("cur_pal2",0);
  const bool ok = old.isKey("boot_pal2") &&
      (!old.isKey("cur_pal2") || cur==1 || cur==769);
  old.end(); return ok;
}
bool pal1V3DeadPreserved() {
  Preferences old;
  if (!old.begin("pal1_v3", true)) return false;
  const bool ok = old.isKey("boot_pal3") &&
      (!old.isKey("cur_pal3") || old.getUShort("cur_pal3",0)==1);
  old.end(); return ok;
}
bool pal1V4DeadPreserved() {
  Preferences old;
  if (!old.begin("pal1_v4", true)) return false;
  const bool ok = old.isKey("boot_pal4") &&
      (!old.isKey("cur_pal4") || old.getUShort("cur_pal4",0)==1);
  old.end(); return ok;
}
// V4: split the LH3-white segment out of whiteSourceReady so the identity
// JSON can report every gate segment individually (PAL1-R3-D3 diagnostics).
bool lh3WhiteConsumed() {
  Preferences white;
  if (!white.begin("lh3srcw_v1", true)) return false;
  const bool ready=white.isKey("used_lh3sw1") && white.getUShort("used_lh3sw1",0)==2;
  white.end();
  return ready;
}
String lhGateDetailJson() {
  return String(",\\\"gate_detail\\\":{\\\"old_fault\\\":")+(oldFaultPreserved()?"true":"false")+
    ",\\\"rebound_v2\\\":"+(reboundV2TerminalPreserved()?"true":"false")+
    ",\\\"lh2_map\\\":"+(lh2DriveMapTerminalComplete()?"true":"false")+
    ",\\\"lh2_white\\\":"+(lh2WhitePreserved()?"true":"false")+
    ",\\\"lh3dose_v1\\\":"+(lh3DoseV1BrickedPreserved()?"true":"false")+
    ",\\\"lh3dose_v2\\\":"+(lh3DoseV2TerminalComplete()?"true":"false")+
    ",\\\"pal1_v1\\\":"+(pal1V1DeadPreserved()?"true":"false")+
    ",\\\"pal1_v2\\\":"+(pal1V2DeadPreserved()?"true":"false")+
    ",\\\"pal1_v3\\\":"+(pal1V3DeadPreserved()?"true":"false")+
    ",\\\"pal1_v4\\\":"+(pal1V4DeadPreserved()?"true":"false")+
    ",\\\"lh3_white\\\":"+(lh3WhiteConsumed()?"true":"false")+"}";
}
'''
        # V4 splits the LH3-white segment out of whiteSourceReady so the
        # identity JSON can report every gate segment individually.
        old_white = ('bool whiteSourceReady() {\n'
            '  Preferences white;\n'
            '  if (!white.begin("lh3srcw_v1", true)) return false;\n'
            '  const bool ready=white.isKey("used_lh3sw1") && white.getUShort("used_lh3sw1",0)==2;\n'
            '  white.end();\n'
            '  return ready;\n'
            '}')
        new_white = (preserved
            + 'bool whiteSourceReady() {\n'
            '  if (!oldFaultPreserved() || !reboundV2TerminalPreserved() || !lh2DriveMapTerminalComplete() || !lh2WhitePreserved() || !lh3DoseV1BrickedPreserved() || !lh3DoseV2TerminalComplete() || !pal1V1DeadPreserved() || !pal1V2DeadPreserved() || !pal1V3DeadPreserved() || !pal1V4DeadPreserved()) return false;\n'
            '  return lh3WhiteConsumed();\n'
            '}')
        if text.count(old_white) != 1:
            raise ValueError('whiteSourceReady body anchor changed')
        text = text.replace(old_white, new_white)
        text = text.replace('  if(action.ordinal==1 && prior!=source)',
            f'  if(source!="{anchor_sha}") return "source_review_anchor_mismatch";\n  if(action.ordinal==1 && prior!=source)')
        return text

    def identity(c):
        return original_identity(c).replace('mf1750_lightness_history_v1',CPP_NAMESPACE).replace(
            'kTargetCodes[2]={3,7}', 'kTargetCodes[8]={0,1,2,3,4,5,6,7}').replace(
            'kActions[4]={{},', 'kActions[2]={{},')

    def frame():
        text = original_frame().replace('ec5_lightness_history_v1_identity.inc',PREFIX+'_identity.inc').replace('mf1750_lightness_history_v1',CPP_NAMESPACE)
        old_rule = '    const uint8_t code=role==1 ? 7 : role==2 ? recipe%8 : kTargetCodes[recipe/8];'
        new_rule = '    const uint8_t code=role==1 ? (uint8_t)(i%8) : 7;'
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
                         ('LH1 forbids in-campaign white recovery', 'PAL1 forbids in-campaign white recovery')):
            if main.count(old) != 1:
                raise ValueError('main label anchor changed: ' + old[:60])
            main = main.replace(old, new)
        if 'single-pixel lightness history V1' not in main:
            raise ValueError('main label anchor changed: lightness history label')
        main = main.replace('single-pixel lightness history V1', 'PAL1 measured palette calibration V5')
        if 'FRESH_P2_FACTORY_WHITE' in main:
            raise ValueError('stale source-state compiled')
        old_count = 'static constexpr uint8_t kActionCount = 3;'
        if main.count(old_count) != 1:
            raise ValueError('kActionCount anchor changed')
        main = main.replace(old_count, 'static constexpr uint8_t kActionCount = 1;')
        dispatch = [line for line in main.split('\n') if 'if(action.ordinal==1) return String(' in line]
        if len(dispatch) != 1 or '\\"controller_tuple_dispatch\\":\\"AA\\"' not in dispatch[0]:
            raise ValueError('ordinal-1 transport dispatch must be AA')
        if 'if(action.ordinal==2) return String(' in main or 'if(action.ordinal==3) return String(' in main:
            raise ValueError('single-action chain must not compile ordinals 2/3')
        # V4 (PAL1-R3-D3): append the per-segment gate bitmap to the shared
        # identity JSON so the device self-reports which gate segment fails.
        old_tail = r'+",\"review_digests_are_host_assertions_only\":true";'
        new_tail = r'+",\"review_digests_are_host_assertions_only\":true"+lhGateDetailJson();'
        if main.count(old_tail) != 1:
            raise ValueError('identity JSON tail anchor changed')
        main = main.replace(old_tail, new_tail)
        if 'String lhGateDetailJson()' not in main:
            raise ValueError('gate detail function missing')
        sources[name] = main
        driver = sources[PREFIX+'_driver.inc']
        # PAL1 is active-header: the commented-tuple branch must stay Mid-only;
        # the Source role (and any Target role) keeps the active profile.
        active_branch = '#if defined('+MACRO+')\n  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;'
        if driver.count(active_branch) != 1:
            raise ValueError('commented-profile branch anchor changed')
        driver = driver.replace(
            '// Isolated LH1 full-frame history driver, symmetric complete tuples.',
            '// Isolated PAL1 full-frame measured-palette driver, symmetric complete tuples; single active Source action.\n// PAL1-R1-D1 fix: the fixture loop validates only the roles that exist.')
        # PAL1-R1-D1 fix: the frozen fixture loop validates {Source,Mid,Target}
        # and phValidateRole indexes ph::kActions[role] (1-based); with a single
        # action the identity compiles kActions[2], so Mid/Target read out of
        # bounds and the boot-time fixture self-check fails on real hardware.
        # Validate only the Source role, and reject Mid/Target in phRoleValid.
        old_roles = '  static constexpr EpdChromaGridRole kRoles[] = {EpdChromaGridRole::Source,EpdChromaGridRole::Mid,EpdChromaGridRole::Target};'
        new_roles = '  static constexpr EpdChromaGridRole kRoles[] = {EpdChromaGridRole::Source};'
        if driver.count(old_roles) != 1:
            raise ValueError('kRoles anchor changed')
        driver = driver.replace(old_roles, new_roles)
        old_role_valid = '  return phRoleIndex(role) >= 1 && phRoleIndex(role) <= 3;'
        new_role_valid = '  return phRoleIndex(role) == 1;'
        if driver.count(old_role_valid) != 1:
            raise ValueError('phRoleValid anchor changed')
        driver = driver.replace(old_role_valid, new_role_valid)
        # phLayoutValid pins the LH1 target-code pair; PAL1 enumerates all
        # eight codes as columns, so the layout gate pins the new array's
        # endpoints instead (LH2-DM-D1 defect class).
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
