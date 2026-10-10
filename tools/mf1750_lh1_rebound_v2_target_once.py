"""Exact V2 TARGET only; durable claim, fresh evidence, no retry/reflash/relay.

The retained same-boot MIDDLE terminal is mandatory. A fresh reviewed full-panel
capture of the retained MIDDLE matrix, the sealed MIDDLE analysis review and a
separately sealed stage release must exist before this host sends POST.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

from tools import mf1750_lh1_rebound_v2_review as review
from tools import mf1750_lh1_rebound_v2_middle_once as middle
from tools import mf1750_lh1_lh4_middle_once_v2 as http
from tools import mf1750_lh1_lh4_once as rec
from tools import mf1750_lh1_lh4_once_operator_v2 as gates

CLAIMS = review.ROOT / '.test-output/hardware/.mf1750_lh1_rebound_v2_action_claims'
INITIAL_WAIT = 65
MAX_POLLS = 30
require = rec._require
Error = rec.RunnerError


def dependencies():
    return [rec.file_binding(Path(m.__file__)) for m in (review, middle, http, rec, gates)] + [rec.file_binding(Path(__file__))]


def claim_path():
    return CLAIMS / (review.CONTRACT + '-ordinal3.json')


def identity(ctx, value, prior, *, require_boot=True):
    require(value, {**ctx['identity'],
        'source_nvs_complete': True, 'run_id': review.RUN,
        'source_review_sha256': review.ANCHOR, 'prior_review_sha256': prior,
        'waveform_internal_phase': 'OPAQUE', 'qualified_count': 0,
        'review_digests_are_host_assertions_only': True}, 'identity/review')
    if require_boot or 'boot_nonce' in value:
        require(value, {'boot_nonce': review.BOOT}, 'boot identity')
    if 'running_app_elf_sha256' in value:
        require(value, {'running_app_elf_sha256': review.ELF}, 'running ELF')


def validate_middle_terminal(ctx, status, report, prior):
    # The MIDDLE terminal is validated by the exact MIDDLE host rules; the TARGET
    # host adds no reinterpretation of that stage.
    middle.validate_terminal(ctx, status, report, prior)


def validate_preflight(ctx, values, prior):
    for name, value in values.items():
        identity(ctx, value, prior, require_boot=name not in ('version', 'manifest'))
        require(value, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-' + name}, name)
    validate_middle_terminal(ctx, values['status'], values['report'], prior)
    for name in ('version', 'manifest'):
        require(values[name], {'action_count': 3, 'automatic_chaining': False,
            'startup_refresh': False, 'retry': False, 'recovery': False,
            'raw_frame_ingress': False, 'caller_electrical_parameter_write': False,
            'device_enforced_same_boot': True, 'dither': False, 'spatial_mixing': False,
            'full_screen_global_refresh': True, 'partial_refresh': False}, name)
        require(values[name]['nvs_contract'], {'namespace': review.NVS['namespace'],
            'key': review.NVS['cursor'], 'campaign_boot_key': review.NVS['boot']}, name + ' NVS')
    actions = values['manifest'].get('actions')
    if not isinstance(actions, list) or len(actions) != 3:
        raise Error('device action list differs')
    for index, action in enumerate(actions):
        want = ctx['contract']['actions'][index]
        require(action, gates.expected_action(ctx, index), 'compiled action')
        require(action, {'frame_sha256': want['frame']['sha256'],
            'cs1_dtm_sha256': want['cs1_dtm']['sha256'], 'cs2_dtm_sha256': want['cs2_dtm']['sha256'],
            'transport_code_histogram': want['frame']['histogram'],
            'prior_static_action_id': want['prior_action_id']}, 'compiled frame')


def validate_terminal(ctx, status, report, prior):
    identity(ctx, status, prior)
    identity(ctx, report, prior)
    require(report, gates.expected_action(ctx, 2), 'TARGET action')
    require(report, {'valid': True, 'terminal_state': 'COMPLETE', 'result': True,
        'driver_called': True, 'driver_call_count_for_action': 1, 'total_driver_call_count': 3,
        'job_id': 3, 'phase': 0, 'phase_name': 'READY', 'next_ordinal': 4,
        'campaign_complete': True, 'no_retry': True, 'no_recovery': True}, 'terminal')
    require(status, {'state': 'complete', 'phase': 0, 'phase_name': 'READY',
        'cursor_raw': 4, 'next_ordinal': 4, 'arm_request_count': 3, 'execute_request_count': 3,
        'total_driver_call_count': 3, 'execute_pending': False, 'current_action': None,
        'campaign_complete': True, 'cursor_valid': True, 'persistent_key_present': True,
        'campaign_boot_matches_current': True,
        'persisted_campaign_boot_nonce': review.BOOT, 'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}, 'terminal status')
    a = ctx['contract']['actions'][2]
    d = report['driver']
    require(d, {'driver_evidence_schema_version': 2, 'valid': True, 'running': False,
        'sequence_ok': True, 'wait_timeout': False, 'busy_assertion_missing': False,
        'pre_command_idle_failure': False, 'mapping_applied': True,
        'pon_busy_seen': True, 'drf_busy_seen': True, 'pof_busy_seen': True,
        'input_fnv1a': a['frame']['fnv1a'], 'cs1_dtm_fnv1a': a['cs1_dtm']['fnv1a'],
        'cs2_dtm_fnv1a': a['cs2_dtm']['fnv1a'], 'failure_code': 0,
        'operation_id': 3, 'spi_hz': 1000000}, 'driver')
    for key in ('failure_stage', 'timeout_stage', 'busy_missing_stage', 'pre_command_busy_stage'):
        if d.get(key) not in ('', 'none'):
            raise Error('driver failure stage present')
    stages = d['busy_stage_samples']
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
    require(d['safe_finish'], {'busy_before_pins_low': 1, 'busy_after_pins_low': 1,
        'busy_after_5ms': 1, 'final_gpio': {'busy': 1, 'rst': 0, 'cs': 0, 'cs2': 0}}, 'safe finish')
    times = [report.get(k) for k in ('job_queued_at_ms', 'job_started_at_ms', 'job_finished_at_ms')]
    if any(type(t) is not int or t < 0 for t in times) or times != sorted(times):
        raise Error('job chronology differs')


def load_bound_record(binding):
    value = rec.parse_json(rec.read_bound(binding))
    rec.verify_integrity(value)
    return value


def validate_release(path, ctx, base_url, now=None):
    now = now or datetime.now(timezone.utc)
    value = rec.read_record(path)
    require(value, {'kind': 'mf1750-lh1-rebound-v2-target-release-v1',
        'contract_id': review.CONTRACT, 'boot_nonce': review.BOOT, 'run_id': review.RUN,
        'ordinal': 3, 'action_id': ctx['contract']['actions'][2]['action_id'],
        'authorized_refreshes': 1, 'stop_after_action': True, 'source_replay': False,
        'middle_replay': False, 'white_authorized': False, 'live_release': True}, 'release')
    rec._fresh(value['recorded_at'], now)
    if value['dependencies'] != dependencies():
        raise Error('runner dependencies changed')
    native = load_bound_record(value['native_audit'])
    require(native, {'result': 'PASS', 'native_wire_documents': 8,
        'hardware_accessed': False, 'host_preflight_ack_terminal': 'PASS',
        'host': dependencies()}, 'native host audit')
    terminal = load_bound_record(value['middle_terminal'])
    require(terminal, {'kind': 'mf1750-lh1-rebound-v2-middle-result-v1',
        'protocol_verdict': 'PASS', 'arm': 1, 'execute': 1, 'driver': 1,
        'visible_refresh': 1, 'target_executed': False, 'white_executed': False}, 'MIDDLE terminal')
    prior_middle = terminal['report'].get('prior_review_sha256')
    if (not isinstance(prior_middle, str) or len(prior_middle) != 64
            or any(c not in '0123456789abcdef' for c in prior_middle)
            or prior_middle == review.ANCHOR):
        raise Error('MIDDLE stage review digest invalid')
    validate_middle_terminal(ctx, terminal['status'], terminal['report'], prior_middle)
    if not middle.claim_path().exists():
        raise Error('MIDDLE permanent claim missing')
    claimed = load_bound_record(value['middle_claim'])
    require(claimed, {'kind': 'mf1750-lh1-rebound-v2-middle-claim-v1', 'ordinal': 2,
        'contract_id': review.CONTRACT, 'boot_nonce': review.BOOT, 'permanent': True,
        'claim_created_before_arm': True,
        'action_id': ctx['contract']['actions'][1]['action_id']}, 'MIDDLE claim')
    if terminal['claim'] != value['middle_claim']:
        raise Error('MIDDLE result binds another claim')
    on_disk = rec.file_binding(middle.claim_path())
    require(on_disk, {'sha256': value['middle_claim']['sha256'],
        'bytes': value['middle_claim']['bytes']}, 'on-disk MIDDLE claim')
    optical = load_bound_record(value['optical_review'])
    require(optical, {'kind': 'mf1750-lh1-rebound-v2-middle-optical-review-v1',
        'boot_nonce': review.BOOT, 'middle_action_id': ctx['contract']['actions'][1]['action_id'],
        'coverage_scope': 'full_panel', 'full_panel_valid': True, 'four_edges_visible': True,
        'unobstructed': True, 'verdict': 'PASS_MIDDLE_MATRIX_OBSERVATION_ONLY',
        'qualified_count': 0}, 'MIDDLE matrix optical review')
    rec._fresh(optical['recorded_at'], now)
    capture = load_bound_record(optical['capture'])
    require(capture['camera'], {'usb_vid': '32E4', 'usb_pid': '4801'}, 'camera')
    rec._fresh(capture['capture_timing']['completed_at'], now)
    rec.read_bound(optical['photo'])
    require(capture['photo'], {'sha256': optical['photo']['sha256'],
        'bytes': optical['photo']['bytes']}, 'capture/photo binding')
    if Path(capture['photo']['path']).resolve() != Path(optical['photo']['path']).resolve():
        raise Error('photo path is not the captured image')
    # Camera approval is a host visual judgement; it is not inferred from VID/PID.
    if not optical.get('observations'):
        raise Error('visual observations absent')
    analysis = load_bound_record(value['analysis_review'])
    require(analysis, {'kind': 'mf1750-lh1-rebound-v2-middle-analysis-review-v2',
        'analyzer_version': 'mf1750-lh1-rebound-v2-middle-photo-analyzer-v2'}, 'MIDDLE analysis review')
    require(analysis['actual_counts'], {'arm': 0, 'execute': 0, 'driver': 0,
        'visible_refresh': 0, 'hardware_accessed': False}, 'analysis actual counts')
    rec.read_bound(analysis['extraction'])
    rec.read_bound(analysis['observations'])
    rec.validate_ipv4_mac_raw(value['ip_binding'], base_url, now)
    enum = load_bound_record(value['enumeration'])
    rec._fresh(enum['recorded_at'], now)
    esp = [p for p in enum['com_ports'] if p['vid'] == 0x1A86 and p['pid'] == 0x55D3 and p['serial_number'] == '5C4C165475']
    if len(esp) != 1 or len(enum['relay_bindings']) != 1:
        raise Error('current hardware enumeration not unique')
    relay = load_bound_record(value['relay_on_query'])
    rec._fresh(relay['recorded_at'], now)
    require(relay, {'commanded_state': 'ON', 'channel': 1,
                    'contact_switch_performed': False}, 'independent relay query')
    if relay['identity'] != enum['relay_bindings'][0]:
        raise Error('relay identity differs')
    preflight = load_bound_record(value['preflight_off'])
    require(preflight, {'kind': 'mf1750-lh1-rebound-v2-target-preflight-off-v1',
        'result': 'PASS', 'boot_nonce': review.BOOT, 'mutation_count': 0,
        'visible_refresh_count': 0}, 'fresh OFF preflight')
    rec._fresh(preflight['recorded_at'], now)
    require(preflight['status'], {'state': 'ready', 'phase': 0, 'cursor_raw': 3,
        'next_ordinal': 3, 'total_driver_call_count': 2,
        'boot_nonce': review.BOOT}, 'fresh OFF status')
    successor = load_bound_record(value['white_successor_review'])
    require(successor, {'kind': 'mf1750-lh1-rebound-v2-white-applicability-review-v1',
        'source_contract_id': review.CONTRACT, 'source_ordinal': 3,
        'offline_verdict': 'PASS_HASH_CHECK_ONLY', 'auto_recovery': False,
        'live_authorized': False}, 'white materials review')
    # An incompatible historical white is recorded, never used as recovery.
    # No recovery or white mutation is implemented in this ordinal-3 host.
    if type(successor.get('current_source_compatible')) is not bool:
        raise Error('white applicability was not reviewed')
    for b in successor['verified_artifacts']:
        rec.read_bound(b)
    payload = value['review_payload']
    require(payload, {'contract_id': review.CONTRACT, 'boot_nonce': review.BOOT,
        'next_action_id': ctx['contract']['actions'][2]['action_id'],
        'middle_terminal': value['middle_terminal'],
        'optical_review': value['optical_review'],
        'analysis_review': value['analysis_review']}, 'new stage review payload')
    prior = rec.digest(rec.canonical(payload))
    if value['prior_review_sha256'] != prior or prior in (review.ANCHOR, prior_middle):
        raise Error('distinct structured stage review required')
    if not value.get('authorization_messages'):
        raise Error('release must record user authority')
    return value


def run(release_path, output, base_url, *, transport=None, sleeper=time.sleep):
    # All local gates precede network; no ordinal/boot override exists.
    ctx = review.validate_package()
    base_url = rec.origin(base_url)
    release = validate_release(release_path, ctx, base_url)
    if claim_path().exists():
        raise Error('TARGET permanently claimed; no retry')
    prior = release['prior_review_sha256']
    prior_middle = load_bound_record(release['middle_terminal'])['report']['prior_review_sha256']
    session = http.Session(ctx, {}, Path(output), base_url, transport or http._http, sleeper)
    claimed = False
    try:
        pre = {k: session.request('GET', k, 200) for k in ('version', 'manifest', 'status', 'report')}
        validate_preflight(ctx, pre, prior_middle)
        # Prevent stale/changed evidence during preflight from authorizing a POST.
        validate_release(release_path, ctx, base_url)
        claim_path().parent.mkdir(parents=True, exist_ok=True)
        rec.write_new(claim_path(), rec.seal({'kind': 'mf1750-lh1-rebound-v2-target-claim-v1',
            'recorded_at': review.now(), 'contract_id': review.CONTRACT,
            'ordinal': 3, 'boot_nonce': review.BOOT, 'action_id': ctx['contract']['actions'][2]['action_id'],
            'release': rec.file_binding(release_path), 'output': str(Path(output).resolve()),
            'permanent': True, 'claim_created_before_arm': True}))
        claimed = True
        a = ctx['contract']['actions'][2]
        headers = {'X-EC5-Build-Tag': ctx['identity']['build_tag'],
            'X-EC5-Test-Id': ctx['identity']['test_id'], 'X-EC5-Campaign-Id': ctx['identity']['campaign_id'],
            'X-EC5-Action-Id': a['action_id'], 'X-EC5-Ordinal': '3',
            'X-EC5-Descriptor-Id': a['descriptor_id'], 'X-EC5-Boot-Nonce': review.BOOT,
            'X-EC5-Intent': ctx['arm_intent'], 'X-LH-Run-Id': review.RUN,
            'X-LH-Source-Review': review.ANCHOR, 'X-LH-Prior-Review': prior}
        arm = session.request('POST', 'arm', 201, headers)
        identity(ctx, arm, prior)
        require(arm, {**gates.expected_action(ctx, 2), 'accepted': True,
            'armed': True, 'phase': 1}, 'ARM')
        nonce = arm.get('arm_nonce')
        if not isinstance(nonce, str) or not rec.NONCE.fullmatch(nonce):
            raise Error('invalid ARM nonce')
        execute = session.request('POST', 'execute', 202,
            {**headers, 'X-EC5-Intent': ctx['execute_intent'], 'X-EC5-Arm-Nonce': nonce})
        identity(ctx, execute, prior)
        require(execute, {**gates.expected_action(ctx, 2), 'accepted': True,
            'execute_consumed': True, 'phase': 2, 'job_id': 3}, 'EXECUTE')
        # Split host wait permits short tool yields; no requests during synchronous driver.
        for seconds in (30, 30, INITIAL_WAIT - 60):
            sleeper(seconds)
        terminal = None
        for _ in range(MAX_POLLS):
            status = session.request('GET', 'status', 200)
            identity(ctx, status, prior)
            if status.get('phase') == 0 and status.get('cursor_raw') == 4:
                terminal = session.request('GET', 'report', 200)
                validate_terminal(ctx, status, terminal, prior)
                break
            require(status, {'phase': 2, 'cursor_raw': 515, 'next_ordinal': 3}, 'in-flight')
            sleeper(2)
        if terminal is None:
            raise Error('terminal polling budget exhausted')
        result = rec.seal({'kind': 'mf1750-lh1-rebound-v2-target-result-v1',
            'recorded_at': review.now(), 'protocol_verdict': 'PASS',
            'optical_verdict': 'HOLD_FOR_POST_ACTION_REVIEW', 'qualified_count': 0,
            'release': rec.file_binding(release_path), 'claim': rec.file_binding(claim_path()),
            'network': session.counts, 'arm': 1, 'execute': 1, 'driver': 1,
            'visible_refresh': 1, 'status': status, 'report': terminal,
            'campaign_complete': True, 'further_contract_action_available': False,
            'white_executed': False, 'stop_required': True})
        rec.write_new(session.output / 'result.json', result)
        return result
    except Exception as exc:
        rec.write_new(session.output / 'STOP.json', rec.seal({'recorded_at': review.now(),
            'verdict': 'FAIL_STOP', 'error': str(exc), 'network': session.counts,
            'claim_created': claimed, 'no_retry': True, 'no_reset_or_white': True}))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('validate', 'run'))
    p.add_argument('--release', required=True, type=Path)
    p.add_argument('--base-url', required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.command == 'validate':
        validate_release(a.release, review.validate_package(), rec.origin(a.base_url))
        print('PASS_OFFLINE_RELEASE_VALIDATION')
    else:
        if a.output is None:
            p.error('--output required')
        print(rec.canonical(run(a.release, a.output, a.base_url)).decode())


if __name__ == '__main__':
    main()
