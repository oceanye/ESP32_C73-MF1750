"""Regression checks against preserved real SOURCE evidence (no device I/O)."""
from copy import deepcopy

import pytest

from tools import mf1750_lh1_rebound_v2_review as review
from tools import mf1750_lh1_rebound_v2_live_once as quarantined


@pytest.fixture(scope='module')
def observed():
    if not review.PACKAGE.exists():
        pytest.skip('local sealed hardware evidence unavailable')
    ctx = review.validate_package()
    live = review.HISTORY / 'LIVE_RUN_R4'
    return ctx, review.load(live / '007-get-status.body.bin'), review.load(live / '008-get-report.body.bin')


def test_real_terminal(observed):
    review.validate_source(*observed)


@pytest.mark.parametrize(('where', 'path', 'replacement'), [
    ('status', ('boot_nonce',), '0000000000000000'),
    ('status', ('cursor_raw',), 770),
    ('status', ('campaign_boot_matches_current',), False),
    ('status', ('nvs_contract', 'namespace'), 'lhist_v1'),
    ('report', ('action_id',), '0' * 64),
    ('report', ('driver_call_count_for_action',), 2),
    ('report', ('source_review_sha256',), '0' * 64),
    ('report', ('driver', 'cs1_dtm_fnv1a'), 0),
    ('report', ('driver', 'cs2_dtm_fnv1a'), 0),
    ('report', ('driver', 'busy_stage_samples', 'drf', 'assertion_after_idle'), False),
    ('report', ('driver', 'safe_finish', 'final_gpio', 'rst'), 1),
    ('report', ('driver', 'failure_code'), 1),
])
def test_rejects_invalid_terminal(observed, where, path, replacement):
    ctx, status, report = deepcopy(observed)
    node = status if where == 'status' else report
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = replacement
    with pytest.raises(review.Error):
        review.validate_source(ctx, status, report)


def test_duplicate_json_rejected():
    with pytest.raises(review.Error):
        review.records.parse_json(b'{"result":false,"result":true}')


@pytest.mark.parametrize('entry', ['run', 'run_on_only'])
def test_old_mutation_entries_stop_before_cfg_or_network(monkeypatch, entry):
    def forbidden(*args, **kwargs):
        pytest.fail('quarantined runner reached an operation')
    monkeypatch.setattr(quarantined, 'cfg', forbidden)
    monkeypatch.setattr(quarantined, 'Once', forbidden)
    with pytest.raises(RuntimeError, match='QUARANTINED'):
        if entry == 'run':
            quarantined.run('http://192.168.1.4', 'unused', {}, {})
        else:
            quarantined.run_on_only('http://192.168.1.4', 'unused', {}, '7274e005c8833ca1')
