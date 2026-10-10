"""Offline V2 package and SOURCE reconciliation; never opens a device.

Retrospective validation does not erase the original runner's transport failure
or manufacture a claim which was absent when the action executed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from tools import mf1750_lh1_lh4_once as records
from tools import mf1750_lh1_lh4_once_operator_v2 as terminal_gate

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / '.test-output/offline/LH1_REBOUND_20260916_V2_R1'
HISTORY = ROOT / '.test-output/hardware/LH1_REBOUND_20260916_V2'
CONTRACT = '021c35abd47f6caa52b11cec98b73a79f11c585bdbc1ed976c2dde868bc5259e'
BIN = '9fba6008358e5be1c766edf18fc362caae3bb33554550b2a03147d2d9efe7614'
ELF = '0ce109accf39ccb27035a2a5dd7db0a07c579f3c522b4266c0b9b548ffb88898'
BOOT = '7274e005c8833ca1'
RUN = 'LH1_REBOUND_V2_SOURCE_20260916'
ANCHOR = '3bbf1bfffe29bf51eca3f1d876161c4fdd37ec792b9175b250549aa88ed72f84'
NVS = {'namespace': 'lh1reb_v2', 'cursor': 'cur_lh1r', 'boot': 'boot_lh1r'}
PREFIX = 'ec5_lightness_lh1_rebound_v2'
Error = records.RunnerError


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path):
    return records.parse_json(records._regular(Path(path)))


def validate_package(package=PACKAGE):
    package = Path(package).resolve()
    manifest = records.read_record(package / 'manifest.json')
    build = records.read_record(package / 'build-report.json')
    contract = load(package / 'contract.json')
    body = deepcopy(contract)
    stated = body.pop('contract_id', None)
    if stated != CONTRACT or records.digest(records.canonical(body)) != stated:
        raise Error('V2 contract identity mismatch')
    records._require(contract, {'nvs': NVS, 'action_count': 3,
        'startup_refresh': False, 'autochain': False, 'retry': False,
        'white_or_repeat_action': False}, 'contract')
    records._require(build, {'result': 'PASS', 'contract_id': CONTRACT,
        'hardware_accessed': False, 'firmware_flashed': False,
        'compiled_actions': 3}, 'build')
    records._require(manifest, {'contract_id': CONTRACT}, 'manifest')
    if Path(build['manifest']['path']).resolve() != package / 'manifest.json':
        raise Error('build binds another manifest')
    for binding in manifest['inputs'] + manifest['outputs'] + build['artifacts'] + [build['log'], build['manifest']]:
        records.read_bound(binding)
    for relative, sha in contract['implementation_sha256'].items():
        if records.digest(records._regular(ROOT / relative)) != sha:
            raise Error('implementation changed: ' + relative)
    outputs = {Path(x['path']).resolve() for x in manifest['outputs']}
    names = ['contract.json', 'platformio.ini', 'source.frame4bpp',
             'middle.frame4bpp', 'target.frame4bpp']
    names += ['generated/' + PREFIX + suffix for suffix in
              ('_main.cpp', '_main_config.inc', '_identity.inc', '_driver.inc')]
    names += ['generated/frozen_epd_driver.cpp.inc']
    for name in names:
        if package / name not in outputs:
            raise Error('unsealed output: ' + name)
    cfg = records._regular(package / ('generated/' + PREFIX + '_main_config.inc')).decode('utf8')
    identity = {key: records._string(cfg, symbol) for key, symbol in (
        ('build_tag', 'kBuildTag'), ('test_id', 'kTestId'),
        ('campaign_id', 'kCampaignId'), ('contract_id', 'kContractId'),
        ('device_api_version', 'kDeviceApiVersion'), ('identity_revision', 'kIdentityRevision'),
        ('compiled_identity_marker', 'kCompiledIdentityMarker'), ('classification', 'kClassification'))}
    records._require(identity, {'contract_id': CONTRACT,
        'build_tag': contract['build_tag'], 'campaign_id': contract['campaign_id'],
        'test_id': contract['algorithm_id']}, 'compiled identity')
    artifacts = {Path(x['path']).suffix: x for x in build['artifacts']}
    if set(artifacts) != {'.bin', '.elf'}:
        raise Error('BIN/ELF set differs')
    for ext, wanted in (('.bin', BIN), ('.elf', ELF)):
        item = artifacts[ext]
        if item['sha256'] != wanted or not Path(item['path']).resolve().is_relative_to(package / 'build'):
            raise Error('compiled artifact differs')
        if records.read_bound(item).count(identity['compiled_identity_marker'].encode()) != 1:
            raise Error('compiled marker count differs')
    for i, action in enumerate(contract['actions'], 1):
        records._require(action, {'ordinal': i, 'visible_refresh_count': 1,
            'waveform_internal_phase': 'OPAQUE',
            'global_header': 'commented' if i == 2 else 'active'}, 'action')
        if action['prior_action_id'] != (None if i == 1 else contract['actions'][i - 2]['action_id']):
            raise Error('prior action chain differs')
        for key in ('action_id', 'descriptor_id'):
            if action[key] not in cfg:
                raise Error('compiled action identity differs')
        frame = package / (action['stage'].lower() + '.frame4bpp')
        if records.digest(records._regular(frame)) != action['frame']['sha256']:
            raise Error('frame differs')
    if contract['actions'][0]['frame']['histogram'] != [0, 0, 0, 0, 0, 0, 0, 614400]:
        raise Error('SOURCE must be uniform code7')
    for key in ('terminal_evidence', 'clean_white_review', 'close_review'):
        records.read_bound(contract['source_white'][key])
    if contract['source_white']['close_review']['sha256'] != ANCHOR:
        raise Error('white anchor differs')
    return {'package': package, 'contract': contract, 'identity': identity,
            'firmware': artifacts['.bin'], 'elf': artifacts['.elf'],
            'routes': {k: records._string(cfg, 'k' + k.capitalize() + 'Route')
                       for k in ('version', 'manifest', 'status', 'report', 'arm', 'execute')},
            'arm_intent': records._string(cfg, 'kArmIntent'),
            'execute_intent': records._string(cfg, 'kExecuteIntent')}


def validate_source(ctx, status, report):
    evidence = {'boot_nonce': BOOT, 'run_id': RUN, 'source_review_sha256': ANCHOR}
    try:
        terminal_gate.validate_terminal(ctx, report, status, evidence)
    except terminal_gate.RunnerError as exc:
        raise Error(str(exc)) from exc
    records._require(status['nvs_contract'], {'namespace': NVS['namespace'],
        'key': NVS['cursor'], 'campaign_boot_key': NVS['boot'],
        'current_boot_exact_match_required': True, 'reboot_resume_allowed': False}, 'V2 NVS')


def reconcile(output):
    output = Path(output)
    if output.exists():
        raise Error('output already exists')
    ctx = validate_package()
    live = HISTORY / 'LIVE_RUN_R4'
    st_path, rep_path = live / '007-get-status.body.bin', live / '008-get-report.body.bin'
    status, report = load(st_path), load(rep_path)
    validate_source(ctx, status, report)
    flash_path = HISTORY / 'LIVE_FLASH/app-flash.json'
    flash = records.read_record(flash_path)
    records._require(flash, {'outcome': 'app_only_write_verify_single_boot_pass',
                             'j2_confirmed_off': True}, 'flash')
    records._require(flash['binary'], {'observed_sha256': BIN, 'expected_sha256': BIN,
                                     'preflight_verified': True}, 'flash BIN')
    off_path = HISTORY / 'LIVE_RUN_R2/j2-off-result.json'
    off = records.read_record(off_path)
    records._require(off, {'boot_nonce': BOOT, 'result': 'PASS'}, 'postflash OFF')
    records._require(off['responses']['status'], {'boot_nonce': BOOT, 'busy': 0,
        'phase': 0, 'next_ordinal': 1, 'total_driver_call_count': 0}, 'postflash OFF status')
    for name, value in off['responses'].items():
        records._require(value, ctx['identity'], 'OFF ' + name)
    off_time = datetime.fromisoformat(off['recorded_at'])
    if off_time <= datetime.fromisoformat(flash['finished_at']):
        raise Error('OFF diagnostic predates app write')
    mutations = []
    for number, route, http_code, flag in ((5, 'arm', 201, 'armed'), (6, 'execute', 202, 'execute_consumed')):
        stem = live / f'{number:03d}-post-api_ec5_lightness-history-v1_{route}'
        meta = records.read_record(stem.with_suffix('.json'))
        raw = records._regular(stem.with_suffix('.body.bin'))
        if records.digest(raw) != meta['response_sha256']:
            raise Error('mutation response hash differs')
        response = records.parse_json(raw)
        records._require(meta, {'method': 'POST', 'status': http_code}, route + ' metadata')
        records._require(response, {**ctx['identity'], 'boot_nonce': BOOT,
            'accepted': True, flag: True, 'ordinal': 1,
            'action_id': ctx['contract']['actions'][0]['action_id']}, route + ' response')
        mutations.append(records.file_binding(stem.with_suffix('.json')))
    result = records.seal({
        'kind': 'mf1750-lh1-rebound-v2-source-reconciliation-v1', 'recorded_at': now(),
        'contract_id': CONTRACT, 'boot_nonce': BOOT, 'run_id': RUN,
        'source_review_sha256': ANCHOR, 'ordinal': 1,
        'protocol_terminal_verdict': 'PASS', 'original_runner_verdict': 'FAIL_STOP_TRANSPORT',
        'overall_verdict': 'HOLD_FOR_EVIDENCE', 'optical_verdict': 'HOLD_FOR_VALID_FULL_PANEL_CAMERA',
        'qualified_count': 0, 'host_claim_created_before_action': False,
        'device_cursor_consumed': True, 'historical_counts': {
            'flash': 1, 'verify': 1, 'application_start': 1, 'arm': 1, 'execute': 1,
            'driver': 1, 'visible_refresh': 1, 'refresh_count_basis': 'strict device terminal; no full-refresh video',
            'relay_switches': 4, 'relay_queries_standalone': 5, 'relay_queries_inside_commands': 4,
            'get_attempts': 23, 'get_successes': 22, 'get_timeout': 1, 'post': 2,
            'preflight_failures_before_arm': 3, 'mutation_retries': 0},
        'counter_evidence_limitation': 'Initial standalone relay query and timeout have tool transcript evidence but no individual saved raw receipt.',
        'raw_status': records.file_binding(st_path), 'raw_report': records.file_binding(rep_path),
        'terminal_status': status, 'terminal_report': report,
        'app_flash': records.file_binding(flash_path), 'same_boot_postflash_off': records.file_binding(off_path),
        'mutations': mutations, 'firmware': ctx['firmware'], 'elf': ctx['elf'],
        'package_manifest': records.file_binding(PACKAGE / 'manifest.json'),
        'validator': records.file_binding(Path(__file__)),
        'terminal_validator': records.file_binding(Path(terminal_gate.__file__)),
        'human_observation': {'quote': '目前是白色，重新刷入', 'observed_at': None,
            'source': 'user message after SOURCE', 'full_clean_white_details_not_added': True},
        'interpretation': 'Uniform C7 SOURCE is a baseline; white appearance does not test MIDDLE/TARGET lightness. No fresh-white restart is required by that observation alone.',
        'current_device_state': 'NOT_CHECKED_BY_THIS_OFFLINE_REVIEW',
        'next_action': {'ordinal': 2, 'stage': 'MIDDLE', 'action_id': ctx['contract']['actions'][1]['action_id'],
            'conditions': ['fresh same boot/cursor2', 'valid full-panel optical source',
                           'sealed one-shot runner and distinct stage review', 'current stage release'],
            'live_ready': False},
        'screen_refreshes_this_review': 0, 'device_access_this_review': False,
        'temperature_celsius': None, 'controller_revision': {'CS1': None, 'CS2': None},
        'waveform_internal_phase': 'OPAQUE', 'lab_type': 'camera-relative', 'lab_measured': False,
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    records.write_new(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    value = reconcile(args.output)
    print(records.canonical({'protocol_terminal': value['protocol_terminal_verdict'],
        'runner': value['original_runner_verdict'], 'verdict': value['overall_verdict'],
        'qualified': 0, 'output': str(args.output)}).decode())


if __name__ == '__main__':
    main()
