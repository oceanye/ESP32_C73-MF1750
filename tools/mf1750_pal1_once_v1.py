"""PAL1 measured-palette single-action host runner V2.

One PAL1 action (ordinal 1, active header, column c carries code c), terminal
campaign_complete at next_ordinal=2. Exactly 1 ARM / 1 EXECUTE / 1 driver
call / 1 visible refresh, no retry, no second action. A permanent claim is
written before the only ARM; an existing claim refuses the run before any
network I/O. phase==3 (FAULT) stops the host at once and nothing is ever
resent.

V2 (2026-09-24, defect PAL1-R1-D1): the R1 firmware faulted at its first boot
(compiled_fixture_self_check_failed: the frozen fixture role loop indexed the
single-action identity kActions[2] out of bounds). V3 (2026-09-24 evening,
defect PAL1-R2-D2): the V2 gate demanded a pal1_v1 cursor key that the boot
path never writes (the cursor is first written at ARM), so whiteSourceReady
was false on the real device; the read-only NVS dump's RTS reset then killed
the fresh pal1_v2 boot binding before any ARM. V4 (2026-09-25) adds the
per-segment gate_detail bitmap to the identity JSON (PAL1-R3-D3 diagnostics:
V3 booted clean yet source_nvs_complete stayed false with every pin verified
against the dump; the dump's RTS reset killed the fresh pal1_v3 boot binding).
V4 runs on namespace pal1_v4 with claims under .mf1750_pal1_v4_action_claims;
the dead V1/V2/V3 namespaces are pinned to the NVS-dump ground truth (boot key
present, cursor absent-or-1). This runner requires every gate_detail segment
true on any document that carries the bitmap.

The X-LH review chain binds one field run: X-LH-Run-Id is the field run id,
X-LH-Source-Review and X-LH-Prior-Review are both the contract
lh3_white_source_anchor sha256 (ordinal 1 must bind the white anchor).

Device gate (compiled into the firmware and asserted here from the sealed
contract): the LH3 dose V2 campaign must be at its terminal (lh3dose_v2
cur_lh3d2=4, boot 4d53de6fe4b39d3b, campaign complete), the bricked V1 dose
namespace must still read cursor 769, the LH3 white allowance stays consumed
(lh3srcw_v1/used_lh3sw1==2), the LH2 drive-map terminal stays (lh2map_v1
cur_lh2m=4, boot ac92bb9e25c374ef) and lhist_v1 / lh1reb_v2 / lh2srcw_v1 stay
untouched.

OPERATIONAL WARNING (2026-09-24 incident): after flashing, the first boot
writes the campaign boot binding — no MCU reset of any kind (esptool/serial
RTS/pyserial port open) is allowed until the action completes.

Import and validate perform no device access. Field/release collection tools
are separate; this runner only verifies their sealed records. All identity
pins (contract id, anchor, BIN/ELF) are read from the package bindings, not
hardcoded.
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from tools import mf1750_lh1_lh4_middle_once_v2 as http
from tools import mf1750_lh1_lh4_once_operator_v2 as b

ROOT = b.ROOT
PACKAGE = ROOT / '.test-output/offline/PAL1_CAL_20260925_R2'
CLAIMS = ROOT / '.test-output/hardware/.mf1750_pal1_v5_action_claims'
PREFIX = 'pal1_cal_v5'
NVS = {'namespace': 'pal1_v5', 'cursor': 'cur_pal5', 'boot': 'boot_pal5'}
OLD_FAULT = {'namespace': 'lhist_v1', 'cursor': 'cur_lh1', 'boot': 'boot_lh1',
    'expected_cursor_raw': 770, 'expected_boot': '30a9e5989873f4e0',
    'must_remain_untouched': True, 'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
REBOUND = {'namespace': 'lh1reb_v2', 'cursor': 'cur_lh1r', 'boot': 'boot_lh1r',
    'expected_cursor_raw': 4, 'expected_boot': '7274e005c8833ca1',
    'must_remain_untouched': True, 'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch',
    'v2_contract': '021c35abd47f6caa52b11cec98b73a79f11c585bdbc1ed976c2dde868bc5259e'}
LH2_MAP_TERMINAL = {'namespace': 'lh2map_v1', 'cursor': 'cur_lh2m', 'boot': 'boot_lh2m',
    'expected_cursor_raw': 4, 'expected_boot': 'ac92bb9e25c374ef',
    'must_remain_untouched': True, 'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
LH2_WHITE = {'namespace': 'lh2srcw_v1', 'key': 'used_lh2sw1',
    'expected_cursor_raw': 2, 'must_remain_untouched': True,
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
V1_BRICKED = {'namespace': 'lh3dose_v1', 'cursor': 'cur_lh3d', 'boot': 'boot_lh3d',
    'expected_cursor_raw': 769, 'expected_phase': 'FAULT', 'expected_ordinal': 1,
    'driver_call_count_at_brick': 0, 'recoverable': False,
    'must_remain_untouched': True,
    'incident': 'esptool read_mac RTS hard reset after campaign boot binding '
                'was written; campaign_boot_binding_mismatch_at_boot latched '
                'before any ARM/EXECUTE/driver/refresh',
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
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
                    'cursor is first written at the ARM transition)',
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
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
    'inference': "the dump was captured BEFORE the dump operation's own RTS "
                 "reset; the V2 firmware's only possible cursor write before "
                 'any ARM is the persistent boot-fault cursor 769 '
                 '(phase FAULT | ordinal 1). The V4 gate bitmap confirmed '
                 'pal1_v2=false on device. The gate therefore accepts '
                 'cursor absent, 1, or 769.',
    'ground_truth': 'NVS_DUMP_PARSE_20260924_V1: pal1_v2 has boot_pal2 only, '
                    'no cur_pal2 key',
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
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
                    'cursor key (cursor is first written at ARM)',
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
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
                    'no cursor key (cursor is first written at ARM)',
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
GATE_DETAIL_KEYS = ('old_fault', 'rebound_v2', 'lh2_map', 'lh2_white',
    'lh3dose_v1', 'lh3dose_v2', 'pal1_v1', 'pal1_v2', 'pal1_v3', 'pal1_v4',
    'lh3_white')
LH3_DOSE_V2_TERMINAL = {'namespace': 'lh3dose_v2', 'cursor': 'cur_lh3d2', 'boot': 'boot_lh3d2',
    'expected_cursor_raw': 4, 'expected_boot': '4d53de6fe4b39d3b',
    'campaign_complete': True, 'must_remain_untouched': True,
    'device_gate': 'read_only_before_ARM_EXECUTE_and_dispatch'}
RELEASE_SCOPE = 'ONE_INDEPENDENT_PAL1_CAL_ACTION'
SOURCE_STATE = 'LH3_DOSE_V2_COMPLETE_PLUS_CURRENT_HOST_REVIEW_REQUIRED'
INITIAL_WAIT = 65
MAX_POLLS = 30
RUN_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
require = b._require
Error = b.RunnerError


def now():
    return datetime.now(timezone.utc).isoformat()


def dependencies():
    return [b.file_binding(Path(m.__file__)) for m in (http, b)] + [b.file_binding(Path(__file__))]


def claim_path(ctx, claims=None):
    return Path(claims if claims is not None else CLAIMS) / (ctx['contract']['contract_id'] + '-ordinal1.json')


def bound_record(binding):
    value = b.parse_json(b.read_bound(binding))
    b.verify_integrity(value)
    return value


def _binding(record, key):
    binding = record.get(key)
    if not isinstance(binding, dict):
        raise Error('binding missing: ' + key)
    return binding


def validate_package(package=PACKAGE):
    package = Path(package).resolve()
    manifest = b.read_record(package / 'manifest.json')
    build = b.read_record(package / 'build-report.json')
    contract = b.parse_json(b._regular(package / 'contract.json'))
    body = dict(contract)
    stated = body.pop('contract_id', None)
    if not isinstance(stated, str) or not b.HEX.fullmatch(stated) or b.digest(b.canonical(body)) != stated:
        raise Error('PAL1 contract identity mismatch')
    require(contract, {'kind': 'mf1750-lightness-history-firmware-contract-v1',
        'algorithm_id': 'MF1750_PALETTE_CAL_PAL1_V1_20260924',
        'build_tag': 'MF1750_EC5_PALETTE_CAL_PAL1_V5_2026-09-25',
        'campaign_id': 'EC5_PALETTE_CAL_PAL1_V5_20260925',
        'base_route': '/api/ec5/lightness-history-v1',
        'nvs': NVS, 'action_count': 1, 'startup_refresh': False, 'autochain': False,
        'retry': False, 'white_or_repeat_action': False, 'raw_ingress': False,
        'frame_rate_sweep': False, 'new_electrical_values': False,
        'legacy_v3_asymmetric_r20_dispatch_reused': False,
        'both_controllers_use_same_complete_tuple_per_action': True,
        'level_count_is_refresh_count': False, 'level_counts': None,
        'old_boot_ip_com_or_white_anchor_reused': False, 'qualified_count': 0,
        'live_ready': False, 'old_fault_preservation': OLD_FAULT,
        'rebound_v2_terminal_preservation': REBOUND,
        'lh2_map_terminal_preservation': LH2_MAP_TERMINAL,
        'lh2_white_preservation': LH2_WHITE,
        'lh3_dose_v1_bricked_preservation': V1_BRICKED,
        'lh3_dose_v2_terminal_preservation': LH3_DOSE_V2_TERMINAL,
        'pal1_v1_fixture_defect_preservation': PAL1_V1_DEAD,
        'pal1_v2_gate_mismatch_preservation': PAL1_V2_DEAD,
        'pal1_v3_dead_preservation': PAL1_V3_DEAD,
        'pal1_v4_dead_preservation': PAL1_V4_DEAD}, 'PAL1 contract')
    require(contract['palette_calibration'], {'cells_per_side': 64,
        'pal1_codes': list(range(8)), 'columns_per_side': 8, 'rows_per_code_per_side': 8,
        'physical_palette_codes': [0, 1, 2, 3, 5, 6], 'record_only_codes': [4, 7],
        'active_header_production_render_path': True,
        'code7_column_is_session_white_reference': True,
        'frame_rule': 'code=column index 0..7; rows are spatial repeats'}, 'palette calibration')
    require(build, {'result': 'PASS', 'contract_id': contract['contract_id'],
        'hardware_accessed': False, 'firmware_flashed': False,
        'marker_check': 'PASS', 'package_still_matches': True, 'live_ready': False,
        'visible_refresh_count': 0}, 'build')
    require(manifest, {'kind': 'mf1750-lightness-history-firmware-package-v1',
        'contract_id': contract['contract_id'], 'live_ready': False, 'qualified_count': 0}, 'manifest')
    if Path(build['manifest']['path']).resolve() != package / 'manifest.json':
        raise Error('build binds another manifest')
    for binding in manifest['inputs'] + manifest['outputs'] + build['artifacts'] + [build['log'], build['manifest']]:
        b.read_bound(binding)
    for group in ('implementation_sha256', 'identity_dependency_hashes'):
        for relative, sha in contract[group].items():
            if b.digest(b._regular(ROOT / relative)) != sha:
                raise Error('implementation changed: ' + relative)
    outputs = {Path(x['path']).resolve() for x in manifest['outputs']}
    names = ['contract.json', 'platformio.ini', 'pal1.frame4bpp',
             'generated/frozen_epd_driver.cpp.inc', 'generated/lh_frame_fill.hpp']
    names += ['generated/' + PREFIX + suffix for suffix in
              ('_main.cpp', '_main_config.inc', '_identity.inc', '_driver.inc')]
    for name in names:
        if package / name not in outputs:
            raise Error('unsealed output: ' + name)
    cfg = b._regular(package / ('generated/' + PREFIX + '_main_config.inc')).decode('utf8')
    identity = {key: b._string(cfg, symbol) for key, symbol in (
        ('build_tag', 'kBuildTag'), ('test_id', 'kTestId'),
        ('campaign_id', 'kCampaignId'), ('contract_id', 'kContractId'),
        ('device_api_version', 'kDeviceApiVersion'), ('identity_revision', 'kIdentityRevision'),
        ('compiled_identity_marker', 'kCompiledIdentityMarker'), ('classification', 'kClassification'))}
    require(identity, {'contract_id': contract['contract_id'], 'build_tag': contract['build_tag'],
        'campaign_id': contract['campaign_id'], 'test_id': contract['algorithm_id'],
        'identity_revision': 'palette-cal-pal1-v5',
        'device_api_version': 'MF1750_LIGHTNESS_HISTORY_DEVICE_V1'}, 'compiled identity')
    compiled_nvs = {key: b._string(cfg, symbol) for key, symbol in (
        ('namespace', 'kNvsNamespace'), ('cursor', 'kNvsKey'), ('boot', 'kNvsBootKey'))}
    if compiled_nvs != NVS:
        raise Error('compiled NVS contract differs')
    artifacts = {Path(x['path']).suffix: x for x in build['artifacts']}
    if set(artifacts) != {'.bin', '.elf'}:
        raise Error('BIN/ELF set differs')
    for item in artifacts.values():
        if not Path(item['path']).resolve().is_relative_to(package / 'build'):
            raise Error('compiled artifact outside package build')
        if b.read_bound(item).count(identity['compiled_identity_marker'].encode()) != 1:
            raise Error('compiled marker count differs')
    if len(contract['actions']) != 1:
        raise Error('PAL1 contract must hold exactly one action')
    action = contract['actions'][0]
    require(action, {'ordinal': 1, 'visible_refresh_count': 1,
        'waveform_internal_phase': 'OPAQUE', 'stage': 'PAL1', 'role': 'PAL1_CAL',
        'driver_role': 'Source', 'branch': 'PAL1_SYMMETRIC_ACTIVE',
        'global_header': 'active', 'prior_action_id': None}, 'action')
    if action['profile'].get('controller_payloads_byte_identical') is not True:
        raise Error('controller tuple symmetry differs')
    for key in ('action_id', 'descriptor_id'):
        if not b.HEX.fullmatch(action[key]) or action[key] not in cfg:
            raise Error('compiled action identity differs')
    if b.digest(b._regular(package / 'pal1.frame4bpp')) != action['frame']['sha256']:
        raise Error('frame differs')
    if action['frame']['histogram'] != [33280] * 7 + [381440]:
        raise Error('frame histogram differs')
    anchor = contract['lh3_white_source_anchor']
    require(contract['optical_source_authority'], {'historical_anchor': anchor,
        'fresh_host_confirmation_required': True, 'panel_optical_self_report': False,
        'state': SOURCE_STATE}, 'optical source authority')
    require(contract['source_white'], {'close_review': anchor, 'nvs_namespace': 'lh3srcw_v1',
        'nvs_key': 'used_lh3sw1', 'complete_cursor': 2,
        'nvs_is_not_optical_or_electrical_proof': True}, 'source white')
    close = bound_record(anchor)
    # Synthetic close-reviews embed the terminal report; the real 2026-09-22
    # batch carries it in the live-white result record (bound as
    # source_white.terminal_evidence).
    terminal = close.get('terminal_report')
    if terminal is None:
        terminal = bound_record(_binding(contract['source_white'], 'terminal_evidence'))['terminal_report']
    require(terminal, {'terminal_state': 'COMPLETE', 'result': True},
        'white anchor terminal')
    for key in ('terminal_evidence', 'clean_white_review'):
        b.read_bound(contract['source_white'][key])
    # Static anchors in the generated sources; the pack tool seals exactly these.
    main = b._regular(package / ('generated/' + PREFIX + '_main.cpp')).decode('utf8')
    driver = b._regular(package / ('generated/' + PREFIX + '_driver.inc')).decode('utf8')
    ident = b._regular(package / ('generated/' + PREFIX + '_identity.inc')).decode('utf8')
    if 'static constexpr uint8_t kActionCount = 1;' not in main or 'kActions[2]=' not in ident:
        raise Error('single-action constants differ')
    if driver.count('  if (role == EpdChromaGridRole::Mid) useCommentedGlobal = true;') < 1 \
            or 'EpdChromaGridRole::Mid || role == EpdChromaGridRole::Target) useCommentedGlobal' in driver:
        raise Error('commented branch must stay Mid-only for the active PAL1 header')
    if 'ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7' not in driver:
        raise Error('layout gate target-code endpoints differ')
    if 'kTargetCodes[8]={0,1,2,3,4,5,6,7}' not in ident:
        raise Error('PAL1 code enumeration differs')
    dispatch = [line for line in main.split('\n') if 'if(action.ordinal==1) return String(' in line]
    if len(dispatch) != 1 or '\\"controller_tuple_dispatch\\":\\"AA\\"' not in dispatch[0]:
        raise Error('ordinal-1 transport dispatch must be AA')
    if 'if(action.ordinal==2) return String(' in main or 'if(action.ordinal==3) return String(' in main:
        raise Error('single-action chain must not compile ordinals 2/3')
    for token in ('oldFaultPreserved', 'reboundV2TerminalPreserved',
                  'lh2DriveMapTerminalComplete', 'lh2WhitePreserved',
                  'lh3DoseV1BrickedPreserved', 'lh3DoseV2TerminalComplete',
                  'pal1V1DeadPreserved', 'pal1V2DeadPreserved',
                  'old.getUShort("cur_lh1",0)==770', 'old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL',
                  'source.getUShort("cur_lh1r",0)==4', 'source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL',
                  'source.getUShort("cur_lh2m",0)==4', 'source.getULong64("boot_lh2m",0)==0xac92bb9e25c374efULL',
                  'white.getUShort("used_lh2sw1",0)==2',
                  'white.begin("lh3srcw_v1", true)', 'white.getUShort("used_lh3sw1",0)==2',
                  'old.getUShort("cur_lh3d",0)==769',
                  'source.getUShort("cur_lh3d2",0)==4', 'source.getULong64("boot_lh3d2",0)==0x4d53de6fe4b39d3bULL',
                  'old.isKey("boot_pal1")', '!old.isKey("cur_pal1") || old.getUShort("cur_pal1",0)==1',
                  'old.isKey("boot_pal2")',
                  '!old.isKey("cur_pal2") || cur==1 || cur==769',
                  'old.isKey("boot_pal3")', '!old.isKey("cur_pal3") || old.getUShort("cur_pal3",0)==1',
                  'old.isKey("boot_pal4")', '!old.isKey("cur_pal4") || old.getUShort("cur_pal4",0)==1',
                  'cur==1 || cur==769',
                  'String lhGateDetailJson()', '\\"gate_detail\\":{',
                  'if (!oldFaultPreserved() || !reboundV2TerminalPreserved() || !lh2DriveMapTerminalComplete() || !lh2WhitePreserved() || !lh3DoseV1BrickedPreserved() || !lh3DoseV2TerminalComplete() || !pal1V1DeadPreserved() || !pal1V2DeadPreserved() || !pal1V3DeadPreserved() || !pal1V4DeadPreserved()) return false;'):
        if token not in main:
            raise Error('preservation gate missing: ' + token)
    compiled_anchor = re.search(r'if\(source!="([0-9a-f]{64})"\) return "source_review_anchor_mismatch";', main)
    if not compiled_anchor or compiled_anchor.group(1) != anchor['sha256']:
        raise Error('compiled white source anchor differs')
    return {'package': package, 'contract': contract, 'identity': identity,
        'firmware': artifacts['.bin'], 'elf': artifacts['.elf'], 'anchor': anchor['sha256'],
        'routes': {k: b._string(cfg, 'k' + k.capitalize() + 'Route')
                   for k in ('version', 'manifest', 'status', 'report', 'arm', 'execute')},
        'arm_intent': b._string(cfg, 'kArmIntent'), 'execute_intent': b._string(cfg, 'kExecuteIntent')}


def expected_action(ctx):
    a = ctx['contract']['actions'][0]
    return {'ordinal': 1, 'descriptor_id': a['descriptor_id'], 'action_id': a['action_id'],
        'role': a['role'], 'round': 1, 'branch': a['branch'],
        'controller_tuple_dispatch': 'AA',
        'cs1_profile': a['profile']['cs1'], 'cs2_profile': a['profile']['cs2'],
        'driver_entry': 'epdDisplayCompiledChromaGrid', 'global_header': a['global_header'],
        'palette_source': 'L535_RUNTIME', 'profile_id': a['profile_id'],
        'profile_sha256': a['profile_sha256'],
        'source_state': a['source_state'], 'target_state': a['target_state']}


def identity(ctx, value, field, prior, *, latched):
    require(value, ctx['identity'], 'device identity')
    require(value, {'waveform_internal_phase': 'OPAQUE', 'qualified_count': 0,
        'source_nvs_complete': True, 'review_digests_are_host_assertions_only': True,
        'run_id': field['run_id'] if latched else '',
        'source_review_sha256': ctx['anchor'] if latched else '',
        'prior_review_sha256': prior if latched else ''}, 'device review')
    if 'boot_nonce' in value:
        require(value, {'boot_nonce': field['boot_nonce']}, 'boot identity')
    # V4: the device self-reports every gate segment; any false segment stops
    # the run at the first document that carries the bitmap.
    detail = value.get('gate_detail')
    if detail is not None:
        require(detail, {key: True for key in GATE_DETAIL_KEYS}, 'gate detail')


def nvs_gate(value):
    require(value['nvs_contract'], {'namespace': NVS['namespace'], 'key': NVS['cursor'],
        'campaign_boot_key': NVS['boot'], 'current_boot_exact_match_required': True,
        'reboot_resume_allowed': False, 'post_containment_resume_allowed': False,
        'initial_next_ordinal': 1, 'terminal_next_ordinal': 2}, 'NVS')


def driver_gate(ctx, driver):
    """Strict terminal gate; the desktop stub's 255-sentinel trace never passes.

    Real BUSY levels/timings are required here; the strict-native audit proves
    the frame/DTM FNV-1a binding offline with a synthetic stub, which is not
    admissible as a live terminal trace.
    """
    a = ctx['contract']['actions'][0]
    require(driver, {'driver_evidence_schema_version': 2, 'valid': True, 'running': False,
        'sequence_ok': True, 'wait_timeout': False, 'busy_assertion_missing': False,
        'pre_command_idle_failure': False, 'mapping_applied': True,
        'pon_busy_seen': True, 'drf_busy_seen': True, 'pof_busy_seen': True,
        'input_fnv1a': a['frame']['fnv1a'], 'cs1_dtm_fnv1a': a['cs1_dtm']['fnv1a'],
        'cs2_dtm_fnv1a': a['cs2_dtm']['fnv1a'], 'failure_code': 0,
        'operation_id': 1, 'spi_hz': 1000000}, 'driver')
    for key in ('failure_stage', 'timeout_stage', 'busy_missing_stage', 'pre_command_busy_stage'):
        if driver.get(key) not in ('', 'none'):
            raise Error('driver failure stage present')
    stages = driver['busy_stage_samples']
    require(stages, {'unreached_level_sentinel': 255}, 'BUSY schema')
    for name in ('pon', 'drf', 'pof'):
        s = stages[name]
        require(s, {'pre_command_level': 1, 'pre_command_idle_ok': True,
            'assertion_after_idle': True, 'wait_exit_level': 1}, name)
        for key in ('gate_entry_level', 'wait_entry_level'):
            if type(s.get(key)) is not int or s[key] not in (0, 1):
                raise Error('raw BUSY level missing')
        for key in ('wait_ms', 'pre_command_wait_ms', 'assertion_latency_ms'):
            if type(s.get(key)) is not int or not 0 <= s[key] <= 60000:
                raise Error('BUSY timing invalid')
    require(stages['reset'], {'wait_exit_level': 1}, 'reset BUSY')
    require(stages['post_psr'], {'pre_command_level': 1,
        'pre_command_idle_ok': True, 'wait_exit_level': 1}, 'post-PSR BUSY')
    require(driver['safe_finish'], {'busy_before_pins_low': 1, 'busy_after_pins_low': 1,
        'busy_after_5ms': 1, 'final_gpio': {'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}}, 'safe finish')


def validate_terminal(ctx, status, report, field, prior):
    identity(ctx, status, field, prior, latched=True)
    identity(ctx, report, field, prior, latched=True)
    require(report, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-report'}, 'report')
    require(status, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-status'}, 'status')
    require(report, expected_action(ctx), 'terminal action')
    require(report, {'valid': True, 'terminal_state': 'COMPLETE', 'result': True,
        'driver_called': True, 'driver_call_count_for_action': 1,
        'total_driver_call_count': 1, 'job_id': 1, 'phase': 0, 'phase_name': 'READY',
        'next_ordinal': 2, 'campaign_complete': True,
        'no_retry': True, 'no_recovery': True}, 'terminal')
    require(status, {'state': 'complete', 'phase': 0, 'phase_name': 'READY',
        'cursor_raw': 2, 'next_ordinal': 2,
        'arm_request_count': 1, 'execute_request_count': 1,
        'total_driver_call_count': 1, 'execute_pending': False, 'current_action': None,
        'cursor_valid': True, 'persistent_key_present': True, 'campaign_boot_key_present': True,
        'campaign_boot_matches_current': True, 'campaign_complete': True,
        'persisted_campaign_boot_nonce': field['boot_nonce'],
        'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}, 'terminal status')
    nvs_gate(status)
    driver_gate(ctx, report['driver'])
    times = [report.get(k) for k in ('job_queued_at_ms', 'job_started_at_ms', 'job_finished_at_ms')]
    if any(type(t) is not int or t < 0 for t in times) or times != sorted(times):
        raise Error('job chronology differs')


def validate_preflight(ctx, values, field):
    for name, value in values.items():
        identity(ctx, value, field, '', latched=False)
        require(value, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-' + name}, name)
    for name in ('version', 'manifest'):
        require(values[name], {'action_count': 1, 'automatic_chaining': False,
            'startup_refresh': False, 'retry': False, 'recovery': False,
            'raw_frame_ingress': False, 'caller_electrical_parameter_write': False,
            'fixed_profile_parameter_write': True, 'runtime_lut_write': True,
            'device_enforced_same_boot': True, 'dither': False, 'spatial_mixing': False,
            'full_screen_global_refresh': True, 'partial_refresh': False,
            'layout_id': 'PAL1_COLUMNS_8X8', 'lightness_qualification': False,
            'local_hold_claimed': False, 'identical_target_repeat': False,
            'main_campaign_resume_after_containment': False,
            'profile_source': 'complete_symmetric_L535_active_commented_tuples'}, name)
        nvs_gate(values[name])
    require(values['version'], {'automatic_execute': False,
        'driver_api_version': 'MF1750_R16_CASCADE_V3'}, 'version')
    require(values['manifest'], {'one_driver_call_per_action': True,
        'synchronous_both_controllers': True, 'round_count': 1, 'factory_otp': False,
        'custom_lut_or_waveform': True}, 'manifest')
    actions = values['manifest'].get('actions')
    if not isinstance(actions, list) or len(actions) != 1:
        raise Error('device action list differs')
    want = ctx['contract']['actions'][0]
    require(actions[0], expected_action(ctx), 'compiled action')
    require(actions[0], {'frame_sha256': want['frame']['sha256'],
        'cs1_dtm_sha256': want['cs1_dtm']['sha256'], 'cs2_dtm_sha256': want['cs2_dtm']['sha256'],
        'transport_code_histogram': want['frame']['histogram'],
        'prior_static_action_id': None}, 'compiled frame')
    require(values['status'], {'state': 'ready', 'phase': 0, 'phase_name': 'READY',
        'cursor_raw': 1, 'next_ordinal': 1, 'arm_request_count': 0, 'execute_request_count': 0,
        'total_driver_call_count': 0, 'execute_pending': False, 'current_action': None,
        'campaign_complete': False, 'cursor_valid': True, 'persistent_key_present': False,
        'campaign_boot_key_present': True, 'campaign_boot_matches_current': True,
        'persisted_campaign_boot_nonce': field['boot_nonce'],
        'fixture_self_check_passed': True, 'gpio_initialized': True, 'busy': 1}, 'fresh status')
    nvs_gate(values['status'])
    require(values['report'], {'valid': False, 'terminal_state': 'NOT_EXECUTED',
        'ordinal': None, 'action_id': None, 'descriptor_id': None, 'result': False,
        'driver_called': False, 'driver_call_count_for_action': 0,
        'total_driver_call_count': 0, 'phase': 0, 'next_ordinal': 1,
        'no_retry': True, 'no_recovery': True}, 'fresh report')


def validate_field(ctx, path, base_url, now_dt=None, claims=None):
    now_dt = now_dt or datetime.now(timezone.utc)
    field = b.read_record(path)
    a = ctx['contract']['actions'][0]
    require(field, {'kind': 'mf1750-pal1-field-v1',
        'contract_id': ctx['contract']['contract_id'], 'ordinal': 1,
        'action_id': a['action_id'], 'descriptor_id': a['descriptor_id'],
        'base_url': base_url, 'authorized_refreshes': 1, 'stop_after_action': True,
        'autochain': False, 'retry': False, 'live_release': True,
        'electrical_state_proven': False,
        'electrical_policy': 'RECORD_ONLY_BY_EXPLICIT_USER_INSTRUCTION'}, 'field')
    b._fresh(field['recorded_at'], now_dt)
    boot = field.get('boot_nonce')
    if (not isinstance(boot, str) or not b.NONCE.fullmatch(boot)
            or boot in (OLD_FAULT['expected_boot'], REBOUND['expected_boot'],
                        LH2_MAP_TERMINAL['expected_boot'],
                        LH3_DOSE_V2_TERMINAL['expected_boot'], '0' * 16)):
        raise Error('fresh campaign boot required')
    if not isinstance(field.get('run_id'), str) or not RUN_ID.fullmatch(field['run_id']):
        raise Error('field run id missing')
    if field.get('dependencies') != dependencies():
        raise Error('runner dependencies changed')
    native = bound_record(_binding(field, 'native_audit'))
    require(native, {'kind': 'mf1750-pal1-native-audit-v1', 'result': 'PASS',
        'hardware_accessed': False, 'network_accessed': False, 'visible_refreshes': 0,
        'live_ready': False, 'live_authorization_granted': False,
        'failed_scenarios': [], 'defects': []}, 'native audit')
    if native.get('synthetic_white_anchor_sha256') not in (None, ctx['anchor']):
        raise Error('native audit white anchor differs')
    ip = bound_record(_binding(field, 'ip_binding'))
    require(ip, {'binding_passed': True, 'fresh_binding_passed': True,
        'expected_mac': 'A4-CB-8F-D9-FC-D4'}, 'exact network binding')
    b._fresh(ip['finished_at'], now_dt)
    if b.origin(field['base_url']) != 'http://' + ip['candidate_ipv4']:
        raise Error('field IPv4 differs')
    camera = bound_record(_binding(field, 'camera_review'))
    require(camera, {'camera_usb_id': 'VID_32E4:PID_4801', 'full_panel_visible': True,
        'usable_for_state_review': True}, 'current camera review')
    b._fresh(camera['recorded_at'], now_dt)
    b.read_bound(camera['photo'])
    relay = bound_record(_binding(field, 'relay_on'))
    require(relay, {'commanded_state': 'ON', 'channel': 1}, 'relay ON')
    b._fresh(relay['recorded_at'], now_dt)
    flash = bound_record(_binding(field, 'app_flash'))
    require(flash, {'result': 'PASS', 'firmware': ctx['firmware'], 'elf': ctx['elf'],
        'app_only': True, 'nvs_erased': False}, 'post-flash evidence')
    b.read_bound(flash['raw_log'])
    release = bound_record(_binding(field, 'user_release'))
    require(release, {'kind': 'mf1750-pal1-release-v1',
        'contract_id': ctx['contract']['contract_id'], 'ordinal': 1,
        'action_id': a['action_id'], 'authorized_refreshes': 1, 'stop_after_action': True,
        'live_release': True, 'scope': RELEASE_SCOPE}, 'user release')
    if not release.get('authorization_messages'):
        raise Error('release must record user authority')
    return field


def run(ordinal, field_path, output, base_url, *, transport=None, sleeper=time.sleep, claims=None, package=PACKAGE):
    if type(ordinal) is not int or ordinal != 1:
        raise Error('only ordinal 1 exists; PAL1 is a single-action chain')
    # All local gates precede network; no ordinal/boot override exists.
    ctx = validate_package(package)
    base_url = b.origin(base_url)
    field = validate_field(ctx, field_path, base_url, claims=claims)
    claim = claim_path(ctx, claims)
    if claim.exists():
        raise Error('ordinal 1 permanently claimed; no retry')
    session = http.Session(ctx, {}, Path(output), base_url, transport or http._http, sleeper)
    claimed = False
    try:
        pre = {k: session.request('GET', k, 200) for k in ('version', 'manifest', 'status', 'report')}
        validate_preflight(ctx, pre, field)
        # Prevent stale/changed evidence during preflight from authorizing a POST.
        validate_field(ctx, field_path, base_url, claims=claims)
        claim.parent.mkdir(parents=True, exist_ok=True)
        b.write_new(claim, b.seal({'kind': 'mf1750-pal1-claim-v1',
            'recorded_at': now(), 'contract_id': ctx['contract']['contract_id'],
            'ordinal': 1, 'boot_nonce': field['boot_nonce'], 'run_id': field['run_id'],
            'action_id': ctx['contract']['actions'][0]['action_id'],
            'field': b.file_binding(field_path), 'output': str(Path(output).resolve()),
            'permanent': True, 'claim_created_before_arm': True}))
        claimed = True
        a = ctx['contract']['actions'][0]
        headers = {'X-EC5-Build-Tag': ctx['identity']['build_tag'],
            'X-EC5-Test-Id': ctx['identity']['test_id'],
            'X-EC5-Campaign-Id': ctx['identity']['campaign_id'],
            'X-EC5-Action-Id': a['action_id'], 'X-EC5-Ordinal': '1',
            'X-EC5-Descriptor-Id': a['descriptor_id'], 'X-EC5-Boot-Nonce': field['boot_nonce'],
            'X-EC5-Intent': ctx['arm_intent'], 'X-LH-Run-Id': field['run_id'],
            'X-LH-Source-Review': ctx['anchor'], 'X-LH-Prior-Review': ctx['anchor']}
        arm = session.request('POST', 'arm', 201, headers)
        identity(ctx, arm, field, ctx['anchor'], latched=True)
        require(arm, {**expected_action(ctx), 'accepted': True,
            'armed': True, 'phase': 1, 'phase_name': 'ARMED',
            'not_hardware_authorization': True}, 'ARM')
        nonce = arm.get('arm_nonce')
        if not isinstance(nonce, str) or not b.NONCE.fullmatch(nonce):
            raise Error('invalid ARM nonce')
        execute = session.request('POST', 'execute', 202,
            {**headers, 'X-EC5-Intent': ctx['execute_intent'], 'X-EC5-Arm-Nonce': nonce})
        identity(ctx, execute, field, ctx['anchor'], latched=True)
        require(execute, {**expected_action(ctx), 'accepted': True,
            'execute_consumed': True, 'phase': 2, 'phase_name': 'CONSUMED',
            'job_id': 1, 'no_retry': True, 'no_recovery': True}, 'EXECUTE')
        # Split host wait permits short tool yields; no requests during synchronous driver.
        for seconds in (30, 30, INITIAL_WAIT - 60):
            sleeper(seconds)
        terminal = None
        for _ in range(MAX_POLLS):
            status = session.request('GET', 'status', 200)
            identity(ctx, status, field, ctx['anchor'], latched=True)
            if status.get('phase') == 3:
                raise Error('FAULT latched; stop immediately, never resend')
            if status.get('phase') == 0 and status.get('cursor_raw') == 2:
                terminal = session.request('GET', 'report', 200)
                validate_terminal(ctx, status, terminal, field, ctx['anchor'])
                break
            require(status, {'phase': 2, 'cursor_raw': 513,
                'next_ordinal': 1}, 'in-flight')
            sleeper(2)
        if terminal is None:
            raise Error('terminal polling budget exhausted; do not resend')
        result = b.seal({'kind': 'mf1750-pal1-result-v1', 'recorded_at': now(),
            'protocol_verdict': 'PASS', 'optical_verdict': 'HOLD_FOR_POST_ACTION_REVIEW',
            'qualified_count': 0, 'contract_id': ctx['contract']['contract_id'],
            'ordinal': 1, 'run_id': field['run_id'], 'boot_nonce': field['boot_nonce'],
            'stage_review_sha256': b.digest(b.canonical(terminal)),
            'field': b.file_binding(field_path), 'claim': b.file_binding(claim),
            'network': session.counts, 'arm': 1, 'execute': 1, 'driver': 1,
            'visible_refresh': 1, 'status': status, 'report': terminal,
            'campaign_complete': True,
            'further_contract_action_available': False, 'stop_required': True})
        b.write_new(session.output / 'result.json', result)
        return result
    except Exception as exc:
        b.write_new(session.output / 'STOP.json', b.seal({'kind': 'mf1750-pal1-stop-v1',
            'recorded_at': now(), 'verdict': 'FAIL_STOP', 'error': str(exc),
            'ordinal': 1, 'network': session.counts, 'claim_created': claimed,
            'no_retry': True, 'no_recovery': True, 'no_autochain': True}))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('validate', 'run'))
    p.add_argument('--package', type=Path, default=PACKAGE)
    p.add_argument('--ordinal', type=int, choices=(1,))
    p.add_argument('--field', type=Path)
    p.add_argument('--base-url')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    ctx = validate_package(a.package)
    if a.command == 'validate':
        if a.field is not None:
            if not a.base_url:
                p.error('--base-url required with --field')
            validate_field(ctx, a.field, b.origin(a.base_url))
            print('PASS_OFFLINE_FIELD_VALIDATION')
        else:
            print(ctx['contract']['contract_id'])
    else:
        if a.field is None or not a.base_url or a.output is None:
            p.error('run requires --field --base-url --output')
        print(b.canonical(run(1, a.field, a.output, a.base_url)).decode())


if __name__ == '__main__':
    main()
