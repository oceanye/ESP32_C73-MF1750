#!/usr/bin/env python3
"""Strict offline SOURCE admission for the separately built white successor.

The future white action and its WF23_25 profile are not the completed LH1
SOURCE action.  This gate replays an actual LH1 result envelope, permanent
claim and byte-backed HTTP transcript.  It never evaluates physical admission
or performs network/device I/O.  A PASS does not authorize recovery.  This gate
is used after SOURCE1, before a separately authorized white successor; it is
not the offline successor-preparedness gate required before SOURCE1 starts.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import mf1750_lh1_lh4_once as lh1  # noqa: E402


class SourceGateError(ValueError):
    """Missing, ambiguous or inconsistent historical SOURCE evidence."""


def _require(value: dict, expected: dict, label: str) -> None:
    lh1._require(value, expected, label)


def _record(binding: dict) -> dict:
    value = lh1.parse_json(lh1.read_bound(binding))
    lh1.verify_integrity(value)
    return value


def _path(binding: dict) -> Path:
    path = Path(binding['path'])
    return (path if path.is_absolute() else ROOT / path).resolve()


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError) as exc:
        raise SourceGateError('valid evidence timestamp required') from exc
    if parsed.tzinfo is None:
        raise SourceGateError('timezone-aware evidence timestamp required')
    return parsed


def source_context(contract_path: Path) -> tuple[dict, dict]:
    """Derive SOURCE identity from its sealed build, never future white IDs."""
    successor = lh1.read_record(contract_path)
    _require(successor, {'kind': 'mf1750-lh1-source-white-contract-v1',
                        'accepted_source_ordinals': [1],
                        'source_terminal_host_gate_required': True,
                        'source_nvs_is_not_terminal_proof': True,
                        'live_action_authorized': False,
                        'source_nvs': {'namespace': 'lhist_v1', 'cursor_key': 'cur_lh1',
                                       'complete_cursor': 2, 'boot_key': 'boot_lh1'}}, 'successor source contract')
    # The generator hashes the contract before adding derived identity fields.
    basis = {k: v for k, v in successor.items() if k not in (
        'integrity', 'contract_id', 'descriptor_id', 'action_id', 'compiled_marker')}
    contract_id = lh1.digest(lh1.canonical(basis))
    descriptor = lh1.digest(lh1.canonical({'contract': contract_id,
        'role': 'LH1_SOURCE_POST_TEST_WHITE', 'profile': 'WF23_25'}))
    action_id = lh1.digest(lh1.canonical({'descriptor': descriptor, 'ordinal': 1,
        'source_action': successor['source_action_id']}))
    _require(successor, {'contract_id': contract_id, 'descriptor_id': descriptor,
                        'action_id': action_id, 'profile_id': 'WF23_25',
                        'compiled_marker': 'MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE_AFTER_LH1_SOURCE_ORDINAL1_COMPLETE|SHA256=' + descriptor}, 'successor derived identity')
    _record(successor['source_build'])
    ctx = lh1.validate_package(_path(successor['source_build']).parent)
    action = ctx['contract']['actions'][0]
    _require(successor, {'source_build': ctx['build_binding'],
                        'source_firmware': ctx['firmware'], 'source_elf': ctx['elf'],
                        'source_contract_id': ctx['contract']['contract_id'],
                        'source_campaign_id': ctx['contract']['campaign_id'],
                        'source_action_id': action['action_id']}, 'actual LH1 source binding')
    _require(action, {'ordinal': 1, 'stage': 'SOURCE', 'role': 'LH1_SOURCE',
                     'source_state': 'FRESH_P2_FACTORY_WHITE', 'target_state': 'LH1_SOURCE'}, 'SOURCE action')
    if action['action_id'] == successor['action_id'] or action['profile_id'] == successor['profile_id']:
        raise SourceGateError('source and future white identities are conflated')
    return successor, ctx


def _transcript(metadata_binding: dict, *, expected_directory: Path | None = None) -> dict:
    meta = _record(metadata_binding)
    path = _path(metadata_binding)
    match = re.fullmatch(r'(\d{3})-(get|post)-(version|manifest|status|report|arm|execute)\.json', path.name)
    if not match:
        raise SourceGateError('unexpected transcript name')
    index, method, route = match.groups()
    body_path = path.with_suffix('.body.bin')
    if expected_directory is not None and path.parent != expected_directory:
        raise SourceGateError('transcript is outside immutable claim output')
    if _path(meta['response_body']) != body_path:
        raise SourceGateError('response body path differs from transcript')
    raw = lh1.read_bound(meta['response_body'])
    start, end = _timestamp(meta['started_at']), _timestamp(meta['finished_at'])
    if start > end:
        raise SourceGateError('response finishes before request start')
    _require(meta, {'method': method.upper(), 'request_body_bytes': 0}, 'bodyless transcript')
    return {'index': int(index), 'route': route, 'method': method.upper(), 'metadata': meta,
            'metadata_binding': metadata_binding, 'value': lh1.parse_json(raw),
            'started': start, 'finished': end}


def _diagnostic(ctx: dict, claim: dict, field: dict) -> dict:
    """Replay historical diagnosis without applying live freshness/physical gates."""
    diagnostic = _record(claim['diagnostic'])
    _require(diagnostic, {'kind': 'mf1750-lh1-lh4-j2-off-diagnostic-v1', 'result': 'PASS',
        'contract_id': ctx['contract']['contract_id'], 'package_build': ctx['build_binding'],
        'firmware': ctx['firmware'], 'elf': ctx['elf'], 'base_url': field['base_url'],
        'boot_nonce': field['boot_nonce'], 'run_id': field['run_id'],
        'source_review_sha256': field['source_review_sha256'],
        'network': {'get': 4, 'post': 0}, 'busy': 0, 'driver_calls': 0,
        'visible_refreshes': 0, 'claim_created': False}, 'historical diagnosis')
    off_field = _record(diagnostic['evidence'])
    for key in ('run_id', 'source_review_sha256', 'app_flash_record', 'current_white_review'):
        _require(off_field, {key: field[key]}, 'off/on identity binding')
    bindings = diagnostic.get('transcripts')
    if not isinstance(bindings, list) or len(bindings) != 8:
        raise SourceGateError('diagnosis must bind four metadata/body pairs')
    names = {_path(item).name: item for item in bindings}
    if len(names) != 8:
        raise SourceGateError('duplicate diagnostic transcript reference')
    previous = None
    for index, route in enumerate(('version', 'manifest', 'status', 'report'), 1):
        stem = f'{index:03d}-get-{route}'
        item = _transcript(names[stem + '.json'])
        _require(item['metadata'], {'url': field['base_url'] + ctx['routes'][route], 'status': 200,
                  'headers': {}, 'response_body': names[stem + '.body.bin']}, 'diagnostic transcript')
        _require(diagnostic['responses'], {route: item['value']}, 'diagnostic raw response')
        if previous is not None and item['started'] < previous:
            raise SourceGateError('diagnostic chronology differs')
        previous = item['finished']
    lh1.validate_four_get(ctx, diagnostic['responses'], field, busy=0)
    if previous > _timestamp(diagnostic['recorded_at']) or _timestamp(diagnostic['recorded_at']) > _timestamp(claim['recorded_at']):
        raise SourceGateError('diagnostic/claim chronology differs')
    return diagnostic


def validate_source(contract_path: Path, candidate_path: Path) -> dict:
    successor, ctx = source_context(Path(contract_path))
    candidate_path = Path(candidate_path).resolve()
    envelope = lh1.read_record(candidate_path)
    if candidate_path.name != 'result.json':
        raise SourceGateError('actual runner result.json envelope required')
    _require(envelope, {'kind': 'mf1750-lh1-lh4-source-result-v1', 'outcome': 'complete_pass',
        'ordinal': 1, 'contract_id': ctx['contract']['contract_id'],
        # This is the LH1 runner's upstream WHITE anchor, not the SOURCE action.
        'source_action_id': ctx['source']['action_id'], 'driver_calls': 1,
        'visible_refreshes': 1, 'qualified_count': 0, 'next_action_authorized': False,
        'stop_and_review_required': True}, 'SOURCE result envelope')
    claim = _record(envelope['claim'])
    if _path(envelope['claim']) != lh1.claim_path(ctx).resolve():
        raise SourceGateError('claim is not the fixed source-wide permanent claim')
    if Path(claim['output']).resolve() != candidate_path.parent:
        raise SourceGateError('result is outside permanent claim output')
    _require(claim, {'kind': 'mf1750-lh1-lh4-source-consumption-claim-v1',
        'state': 'permanently_consumed_before_first_arm', 'write_contract': 'O_EXCL',
        'contract_id': ctx['contract']['contract_id'], 'action_id': ctx['contract']['actions'][0]['action_id'],
        'source_campaign_id': ctx['source']['campaign_id'], 'source_action_id': ctx['source']['action_id'],
        'firmware': ctx['firmware'], 'elf': ctx['elf']}, 'permanent SOURCE claim')
    field = _record(claim['evidence'])
    _require(field, {'kind': 'mf1750-lh1-lh4-field-evidence-v1',
        'contract_id': ctx['contract']['contract_id'], 'boot_nonce': claim['boot_nonce'],
        'run_id': claim['run_id']}, 'claimed field identity')
    if not isinstance(claim['boot_nonce'], str) or not lh1.NONCE.fullmatch(claim['boot_nonce']) or claim['boot_nonce'] == '0' * 16:
        raise SourceGateError('valid SOURCE boot nonce required')
    if not isinstance(claim['run_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', claim['run_id']):
        raise SourceGateError('valid SOURCE run ID required')
    if not isinstance(field.get('source_review_sha256'), str) or not lh1.HEX.fullmatch(field['source_review_sha256']):
        raise SourceGateError('claimed review digest required')
    lh1.origin(field['base_url'])
    _record(field['current_white_review'])
    if field['current_white_review']['sha256'] != field['source_review_sha256']:
        raise SourceGateError('claimed review bytes differ from request review digest')
    # These are byte/protocol bindings only. In particular, never call
    # validate_evidence() or substitute synthetic sensor data for real readings.
    diagnostic = _diagnostic(ctx, claim, field)
    lh1.validate_terminal(ctx, envelope['terminal'], envelope['status'], field)
    _require(envelope['status'], {'campaign_complete': False, 'campaign_boot_key_present': True,
        'fixture_self_check_passed': True, 'device_enforced_same_boot': True,
        'reboot_resume_allowed': False, 'post_containment_resume_allowed': False}, 'SOURCE final status')
    lh1._nvs(envelope['status'])
    output = candidate_path.parent
    if (output / 'STOP.json').exists() or any(output.glob('*.error.json')):
        raise SourceGateError('failed/uncertain invocation cannot be admitted')
    files = sorted(p for p in output.glob('*.json') if re.fullmatch(r'\d{3}-(get|post)-.*\.json', p.name))
    transcript = [_transcript(lh1.file_binding(p), expected_directory=output) for p in files]
    if len(transcript) < 8 or [v['index'] for v in transcript] != list(range(1, len(transcript) + 1)):
        raise SourceGateError('complete contiguous runner transcript required')
    sequence = [(v['method'], v['route']) for v in transcript]
    first = [('GET', key) for key in ('version', 'manifest', 'status', 'report')]
    if sequence[:6] != first + [('POST', 'arm'), ('POST', 'execute')] or sequence[-1] != ('GET', 'report') or any(v != ('GET', 'status') for v in sequence[6:-1]):
        raise SourceGateError('expected four GET, one ARM, one EXECUTE, status polls, terminal report')
    if len(transcript[6:-1]) > lh1.MAX_STATUS_POLLS:
        raise SourceGateError('status polls exceed actual runner limit')
    counts = {'get': sum(v['method'] == 'GET' for v in transcript),
              'post': sum(v['method'] == 'POST' for v in transcript)}
    _require(envelope, {'network': counts}, 'recorded request counts')
    initial = {v['route']: v['value'] for v in transcript[:4]}
    lh1.validate_four_get(ctx, initial, field, busy=1)
    arm_nonce = transcript[4]['value'].get('arm_nonce')
    if not isinstance(arm_nonce, str) or not lh1.NONCE.fullmatch(arm_nonce) or arm_nonce == '0' * 16:
        raise SourceGateError('valid ARM nonce required')
    previous = _timestamp(diagnostic['recorded_at'])
    for item in transcript:
        method, route, meta = item['method'], item['route'], item['metadata']
        wanted_status = 201 if route == 'arm' else 202 if route == 'execute' else 200
        headers = lh1.mutation_headers(ctx, field, arm_nonce=arm_nonce if route == 'execute' else None) if method == 'POST' else {}
        _require(meta, {'url': field['base_url'] + ctx['routes'][route],
                       'status': wanted_status, 'headers': headers}, 'request/response transcript')
        if item['started'] < previous:
            raise SourceGateError('request chronology differs')
        previous = item['finished']
    if not transcript[3]['finished'] <= _timestamp(claim['recorded_at']) <= transcript[4]['started']:
        raise SourceGateError('claim was not reserved after four GET and before ARM')
    for index, executing in ((4, False), (5, True)):
        ack = transcript[index]['value']
        lh1._identity(ctx, ack, field, latched=True)
        _require(ack, lh1.expected_action(ctx), 'actual SOURCE acknowledgement')
        _require(ack, {'accepted': True, 'boot_nonce': claim['boot_nonce'],
            'phase': 2 if executing else 1, 'phase_name': 'CONSUMED' if executing else 'ARMED'}, 'acknowledgement phase')
        _require(ack, {'execute_consumed': True, 'job_id': 1, 'no_retry': True, 'no_recovery': True}
                 if executing else {'armed': True, 'not_hardware_authorization': True}, 'acknowledgement semantics')
    for item in transcript[6:-1]:
        status = item['value']
        lh1._identity(ctx, status, field, latched=True)
        _require(status, {'schema_version': 3, 'kind': 'mf1750-lightness-history-v1-status',
            'boot_nonce': claim['boot_nonce'], 'arm_request_count': 1, 'execute_request_count': 1,
            'cursor_valid': True, 'campaign_boot_matches_current': True,
            'persisted_campaign_boot_nonce': claim['boot_nonce']}, 'SOURCE status poll')
        if type(status.get('total_driver_call_count')) is not int or status['total_driver_call_count'] not in (0, 1):
            raise SourceGateError('invalid in-flight driver count')
        final = item is transcript[-2]
        valid_phase = (type(status.get('phase')) is int and
                       status['phase'] in ((0,) if final else (1, 2)))
        if not valid_phase or type(status.get('next_ordinal')) is not int or status['next_ordinal'] != (2 if final else 1):
            raise SourceGateError('fault/foreign cursor in status transcript')
    _require(envelope, {'status': transcript[-2]['value'], 'terminal': transcript[-1]['value']}, 'terminal raw byte binding')
    if previous > _timestamp(envelope['recorded_at']):
        raise SourceGateError('result precedes final raw response')
    return {'source_contract_id': ctx['contract']['contract_id'],
            'source_action_id': ctx['contract']['actions'][0]['action_id'],
            'source_descriptor_id': ctx['contract']['actions'][0]['descriptor_id'],
            'source_profile_id': ctx['contract']['actions'][0]['profile_id'],
            'future_white_action_id': successor['action_id'],
            'white_origin_action_id': ctx['source']['action_id'],
            'boot_nonce': claim['boot_nonce'], 'run_id': claim['run_id'],
            'source_firmware': ctx['firmware'], 'source_elf': ctx['elf'],
            'claim': envelope['claim'], 'source_build': ctx['build_binding'],
            'cursor_raw': 2, 'campaign_complete': False, 'pending_ordinals': [2, 3],
            'network_recorded_by_source_runner': counts,
            'raw_transcripts': [v['metadata_binding'] for v in transcript]}


def evaluate(contract_path: Path, candidate_path: Path) -> dict:
    review = {'schema_version': 2, 'kind': 'mf1750-lh1-source-white-source-gate-v2',
        'scope': 'OFFLINE_HISTORICAL_SOURCE_PROTOCOL_ONLY', 'result': 'FAIL_STOP',
        'hardware_accessed': False, 'network_accessed': False, 'live_ready': False,
        'recovery_authorized': False, 'physical_admission_evaluated': False,
        'electrical_state_proven': False, 'qualified_count': 0,
        'checks': {}, 'failures': [],
        'evidence_boundary': 'PASS verifies sealed historical SOURCE1 identity, permanent claim and raw protocol consistency. It does not authenticate physical measurements, prove electrical/optical safety, authorize white recovery or resume MIDDLE/TARGET.'}
    try:
        review['contract'] = lh1.file_binding(contract_path)
        review['candidate'] = lh1.file_binding(candidate_path)
        review['checks'] = validate_source(contract_path, candidate_path)
        review['result'] = 'PASS'
    except (lh1.RunnerError, SourceGateError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        review['failures'].append(str(exc))
    return lh1.seal(review)


def write_review(path: Path, review: dict) -> dict:
    lh1.verify_integrity(review)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lh1.write_new(path, review)
    return review


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = write_review(args.output, evaluate(args.contract, args.candidate))
    except (OSError, ValueError, lh1.RunnerError) as exc:
        print('SOURCE gate stopped: ' + str(exc), file=sys.stderr)
        return 2
    return 0 if result['result'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
