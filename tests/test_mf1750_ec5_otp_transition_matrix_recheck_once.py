from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_otp_transition_matrix_recheck_once as recheck


def _identity(kind: str) -> dict[str, Any]:
    return {
        "kind": f"mf1750-ec5-otp-transition-matrix-{kind}",
        "build_tag": recheck.BUILD_TAG,
        "test_id": recheck.TEST_ID,
        "campaign_id": recheck.CAMPAIGN_ID,
        "device_api_version": recheck.DEVICE_API_VERSION,
        "identity_revision": recheck.IDENTITY_REVISION,
        "contract_id": recheck.CONTRACT_ID,
        "classification": recheck.CLASSIFICATION,
    }


class FakeDevice:
    def __init__(self, *, busy: int = 1) -> None:
        self.busy = busy
        self.boot_nonce = "0123456789abcdef"
        self.armed = False
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        assert timeout > 0
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        if name == "version":
            return 200, {
                **_identity("version"),
                "action_count": 3,
                **{
                    key: False
                    for key in (
                        "automatic_execute",
                        "automatic_chaining",
                        "startup_refresh",
                        "raw_frame_ingress",
                        "runtime_lut_write",
                        "electrical_parameter_write",
                        "dither",
                        "spatial_mixing",
                        "retry",
                        "recovery",
                    )
                },
                "nvs_contract": {
                    "namespace": recheck.NVS_NAMESPACE,
                    "key": recheck.NVS_KEY,
                },
            }
        if name == "manifest":
            return 200, {
                **_identity("manifest"),
                "action_count": 3,
                "one_driver_call_per_action": True,
                "actions": list(recheck.ACTIONS),
            }
        if name == "status":
            return 200, {
                **_identity("status"),
                "boot_nonce": self.boot_nonce,
                "state": "ready",
                "phase": 0,
                "phase_name": "READY",
                "cursor_raw": 1,
                "next_ordinal": 1,
                "current_action": None,
                "campaign_complete": False,
                "fixture_self_check_passed": True,
                "cursor_valid": True,
                "gpio_initialized": True,
                "busy": self.busy,
                "rst": 0,
                "cs": 0,
                "cs2": 0,
                "execute_pending": False,
                "persistent_key_present": False,
            }
        if name == "report":
            if self.executed:
                return 200, {
                    **_identity("report"),
                    "boot_nonce": self.boot_nonce,
                    "ordinal": 1,
                    "action_id": recheck.ACTION_IDS[0],
                    "terminal_state": "COMPLETE",
                    "result": True,
                    "driver_called": True,
                    "driver_call_count_for_action": 1,
                }
            return 200, {
                **_identity("report"),
                "boot_nonce": self.boot_nonce,
                "terminal_state": "NOT_EXECUTED",
                "valid": False,
            }
        if name == "arm":
            assert method == "POST"
            assert headers is not None and "X-EC5-Arm-Nonce" not in headers
            self.armed = True
            return 201, {
                "accepted": True,
                "armed": True,
                "action_id": recheck.ACTION_IDS[0],
                "boot_nonce": self.boot_nonce,
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            assert method == "POST" and self.armed
            assert headers is not None
            assert headers["X-EC5-Arm-Nonce"] == "fedcba9876543210"
            self.executed = True
            return 202, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": recheck.ACTION_IDS[0],
                "boot_nonce": self.boot_nonce,
            }
        raise AssertionError(name)


def test_description_is_offline_and_never_autochains() -> None:
    value = recheck.describe()
    assert value["visible_actions"] == 3
    assert value["startup_refresh"] is False
    assert value["automatic_chaining"] is False
    assert value["live_authorized"] is False
    assert value["nvs"]["namespace"] == "mf1750_otpm8r2"


def test_j2_off_diagnostic_is_four_gets_and_no_refresh(tmp_path: Path) -> None:
    fake = FakeDevice(busy=0)
    value = recheck.diagnose_j2_off(
        "http://192.0.2.1",
        output=tmp_path / "diagnostic.json",
        requester=fake,
    )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert value["visible_refreshes"] == 0


def test_one_action_claims_before_exactly_one_arm_and_execute(tmp_path: Path) -> None:
    fake = FakeDevice()
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    value = recheck.run_once(
        "http://192.0.2.1",
        1,
        claims=claims,
        output=output,
        requester=fake,
        poll_seconds=0,
        poll_count=1,
    )
    assert value["outcome"] == "complete_pass"
    assert value["network"]["arm_post"] == 1
    assert value["network"]["execute_post"] == 1
    assert (claims / f"{recheck.ACTION_IDS[0]}.json").is_file()
    with pytest.raises(recheck.RecheckError, match="already permanently claimed"):
        recheck.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "second.json",
            requester=FakeDevice(),
            poll_seconds=0,
            poll_count=1,
        )
