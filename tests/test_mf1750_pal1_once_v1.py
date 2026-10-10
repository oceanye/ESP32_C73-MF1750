"""Offline PAL1 runner tests; no device, camera, relay or network I/O.

Wire documents are adapted from the sealed strict-native audit
PAL1_CAL_NATIVE_20260925_R2 (desktop stub, auditing the real sealed PAL1
V5 package): identity fields are rewritten to the sealed PAL1 package contract.
The stub's 255-sentinel BUSY trace is never admissible; the terminal driver
section uses the real historical BUSY trace from the LH1 rebound V2
same-generator run with fnv1a fields patched to the PAL1 contract values whose
offline binding the native audit already proved.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import mf1750_lh1_lh4_once_operator_v2 as b
from tools import mf1750_pal1_once_v1 as host

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / '.test-output/offline/PAL1_CAL_20260925_R2'
NATIVE = ROOT / '.test-output/offline/PAL1_CAL_NATIVE_20260925_R2/strict-native-audit.json'
HISTORICAL = ROOT / '.test-output/hardware/LH1_REBOUND_20260916_V2/LIVE_RUN_R4/008-get-report.body.bin'
BOOT = '0000000200000009'
RUN = 'PAL1_UNIT_TEST_NO_HARDWARE'
BASE = 'http://192.168.1.4'


@pytest.fixture(scope='module')
def ctx():
    return host.validate_package(PACKAGE)


@pytest.fixture(scope='module')
def native():
    return json.loads(NATIVE.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def real_driver():
    return json.loads(HISTORICAL.read_text(encoding='utf-8'))['driver']


def _adapt(doc, ctx):
    doc['contract_id'] = ctx['contract']['contract_id']
    doc['compiled_identity_marker'] = ctx['identity']['compiled_identity_marker']
    return doc


def _latched(doc, ctx):
    doc['run_id'] = RUN
    doc['source_review_sha256'] = ctx['anchor']
    doc['prior_review_sha256'] = ctx['anchor']
    return doc


def terminal_report(ctx, native, real_driver):
    doc = copy.deepcopy(native['cases']['chain']['documents'][0]['json'])
    _adapt(doc, ctx)
    _latched(doc, ctx)
    a = ctx['contract']['actions'][0]
    doc['action_id'] = a['action_id']
    doc['descriptor_id'] = a['descriptor_id']
    doc['boot_nonce'] = BOOT
    driver = copy.deepcopy(real_driver)
    driver['operation_id'] = 1
    driver['input_fnv1a'] = a['frame']['fnv1a']
    driver['cs1_dtm_fnv1a'] = a['cs1_dtm']['fnv1a']
    driver['cs2_dtm_fnv1a'] = a['cs2_dtm']['fnv1a']
    doc['driver'] = driver
    doc['job_queued_at_ms'] = 0
    doc['job_started_at_ms'] = 1
    doc['job_finished_at_ms'] = 2
    return doc


def terminal_status(ctx, native):
    doc = copy.deepcopy(native['cases']['chain']['documents'][1]['json'])
    _adapt(doc, ctx)
    _latched(doc, ctx)
    doc['boot_nonce'] = BOOT
    doc['persisted_campaign_boot_nonce'] = BOOT
    doc.update(busy=1, rst=0, cs=0, cs2=0)
    return doc


def poll_status(ctx, native, phase):
    doc = copy.deepcopy(native['cases']['chain']['documents'][1]['json'])
    _adapt(doc, ctx)
    _latched(doc, ctx)
    doc['boot_nonce'] = BOOT
    doc['persisted_campaign_boot_nonce'] = BOOT
    doc.update(phase=phase, phase_name={2: 'CONSUMED', 3: 'FAULT'}[phase],
               state={2: 'consumed', 3: 'fault_locked'}[phase],
               cursor_raw=(phase << 8) | 1, next_ordinal=1,
               arm_request_count=1, execute_request_count=1,
               total_driver_call_count=0)
    return doc


def preflight_gets(ctx, native):
    docs = [copy.deepcopy(d['json']) for d in native['cases']['read_only']['documents']]
    version, manifest, status, report = docs
    for doc in docs:
        _adapt(doc, ctx)
        doc['run_id'] = ''
        doc['source_review_sha256'] = ''
        doc['prior_review_sha256'] = ''
    want = ctx['contract']['actions'][0]
    manifest['actions'][0]['action_id'] = want['action_id']
    manifest['actions'][0]['descriptor_id'] = want['descriptor_id']
    status['boot_nonce'] = BOOT
    status['persisted_campaign_boot_nonce'] = BOOT
    report['boot_nonce'] = BOOT
    return {'version': version, 'manifest': manifest, 'status': status, 'report': report}


def ack(ctx, route):
    base = {**ctx['identity'], 'waveform_internal_phase': 'OPAQUE', 'qualified_count': 0,
            'source_nvs_complete': True, 'review_digests_are_host_assertions_only': True,
            'run_id': RUN, 'source_review_sha256': ctx['anchor'],
            'prior_review_sha256': ctx['anchor'], 'boot_nonce': BOOT,
            **host.expected_action(ctx)}
    if route == 'arm':
        return {**base, 'accepted': True, 'armed': True, 'phase': 1, 'phase_name': 'ARMED',
                'arm_nonce': '0000000400000005', 'not_hardware_authorization': True}
    return {**base, 'accepted': True, 'execute_consumed': True, 'phase': 2,
            'phase_name': 'CONSUMED', 'job_id': 1, 'no_retry': True, 'no_recovery': True}


class Transport:
    def __init__(self, rows, claim=None):
        self.rows = rows
        self.calls = []
        self.claim = claim

    def __call__(self, method, url, headers, timeout):
        index = len(self.calls)
        self.calls.append((method, url, headers))
        assert index < len(self.rows), 'automatic extra request/chain'
        row = self.rows[index]
        if method == 'POST':
            assert self.claim is not None and self.claim.exists(), 'mutation before permanent claim'
        if isinstance(row, tuple):
            return row[0], b.canonical(row[1])
        code = 201 if url.endswith('/arm') else 202 if method == 'POST' else 200
        return code, b.canonical(row)


def make_field(tmp_path, ctx, *, release_live=True):
    now = datetime.now(timezone.utc).isoformat()
    a = ctx['contract']['actions'][0]
    slot = len(list(tmp_path.glob('field-*.json')))

    def sealed(name, value):
        path = tmp_path / ('%s-%d.json' % (name, slot))
        b.write_new(path, b.seal(value))
        return b.file_binding(path)

    photo = tmp_path / ('photo-%d.bin' % slot)
    photo.write_bytes(b'synthetic full-panel observation')
    field = {'kind': 'mf1750-pal1-field-v1', 'recorded_at': now,
        'contract_id': ctx['contract']['contract_id'], 'ordinal': 1,
        'action_id': a['action_id'], 'descriptor_id': a['descriptor_id'],
        'base_url': BASE, 'run_id': RUN, 'boot_nonce': BOOT,
        'authorized_refreshes': 1, 'stop_after_action': True, 'autochain': False,
        'retry': False, 'live_release': True, 'electrical_state_proven': False,
        'electrical_policy': 'RECORD_ONLY_BY_EXPLICIT_USER_INSTRUCTION',
        'dependencies': host.dependencies(), 'native_audit': b.file_binding(NATIVE),
        'ip_binding': sealed('ip', {'kind': 'mf1750-exact-ipv4-mac-binding-attempt-v1',
            'candidate_ipv4': '192.168.1.4', 'expected_mac': 'A4-CB-8F-D9-FC-D4',
            'binding_passed': True, 'fresh_binding_passed': True, 'finished_at': now}),
        'camera_review': sealed('camera', {'camera_usb_id': 'VID_32E4:PID_4801',
            'full_panel_visible': True, 'usable_for_state_review': True,
            'recorded_at': now, 'photo': b.file_binding(photo)}),
        'relay_on': sealed('relay', {'commanded_state': 'ON', 'channel': 1,
            'recorded_at': now}),
        'app_flash': sealed('flash', {'result': 'PASS',
            'firmware': ctx['firmware'], 'elf': ctx['elf'], 'app_only': True,
            'nvs_erased': False, 'raw_log': sealed('flash-log',
            {'tool': 'esptool', 'synthetic': True})}),
        'user_release': sealed('release', {'kind': 'mf1750-pal1-release-v1',
            'contract_id': ctx['contract']['contract_id'], 'ordinal': 1,
            'action_id': a['action_id'], 'authorized_refreshes': 1, 'stop_after_action': True,
            'live_release': release_live, 'scope': host.RELEASE_SCOPE,
            'authorization_messages': ['synthetic unit-test release']})}
    path = tmp_path / ('field-%d.json' % slot)
    b.write_new(path, b.seal(field))
    return path


def stage_rows(ctx, native, real_driver):
    pre = preflight_gets(ctx, native)
    return [pre['version'], pre['manifest'], pre['status'], pre['report'],
            ack(ctx, 'arm'), ack(ctx, 'execute'),
            terminal_status(ctx, native),
            terminal_report(ctx, native, real_driver)]


def test_validate_package_binds_sealed_contract(ctx):
    assert ctx['contract']['contract_id'] == '97087d969844d3bb3d13a70e647f4ea81d5950c2236cbdf093a4a6350945d730'
    assert ctx['anchor'] == '5dd81034bd9a963d89b91fc4ce9e7a01d8eaf4f99fc883e8ce0a3bc8f77dc9b0'
    assert ctx['firmware']['sha256'] == '0386f578e8d412c2f8b20b1249873764e6290c3cb15b98908f5f1cc38f460237'
    assert ctx['elf']['sha256'] == '8e83006a8785a5261fb50496a371836780fab53da072eb6c650452b3f21c8dc5'
    assert ctx['routes']['arm'].endswith('/lightness-history-v1/arm')
    assert len(ctx['contract']['actions']) == 1
    assert ctx['contract']['actions'][0]['global_header'] == 'active'
    assert ctx['contract']['nvs'] == {'namespace': 'pal1_v5', 'cursor': 'cur_pal5',
                                      'boot': 'boot_pal5'}
    v2 = ctx['contract']['pal1_v2_gate_mismatch_preservation']
    assert v2['inferred_cursor_fault_769'] is True
    v4 = ctx['contract']['pal1_v4_dead_preservation']
    assert v4['cursor_key_may_be_absent'] is True and v4['recoverable'] is False
    v1 = ctx['contract']['pal1_v1_fixture_defect_preservation']
    assert v1['expected_cursor_raw'] == 1 and v1['recoverable'] is False
    assert v1['cursor_key_may_be_absent'] is True
    v2 = ctx['contract']['pal1_v2_gate_mismatch_preservation']
    assert v2['namespace'] == 'pal1_v2' and v2['cursor_key_may_be_absent'] is True


def test_validate_package_rejects_missing_package(tmp_path):
    with pytest.raises(host.Error):
        host.validate_package(tmp_path)


def test_only_ordinal_one(ctx):
    assert host.expected_action(ctx)['controller_tuple_dispatch'] == 'AA'
    with pytest.raises(host.Error, match='single-action'):
        host.run(2, Path('never'), Path('never'), BASE,
                 transport=lambda *a: pytest.fail('ordinal 2 reached network'),
                 sleeper=lambda s: None, claims=None, package=PACKAGE)


def test_field_validation_standalone(tmp_path, ctx):
    field = make_field(tmp_path, ctx)
    assert host.validate_field(ctx, field, BASE)['ordinal'] == 1


def test_pending_release_never_reaches_network(tmp_path, ctx):
    field = make_field(tmp_path, ctx, release_live=False)
    with pytest.raises(host.Error, match='user release'):
        host.run(1, field, tmp_path / 'live', BASE,
                 transport=lambda *a: pytest.fail('pending release contacted network'),
                 sleeper=lambda s: None, claims=tmp_path / 'claims', package=PACKAGE)
    assert not (tmp_path / 'live').exists()


def test_full_single_action_chain(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    rows = stage_rows(ctx, native, real_driver)
    field = make_field(tmp_path, ctx)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    result = host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                      sleeper=lambda s: None, claims=claims, package=PACKAGE)
    assert result['protocol_verdict'] == 'PASS'
    assert result['campaign_complete'] is True
    assert result['further_contract_action_available'] is False
    assert result['network'] == {'GET': 6, 'POST': 2}
    posts = [h for m, u, h in transport.calls if m == 'POST']
    assert all(h['X-LH-Source-Review'] == ctx['anchor'] for h in posts)
    assert all(h['X-LH-Prior-Review'] == ctx['anchor'] for h in posts)
    assert all(h['X-EC5-Ordinal'] == '1' for h in posts)
    assert claim.exists()
    # Replay refuses before any request.
    field2 = make_field(tmp_path, ctx)
    before = len(transport.calls)
    with pytest.raises(host.Error, match='permanently claimed'):
        host.run(1, field2, tmp_path / 'replay', BASE,
                 transport=Transport([], None), sleeper=lambda s: None,
                 claims=claims, package=PACKAGE)
    assert len(transport.calls) == before
    assert not (tmp_path / 'replay').exists()


@pytest.mark.parametrize(('index', 'key', 'bad'), [
    (0, 'layout_id', 'LH3_DOSE_COLUMNS_8X8'),
    (2, 'cursor_raw', 2),
    (2, 'busy', 0),
    (3, 'valid', True),
])
def test_preflight_mismatch_zero_post(tmp_path, ctx, native, real_driver, index, key, bad):
    rows = stage_rows(ctx, native, real_driver)
    rows[index][key] = bad
    field = make_field(tmp_path, ctx)
    transport = Transport(rows, None)
    with pytest.raises(host.Error):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=tmp_path / 'claims', package=PACKAGE)
    assert all(m == 'GET' for m, u, h in transport.calls)
    assert not (tmp_path / 'claims').exists()


def test_terminal_fnv1a_tamper_stops_after_claim(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver)
    rows[7]['driver']['cs2_dtm_fnv1a'] = 0
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='driver'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims, package=PACKAGE)
    assert len(transport.calls) == 8 and claim.exists()
    stop = b.read_record(tmp_path / 'live' / 'STOP.json')
    assert stop['kind'] == 'mf1750-pal1-stop-v1'
    assert stop['claim_created'] is True and stop['no_retry'] is True


def test_fault_stops_immediately_and_never_resends(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver)[:6]
    rows.append(poll_status(ctx, native, 3))
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='FAULT'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims, package=PACKAGE)
    assert len(transport.calls) == 7


def test_cursor_not_advancing_exhausts_budget_without_resend(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver)[:6]
    rows += [poll_status(ctx, native, 2)] * host.MAX_POLLS
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='budget exhausted'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims, package=PACKAGE)
    assert len(transport.calls) == 6 + host.MAX_POLLS
    assert [m for m, u, h in transport.calls].count('POST') == 2


def test_device_rejection_ack_is_not_retried(tmp_path, ctx, native, real_driver):
    rejected = native['cases']['busy_arm']['documents'][0]['json']
    assert rejected['accepted'] is False and rejected['fault_locked'] is True
    rows = stage_rows(ctx, native, real_driver)
    rows[4] = (503, rejected)
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.http.MiddleRunnerError, match='HTTP 503'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims, package=PACKAGE)
    assert len(transport.calls) == 5  # ARM rejected: EXECUTE is never sent
    assert claim.exists()
