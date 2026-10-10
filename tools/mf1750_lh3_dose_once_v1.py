"""LH3 dose-axis three-stage host runner V2; one ordinal per invocation.

SOURCE (ordinal 1, active C7) -> DOSE1 (ordinal 2, commented, column c carries
code c) -> DOSE2 (ordinal 3, commented, frame byte-identical to DOSE1,
terminal campaign_complete).  Each stage is released and executed
independently: exactly 1 ARM / 1 EXECUTE / 1 driver call / 1 visible refresh,
no autochain, no retry, no fourth action.  A permanent per-ordinal claim is
written before the only ARM; an existing claim refuses the run before any
network I/O.  phase==3 (FAULT) stops the host at once and nothing is ever
resent.

V2 (2026-09-24): the V1 campaign (lh3dose_v1) was bricked before its first ARM
by an esptool read_mac RTS hard reset (campaign boot binding is written at
first boot; the reboot latched campaign_boot_binding_mismatch_at_boot with
cursor_raw=769, zero driver calls). V2 runs the campaign on namespace
lh3dose_v2; the bricked V1 namespace is pinned at exactly cursor 769 as
untouchable historical evidence. WARNING: after flashing, the first boot
writes the campaign boot binding — no MCU reset of any kind (esptool/serial
RTS/pyserial port open) is allowed until the three-stage chain completes.

The X-LH review chain binds one field chain: X-LH-Run-Id is the field run id
shared by all three stages, X-LH-Source-Review is always the contract
lh3_white_source_anchor sha256, X-LH-Prior-Review is the anchor for ordinal 1
and the canonical sha256 of the previous stage terminal report for ordinals
2/3 (required distinct from the anchor and from the digest that stage echoed).

Device gate (compiled into the firmware and asserted here from the sealed
contract): the LH3 source-white allowance must already be consumed
(lh3srcw_v1/used_lh3sw1==2), the LH2 drive-map campaign must be at its exact
terminal (lh2map_v1 cur_lh2m=4, boot ac92bb9e25c374ef, campaign complete), the
lhist_v1 / lh1reb_v2 / lh2srcw_v1 namespaces must remain untouched, and the
bricked lh3dose_v1 namespace must still read exactly cursor 769.

Import and validate perform no device access.  Field/release collection tools
are separate; this runner only verifies their sealed records.  All identity
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
PACKAGE = ROOT / '.test-output/offline/LH3_DOSE_20260924_R2'
CLAIMS = ROOT / '.test-output/hardware/.mf1750_lh3_dose_v2_action_claims'
PREFIX = 'ec5_lightness_lh3_dose_v2'
NVS = {'namespace': 'lh3dose_v2', 'cursor': 'cur_lh3d2', 'boot': 'boot_lh3d2'}
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
RELEASE_SCOPE = 'ONE_INDEPENDENT_LH3_DOSE_ACTION'
SOURCE_STATE = 'LH3_WHITE_COMPLETE_PLUS_CURRENT_HOST_CLEAN_WHITE_REVIEW_REQUIRED'
INITIAL_WAIT = 65
MAX_POLLS = 30
RUN_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
require = b._require
Error = b.RunnerError


def now():
    return datetime.now(timezone.utc).isoformat()


def dependencies():
    return [b.file_binding(Path(m.__file__)) for m in (http, b)] + [b.file_binding(Path(__file__))]


def claim_path(ctx, ordinal, claims=None):
    return Path(claims if claims is not None else CLAIMS) / (ctx['contract']['contract_id'] + '-ordinal%d.json' % ordinal)


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
        raise Error('LH3 dose contract identity mismatch')
    require(contract, {'kind': 'mf1750-lightness-history-firmware-contract-v1',
        'algorithm_id': 'MF1750_LIGHTNESS_HISTORY_LH3_DOSE_V1_20260921',
        'build_tag': 'MF1750_EC5_LIGHTNESS_HISTORY_LH3_DOSE_V2_2026-09-24',
        'campaign_id': 'EC5_LIGHTNESS_HISTORY_LH3_DOSE_V2_20260924',
        'base_route': '/api/ec5/lightness-history-v1',
        'nvs': NVS, 'action_count': 3, 'startup_refresh': False, 'autochain': False,
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
        'lh3_dose_v1_bricked_preservation': V1_BRICKED}, 'LH3 dose contract')
    require(contract['dose_axis'], {'cells_per_side': 64, 'dose_codes': list(range(8)),
        'columns_per_side': 8, 'rows_per_code_per_side': 8,
        'dose2_frame_byte_identical_to_dose1': True,
        'commented_profile_for_dose1_and_dose2': True,
        'frame_rule': 'code=column index 0..7; rows are spatial repeats'}, 'dose axis')
    require(build, {'result': 'PASS', 'contract_id': contract['contract_id'],
        'hardware_accessed': False, 'firmware_flashed': False, 'compiled_actions': 3,
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
    names = ['contract.json', 'platformio.ini', 'source.frame4bpp', 'dose1.frame4bpp', 'dose2.frame4bpp',
             'generated/frozen_epd_driver.cpp.inc', 'generated/lh_frame_fill.hpp']
    names += ['generated/' + PREFIX + suffix for suffix in
              ('_main.cpp', '_main_config.inc', '_identity.inc', '_driver.inc')]
    for name in names:
        if package / name not in outputs:
            raise Error('unsealed output: ' + name)
    if b._regular(package / 'dose2.frame4bpp') != b._regular(package / 'dose1.frame4bpp'):
        raise Error('DOSE2 packaged frame differs from DOSE1')
    cfg = b._regular(package / ('generated/' + PREFIX + '_main_config.inc')).decode('utf8')
    identity = {key: b._string(cfg, symbol) for key, symbol in (
        ('build_tag', 'kBuildTag'), ('test_id', 'kTestId'),
        ('campaign_id', 'kCampaignId'), ('contract_id', 'kContractId'),
        ('device_api_version', 'kDeviceApiVersion'), ('identity_revision', 'kIdentityRevision'),
        ('compiled_identity_marker', 'kCompiledIdentityMarker'), ('classification', 'kClassification'))}
    require(identity, {'contract_id': contract['contract_id'], 'build_tag': contract['build_tag'],
        'campaign_id': contract['campaign_id'], 'test_id': contract['algorithm_id'],
        'identity_revision': 'lightness-lh3-dose-v2',
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
    for i, action in enumerate(contract['actions'], 1):
        require(action, {'ordinal': i, 'visible_refresh_count': 1,
            'waveform_internal_phase': 'OPAQUE',
            'stage': {1: 'SOURCE', 2: 'DOSE1', 3: 'DOSE2'}[i],
            'role': {1: 'LH3_SOURCE', 2: 'LH3_DOSE1', 3: 'LH3_DOSE2'}[i],
            'driver_role': {1: 'Source', 2: 'Mid', 3: 'Target'}[i],
            'branch': {1: 'LH3_SYMMETRIC_SOURCE', 2: 'LH3_SYMMETRIC_DOSE1', 3: 'LH3_SYMMETRIC_DOSE2'}[i],
            'global_header': 'active' if i == 1 else 'commented'}, 'action')
        if action['profile'].get('controller_payloads_byte_identical') is not True:
            raise Error('controller tuple symmetry differs')
        if action['prior_action_id'] != (None if i == 1 else contract['actions'][i - 2]['action_id']):
            raise Error('prior action chain differs')
        for key in ('action_id', 'descriptor_id'):
            if not b.HEX.fullmatch(action[key]) or action[key] not in cfg:
                raise Error('compiled action identity differs')
        frame = package / (action['stage'].lower() + '.frame4bpp')
        if b.digest(b._regular(frame)) != action['frame']['sha256']:
            raise Error('frame differs')
        want_histogram = [0, 0, 0, 0, 0, 0, 0, 614400] if i == 1 else [33280] * 7 + [381440]
        if action['frame']['histogram'] != want_histogram:
            raise Error('frame histogram differs')
    dose1, dose2 = contract['actions'][1], contract['actions'][2]
    if dose1['frame'] != dose2['frame'] or dose1['cs1_dtm'] != dose2['cs1_dtm'] or dose1['cs2_dtm'] != dose2['cs2_dtm']:
        raise Error('DOSE2 contract frame/DTM identity differs from DOSE1')
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
    if driver.count('if (role == EpdChromaGridRole::Mid || role == EpdChromaGridRole::Target) useCommentedGlobal = true;') != 1:
        raise Error('commented Mid||Target profile branch missing')
    if 'ph::kTargetCodes[0] != 0 || ph::kTargetCodes[7] != 7' not in driver:
        raise Error('layout gate target-code endpoints differ')
    if 'kTargetCodes[8]={0,1,2,3,4,5,6,7}' not in ident:
        raise Error('dose code enumeration differs')
    dispatch = [line for line in main.split('\n') if 'if(action.ordinal==3) return String(' in line]
    if len(dispatch) != 1 or '\\"controller_tuple_dispatch\\":\\"CC\\"' not in dispatch[0]:
        raise Error('ordinal-3 transport dispatch must be CC')
    for token in ('oldFaultPreserved', 'reboundV2TerminalPreserved',
                  'lh2DriveMapTerminalComplete', 'lh2WhitePreserved',
                  'lh3DoseV1BrickedPreserved',
                  'old.getUShort("cur_lh1",0)==770', 'old.getULong64("boot_lh1",0)==0x30a9e5989873f4e0ULL',
                  'source.getUShort("cur_lh1r",0)==4', 'source.getULong64("boot_lh1r",0)==0x7274e005c8833ca1ULL',
                  'source.getUShort("cur_lh2m",0)==4', 'source.getULong64("boot_lh2m",0)==0xac92bb9e25c374efULL',
                  'white.getUShort("used_lh2sw1",0)==2',
                  'white.begin("lh3srcw_v1", true)', 'white.getUShort("used_lh3sw1",0)==2',
                  'old.getUShort("cur_lh3d",0)==769',
                  'if (!oldFaultPreserved() || !reboundV2TerminalPreserved() || !lh2DriveMapTerminalComplete() || !lh2WhitePreserved() || !lh3DoseV1BrickedPreserved()) return false;'):
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


def expected_action(ctx, index):
    a = ctx['contract']['actions'][index]
    return {'ordinal': a['ordinal'], 'descriptor_id': a['descriptor_id'], 'action_id': a['action_id'],
        'role': a['role'], 'round': 1, 'branch': a['branch'],
        'controller_tuple_dispatch': 'AA' if index == 0 else 'CC',
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


def nvs_gate(value):
    require(value['nvs_contract'], {'namespace': NVS['namespace'], 'key': NVS['cursor'],
        'campaign_boot_key': NVS['boot'], 'current_boot_exact_match_required': True,
        'reboot_resume_allowed': False, 'post_containment_resume_allowed': False,
        'initial_next_ordinal': 1, 'terminal_next_ordinal': 4}, 'NVS')


def driver_gate(ctx, driver, ordinal):
    """Strict terminal gate; the desktop stub's 255-sentinel trace never passes.

    Real BUSY levels/timings are required here; the strict-native audit proves
    the frame/DTM FNV-1a binding offline with a synthetic stub, which is not
    admissible as a live terminal trace.
    """
    a = ctx['contract']['actions'][ordinal - 1]
    require(driver, {'driver_evidence_schema_version': 2, 'valid': True, 'running': False,
        'sequence_ok': True, 'wait_timeout': False, 'busy_assertion_missing': False,
        'pre_command_idle_failure': False, 'mapping_applied': True,
        'pon_busy_seen': True, 'drf_busy_seen': True, 'pof_busy_seen': True,
        'input_fnv1a': a['frame']['fnv1a'], 'cs1_dtm_fnv1a': a['cs1_dtm']['fnv1a'],
        'cs2_dtm_fnv1a': a['cs2_dtm']['fnv1a'], 'failure_code': 0,
        'operation_id': ordinal, 'spi_hz': 1000000}, 'driver')
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


def validate_terminal(ctx, status, report, field, ordinal, prior):
    identity(ctx, status, field, prior, latched=True)
    identity(ctx, report, field, prior, latched=True)
    require(report, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-report'}, 'report')
    require(status, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-status'}, 'status')
    require(report, expected_action(ctx, ordinal - 1), 'terminal action')
    require(report, {'valid': True, 'terminal_state': 'COMPLETE', 'result': True,
        'driver_called': True, 'driver_call_count_for_action': 1,
        'total_driver_call_count': ordinal, 'job_id': ordinal, 'phase': 0, 'phase_name': 'READY',
        'next_ordinal': ordinal + 1, 'campaign_complete': ordinal == 3,
        'no_retry': True, 'no_recovery': True}, 'terminal')
    require(status, {'state': 'complete' if ordinal == 3 else 'ready', 'phase': 0,
        'phase_name': 'READY', 'cursor_raw': ordinal + 1, 'next_ordinal': ordinal + 1,
        'arm_request_count': ordinal, 'execute_request_count': ordinal,
        'total_driver_call_count': ordinal, 'execute_pending': False, 'current_action': None,
        'cursor_valid': True, 'persistent_key_present': True, 'campaign_boot_key_present': True,
        'campaign_boot_matches_current': True, 'campaign_complete': ordinal == 3,
        'persisted_campaign_boot_nonce': field['boot_nonce'],
        'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}, 'terminal status')
    nvs_gate(status)
    driver_gate(ctx, report['driver'], ordinal)
    times = [report.get(k) for k in ('job_queued_at_ms', 'job_started_at_ms', 'job_finished_at_ms')]
    if any(type(t) is not int or t < 0 for t in times) or times != sorted(times):
        raise Error('job chronology differs')


def validate_preflight(ctx, values, field, ordinal, prior_echo, prior_report=None):
    for name, value in values.items():
        identity(ctx, value, field, prior_echo, latched=ordinal > 1)
        require(value, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-' + name}, name)
    for name in ('version', 'manifest'):
        require(values[name], {'action_count': 3, 'automatic_chaining': False,
            'startup_refresh': False, 'retry': False, 'recovery': False,
            'raw_frame_ingress': False, 'caller_electrical_parameter_write': False,
            'fixed_profile_parameter_write': True, 'runtime_lut_write': True,
            'device_enforced_same_boot': True, 'dither': False, 'spatial_mixing': False,
            'full_screen_global_refresh': True, 'partial_refresh': False,
            'layout_id': 'LH3_DOSE_COLUMNS_8X8', 'lightness_qualification': False,
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
    if not isinstance(actions, list) or len(actions) != 3:
        raise Error('device action list differs')
    for index, action in enumerate(actions):
        want = ctx['contract']['actions'][index]
        require(action, expected_action(ctx, index), 'compiled action')
        require(action, {'frame_sha256': want['frame']['sha256'],
            'cs1_dtm_sha256': want['cs1_dtm']['sha256'], 'cs2_dtm_sha256': want['cs2_dtm']['sha256'],
            'transport_code_histogram': want['frame']['histogram'],
            'prior_static_action_id': want['prior_action_id']}, 'compiled frame')
    if values['manifest']['actions'][2]['frame_sha256'] != values['manifest']['actions'][1]['frame_sha256']:
        raise Error('device DOSE2 frame must equal DOSE1 frame')
    if ordinal == 1:
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
    else:
        if prior_report is None or values['report'] != prior_report:
            raise Error('retained prior terminal report differs')
        validate_terminal(ctx, values['status'], values['report'], field, ordinal - 1, prior_echo)


def validate_field(ctx, path, ordinal, base_url, now_dt=None, claims=None):
    now_dt = now_dt or datetime.now(timezone.utc)
    field = b.read_record(path)
    a = ctx['contract']['actions'][ordinal - 1]
    require(field, {'kind': 'mf1750-lh3-dose-field-v1',
        'contract_id': ctx['contract']['contract_id'], 'ordinal': ordinal,
        'action_id': a['action_id'], 'descriptor_id': a['descriptor_id'],
        'base_url': base_url, 'authorized_refreshes': 1, 'stop_after_action': True,
        'autochain': False, 'retry': False, 'live_release': True,
        'electrical_state_proven': False,
        'electrical_policy': 'RECORD_ONLY_BY_EXPLICIT_USER_INSTRUCTION'}, 'field')
    b._fresh(field['recorded_at'], now_dt)
    boot = field.get('boot_nonce')
    if (not isinstance(boot, str) or not b.NONCE.fullmatch(boot)
            or boot in (OLD_FAULT['expected_boot'], REBOUND['expected_boot'],
                        LH2_MAP_TERMINAL['expected_boot'], '0' * 16)):
        raise Error('fresh campaign boot required')
    if not isinstance(field.get('run_id'), str) or not RUN_ID.fullmatch(field['run_id']):
        raise Error('field run id missing')
    if field.get('dependencies') != dependencies():
        raise Error('runner dependencies changed')
    native = bound_record(_binding(field, 'native_audit'))
    require(native, {'kind': 'mf1750-lh3-dose-native-audit-v1', 'result': 'PASS',
        'hardware_accessed': False, 'network_accessed': False, 'visible_refreshes': 0,
        'live_ready': False, 'live_authorization_granted': False,
        'dose2_frame_byte_identical_to_dose1': True,
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
    require(release, {'kind': 'mf1750-lh3-dose-release-v1',
        'contract_id': ctx['contract']['contract_id'], 'ordinal': ordinal,
        'action_id': a['action_id'], 'authorized_refreshes': 1, 'stop_after_action': True,
        'live_release': True, 'scope': RELEASE_SCOPE}, 'user release')
    if not release.get('authorization_messages'):
        raise Error('release must record user authority')
    if ordinal == 1:
        return field, ctx['anchor'], None, None
    prior = bound_record(_binding(field, 'prior_stage_result'))
    require(prior, {'kind': 'mf1750-lh3-dose-result-v1', 'ordinal': ordinal - 1,
        'contract_id': ctx['contract']['contract_id'], 'protocol_verdict': 'PASS',
        'boot_nonce': boot, 'run_id': field['run_id'], 'arm': 1, 'execute': 1,
        'driver': 1, 'visible_refresh': 1}, 'prior stage result')
    echo = prior['report'].get('prior_review_sha256')
    if ordinal == 2:
        if echo != ctx['anchor']:
            raise Error('SOURCE stage did not echo the white anchor')
    elif not isinstance(echo, str) or not b.HEX.fullmatch(echo) or echo == ctx['anchor']:
        raise Error('DOSE1 stage review digest invalid')
    validate_terminal(ctx, prior['status'], prior['report'], field, ordinal - 1, echo)
    digest = b.digest(b.canonical(prior['report']))
    if digest == ctx['anchor'] or digest == echo:
        raise Error('stage review digests must be distinct')
    on_disk = claim_path(ctx, ordinal - 1, claims)
    if not on_disk.exists():
        raise Error('prior stage permanent claim missing')
    require(b.file_binding(on_disk), {'sha256': prior['claim']['sha256'],
        'bytes': prior['claim']['bytes']}, 'on-disk prior claim')
    return field, digest, echo, prior['report']


def run(ordinal, field_path, output, base_url, *, transport=None, sleeper=time.sleep, claims=None, package=PACKAGE):
    if type(ordinal) is not int or ordinal not in (1, 2, 3):
        raise Error('only ordinals 1/2/3 exist; there is no fourth action')
    # All local gates precede network; no ordinal/boot override exists.
    ctx = validate_package(package)
    base_url = b.origin(base_url)
    field, prior_send, prior_echo, prior_report = validate_field(ctx, field_path, ordinal, base_url, claims=claims)
    claim = claim_path(ctx, ordinal, claims)
    if claim.exists():
        raise Error('ordinal %d permanently claimed; no retry' % ordinal)
    session = http.Session(ctx, {}, Path(output), base_url, transport or http._http, sleeper)
    claimed = False
    try:
        pre = {k: session.request('GET', k, 200) for k in ('version', 'manifest', 'status', 'report')}
        validate_preflight(ctx, pre, field, ordinal, prior_echo or '', prior_report)
        # Prevent stale/changed evidence during preflight from authorizing a POST.
        validate_field(ctx, field_path, ordinal, base_url, claims=claims)
        claim.parent.mkdir(parents=True, exist_ok=True)
        b.write_new(claim, b.seal({'kind': 'mf1750-lh3-dose-claim-v1',
            'recorded_at': now(), 'contract_id': ctx['contract']['contract_id'],
            'ordinal': ordinal, 'boot_nonce': field['boot_nonce'], 'run_id': field['run_id'],
            'action_id': ctx['contract']['actions'][ordinal - 1]['action_id'],
            'field': b.file_binding(field_path), 'output': str(Path(output).resolve()),
            'permanent': True, 'claim_created_before_arm': True}))
        claimed = True
        a = ctx['contract']['actions'][ordinal - 1]
        headers = {'X-EC5-Build-Tag': ctx['identity']['build_tag'],
            'X-EC5-Test-Id': ctx['identity']['test_id'],
            'X-EC5-Campaign-Id': ctx['identity']['campaign_id'],
            'X-EC5-Action-Id': a['action_id'], 'X-EC5-Ordinal': str(ordinal),
            'X-EC5-Descriptor-Id': a['descriptor_id'], 'X-EC5-Boot-Nonce': field['boot_nonce'],
            'X-EC5-Intent': ctx['arm_intent'], 'X-LH-Run-Id': field['run_id'],
            'X-LH-Source-Review': ctx['anchor'], 'X-LH-Prior-Review': prior_send}
        arm = session.request('POST', 'arm', 201, headers)
        identity(ctx, arm, field, prior_send, latched=True)
        require(arm, {**expected_action(ctx, ordinal - 1), 'accepted': True,
            'armed': True, 'phase': 1, 'phase_name': 'ARMED',
            'not_hardware_authorization': True}, 'ARM')
        nonce = arm.get('arm_nonce')
        if not isinstance(nonce, str) or not b.NONCE.fullmatch(nonce):
            raise Error('invalid ARM nonce')
        execute = session.request('POST', 'execute', 202,
            {**headers, 'X-EC5-Intent': ctx['execute_intent'], 'X-EC5-Arm-Nonce': nonce})
        identity(ctx, execute, field, prior_send, latched=True)
        require(execute, {**expected_action(ctx, ordinal - 1), 'accepted': True,
            'execute_consumed': True, 'phase': 2, 'phase_name': 'CONSUMED',
            'job_id': ordinal, 'no_retry': True, 'no_recovery': True}, 'EXECUTE')
        # Split host wait permits short tool yields; no requests during synchronous driver.
        for seconds in (30, 30, INITIAL_WAIT - 60):
            sleeper(seconds)
        terminal = None
        for _ in range(MAX_POLLS):
            status = session.request('GET', 'status', 200)
            identity(ctx, status, field, prior_send, latched=True)
            if status.get('phase') == 3:
                raise Error('FAULT latched; stop immediately, never resend')
            if status.get('phase') == 0 and status.get('cursor_raw') == ordinal + 1:
                terminal = session.request('GET', 'report', 200)
                validate_terminal(ctx, status, terminal, field, ordinal, prior_send)
                break
            require(status, {'phase': 2, 'cursor_raw': 512 + ordinal,
                'next_ordinal': ordinal}, 'in-flight')
            sleeper(2)
        if terminal is None:
            raise Error('terminal polling budget exhausted; do not resend')
        result = b.seal({'kind': 'mf1750-lh3-dose-result-v1', 'recorded_at': now(),
            'protocol_verdict': 'PASS', 'optical_verdict': 'HOLD_FOR_POST_ACTION_REVIEW',
            'qualified_count': 0, 'contract_id': ctx['contract']['contract_id'],
            'ordinal': ordinal, 'run_id': field['run_id'], 'boot_nonce': field['boot_nonce'],
            'stage_review_sha256': b.digest(b.canonical(terminal)),
            'field': b.file_binding(field_path), 'claim': b.file_binding(claim),
            'network': session.counts, 'arm': 1, 'execute': 1, 'driver': 1,
            'visible_refresh': 1, 'status': status, 'report': terminal,
            'campaign_complete': ordinal == 3,
            'further_contract_action_available': ordinal < 3, 'stop_required': True})
        b.write_new(session.output / 'result.json', result)
        return result
    except Exception as exc:
        b.write_new(session.output / 'STOP.json', b.seal({'kind': 'mf1750-lh3-dose-stop-v1',
            'recorded_at': now(), 'verdict': 'FAIL_STOP', 'error': str(exc),
            'ordinal': ordinal, 'network': session.counts, 'claim_created': claimed,
            'no_retry': True, 'no_recovery': True, 'no_autochain': True}))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('validate', 'run'))
    p.add_argument('--package', type=Path, default=PACKAGE)
    p.add_argument('--ordinal', type=int, choices=(1, 2, 3))
    p.add_argument('--field', type=Path)
    p.add_argument('--base-url')
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    ctx = validate_package(a.package)
    if a.command == 'validate':
        if a.field is not None:
            if a.ordinal is None or not a.base_url:
                p.error('--ordinal and --base-url required with --field')
            validate_field(ctx, a.field, a.ordinal, b.origin(a.base_url))
            print('PASS_OFFLINE_FIELD_VALIDATION')
        else:
            print(ctx['contract']['contract_id'])
    else:
        if a.ordinal is None or a.field is None or not a.base_url or a.output is None:
            p.error('run requires --ordinal --field --base-url --output')
        print(b.canonical(run(a.ordinal, a.field, a.output, a.base_url)).decode())


if __name__ == '__main__':
    main()
