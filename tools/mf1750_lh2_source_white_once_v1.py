"""Bounded LH2 white runner; never resumes or resets the rebound V2 main.

Requires a separate audited LH2 source-white package, exact current field
evidence, post-flash J2-OFF diagnostic, and a workspace-global claim before
the only ARM.  Imports and validate perform no device access.  There are no
mutation retries.
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from tools import mf1750_lh1_lh4_once_operator_v2 as b
from tools import mf1750_lh2_source_white_firmware_v1 as firmware
from tools.mf17506_stage23.relay_exact_bound_switch import validate_receipt

CLAIM = b.ROOT / '.test-output/hardware/.mf1750_lh2_source_white_consumption/lh2srcw_v1-used_lh2sw1.json'
R5 = b.ROOT / '.test-output/offline/LH1_SOURCE_WHITE_20260913_R5'
WAIT_SECONDS = 65
MAX_POLLS = 30


def record(path):
    value = b.parse_json(Path(path).read_bytes())
    b.verify_integrity(value)
    return value


def bound_record(binding):
    value = b.parse_json(b.read_bound(binding))
    b.verify_integrity(value)
    return value


def validate_package(path):
    path = Path(path).resolve()
    contract, manifest, build = [record(path / name) for name in ('contract.json', 'manifest.json', 'build-report.json')]
    b._require(contract, {'kind': 'mf1750-lh2-source-white-contract-v1',
        'retry': False, 'automatic_recovery': False, 'main_resume_after_recovery': False,
        'no_main_nvs_clear_route': True, 'driver_body_unchanged_from_r5': True,
        'profile_id': 'WF23_25',
        'source_terminal_gate': {'namespace': 'lh1reb_v2', 'cursor_key': 'cur_lh1r',
            'expected_cursor_raw': firmware.EXPECTED_V2_CURSOR, 'boot_key': 'boot_lh1r',
            'expected_boot_nonce': firmware.EXPECTED_V2_BOOT},
        'old_fault_preservation': {'namespace': 'lhist_v1', 'cursor_key': 'cur_lh1',
            'expected_cursor_raw': firmware.EXPECTED_OLD_FAULT_CURSOR, 'boot_key': 'boot_lh1',
            'expected_boot_nonce': firmware.EXPECTED_OLD_FAULT_BOOT,
            'must_remain_untouched': True},
        'successor_nvs': {'namespace': 'lh2srcw_v1', 'cursor_key': 'used_lh2sw1',
            'initial_cursor': 1, 'complete_cursor': 2}}, 'LH2 source-white contract')
    b._require(build, {'result': 'PASS'}, 'build')
    b._require(manifest, {'contract_id': contract['contract_id']}, 'manifest')
    for item in manifest['inputs'] + manifest['outputs'] + build['artifacts'] + [build['contract'], build['manifest']]:
        b.read_bound(item)
    artifacts = {Path(x['path']).suffix: x for x in build['artifacts']}
    if set(artifacts) != {'.bin', '.elf'}:
        raise b.RunnerError('exact BIN/ELF required')
    for item in artifacts.values():
        if b.read_bound(item).count(contract['compiled_marker'].encode()) != 1:
            raise b.RunnerError('compiled marker mismatch')
    main = (path / 'generated/main.cpp').read_text(encoding='utf-8')
    identity = (path / 'generated/identity.inc').read_text(encoding='utf-8')
    combined = main + identity
    def text(key):
        matches = re.findall(r'static constexpr const char \*' + key + r'\s*=\s*"([^"]*)";', combined)
        if len(matches) != 1 or not matches[0]:
            raise b.RunnerError('missing/duplicate compiled constant: ' + key)
        return matches[0]
    expected = {k: text(c) for k, c in (
        ('build_tag', 'kBuildTag'), ('test_id', 'kTestId'), ('campaign_id', 'kCampaignId'),
        ('contract_id', 'kContractId'), ('environment', 'kEnvironmentId'),
        ('profile_id', 'kProfileId'), ('device_api_version', 'kDeviceApiVersion'),
        ('identity_revision', 'kIdentityRevision'), ('source_main_contract_id', 'kSourceMainContractId'),
        ('transaction_descriptor_sha256', 'kDescriptorId'))}
    expected['running_app_elf_sha256'] = artifacts['.elf']['sha256']
    if expected['contract_id'] != contract['contract_id'] or expected['transaction_descriptor_sha256'] != contract['descriptor_id']:
        raise b.RunnerError('compiled contract/descriptor mismatch')
    r5_driver = (R5 / 'generated/frozen_epd_driver.cpp.inc').read_bytes()
    if (path / 'generated/frozen_epd_driver.cpp.inc').read_bytes() != r5_driver:
        raise b.RunnerError('factory driver changed')
    # The driver_gate FNV-1a constants below are the R4/R5 values; they are
    # valid for this package only because the pure-white frame and DTM bytes
    # are unchanged, proven here by contract hash equality with R5.
    r5_contract = record(R5 / 'contract.json')
    b._require(contract, {'frame_sha256': r5_contract['frame_sha256'],
        'dtm_sha256': r5_contract['dtm_sha256']}, 'R5 white frame/DTM equality')
    return {'package': path, 'contract': contract, 'expected': expected,
        'firmware': artifacts['.bin'], 'elf': artifacts['.elf'],
        'routes': {name: text('k' + name.capitalize() + 'Route') for name in ('version', 'manifest', 'status', 'report', 'arm', 'execute')},
        'arm_intent': text('kArmIntent'), 'execute_intent': text('kExecuteIntent')}


def identity(ctx, value):
    b._require(value, ctx['expected'], 'white runtime identity')
    b._require(value, {'main_campaign_resume_after_containment': False,
        'source_main_direct_exact_post_resume_after_reboot': False}, 'no main resume')


def source_nvs(value):
    b._require(value, {'source_cursor_key_present': True, 'source_boot_key_present': True,
        'source_observed_cursor_raw': firmware.EXPECTED_V2_CURSOR,
        'source_observed_boot_nonce': firmware.EXPECTED_V2_BOOT,
        'old_fault_cursor_raw': firmware.EXPECTED_OLD_FAULT_CURSOR,
        'source_terminal_gate_pass': True}, 'read-only source NVS observation')


def preflight(ctx, values, busy, boot=None):
    for value in values.values():
        identity(ctx, value)
    s, r, m = values['status'], values['report'], values['manifest']
    source_nvs(s)
    b._require(s, {'state': 'ready', 'phase': 0, 'next_ordinal': 1, 'cursor_raw': 1,
        'campaign_complete': False, 'cursor_valid': True, 'fixture_self_check_passed': True,
        'execute_pending': False, 'arm_request_count': 0, 'execute_request_count': 0,
        'total_driver_call_count': 0, 'gpio_initialized': True, 'busy': busy}, 'white preflight')
    b._require(r, {'terminal_state': 'NOT_EXECUTED', 'valid': False,
        'result': False, 'driver_called': False, 'driver_call_count_for_action': 0}, 'unused report')
    b._require(m, {'action_count': 1, 'startup_refresh': False, 'retry': False,
        'automatic_chaining': False, 'raw_frame_ingress': False, 'raw_lut_ingress': False}, 'white allowlist')
    b._require(m['actions'][0], {'ordinal': 1, 'action_id': ctx['contract']['action_id'],
        'descriptor_id': ctx['contract']['descriptor_id'], 'frame_sha256': ctx['contract']['frame_sha256'],
        'cs1_dtm_sha256': ctx['contract']['dtm_sha256'], 'cs2_dtm_sha256': ctx['contract']['dtm_sha256']}, 'white action')
    b._require(m['nvs_contract'], {'namespace': 'lh2srcw_v1', 'key': 'used_lh2sw1',
        'initial_cursor': 1, 'terminal_cursor': 2}, 'single shared white allowance')
    current_boot = s.get('boot_nonce')
    if not isinstance(current_boot, str) or not b.NONCE.fullmatch(current_boot) or current_boot == firmware.EXPECTED_V2_BOOT or (boot and boot != current_boot):
        raise b.RunnerError('new same-session white boot required')
    return current_boot


def validate_field(ctx, path, phase):
    field = record(path)
    b._fresh(field['recorded_at'], datetime.now(timezone.utc))
    b._require(field, {'kind': 'mf1750-lh2-source-white-field-v1',
        'contract_id': ctx['contract']['contract_id'], 'electrical_state_proven': False,
        'electrical_policy': 'RECORD_ONLY_BY_EXPLICIT_USER_INSTRUCTION'}, 'field')
    ip = bound_record(field['ip_binding'])
    b._require(ip, {'binding_passed': True, 'fresh_binding_passed': True,
        'expected_mac': 'A4-CB-8F-D9-FC-D4'}, 'exact network binding')
    b._fresh(ip['finished_at'], datetime.now(timezone.utc))
    if b.origin(field['base_url']) != 'http://' + ip['candidate_ipv4']:
        raise b.RunnerError('field IPv4 differs')
    gate = bound_record(field['source_gate'])
    b._require(gate, {'result': 'PASS', 'rebound_v2_cursor': firmware.EXPECTED_V2_CURSOR,
        'rebound_v2_boot': firmware.EXPECTED_V2_BOOT,
        'old_fault_cursor': firmware.EXPECTED_OLD_FAULT_CURSOR,
        'old_fault_boot': firmware.EXPECTED_OLD_FAULT_BOOT,
        'main_campaign_resume_allowed': False}, 'rebound V2 terminal eligibility')
    for item in gate['bindings']:
        b.read_bound(item)
    review = bound_record(field['camera_review'])
    b._require(review, {'camera_usb_id': 'VID_32E4:PID_4801'}, 'authorized camera')
    if review.get('observation_mode') == 'MANUAL_OPERATOR_PRESENT':
        b._require(review, {'operator_present': True,
            'operator_statement': '我人在的，可以直接看屏幕，你直接刷入真屏即可',
            'full_panel_visible': False, 'usable_for_state_review': False,
            'optical_acceptance': 'PENDING_POST_RECOVERY_HUMAN_REVIEW',
            'scope': 'ONE_INDEPENDENT_LH2_SOURCE_WHITE_ACTION'}, 'manual recovery observation')
    else:
        b._require(review, {'full_panel_visible': True, 'usable_for_state_review': True},
            'current camera review')
    b._fresh(review['recorded_at'], datetime.now(timezone.utc))
    b.read_bound(review['photo'])
    bound_record(review['sidecar'])
    release = bound_record(field['user_release'])
    b._require(release, {'scope': 'ONE_INDEPENDENT_LH2_SOURCE_WHITE_ACTION',
        'recovery_authorized': True, 'middle_retry_authorized': False}, 'release scope')
    flash = bound_record(field['app_flash'])
    b._require(flash, {'result': 'PASS', 'firmware': ctx['firmware'],
        'app_only': True, 'application_starts': 1, 'nvs_erased': False}, 'post-flash evidence')
    b.read_bound(flash['raw_log'])
    off = bound_record(field['relay_off'])
    b._require(off, {'commanded_state': 'OFF', 'electrical_state_proven': False}, 'relay OFF')
    if phase == 'on':
        on = validate_receipt(bound_record(field['relay_on']))
        b._require(on, {'target_state': 'ON', 'commanded_state': 'ON',
            'target_gate_passed': True}, 'exact ON')
        b._fresh(on['switched_at'], datetime.now(timezone.utc))
    return field


def headers(ctx, boot, nonce=None):
    e, c = ctx['expected'], ctx['contract']
    result = {'X-EC5-Build-Tag': e['build_tag'], 'X-EC5-Test-Id': e['test_id'],
        'X-EC5-Campaign-Id': e['campaign_id'], 'X-EC5-Action-Id': c['action_id'],
        'X-EC5-Descriptor-Id': c['descriptor_id'], 'X-EC5-Ordinal': '1',
        'X-EC5-Boot-Nonce': boot,
        'X-EC5-Intent': ctx['execute_intent'] if nonce else ctx['arm_intent']}
    if nonce:
        result['X-EC5-Arm-Nonce'] = nonce
    return result


def driver_gate(driver):
    """Terminal gate for the unchanged factory driver.

    The FNV-1a constants (input 322178501, CS1/CS2 DTM 3081262533) are carried
    over from the R4 runner.  They are admissible here only because
    validate_package proved this package's frame_sha256/dtm_sha256 equal the R5
    contract's and the frozen driver body is byte-identical to R5's, so the
    hashed bytes are the same.  The LH2 strict-native audit runs a synthetic
    desktop stub and does not establish these values; they were established by
    the R5 real-panel batch of 2026-09-13/14.
    """
    b._require(driver, {'valid': True, 'running': False, 'sequence_ok': True,
        'wait_timeout': False, 'busy_assertion_missing': False,
        'pre_command_idle_failure': False, 'failure_code': 0,
        'pon_busy_seen': True, 'drf_busy_seen': True, 'pof_busy_seen': True,
        'mapping_applied': True, 'spi_hz': 1000000, 'operation_id': 1,
        'input_fnv1a': 322178501, 'cs1_dtm_fnv1a': 3081262533,
        'cs2_dtm_fnv1a': 3081262533, 'busy_trace_schema_version': 1}, 'factory driver')
    for key in ('failure_stage', 'timeout_stage', 'busy_missing_stage', 'pre_command_busy_stage'):
        if driver.get(key) not in ('none', ''):
            raise b.RunnerError('driver failure: ' + key)
    trace = driver['busy_trace']
    for name in ('pon', 'drf', 'pof'):
        b._require(trace[name], {'pre_command_idle_ok': True, 'pre_command_level': 1,
            'assertion_after_idle': True, 'wait_exit_level': 1}, name + ' BUSY')
        if type(trace[name]['wait_ms']) is not int or trace[name]['wait_ms'] <= 0:
            raise b.RunnerError('missing BUSY duration')
    b._require(trace['safe_finish'], {'busy_before_pins_low': 1,
        'busy_after_pins_low': 1, 'busy_after_5ms': 1}, 'safe finish')
    b._require(trace['final_gpio'], {'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0,
        'sck': 0, 'dc': 0, 'mosi': 0}, 'safe finish GPIO')


def diagnose(package, field_path, output, transport=None):
    ctx = validate_package(package)
    field = validate_field(ctx, field_path, 'off')
    session = b.Session(ctx, field, output, field['base_url'], transport)
    values = {k: session.request('GET', k, 200) for k in ('version', 'manifest', 'status', 'report')}
    boot = preflight(ctx, values, 0)
    result = b.seal({'kind': 'mf1750-lh2-source-white-j2-off-diagnostic-v1',
        'recorded_at': datetime.now(timezone.utc).isoformat(), 'result': 'PASS',
        'boot_nonce': boot, 'contract_id': ctx['contract']['contract_id'],
        'field': b.file_binding(field_path), 'responses': values,
        'transcripts': [b.file_binding(p) for p in sorted(session.output.iterdir())],
        'network': session.counts, 'driver_calls': 0, 'visible_refreshes': 0})
    b.write_new(session.output / 'diagnostic.json', result)
    return result


def run(package, field_path, diagnostic_path, output, transport=None, sleeper=time.sleep, claim_path=CLAIM):
    ctx = validate_package(package)
    field = validate_field(ctx, field_path, 'on')
    diagnostic = record(diagnostic_path)
    b._fresh(diagnostic['recorded_at'], datetime.now(timezone.utc))
    b._require(diagnostic, {'result': 'PASS', 'contract_id': ctx['contract']['contract_id'],
        'network': {'get': 4, 'post': 0}}, 'post-flash diagnostic')
    for item in diagnostic['transcripts']:
        b.read_bound(item)
    # The diagnostic is taken with the panel powered and relay ON.  BUSY must
    # therefore be idle-high (1); the separate J2-OFF diagnostic uses 0.
    boot = preflight(ctx, diagnostic['responses'], 1, diagnostic['boot_nonce'])
    old_field = bound_record(diagnostic['field'])
    for key in ('app_flash', 'camera_review', 'source_gate', 'user_release', 'run_id'):
        if old_field[key] != field[key]:
            raise b.RunnerError('diagnostic field binding changed: ' + key)
    if Path(claim_path).exists():
        raise b.RunnerError('shared white allowance already claimed')
    session = b.Session(ctx, field, output, field['base_url'], transport)
    try:
        values = {k: session.request('GET', k, 200) for k in ('version', 'manifest', 'status', 'report')}
        preflight(ctx, values, 1, boot)
        Path(claim_path).parent.mkdir(parents=True, exist_ok=True)
        b.write_new(Path(claim_path), b.seal({'kind': 'mf1750-lh2-source-white-claim-v1',
            'recorded_at': datetime.now(timezone.utc).isoformat(), 'state': 'PERMANENTLY_CONSUMED_BEFORE_ARM',
            'action_id': ctx['contract']['action_id'], 'successor_nvs': ctx['contract']['successor_nvs'],
            'boot_nonce': boot, 'field': b.file_binding(field_path), 'output': str(session.output)}))
        arm = session.request('POST', 'arm', 201, headers(ctx, boot))
        identity(ctx, arm)
        b._require(arm, {'accepted': True, 'armed': True, 'ordinal': 1,
            'boot_nonce': boot, 'action_id': ctx['contract']['action_id']}, 'white ARM')
        nonce = arm.get('arm_nonce')
        if not isinstance(nonce, str) or not b.NONCE.fullmatch(nonce) or nonce == '0' * 16:
            raise b.RunnerError('invalid ARM nonce')
        exe = session.request('POST', 'execute', 202, headers(ctx, boot, nonce))
        identity(ctx, exe)
        b._require(exe, {'accepted': True, 'job_id': 1, 'execute_consumed': True,
            'action_id': ctx['contract']['action_id'], 'no_retry': True}, 'white EXEC')
        sleeper(WAIT_SECONDS)
        for _ in range(MAX_POLLS):
            status = session.request('GET', 'status', 200)
            identity(ctx, status)
            source_nvs(status)
            b._require(status, {'boot_nonce': boot, 'arm_request_count': 1,
                'execute_request_count': 1}, 'white counters')
            if status['phase'] == 3:
                raise b.RunnerError('white FAULT; no retry or automatic recovery')
            if status['phase'] == 0 and status['cursor_raw'] == 2:
                break
            if status['phase'] != 2 or status['next_ordinal'] != 1:
                raise b.RunnerError('invalid in-flight state')
            sleeper(2)
        else:
            raise b.RunnerError('white poll deadline; do not resend mutation')
        report = session.request('GET', 'report', 200)
        identity(ctx, report)
        b._require(status, {'state': 'complete', 'total_driver_call_count': 1,
            'campaign_complete': True, 'execute_pending': False, 'busy': 1}, 'white COMPLETE status')
        b._require(report, {'valid': True, 'terminal_state': 'COMPLETE', 'result': True,
            'ordinal': 1, 'action_id': ctx['contract']['action_id'], 'driver_called': True,
            'driver_call_count_for_action': 1, 'total_driver_call_count': 1,
            'next_ordinal': 2, 'campaign_complete': True, 'no_retry': True}, 'white terminal')
        driver_gate(report['driver'])
        result = b.seal({'kind': 'mf1750-lh2-source-white-result-v1', 'result': 'PASS',
            'recorded_at': datetime.now(timezone.utc).isoformat(), 'boot_nonce': boot,
            'field': b.file_binding(field_path), 'claim': b.file_binding(claim_path),
            'diagnostic': b.file_binding(diagnostic_path), 'terminal_report': report,
            'status': status, 'network': session.counts, 'driver_calls': 1,
            'visible_refreshes': 1, 'main_campaign_resume_allowed': False,
            'qualified_count': 0, 'optical_verdict': 'PENDING_CAMERA_REVIEW',
            'transcripts': [b.file_binding(p) for p in sorted(session.output.iterdir())]})
        b.write_new(session.output / 'result.json', result)
        return result
    except Exception as exc:
        b.write_new(session.output / 'STOP.json', b.seal({'kind': 'mf1750-lh2-source-white-stop-v1',
            'reason': str(exc), 'network_attempts': session.counts, 'mutation_retry': False,
            'automatic_recovery': False, 'claim_preserved': Path(claim_path).exists()}))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('validate', 'diagnose-j2-off', 'run'))
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--field', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--diagnostic', type=Path)
    a = p.parse_args()
    if a.command == 'validate':
        print(validate_package(a.package)['contract']['contract_id'])
    elif a.command == 'diagnose-j2-off':
        print(diagnose(a.package, a.field, a.output)['result'])
    else:
        print(run(a.package, a.field, a.diagnostic, a.output)['result'])


if __name__ == '__main__':
    main()
