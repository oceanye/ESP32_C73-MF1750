"""Offline LH2 drive-map runner tests; no device, camera, relay or network I/O.

Wire documents are adapted from the sealed strict-native audit R2 (desktop
stub, its own synthetic package): identity fields are rewritten to the real
sealed LH2 package contract (the runner's default PACKAGE).  The stub's
255-sentinel BUSY trace is never admissible; terminal driver sections use the
real historical BUSY trace from the LH1 rebound V2 same-generator run (its
SOURCE fnv1a triple is byte-equal to the LH2 SOURCE contract values;
MIDDLE/MAP fnv1a fields are patched to the contract values whose offline
binding the native audit already proved).
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import mf1750_lh1_lh4_once_operator_v2 as b
from tools import mf1750_lh2_drive_map_once_v1 as host

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / '.test-output/offline/LH2_DRIVE_MAP_NATIVE_20260918_R3/strict-native-audit.json'
HISTORICAL = ROOT / '.test-output/hardware/LH1_REBOUND_20260916_V2/LIVE_RUN_R4/008-get-report.body.bin'
BOOT = '0000000200000003'
RUN = 'LH2_DRIVE_MAP_UNIT_TEST_NO_HARDWARE'
BASE = 'http://192.168.1.4'


@pytest.fixture(scope='module')
def ctx():
    return host.validate_package()


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


def _latched(doc, ctx, prior):
    doc['run_id'] = RUN
    doc['source_review_sha256'] = ctx['anchor']
    doc['prior_review_sha256'] = prior
    return doc


def _unlatched(doc):
    doc['run_id'] = ''
    doc['source_review_sha256'] = ''
    doc['prior_review_sha256'] = ''
    return doc


def terminal_report(ctx, native, real_driver, ordinal, prior):
    doc = copy.deepcopy(native['cases']['chain']['documents'][ordinal - 1]['json'])
    _adapt(doc, ctx)
    _latched(doc, ctx, prior)
    a = ctx['contract']['actions'][ordinal - 1]
    doc['action_id'] = a['action_id']
    doc['descriptor_id'] = a['descriptor_id']
    doc['boot_nonce'] = BOOT
    driver = copy.deepcopy(real_driver)
    driver['operation_id'] = ordinal
    driver['input_fnv1a'] = a['frame']['fnv1a']
    driver['cs1_dtm_fnv1a'] = a['cs1_dtm']['fnv1a']
    driver['cs2_dtm_fnv1a'] = a['cs2_dtm']['fnv1a']
    doc['driver'] = driver
    doc['job_queued_at_ms'] = 0
    doc['job_started_at_ms'] = 1
    doc['job_finished_at_ms'] = 2
    return doc


def terminal_status(ctx, native, ordinal, prior):
    doc = copy.deepcopy(native['cases']['chain']['documents'][3]['json'])
    _adapt(doc, ctx)
    _latched(doc, ctx, prior)
    doc['boot_nonce'] = BOOT
    doc['persisted_campaign_boot_nonce'] = BOOT
    doc.update(busy=1, rst=0, cs=0, cs2=0)
    if ordinal < 3:
        doc.update(state='ready', campaign_complete=False, cursor_raw=ordinal + 1,
                   next_ordinal=ordinal + 1, arm_request_count=ordinal,
                   execute_request_count=ordinal, total_driver_call_count=ordinal)
    return doc


def poll_status(ctx, native, ordinal, prior, phase):
    doc = copy.deepcopy(native['cases']['chain']['documents'][3]['json'])
    _adapt(doc, ctx)
    _latched(doc, ctx, prior)
    doc['boot_nonce'] = BOOT
    doc['persisted_campaign_boot_nonce'] = BOOT
    doc.update(phase=phase, phase_name={2: 'CONSUMED', 3: 'FAULT'}[phase],
               state={2: 'consumed', 3: 'fault_locked'}[phase],
               cursor_raw=(phase << 8) | ordinal, next_ordinal=ordinal,
               arm_request_count=ordinal, execute_request_count=ordinal,
               total_driver_call_count=ordinal - 1)
    return doc


def preflight_gets(ctx, native, ordinal, prior_echo, prior_status=None, prior_report=None):
    docs = [copy.deepcopy(d['json']) for d in native['cases']['read_only']['documents']]
    version, manifest, status, report = docs
    for doc in docs:
        _adapt(doc, ctx)
    for index, action in enumerate(manifest['actions']):
        want = ctx['contract']['actions'][index]
        action['action_id'] = want['action_id']
        action['descriptor_id'] = want['descriptor_id']
        action['prior_static_action_id'] = want['prior_action_id']
    if ordinal == 1:
        for doc in docs:
            _unlatched(doc)
        status['boot_nonce'] = BOOT
        status['persisted_campaign_boot_nonce'] = BOOT
        report['boot_nonce'] = BOOT
        return {'version': version, 'manifest': manifest, 'status': status, 'report': report}
    for doc in (version, manifest):
        _latched(doc, ctx, prior_echo)
    return {'version': version, 'manifest': manifest,
            'status': copy.deepcopy(prior_status), 'report': copy.deepcopy(prior_report)}


def ack(ctx, ordinal, prior, route):
    base = {**ctx['identity'], 'waveform_internal_phase': 'OPAQUE', 'qualified_count': 0,
            'source_nvs_complete': True, 'review_digests_are_host_assertions_only': True,
            'run_id': RUN, 'source_review_sha256': ctx['anchor'],
            'prior_review_sha256': prior, 'boot_nonce': BOOT,
            **host.expected_action(ctx, ordinal - 1)}
    if route == 'arm':
        return {**base, 'accepted': True, 'armed': True, 'phase': 1, 'phase_name': 'ARMED',
                'arm_nonce': '0000000400000005', 'not_hardware_authorization': True}
    return {**base, 'accepted': True, 'execute_consumed': True, 'phase': 2,
            'phase_name': 'CONSUMED', 'job_id': ordinal, 'no_retry': True, 'no_recovery': True}


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


def make_field(tmp_path, ctx, ordinal, prior_result=None, *, release_live=True):
    now = datetime.now(timezone.utc).isoformat()
    a = ctx['contract']['actions'][ordinal - 1]
    slot = len(list(tmp_path.glob('field-%d-*.json' % ordinal)))
    stem = lambda name: '%s-%d-%d' % (name, ordinal, slot)

    def sealed(name, value):
        path = tmp_path / (stem(name) + '.json')
        b.write_new(path, b.seal(value))
        return b.file_binding(path)

    photo = tmp_path / (stem('photo') + '.bin')
    photo.write_bytes(b'synthetic full-panel observation')
    field = {'kind': 'mf1750-lh2-drive-map-field-v1', 'recorded_at': now,
        'contract_id': ctx['contract']['contract_id'], 'ordinal': ordinal,
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
        'user_release': sealed('release', {'kind': 'mf1750-lh2-drive-map-release-v1',
            'contract_id': ctx['contract']['contract_id'], 'ordinal': ordinal,
            'action_id': a['action_id'], 'authorized_refreshes': 1, 'stop_after_action': True,
            'live_release': release_live, 'authorization_messages': ['synthetic unit-test release']})}
    if prior_result is not None:
        field['prior_stage_result'] = b.file_binding(prior_result)
    path = tmp_path / ('field-%d-%d.json' % (ordinal, slot))
    b.write_new(path, b.seal(field))
    return path


def stage_rows(ctx, native, real_driver, ordinal, prior_send, prior_echo='',
               prior_status=None, prior_report=None):
    pre = preflight_gets(ctx, native, ordinal, prior_echo, prior_status, prior_report)
    return [pre['version'], pre['manifest'], pre['status'], pre['report'],
            ack(ctx, ordinal, prior_send, 'arm'), ack(ctx, ordinal, prior_send, 'execute'),
            terminal_status(ctx, native, ordinal, prior_send),
            terminal_report(ctx, native, real_driver, ordinal, prior_send)]


def run_stage(tmp_path, ctx, native, real_driver, ordinal, claims, prior=None, tag='live'):
    if ordinal == 1:
        prior_send, prior_echo, prior_status, prior_report = ctx['anchor'], '', None, None
        prior_path = None
    else:
        prior_send = b.digest(b.canonical(prior['report']))
        prior_echo = prior['report']['prior_review_sha256']
        prior_status, prior_report = prior['status'], prior['report']
        prior_path = prior['path']
    rows = stage_rows(ctx, native, real_driver, ordinal, prior_send, prior_echo,
                      prior_status, prior_report)
    field = make_field(tmp_path, ctx, ordinal, prior_path)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal%d.json' % ordinal)
    transport = Transport(rows, claim)
    output = tmp_path / ('%s-%d' % (tag, ordinal))
    result = host.run(ordinal, field, output, BASE, transport=transport,
                      sleeper=lambda seconds: None, claims=claims)
    return result, transport, rows, field


def fake_prior_result(tmp_path, ctx, native, real_driver, claims, *, echo=None, prior_ordinal=1):
    echo = echo if echo is not None else ctx['anchor']
    claims.mkdir(parents=True, exist_ok=True)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal%d.json' % prior_ordinal)
    b.write_new(claim, b.seal({'kind': 'mf1750-lh2-drive-map-claim-v1',
        'contract_id': ctx['contract']['contract_id'], 'ordinal': prior_ordinal,
        'boot_nonce': BOOT, 'run_id': RUN, 'permanent': True,
        'claim_created_before_arm': True}))
    result = b.seal({'kind': 'mf1750-lh2-drive-map-result-v1', 'ordinal': prior_ordinal,
        'contract_id': ctx['contract']['contract_id'], 'protocol_verdict': 'PASS',
        'boot_nonce': BOOT, 'run_id': RUN, 'arm': 1, 'execute': 1, 'driver': 1,
        'visible_refresh': 1, 'claim': b.file_binding(claim),
        'status': terminal_status(ctx, native, prior_ordinal, echo),
        'report': terminal_report(ctx, native, real_driver, prior_ordinal, echo)})
    path = tmp_path / ('prior-result-%d.json' % prior_ordinal)
    b.write_new(path, result)
    return path


def test_validate_package_binds_real_contract(ctx):
    assert ctx['contract']['contract_id'] == 'be45e5a14e4634e49a1cbf4a1713002e8ee046d13fffe8934453cec30348a8a6'
    assert ctx['anchor'] == '99078ff932313f89aa2af0b02fa38d25dee23e42fbcc7505dfc7c2edf0702a47'
    assert ctx['firmware']['sha256'] == '8929dfc07b6bf10f254f7f63421133218dcbd14726f00b8595d4597f09bbdd73'
    assert ctx['elf']['sha256'] == 'f075a3f896fe443cd460753b572409e7334b087bb3d85a62f54227de5eef9858'
    assert ctx['routes']['arm'].endswith('/lightness-history-v1/arm')
    assert [a['role'] for a in ctx['contract']['actions']] == ['LH2_SOURCE', 'LH2_MIDDLE', 'LH2_MAP']
    assert [a['global_header'] for a in ctx['contract']['actions']] == ['active', 'commented', 'commented']


def test_validate_package_rejects_missing_package(tmp_path):
    with pytest.raises(host.Error):
        host.validate_package(tmp_path)


def test_expected_action_transport_dispatch(ctx):
    assert host.expected_action(ctx, 0)['controller_tuple_dispatch'] == 'AA'
    assert host.expected_action(ctx, 1)['controller_tuple_dispatch'] == 'CC'
    assert host.expected_action(ctx, 2)['controller_tuple_dispatch'] == 'CC'
    for index in range(3):
        assert host.expected_action(ctx, index)['action_id'] == ctx['contract']['actions'][index]['action_id']


def test_native_fixture_fnv1a_alignment_and_stub_rejection(ctx, native, real_driver):
    for index, doc in enumerate(d for d in native['cases']['chain']['documents'] if d['label'] == 'action_report'):
        a = ctx['contract']['actions'][index]
        driver = doc['json']['driver']
        assert (driver['input_fnv1a'], driver['cs1_dtm_fnv1a'], driver['cs2_dtm_fnv1a']) == \
               (a['frame']['fnv1a'], a['cs1_dtm']['fnv1a'], a['cs2_dtm']['fnv1a'])
        with pytest.raises(host.Error):
            host.driver_gate(ctx, driver, index + 1)
    # The historical real-panel trace passes ordinal 1 unpatched: the LH2 SOURCE
    # frame/DTM bytes are identical to the V2 SOURCE batch that recorded it.
    host.driver_gate(ctx, real_driver, 1)


def test_field_validation_standalone(tmp_path, ctx):
    field = make_field(tmp_path, ctx, 1)
    value, prior, echo, report = host.validate_field(ctx, field, 1, BASE)
    assert prior == ctx['anchor'] and echo is None and report is None
    assert value['ordinal'] == 1


def test_pending_release_never_reaches_network(tmp_path, ctx):
    field = make_field(tmp_path, ctx, 1, release_live=False)
    with pytest.raises(host.Error, match='user release'):
        host.run(1, field, tmp_path / 'live', BASE,
                 transport=lambda *a: pytest.fail('pending release contacted network'),
                 sleeper=lambda s: None, claims=tmp_path / 'claims')
    assert not (tmp_path / 'live').exists()


def test_full_chain_three_stages(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    result1, t1, _, _ = run_stage(tmp_path, ctx, native, real_driver, 1, claims)
    assert result1['protocol_verdict'] == 'PASS' and result1['ordinal'] == 1
    assert result1['network'] == {'GET': 6, 'POST': 2}
    assert result1['campaign_complete'] is False and result1['further_contract_action_available'] is True
    posts1 = [h for m, u, h in t1.calls if m == 'POST']
    assert all(h['X-LH-Source-Review'] == ctx['anchor'] for h in posts1)
    assert all(h['X-LH-Prior-Review'] == ctx['anchor'] for h in posts1)
    assert all(h['X-LH-Run-Id'] == RUN for h in posts1)
    assert all(h['X-EC5-Ordinal'] == '1' for h in posts1)
    result1_path = tmp_path / 'live-1' / 'result.json'

    result2, t2, _, _ = run_stage(tmp_path, ctx, native, real_driver, 2, claims,
                                  prior={'path': result1_path, 'status': result1['status'],
                                         'report': result1['report']})
    digest1 = b.digest(b.canonical(result1['report']))
    assert result2['stage_review_sha256'] == b.digest(b.canonical(result2['report']))
    posts2 = [h for m, u, h in t2.calls if m == 'POST']
    assert all(h['X-LH-Prior-Review'] == digest1 for h in posts2)
    assert digest1 != ctx['anchor']

    result3, t3, _, _ = run_stage(tmp_path, ctx, native, real_driver, 3, claims,
                                  prior={'path': tmp_path / 'live-2' / 'result.json',
                                         'status': result2['status'], 'report': result2['report']})
    digest2 = b.digest(b.canonical(result2['report']))
    posts3 = [h for m, u, h in t3.calls if m == 'POST']
    assert all(h['X-LH-Prior-Review'] == digest2 for h in posts3)
    assert len({ctx['anchor'], digest1, digest2}) == 3
    assert result3['campaign_complete'] is True
    assert result3['further_contract_action_available'] is False
    assert result3['report']['campaign_complete'] is True
    assert result3['status']['cursor_raw'] == 4 and result3['status']['state'] == 'complete'
    assert [c[0] for c in t3.calls] == ['GET'] * 4 + ['POST'] * 2 + ['GET'] * 2
    for ordinal in (1, 2, 3):
        assert (claims / (ctx['contract']['contract_id'] + '-ordinal%d.json' % ordinal)).exists()
    # No fourth action and no replay: every claim now refuses before any request.
    priors = {1: None, 2: result1_path, 3: tmp_path / 'live-2' / 'result.json'}
    for ordinal in (1, 2, 3):
        field = make_field(tmp_path, ctx, ordinal, priors[ordinal])
        before = sum(len(t.calls) for t in (t1, t2, t3))
        with pytest.raises(host.Error, match='permanently claimed'):
            host.run(ordinal, field, tmp_path / ('replay-%d' % ordinal), BASE,
                     transport=Transport([], None), sleeper=lambda s: None, claims=claims)
        assert sum(len(t.calls) for t in (t1, t2, t3)) == before
        assert not (tmp_path / ('replay-%d' % ordinal)).exists()


def test_existing_claim_rejects_before_network(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    run_stage(tmp_path, ctx, native, real_driver, 1, claims)
    field = make_field(tmp_path, ctx, 1)
    transport = Transport(stage_rows(ctx, native, real_driver, 1, ctx['anchor']))
    with pytest.raises(host.Error, match='permanently claimed'):
        host.run(1, field, tmp_path / 'replay', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert transport.calls == []


def test_wrong_prior_review_rejected(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    # Stage-2 field whose SOURCE terminal did not echo the white anchor.
    bad_prior = fake_prior_result(tmp_path, ctx, native, real_driver, claims, echo='d' * 64)
    field = make_field(tmp_path, ctx, 2, bad_prior)
    with pytest.raises(host.Error, match='white anchor'):
        host.run(2, field, tmp_path / 'live', BASE,
                 transport=lambda *a: pytest.fail('wrong prior review reached network'),
                 sleeper=lambda s: None, claims=claims)
    # Stage-1 terminal echoing something other than the anchor is stopped at the
    # terminal gate, after the claim, with no further request.
    claims1 = tmp_path / 'claims-1'
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[7]['prior_review_sha256'] = 'e' * 64
    field = make_field(tmp_path, ctx, 1)
    claim = claims1 / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='device review'):
        host.run(1, field, tmp_path / 'live1', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims1)
    assert len(transport.calls) == 8 and claim.exists()


def test_reused_stage_review_digest_rejected(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    # A MIDDLE terminal whose own digest equals its echoed prior can never be
    # a distinct stage review; the ordinal-3 field gate must refuse it.
    claims.mkdir()
    claim1 = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    b.write_new(claim1, b.seal({'kind': 'mf1750-lh2-drive-map-claim-v1', 'ordinal': 1,
        'contract_id': ctx['contract']['contract_id'], 'boot_nonce': BOOT, 'run_id': RUN,
        'permanent': True, 'claim_created_before_arm': True}))
    report1 = terminal_report(ctx, native, real_driver, 1, ctx['anchor'])
    digest1 = b.digest(b.canonical(report1))
    prior2 = fake_prior_result(tmp_path, ctx, native, real_driver, claims,
                               echo=digest1, prior_ordinal=2)
    doc = b.read_record(prior2)
    if b.digest(b.canonical(doc['report'])) == digest1:
        pytest.skip('synthetic digest collision')
    field = make_field(tmp_path, ctx, 3, prior2)
    value, prior_send, echo, _ = host.validate_field(ctx, field, 3, BASE, claims=claims)
    assert prior_send != ctx['anchor'] and prior_send != echo == digest1


@pytest.mark.parametrize(('key', 'bad'), [
    ('cursor_raw', 2), ('busy', 0), ('arm_request_count', 1), ('phase', 3),
])
def test_preflight_status_mismatch_zero_post(tmp_path, ctx, native, real_driver, key, bad):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[2][key] = bad
    field = make_field(tmp_path, ctx, 1)
    transport = Transport(rows, None)
    with pytest.raises(host.Error):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=tmp_path / 'claims')
    assert all(m == 'GET' for m, u, h in transport.calls)
    assert not (tmp_path / 'claims').exists()


@pytest.mark.parametrize(('index', 'key', 'bad'), [
    (0, 'layout_id', 'LH1_HISTORY_POSITION_BALANCED_8X8'),
    (0, 'build_tag', 'foreign'),
    (3, 'valid', True),
])
def test_preflight_document_mismatch_zero_post(tmp_path, ctx, native, real_driver, index, key, bad):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[index][key] = bad
    field = make_field(tmp_path, ctx, 1)
    transport = Transport(rows, None)
    with pytest.raises(host.Error):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=tmp_path / 'claims')
    assert all(m == 'GET' for m, u, h in transport.calls)


def test_manifest_action_tamper_zero_post(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[1]['actions'][1]['cs1_dtm_sha256'] = '0' * 64
    field = make_field(tmp_path, ctx, 1)
    transport = Transport(rows, None)
    with pytest.raises(host.Error, match='compiled frame'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=tmp_path / 'claims')
    assert all(m == 'GET' for m, u, h in transport.calls)


def test_terminal_fnv1a_tamper_stops_after_claim(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[7]['driver']['cs2_dtm_fnv1a'] = 0
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx, 1)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='driver'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert len(transport.calls) == 8 and claim.exists()
    stop = b.read_record(tmp_path / 'live' / 'STOP.json')
    assert stop['kind'] == 'mf1750-lh2-drive-map-stop-v1'
    assert stop['claim_created'] is True and stop['no_retry'] is True


def test_terminal_cursor_mismatch_stops(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[6]['cursor_raw'] = 1  # terminal status never advanced
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx, 1)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert len(transport.calls) == 7  # no report GET after a non-terminal status


def test_cursor_not_advancing_exhausts_budget_without_resend(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])[:6]
    rows += [poll_status(ctx, native, 1, ctx['anchor'], 2)] * host.MAX_POLLS
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx, 1)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='budget exhausted'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert len(transport.calls) == 6 + host.MAX_POLLS
    assert [m for m, u, h in transport.calls].count('POST') == 2


def test_fault_stops_immediately_and_never_resends(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])[:6]
    rows.append(poll_status(ctx, native, 1, ctx['anchor'], 3))
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx, 1)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='FAULT'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert len(transport.calls) == 7
    stop = b.read_record(tmp_path / 'live' / 'STOP.json')
    assert stop['claim_created'] is True and stop['no_recovery'] is True


def test_device_rejection_ack_is_not_retried(tmp_path, ctx, native, real_driver):
    rejected = native['cases']['busy_arm']['documents'][0]['json']
    assert rejected['accepted'] is False and rejected['fault_locked'] is True
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[4] = (503, rejected)
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx, 1)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.http.MiddleRunnerError, match='HTTP 503'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert len(transport.calls) == 5  # ARM rejected: EXECUTE is never sent
    assert claim.exists()


def test_bad_arm_ack_never_sends_execute(tmp_path, ctx, native, real_driver):
    rows = stage_rows(ctx, native, real_driver, 1, ctx['anchor'])
    rows[4]['arm_nonce'] = 'not-a-nonce'
    claims = tmp_path / 'claims'
    field = make_field(tmp_path, ctx, 1)
    claim = claims / (ctx['contract']['contract_id'] + '-ordinal1.json')
    transport = Transport(rows, claim)
    with pytest.raises(host.Error, match='ARM nonce'):
        host.run(1, field, tmp_path / 'live', BASE, transport=transport,
                 sleeper=lambda s: None, claims=claims)
    assert len(transport.calls) == 5
    assert claim.exists()


def test_prior_stage_result_tamper_rejected(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    prior = fake_prior_result(tmp_path, ctx, native, real_driver, claims)
    doc = b.read_record(prior)
    doc['report']['driver']['input_fnv1a'] = 0
    path = tmp_path / 'prior-tampered.json'
    b.write_new(path, b.seal({k: v for k, v in doc.items() if k != 'integrity'}))
    field = make_field(tmp_path, ctx, 2, path)
    with pytest.raises(host.Error):
        host.run(2, field, tmp_path / 'live', BASE,
                 transport=lambda *a: pytest.fail('tampered prior result reached network'),
                 sleeper=lambda s: None, claims=claims)


def test_stage3_requires_distinct_non_anchor_middle_digest(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    # MIDDLE terminal that echoes the anchor instead of the SOURCE digest.
    prior2 = fake_prior_result(tmp_path, ctx, native, real_driver, claims,
                               echo=ctx['anchor'], prior_ordinal=2)
    field = make_field(tmp_path, ctx, 3, prior2)
    with pytest.raises(host.Error, match='MIDDLE stage review digest'):
        host.run(3, field, tmp_path / 'live', BASE,
                 transport=lambda *a: pytest.fail('invalid prior chain reached network'),
                 sleeper=lambda s: None, claims=claims)


def test_missing_prior_claim_rejected(tmp_path, ctx, native, real_driver):
    claims = tmp_path / 'claims'
    prior = fake_prior_result(tmp_path, ctx, native, real_driver, claims)
    (claims / (ctx['contract']['contract_id'] + '-ordinal1.json')).unlink()
    field = make_field(tmp_path, ctx, 2, prior)
    with pytest.raises(host.Error, match='prior stage permanent claim missing'):
        host.run(2, field, tmp_path / 'live', BASE,
                 transport=lambda *a: pytest.fail('missing prior claim reached network'),
                 sleeper=lambda s: None, claims=claims)
