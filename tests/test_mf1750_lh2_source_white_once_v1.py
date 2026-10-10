"""Offline tests for the LH2 source-white runner; no I/O beyond sealed fixtures."""
from pathlib import Path
import copy
import json

import pytest

from tools import mf1750_lh2_source_white_once_v1 as w

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / '.test-output/offline/LH2_SOURCE_WHITE_20260917_R1'
NATIVE = ROOT / '.test-output/offline/LH2_SOURCE_WHITE_STRICT_NATIVE_20260917_R1/strict-native-audit.json'
HISTORICAL = ROOT / '.test-output/hardware/MF1750_P2_WHITE_LH4_20260912_V1/action-01-factory-otp-white.json'


def ctx():
    return w.validate_package(PKG)


def docs():
    return json.loads(NATIVE.read_text(encoding='utf-8'))['cases']['all']['documents']


def test_package_and_compiled_constants_are_exact():
    c = ctx()
    assert c['contract']['contract_id'] == 'aa9cd737c200744c5a795c6145afa2defe26e69b9458780abd232006c3241a20'
    assert c['expected']['build_tag'] == 'MF1750_EC5_LH2_SOURCE_WHITE_V1_2026-09-17'
    assert c['expected']['test_id'] == 'EC5-LH1-SOURCE-WHITE-V1'
    assert c['expected']['source_main_contract_id'] == '021c35abd47f6caa52b11cec98b73a79f11c585bdbc1ed976c2dde868bc5259e'
    assert c['routes']['arm'].endswith('/arm')
    r5 = json.loads((ROOT / '.test-output/offline/LH1_SOURCE_WHITE_20260913_R5/contract.json').read_text(encoding='utf-8'))
    assert c['contract']['frame_sha256'] == r5['frame_sha256']
    assert c['contract']['dtm_sha256'] == r5['dtm_sha256']


def test_headers_match_native_constants_and_nonce_phase():
    c = ctx()
    h = w.headers(c, '0000000200000003')
    assert h == {'X-EC5-Build-Tag': c['expected']['build_tag'], 'X-EC5-Test-Id': c['expected']['test_id'],
                 'X-EC5-Campaign-Id': c['expected']['campaign_id'], 'X-EC5-Action-Id': c['contract']['action_id'],
                 'X-EC5-Descriptor-Id': c['contract']['descriptor_id'], 'X-EC5-Ordinal': '1',
                 'X-EC5-Boot-Nonce': '0000000200000003', 'X-EC5-Intent': c['arm_intent']}
    e = w.headers(c, '0000000200000003', '0000000400000005')
    assert e['X-EC5-Intent'] == c['execute_intent'] and e['X-EC5-Arm-Nonce'] == '0000000400000005'


def test_native_identity_and_ack_adapters():
    c = ctx()
    ds = docs()
    w.identity(c, ds[0]['json'])
    w.identity(c, ds[4]['json'])
    w.identity(c, ds[5]['json'])
    assert 'phase' not in ds[4]['json'] and 'boot_nonce' not in ds[5]['json']


def test_native_terminal_driver_gate_uses_real_schema():
    # The native terminal driver is a synthetic desktop stub; the real driver
    # schema and FNV-1a values come from the historical white run, legitimate
    # here because the LH2 frame/DTM/driver are byte-identical to R5.
    report = json.loads(HISTORICAL.read_text(encoding='utf-8'))
    w.driver_gate(report['terminal_report']['driver'])


def test_driver_gate_rejects_counter_or_trace_tamper():
    with pytest.raises(Exception):
        w.driver_gate({'valid': True, 'running': False, 'sequence_ok': True})


def test_preflight_accepts_native_four_get_and_rejects_busy_or_gate_tamper():
    c = ctx()
    vals = {k: copy.deepcopy(d['json']) for k, d in zip(('version', 'manifest', 'status', 'report'), docs()[:4])}
    assert w.preflight(c, vals, 1) == '0000000200000003'
    with pytest.raises(Exception):
        w.preflight(c, vals, 0)
    tampered = copy.deepcopy(vals)
    tampered['status']['source_terminal_gate_pass'] = False
    with pytest.raises(Exception):
        w.preflight(c, tampered, 1)
    reused = copy.deepcopy(vals)
    reused['status']['boot_nonce'] = '7274e005c8833ca1'
    with pytest.raises(Exception):
        w.preflight(c, reused, 1)


def test_source_nvs_rejects_reboot_cursor_or_gate_mismatch():
    s = copy.deepcopy(docs()[2]['json'])
    with pytest.raises(Exception):
        s['source_observed_boot_nonce'] = '1111111111111111'
        w.source_nvs(s)
    s = copy.deepcopy(docs()[2]['json'])
    with pytest.raises(Exception):
        s['source_observed_cursor_raw'] = 5
        w.source_nvs(s)
    s = copy.deepcopy(docs()[2]['json'])
    with pytest.raises(Exception):
        s['old_fault_cursor_raw'] = 769
        w.source_nvs(s)
    s = copy.deepcopy(docs()[2]['json'])
    with pytest.raises(Exception):
        s['source_terminal_gate_pass'] = False
        w.source_nvs(s)


def test_field_record_rejects_missing_or_tampered_evidence(tmp_path):
    c = ctx()
    p = tmp_path / 'field.json'
    w.b.write_new(p, w.b.seal({'kind': 'mf1750-lh2-source-white-field-v1',
                               'recorded_at': '2026-09-17T00:00:00+00:00'}))
    with pytest.raises(Exception):
        w.validate_field(c, p, 'off')


def test_claim_and_no_retry_contract_are_frozen():
    c = ctx()
    assert c['contract']['retry'] is False and c['contract']['automatic_recovery'] is False
    assert not c['contract']['live_action_authorized']
    assert c['contract']['source_terminal_gate']['expected_cursor_raw'] == 4
    assert c['contract']['old_fault_preservation']['must_remain_untouched'] is True
    assert c['contract']['successor_nvs'] == {'namespace': 'lh2srcw_v1', 'cursor_key': 'used_lh2sw1',
                                            'initial_cursor': 1, 'complete_cursor': 2}


def _fixture(monkeypatch, tmp_path, failure=None):
    from datetime import datetime, timezone
    c = ctx()
    native = docs()
    vals = {k: copy.deepcopy(native[i]['json']) for i, k in enumerate(('version', 'manifest', 'status', 'report'))}
    boot = vals['status']['boot_nonce']
    vals['status']['busy'] = 1
    field = {'base_url': 'http://192.168.1.4', 'run_id': 'UNIT_TEST_NO_HARDWARE',
             **{key: {'unit_test_binding': True} for key in ('app_flash', 'camera_review', 'source_gate', 'user_release')}}
    field_path = tmp_path / 'field.json'
    w.b.write_new(field_path, w.b.seal(field))
    diag_path = tmp_path / 'diag.json'
    w.b.write_new(diag_path, w.b.seal({'recorded_at': datetime.now(timezone.utc).isoformat(),
        'result': 'PASS', 'contract_id': c['contract']['contract_id'],
        'network': {'get': 4, 'post': 0}, 'boot_nonce': boot, 'responses': vals,
        'transcripts': [], 'field': w.b.file_binding(field_path)}))
    monkeypatch.setattr(w, 'validate_field', lambda *a: field)
    terminal = copy.deepcopy(native[-1]['json'])
    historical = json.loads(HISTORICAL.read_text(encoding='utf-8'))
    terminal['driver'] = historical['terminal_report']['driver']
    claim = tmp_path / 'claim.json'

    class Transport:
        def __init__(self):
            self.calls = []
            self.executed = False

        def __call__(self, method, url, headers, timeout):
            route = url.rsplit('/', 1)[-1]
            self.calls.append((method, route, headers))
            if method == 'GET':
                if route == 'report' and self.executed:
                    return 200, w.b.canonical(terminal)
                value = copy.deepcopy(vals[route])
                if route == 'status':
                    value['busy'] = 1
                    if self.executed:
                        value.update(state='complete', phase=0, cursor_raw=2, next_ordinal=2,
                            campaign_complete=True, total_driver_call_count=1,
                            arm_request_count=1, execute_request_count=1, execute_pending=False)
                return 200, w.b.canonical(value)
            assert claim.exists(), 'claim must exist BEFORE network mutation'
            if route == 'arm':
                if failure == 'arm':
                    return 400, w.b.canonical({'accepted': False, 'error': 'unit_test_rejection'})
                assert headers == w.headers(c, boot)
                return 201, w.b.canonical(native[4]['json'])
            assert route == 'execute'
            assert headers == w.headers(c, boot, native[4]['json']['arm_nonce'])
            if failure == 'execute':
                raise TimeoutError('unit test ambiguous EXEC delivery')
            self.executed = True
            return 202, w.b.canonical(native[5]['json'])

    return field_path, diag_path, claim, Transport()


def test_diagnose_j2_off_pass(monkeypatch, tmp_path):
    field_path, _, _, t = _fixture(monkeypatch, tmp_path)
    off = copy.deepcopy(docs()[2]['json'])
    off['busy'] = 0
    original = t.__call__

    def transport(method, url, headers, timeout):
        if method == 'GET' and url.rsplit('/', 1)[-1] == 'status':
            t.calls.append((method, 'status', headers))
            return 200, w.b.canonical(off)
        return original(method, url, headers, timeout)

    result = w.diagnose(PKG, field_path, tmp_path / 'j2off', transport=transport)
    assert result['result'] == 'PASS' and result['network'] == {'get': 4, 'post': 0}
    assert result['driver_calls'] == 0 and result['visible_refreshes'] == 0
    assert w.record(tmp_path / 'j2off' / 'diagnostic.json')['kind'] == 'mf1750-lh2-source-white-j2-off-diagnostic-v1'


def test_run_exact_single_transaction_success(monkeypatch, tmp_path):
    field, diag, claim, t = _fixture(monkeypatch, tmp_path)
    sleeps = []
    result = w.run(PKG, field, diag, tmp_path / 'live', transport=t, sleeper=sleeps.append, claim_path=claim)
    assert result['result'] == 'PASS' and result['driver_calls'] == 1
    assert result['network'] == {'get': 6, 'post': 2}
    assert result['kind'] == 'mf1750-lh2-source-white-result-v1'
    assert sleeps == [65]
    assert [r for m, r, h in t.calls if m == 'POST'] == ['arm', 'execute']
    assert claim.exists()
    before = len(t.calls)
    with pytest.raises(w.b.RunnerError, match='already claimed'):
        w.run(PKG, field, diag, tmp_path / 'replay', transport=t, sleeper=sleeps.append, claim_path=claim)
    assert len(t.calls) == before and not (tmp_path / 'replay').exists()


def test_run_rejects_terminal_gate_failure_before_any_mutation(monkeypatch, tmp_path):
    field, diag, claim, t = _fixture(monkeypatch, tmp_path)
    original = t.__call__

    def transport(method, url, headers, timeout):
        status, raw = original(method, url, headers, timeout)
        if method == 'GET' and url.rsplit('/', 1)[-1] == 'status':
            value = copy.deepcopy(json.loads(raw))
            value['source_terminal_gate_pass'] = False
            return 200, w.b.canonical(value)
        return status, raw

    with pytest.raises(w.b.RunnerError):
        w.run(PKG, field, diag, tmp_path / 'live', transport=transport, sleeper=lambda s: None, claim_path=claim)
    assert not claim.exists()
    assert [x for x in t.calls if x[0] == 'POST'] == []
    stop = w.record(tmp_path / 'live' / 'STOP.json')
    assert stop['claim_preserved'] is False and stop['mutation_retry'] is False


@pytest.mark.parametrize('failure,post_count', [('arm', 1), ('execute', 2)])
def test_run_mutation_failure_preserves_claim_and_never_retries(monkeypatch, tmp_path, failure, post_count):
    field, diag, claim, t = _fixture(monkeypatch, tmp_path, failure)
    sleeps = []
    with pytest.raises(w.b.RunnerError):
        w.run(PKG, field, diag, tmp_path / 'live', transport=t, sleeper=sleeps.append, claim_path=claim)
    assert claim.exists() and sleeps == []
    assert len([x for x in t.calls if x[0] == 'POST']) == post_count
    stop = w.record(tmp_path / 'live' / 'STOP.json')
    assert stop['claim_preserved'] and stop['mutation_retry'] is False
