from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

from tools import mf1750_ec5_stage_a_v2_identity as identity


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frozen_action_ids_recompute_from_exact_canonical_preimages() -> None:
    expected = {
        "U04": "f03e53525df228719e1e48042e6d924887acb0a9d14d7a00416cc3590830c8d3",
        "U07": "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae",
    }
    for candidate, action_id in expected.items():
        preimage = identity.action_identity_preimage(candidate)
        canonical = identity.canonical_json_bytes(preimage)
        assert not canonical.endswith(b"\n")
        assert hashlib.sha256(canonical).hexdigest() == action_id
        assert identity.derive_action_id(preimage) == action_id
        assert identity.action_id(candidate) == action_id
        assert identity.VARIANTS[candidate]["action_id"] == action_id


def test_preimages_preserve_exact_value_types_and_candidate_migration_state() -> None:
    u04 = identity.action_identity_preimage("U04")
    u07 = identity.action_identity_preimage("U07")
    for value in (u04, u07):
        assert value["schema_version"] == 1
        assert type(value["schema_version"]) is int
        assert value["identity_revision"] == "corrected-v2"
        assert value["device_api_version"] == "MF1750_EC5_DEVICE_V3"
        assert value["active_nvs_namespace"] == "mf1750_ec5v2"
        assert value["active_key_present_expected_before_arm"] is False
        assert value["maximum_arm_posts"] == 1
        assert value["maximum_execute_posts"] == 1
        assert value["retry_allowed"] is False
        assert value["recovery_included"] is False
    assert u04["legacy_nvs_key"] == "u04_phase"
    assert u04["legacy_key_present_expected"] is True
    assert u04["legacy_expected_phase"] == 2
    assert u04["active_nvs_key"] == "u04v2_phase"
    assert u07["legacy_nvs_key"] == "u07_phase"
    assert u07["legacy_key_present_expected"] is False
    assert u07["legacy_expected_phase"] == 0
    assert u07["active_nvs_key"] == "u07v2_phase"


def test_preimage_copy_is_independent_and_any_drift_changes_action_id() -> None:
    original = identity.action_identity_preimage("U04")
    changed = deepcopy(original)
    changed["legacy_expected_phase"] = 0
    assert identity.derive_action_id(changed) != identity.action_id("U04")
    changed_again = identity.action_identity_preimage("U04")
    assert changed_again == original


def test_release_facing_nvs_contract_and_device_source_match_frozen_identity() -> None:
    main = (REPO_ROOT / "src/ec5_unknown_probe_main.cpp").read_text(
        encoding="utf-8"
    )
    for candidate in ("U04", "U07"):
        variant = identity.VARIANTS[candidate]
        assert variant["top_schema_version"] == 3
        assert variant["driver_evidence_schema_version"] == 2
        assert variant["nvs_contract"] == identity.nvs_contract(candidate)
        for token in (
            variant["build_tag"],
            variant["test_id"],
            variant["action_id"],
            variant["nvs_contract"]["legacy"]["key"],
            variant["nvs_contract"]["active"]["key"],
        ):
            assert main.count(str(token)) == 1
    assert main.count(identity.DEVICE_API_VERSION) == 1
    assert main.count(identity.IDENTITY_REVISION) == 1

