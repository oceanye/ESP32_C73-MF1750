from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import mf1750_exact_ipv4_mac_binding_once as binding


MAC = "A4-CB-8F-D9-FC-D4"


class FakeRunner:
    def __init__(
        self, *, candidate_local: bool = False, state: str | int = "Reachable"
    ):
        self.commands: list[list[str]] = []
        self.candidate_local = candidate_local
        self.state = state

    def __call__(self, command: list[str], timeout: float) -> binding.CommandResult:
        del timeout
        self.commands.append(list(command))
        joined = " ".join(command)
        if "Get-NetIPAddress" in joined:
            ip = "192.168.1.11" if self.candidate_local else "192.168.1.7"
            payload = [{"InterfaceIndex": 16, "IPAddress": ip, "PrefixLength": 24}]
            return binding.CommandResult(0, json.dumps(payload).encode(), b"")
        if command[0] == "ping.exe":
            return binding.CommandResult(0, b"one reply", b"")
        if "Get-NetNeighbor" in joined:
            payload = [
                {
                    "ifIndex": 16,
                    "IPAddress": "192.168.1.11",
                    "LinkLayerAddress": MAC,
                    "State": self.state,
                }
            ]
            return binding.CommandResult(0, json.dumps(payload).encode(), b"")
        raise AssertionError(command)


def test_active_single_candidate_passes_and_is_terminal(tmp_path: Path) -> None:
    runner = FakeRunner()
    output = tmp_path / "binding.json"
    result = binding.bind_once(
        candidate_ip="192.168.1.11",
        expected_mac=MAC.lower().replace("-", ":"),
        output=output,
        active_probe=True,
        confirm_single_candidate=True,
        runner=runner,
    )
    assert result["binding_passed"] is True
    assert result["fresh_binding_passed"] is True
    assert result["outcome"] == "active_exact_mac_binding_pass"
    assert result["device_application_identity_proven"] is False
    assert result["http_requests"] == 0
    assert result["active_probe"]["attempts"] == 1
    assert len([item for item in runner.commands if item[0] == "ping.exe"]) == 1
    with pytest.raises(binding.BindingError, match="overwrite"):
        binding.bind_once(
            candidate_ip="192.168.1.11",
            expected_mac=MAC,
            output=output,
            active_probe=True,
            confirm_single_candidate=True,
            runner=runner,
        )


def test_local_candidate_fails_before_probe(tmp_path: Path) -> None:
    runner = FakeRunner(candidate_local=True)
    result = binding.bind_once(
        candidate_ip="192.168.1.11",
        expected_mac=MAC,
        output=tmp_path / "local.json",
        active_probe=True,
        confirm_single_candidate=True,
        runner=runner,
    )
    assert result["binding_passed"] is False
    assert result["fresh_binding_passed"] is False
    assert "belongs to this host" in result["error"]["message"]
    assert not any(item[0] == "ping.exe" for item in runner.commands)


def test_stale_post_probe_is_terminal_failure(tmp_path: Path) -> None:
    runner = FakeRunner(state=4)
    result = binding.bind_once(
        candidate_ip="192.168.1.11",
        expected_mac=MAC,
        output=tmp_path / "stale.json",
        active_probe=True,
        confirm_single_candidate=True,
        runner=runner,
    )
    assert result["binding_passed"] is False
    assert result["fresh_binding_passed"] is False
    assert result["outcome"] == "terminal_binding_failure_no_retry"
    assert result["network_layer_mac_binding_observed"] is True
    assert result["observed_state"] == "STALE"


def test_passive_snapshot_never_claims_freshness(tmp_path: Path) -> None:
    runner = FakeRunner(state="Stale")
    result = binding.bind_once(
        candidate_ip="192.168.1.11",
        expected_mac=MAC,
        output=tmp_path / "passive.json",
        active_probe=False,
        confirm_single_candidate=True,
        runner=runner,
    )
    assert result["binding_passed"] is True
    assert result["fresh_binding_passed"] is False
    assert result["outcome"].endswith("not_freshness_proof")
    assert result["active_probe"]["attempts"] == 0


@pytest.mark.parametrize("candidate", ["hostname.local", "::1", "127.0.0.1"])
def test_rejects_noneligible_candidate_before_output(
    tmp_path: Path, candidate: str
) -> None:
    with pytest.raises(binding.BindingError):
        binding.bind_once(
            candidate_ip=candidate,
            expected_mac=MAC,
            output=tmp_path / "bad.json",
            active_probe=False,
            confirm_single_candidate=True,
            runner=FakeRunner(),
        )
