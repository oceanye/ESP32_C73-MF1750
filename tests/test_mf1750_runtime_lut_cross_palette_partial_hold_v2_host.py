from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_cross_palette_partial_hold_v2_once as once
from tools import mf1750_runtime_lut_cross_palette_partial_hold_v2_pack as pack


def test_dry_validate_binds_artifacts_and_qualifier_without_network() -> None:
    value = once.host.dry_validate()
    assert value["verified"] is True
    assert value["network"] == {"get": 0, "post": 0}
    assert value["hardware_accessed"] is False
    assert value["contract_id"] == pack.CONTRACT_ID
    assert value["descriptor_ids"] == list(pack.DESCRIPTOR_IDS)
    assert value["action_ids"] == list(pack.ACTION_IDS)
    assert value["qualifier_v2_prerequisite"]["verified"] is True
    assert all(
        item["verified"] is True
        for item in value["artifact_binding_status"].values()
    )


def test_describe_exposes_exact_five_actions_and_clean_transport() -> None:
    value = once.describe()
    assert value["action_order"] == [
        "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "PATCH_A_ACTIVE_CODE5",
        "PATCH_B_COMMENTED_CODE6_HOLD_A",
        "PATCH_C_ACTIVE_CODE3_HOLD_AB",
        "FACTORY_OTP_WHITE_RECOVERY",
    ]
    transport = value["fixed_transport"]
    assert transport["runtime_lut_codes"] == [5, 6, 3]
    assert transport["runtime_global_headers"] == ["active", "commented", "active"]
    assert transport["ptlw_writes_per_controller_for_partial_actions"] == 1
    assert transport["repeat_ptlw_after_pon_busy"] is False
    assert transport["action_stage_cdi"] is False
    assert transport["action_stage_btst2"] is False
    assert transport["command_0x86"] is False
    assert value["live_authorized"] is False


@pytest.mark.parametrize(
    ("ordinal", "expected"),
    [
        (1, {"dtm_bytes": 307_200, "lut_bytes": 0, "ptlw_writes": 0}),
        (2, {"dtm_bytes": 326_400, "lut_bytes": 2_478, "ptlw_writes": 2}),
        (3, {"dtm_bytes": 326_400, "lut_bytes": 2_478, "ptlw_writes": 2}),
        (4, {"dtm_bytes": 326_400, "lut_bytes": 2_478, "ptlw_writes": 2}),
        (5, {"dtm_bytes": 307_200, "lut_bytes": 0, "ptlw_writes": 0}),
    ],
)
def test_action_stage_counts_are_exact(
    ordinal: int, expected: dict[str, int]
) -> None:
    value = once._expected_action_stage_counts(ordinal)  # noqa: SLF001
    for key, wanted in expected.items():
        assert value[key] == wanted
    assert value["pon"] == value["drf"] == value["pof"] == 1
    assert value["command_0x86"] == 0
    assert value["visible_refresh_requests"] == 1


def test_run_without_explicit_j2_on_fails_before_request_or_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched = False

    def forbidden_request(*_args: object, **_kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(once.base.runner, "_request", forbidden_request)
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    with pytest.raises(once.base.runner.RecheckError, match="J2-ON"):
        once.host.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=output,
            confirm_j2_on=False,
        )
    assert touched is False
    assert not claims.exists()
    assert not output.exists()


def test_new_routes_claims_nvs_and_ids_are_isolated() -> None:
    runner = once.base.runner
    assert set(runner.ENDPOINTS) == {
        "version",
        "manifest",
        "status",
        "report",
        "arm",
        "execute",
    }
    assert all(pack.ENDPOINT_BASE in route for route in runner.ENDPOINTS.values())
    assert runner.NVS_NAMESPACE == "rlxph_v2"
    assert runner.NVS_KEY == "cursor_cxph2"
    assert "cross_palette_partial_hold_v2_claims" in str(runner.DEFAULT_CLAIMS)
    assert runner.CONTRACT_ID == pack.CONTRACT_ID
    assert runner.ACTION_IDS == pack.ACTION_IDS

