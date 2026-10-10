"""Offline evidence gate for a separate white action after one rejected MIDDLE ARM.

This admits only the observed pre-dispatch review failure. It never converts a
FAULT into COMPLETE, clears NVS/claims, authorizes a refresh, or resumes LH1.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from tools import mf1750_lh1_lh4_once_operator_v2 as base

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.test-output/hardware/LH1_SOURCE_FIELD_20260913_V3'
MIDDLE = SOURCE / 'MIDDLE_ORD2_20260913_V1'
PACKAGE = ROOT / '.test-output/offline/LH1_LH4_20260912_R1'
CLAIM = ROOT / '.test-output/hardware/.mf1750_lh1_lh4_source_claims/c1655f44acc748fb2eb152aaa739eeda8344ed16e1ef10be5aca1a9d1ca4a039.json'
BOOT = '30a9e5989873f4e0'
ERROR = 'prior_review_cannot_reuse_white'


def record(path):
    value = base.parse_json(Path(path).read_bytes())
    base.verify_integrity(value)
    return value


def transcript(path, method, suffix, expected):
    meta = record(path)
    base._require(meta, {'method': method, 'status': expected,
                        'request_body_bytes': 0}, 'HTTP evidence')
    if not meta['url'].endswith('/api/ec5/lightness-history-v1/' + suffix):
        raise base.RunnerError('foreign HTTP route')
    return base.parse_json(base.read_bound(meta['response_body'])), meta


def check_fault(ctx, field, status, report, *, relay_off):
    base._identity(ctx, status, field, latched=True)
    base._identity(ctx, report, field, latched=True)
    base._nvs(status)
    base._require(status, {
        'boot_nonce': BOOT, 'state': 'fault_locked', 'phase': 3,
        'phase_name': 'FAULT', 'cursor_raw': 770, 'next_ordinal': 2,
        'arm_request_count': 2, 'execute_request_count': 1,
        'total_driver_call_count': 1, 'execute_pending': False,
        'cursor_valid': True, 'campaign_complete': False,
        'campaign_boot_matches_current': True, 'persisted_campaign_boot_nonce': BOOT,
        'rst': 0, 'cs': 0, 'cs2': 0,
    }, 'pre-dispatch MIDDLE fault status')
    if relay_off:
        base._require(status, {'busy': 0}, 'relay OFF status')
    action = ctx['contract']['actions'][1]
    base._require(report, {
        'boot_nonce': BOOT, 'ordinal': 2, 'action_id': action['action_id'],
        'descriptor_id': action['descriptor_id'], 'role': 'LH1_MIDDLE',
        'source_state': 'LH1_SOURCE', 'target_state': 'LH1_MIDDLE',
        'profile_id': action['profile_id'], 'profile_sha256': action['profile_sha256'],
        'valid': False, 'terminal_state': 'FAULT', 'result': False, 'error': ERROR,
        'driver_called': False, 'driver_call_count_for_action': 0,
        'total_driver_call_count': 1, 'phase': 3, 'next_ordinal': 2,
        'no_retry': True, 'no_recovery': True,
    }, 'pre-dispatch MIDDLE fault report')
    if 'driver' in report:
        raise base.RunnerError('unexpected MIDDLE driver evidence')


def evaluate(current_observation: Path) -> dict:
    ctx = base.validate_package(PACKAGE)
    claim = record(CLAIM)
    field = base.parse_json(base.read_bound(claim['evidence']))
    base.verify_integrity(field)
    base._require(claim, {'boot_nonce': BOOT,
        'contract_id': ctx['contract']['contract_id'],
        'action_id': ctx['contract']['actions'][0]['action_id'],
        'state': 'permanently_consumed_before_first_arm',
        'firmware': ctx['firmware'], 'elf': ctx['elf']}, 'original SOURCE claim')
    reconciliation = record(SOURCE / 'terminal-reconciliation.json')
    base._require(reconciliation, {'boot_nonce': BOOT,
        'protocol_terminal_validation': 'PASS', 'safe_finish_pass': True,
        'original_runner_result_synthesized': False, 'retry_mutation': False}, 'SOURCE reconciliation')
    source_status = base.parse_json(base.read_bound(reconciliation['raw_status']))
    source_report = base.parse_json(base.read_bound(reconciliation['raw_report']))
    base.validate_terminal(ctx, source_report, source_status, field)
    for ordinal, suffix, code in ((5, 'arm', 201), (6, 'execute', 202)):
        value, meta = transcript(SOURCE / f'source-once/{ordinal:03d}-post-{suffix}.json', 'POST', suffix, code)
        base._identity(ctx, value, field, latched=True)
        base._require(value, {'accepted': True, 'ordinal': 1,
            'action_id': ctx['contract']['actions'][0]['action_id']}, 'actual SOURCE ACK')
        nonce = meta['headers'].get('X-EC5-Arm-Nonce') if suffix == 'execute' else None
        if meta['headers'] != base.mutation_headers(ctx, field, arm_nonce=nonce):
            raise base.RunnerError('original SOURCE request headers differ')
    if not (SOURCE / 'source-once/STOP.json').is_file() or (SOURCE / 'source-once/result.json').exists():
        raise base.RunnerError('original SOURCE transport failure was replaced')
    failed_dir = MIDDLE / 'live2'
    ack, failed_request = transcript(failed_dir / '005-post-arm.json', 'POST', 'arm', 400)
    base._require(ack, {'accepted': False, 'fault_locked': True,
        'error': ERROR, 'no_retry': True, 'no_recovery': True}, 'actual rejected ARM')
    base._require(failed_request['headers'], {
        'X-EC5-Ordinal': '2', 'X-EC5-Boot-Nonce': BOOT,
        'X-EC5-Action-Id': ctx['contract']['actions'][1]['action_id'],
        'X-LH-Source-Review': field['source_review_sha256'],
        'X-LH-Prior-Review': field['source_review_sha256'],
    }, 'actual MIDDLE fault trigger')
    if list(failed_dir.glob('*post-execute*')):
        raise base.RunnerError('MIDDLE EXECUTE evidence exists')
    historical_status = base.parse_json((MIDDLE / 'post-fault-readonly/001-get-status.body.bin').read_bytes())
    historical_report = base.parse_json((MIDDLE / 'post-fault-readonly/002-get-report.body.bin').read_bytes())
    check_fault(ctx, field, historical_status, historical_report, relay_off=True)
    current = record(current_observation)
    base._require(current, {'kind': 'mf1750-lh1-current-fault-observation-v1',
        'network': {'get': 4, 'post': 0}, 'mutations_performed': 0,
        'driver_calls': 0, 'visible_refreshes': 0}, 'current observation')
    bodies = {}
    for item in current['transcripts']:
        base.read_bound(item)
        path = Path(item['path'])
        if path.name.endswith('.json'):
            suffix = path.stem.split('-')[-1]
            value, meta = transcript(path, 'GET', suffix, 200)
            if meta['headers'] != {} or meta['url'] != current['base_url'] + ctx['routes'][suffix]:
                raise base.RunnerError('current read-only request differs')
            bodies[suffix] = value
    if set(bodies) != {'version', 'manifest', 'status', 'report'} or bodies != current['responses']:
        raise base.RunnerError('current observation not bound to all four raw responses')
    check_fault(ctx, field, bodies['status'], bodies['report'], relay_off=True)
    paths = [CLAIM, SOURCE / 'terminal-reconciliation.json', SOURCE / 'source-once/STOP.json',
             failed_dir / 'STOP.json', failed_dir / '005-post-arm.json',
             MIDDLE / 'post-fault-readonly/001-get-status.body.bin',
             MIDDLE / 'post-fault-readonly/002-get-report.body.bin', current_observation]
    return base.seal({'kind': 'mf1750-lh1-middle-fault-source-gate-v1',
        'recorded_at': datetime.now(timezone.utc).isoformat(), 'result': 'PASS',
        'scope': 'OFFLINE_PRE_DISPATCH_FAULT_RECOVERY_ELIGIBILITY_ONLY',
        'source_boot': BOOT, 'source_fault_cursor': 770,
        'source_complete_driver_count': 1, 'middle_driver_count': 0,
        'main_campaign_resume_allowed': False, 'source_stop_preserved': True,
        'source_result_synthesized': False, 'source_claim_preserved': True,
        'source_nvs_write_or_clear': False, 'white_action_performed': False,
        'qualified_count': 0, 'hardware_accessed': False, 'live_ready': False,
        'bindings': [base.file_binding(p) for p in paths],
        'limitation': 'Exact raw protocol and claim evidence only; current optical and physical admission remain separate.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current-observation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = evaluate(args.current_observation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    base.write_new(args.output, value)
    print(value['result'])


if __name__ == '__main__':
    main()
