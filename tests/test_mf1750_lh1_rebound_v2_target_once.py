"""Host failure/at-most-once checks using actual native-generated wire JSON.

Native driver and admission for transaction tests are explicitly synthetic.
No test grants a physical camera/release approval or contacts a device.
"""
from copy import deepcopy

import pytest

from tools import mf1750_lh1_rebound_v2_target_once as host


@pytest.fixture(scope='module')
def native_rows():
    path = host.review.ROOT / '.test-output/offline/LH1_REBOUND_V2_TARGET_NATIVE_20260917_R1/target-wire.log'
    if not path.exists():
        pytest.skip('native wire fixture unavailable')
    return [host.rec.parse_json(line) for line in path.read_bytes().splitlines() if line.startswith(b'{')]


@pytest.fixture(scope='module')
def ctx():
    if not host.review.PACKAGE.exists():
        pytest.skip('local compiled package unavailable')
    return host.review.validate_package()


@pytest.fixture
def admitted(monkeypatch, tmp_path, ctx):
    release = tmp_path / 'synthetic-release.json'
    release.write_text('{"synthetic_test_only":true}', encoding='utf8')
    monkeypatch.setattr(host, 'CLAIMS', tmp_path / 'claims')
    monkeypatch.setattr(host.review, 'validate_package', lambda: ctx)
    monkeypatch.setattr(host, 'validate_release', lambda *a, **k: {
        'prior_review_sha256': 'c' * 64, 'middle_terminal': 'synthetic'})
    monkeypatch.setattr(host, 'load_bound_record', lambda binding: {
        'report': {'prior_review_sha256': 'b' * 64}})
    return release


def transport_for(rows, calls, *, fail_index=None):
    def transport(method, url, headers, timeout):
        index = len(calls)
        calls.append((method, url, headers.copy(), timeout))
        if index == fail_index:
            raise TimeoutError('synthetic transport timeout')
        assert index < len(rows), 'automatic extra action/request'
        code = 201 if index == 4 else 202 if index == 5 else 200
        return code, host.rec.canonical(rows[index])
    return transport


def test_actual_generated_wire_schema(ctx, native_rows):
    host.validate_preflight(ctx, dict(zip(('version', 'manifest', 'status', 'report'), native_rows[:4])), 'b' * 64)
    host.validate_terminal(ctx, native_rows[6], native_rows[7], 'c' * 64)


def test_one_target_and_no_white_or_recovery(admitted, tmp_path, native_rows):
    calls, waits = [], []
    value = host.run(admitted, tmp_path / 'live', 'http://192.168.1.4',
        transport=transport_for(native_rows, calls), sleeper=waits.append)
    assert [c[0] for c in calls] == ['GET'] * 4 + ['POST'] * 2 + ['GET'] * 2
    assert waits == [30, 30, 5]
    assert value['driver'] == 1 and value['visible_refresh'] == 1
    assert value['campaign_complete'] is True and value['further_contract_action_available'] is False
    assert value['white_executed'] is False
    assert host.claim_path().exists()
    for method, url, headers, timeout in calls[4:6]:
        assert headers['X-EC5-Ordinal'] == '3'
        assert headers['X-LH-Run-Id'] == host.review.RUN
        assert headers['X-LH-Prior-Review'] == 'c' * 64
        assert headers['X-LH-Source-Review'] == host.review.ANCHOR


@pytest.mark.parametrize('fail_index', [0, 4, 5, 6])
def test_timeout_never_retries(admitted, tmp_path, native_rows, fail_index):
    calls = []
    with pytest.raises(host.http.MiddleRunnerError):
        host.run(admitted, tmp_path / 'live', 'http://192.168.1.4',
            transport=transport_for(native_rows, calls, fail_index=fail_index), sleeper=lambda _: None)
    assert len(calls) == fail_index + 1
    stop = host.rec.read_record(tmp_path / 'live/STOP.json')
    assert stop['no_retry'] and stop['no_reset_or_white']
    assert stop['claim_created'] == (fail_index >= 4)
    if fail_index >= 4:
        with pytest.raises(host.Error, match='permanently claimed'):
            host.run(admitted, tmp_path / 'different-output', 'http://192.168.1.4',
                transport=transport_for(native_rows, calls), sleeper=lambda _: None)
        assert len(calls) == fail_index + 1


def test_bad_arm_ack_never_sends_execute(admitted, tmp_path, native_rows):
    rows = deepcopy(native_rows)
    rows[4]['boot_nonce'] = '0' * 16
    calls = []
    with pytest.raises(host.Error):
        host.run(admitted, tmp_path / 'live', 'http://192.168.1.4',
            transport=transport_for(rows, calls), sleeper=lambda _: None)
    assert len(calls) == 5
    assert host.claim_path().exists()


@pytest.mark.parametrize(('index', 'key', 'bad'), [
    (0, 'build_tag', 'foreign'), (1, 'source_review_sha256', '0' * 64),
    (2, 'boot_nonce', '0' * 16), (2, 'cursor_raw', 2),
    (2, 'busy', 0), (2, 'total_driver_call_count', 3),
    (3, 'action_id', '0' * 64), (3, 'source_nvs_complete', False),
])
def test_preflight_mismatch_has_zero_post(admitted, tmp_path, native_rows, index, key, bad):
    rows = deepcopy(native_rows)
    rows[index][key] = bad
    calls = []
    with pytest.raises(host.Error):
        host.run(admitted, tmp_path / 'live', 'http://192.168.1.4',
            transport=transport_for(rows, calls), sleeper=lambda _: None)
    assert all(c[0] == 'GET' for c in calls)
    assert not host.claim_path().exists()


@pytest.mark.parametrize(('index', 'path', 'bad'), [
    (6, ('boot_nonce',), '0' * 16), (6, ('campaign_complete',), False),
    (6, ('cursor_raw',), 3), (7, ('driver', 'cs1_dtm_fnv1a'), 0),
    (7, ('driver', 'busy_stage_samples', 'pof', 'assertion_after_idle'), False),
    (7, ('driver', 'safe_finish', 'final_gpio', 'rst'), 1),
])
def test_terminal_mismatch_stops_without_extra_post(admitted, tmp_path, native_rows, index, path, bad):
    rows = deepcopy(native_rows)
    node = rows[index]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad
    calls = []
    with pytest.raises(host.Error):
        host.run(admitted, tmp_path / 'live', 'http://192.168.1.4',
            transport=transport_for(rows, calls), sleeper=lambda _: None)
    assert sum(c[0] == 'POST' for c in calls) == 2
    assert host.claim_path().exists()


def test_no_release_has_zero_network_and_zero_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(host, 'CLAIMS', tmp_path / 'claims')
    def forbidden(*args):
        pytest.fail('unreleased run contacted network')
    with pytest.raises(host.Error):
        host.run(tmp_path / 'absent.json', tmp_path / 'output', 'http://192.168.1.4',
                 transport=forbidden)
    assert not host.claim_path().exists()


def test_pending_release_cannot_run(monkeypatch, tmp_path, ctx):
    monkeypatch.setattr(host, 'CLAIMS', tmp_path / 'claims')
    release = {'kind': 'mf1750-lh1-rebound-v2-target-release-v1',
        'contract_id': host.review.CONTRACT, 'boot_nonce': host.review.BOOT,
        'run_id': host.review.RUN, 'ordinal': 3, 'action_id': ctx['contract']['actions'][2]['action_id'],
        'authorized_refreshes': 1, 'stop_after_action': True, 'source_replay': False,
        'middle_replay': False, 'white_authorized': False, 'live_release': False}
    path = tmp_path / 'pending.json'
    host.rec.write_new(path, host.rec.seal(release))
    with pytest.raises(host.Error, match='live_release'):
        host.run(path, tmp_path / 'output', 'http://192.168.1.4',
                 transport=lambda *a: pytest.fail('pending release contacted network'))
    assert not host.claim_path().exists()
