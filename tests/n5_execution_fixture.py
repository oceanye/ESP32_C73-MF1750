"""Structural-only N5 execution evidence builders used by offline tests."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Any, Mapping, Optional, Sequence

import host.extended_color.execution as execution
from host.visible_refresh_campaign import seal_limit_profile
from tools.mf1750_n5_fixed_execution import load_action_frame


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def seal_external_authorization(payload: Mapping[str, Any]) -> dict[str, Any]:
    unsigned = execution._snapshot(payload)
    return {**unsigned, "integrity": execution._integrity(unsigned)}


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def reviewed_limit_profile(
    contract: Mapping[str, Any], *, last_visible_at: datetime, snapshot_at: datetime
) -> dict[str, Any]:
    p0 = contract["p0_campaign"]
    return seal_limit_profile(
        {
            "schema_version": 1,
            "kind": "mf1750-visible-refresh-limit-profile",
            "profile_id": "n5-structural-test-profile",
            "profile_version": "1.0.0",
            "panel": p0["panel"],
            "firmware": p0["firmware"],
            "action_allowlist": [
                {
                    "action_id": action["identity"]["action_id"],
                    "action_identity_sha256": action["action_identity_sha256"],
                    "method": "POST",
                    "endpoint": action["identity"]["request"]["endpoint"],
                    "frame_sha256": action["identity"]["frame"]["sha256"],
                    "maximum_uses": 1,
                }
                for action in p0["actions"]
            ],
            "limits": {
                "maximum_campaign_visible_refreshes": len(p0["actions"]) + 10,
                "maximum_session_visible_refreshes": 10,
                "maximum_consecutive_visible_refreshes": 10,
                "minimum_interval_seconds": 0,
                "minimum_cooldown_seconds": 0,
                "minimum_start_temperature_c": 0,
                "maximum_start_temperature_c": 50,
                "maximum_post_refresh_temperature_c": 50,
            },
            "usage": {
                "cumulative_visible_refresh_count": 1,
                "session_visible_refresh_count": 1,
                "consecutive_visible_refresh_count": 1,
                "last_visible_refresh_completed_at": _timestamp(last_visible_at),
                "snapshot_at": _timestamp(snapshot_at),
                "evidence_sha256": hash_text("n5-structural-usage"),
            },
            "validity": {
                "valid_from": "2026-08-08T00:00:00Z",
                "expires_at": "2026-08-09T00:00:00Z",
            },
            "review": {
                "approved": True,
                "reviewer_id": "n5-structural-reviewer",
                "reviewed_at": "2026-08-07T00:00:00Z",
                "review_artifact_sha256": hash_text("n5-structural-profile-review"),
            },
        }
    )


def dependency_closure(
    contract: Mapping[str, Any], terminal_action_identity_sha256s: Sequence[str]
) -> list[str]:
    actions = {
        action["action_identity_sha256"]: action
        for action in contract["p0_campaign"]["actions"]
    }
    included: set[str] = set()

    def visit(action_sha: str) -> None:
        if action_sha in included:
            return
        action = actions[action_sha]
        prior = action["identity"]["prior"]
        if prior is not None:
            visit(prior["action_identity_sha256"])
        included.add(action_sha)

    for terminal in terminal_action_identity_sha256s:
        visit(terminal)
    order = {
        entry["action_identity_sha256"]: entry["order"]
        for entry in contract["actions"]
    }
    return sorted(included, key=order.__getitem__)


def _synthetic_measurement_binding(
    action_identity_sha256: str, slot: Mapping[str, str]
) -> dict[str, Any]:
    """Build structural evidence for a frozen slot that has no supplied payload."""

    slot_id = slot["slot_id"]
    phase = slot["measurement_phase"]
    return {
        "slot_id": slot_id,
        "measurement_phase": phase,
        "source_run_sha256": hash_text(
            f"fixture-source-{action_identity_sha256}-{slot_id}-{phase}"
        ),
        "asset_manifest_sha256": hash_text(
            f"fixture-asset-{action_identity_sha256}-{slot_id}-{phase}"
        ),
        "measurement_record_sha256": hash_text(
            f"fixture-measurement-{action_identity_sha256}-{slot_id}-{phase}"
        ),
        "raw_spectrum_artifact_sha256": hash_text(
            f"fixture-raw-{action_identity_sha256}-{slot_id}-{phase}"
        ),
        "spectral_report_file_sha256": hash_text(
            f"fixture-report-{action_identity_sha256}-{slot_id}-{phase}"
        ),
        "metrics_sha256": (
            hash_text(f"fixture-metrics-{action_identity_sha256}-{slot_id}-{phase}")
            if phase == "transition_final"
            else None
        ),
    }


def _measurement_bindings_in_frozen_order(
    action_identity_sha256: str,
    measurement_slots: Sequence[Mapping[str, str]],
    supplied_by_action: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Return complete bindings in snapshot order and reject ambiguous fixtures."""

    expected_keys = [
        (slot["slot_id"], slot["measurement_phase"]) for slot in measurement_slots
    ]
    if len(expected_keys) != len(set(expected_keys)):
        raise AssertionError("frozen measurement slots contain duplicate identities")
    if action_identity_sha256 not in supplied_by_action:
        return [
            _synthetic_measurement_binding(action_identity_sha256, slot)
            for slot in measurement_slots
        ]

    supplied = supplied_by_action[action_identity_sha256]
    if not isinstance(supplied, Sequence) or isinstance(
        supplied, (str, bytes, bytearray)
    ):
        raise AssertionError("supplied measurement bindings must be a sequence")
    bindings_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for binding in supplied:
        if not isinstance(binding, Mapping):
            raise AssertionError("supplied measurement binding must be an object")
        key = (binding.get("slot_id"), binding.get("measurement_phase"))
        if not all(isinstance(value, str) for value in key):
            raise AssertionError("supplied measurement binding identity is invalid")
        if key in bindings_by_key:
            raise AssertionError(
                f"duplicate supplied measurement binding for slot {key!r}"
            )
        bindings_by_key[key] = dict(binding)

    expected_set = set(expected_keys)
    observed_set = set(bindings_by_key)
    if observed_set != expected_set:
        missing = [key for key in expected_keys if key not in observed_set]
        extra = [key for key in bindings_by_key if key not in expected_set]
        raise AssertionError(
            "supplied measurement bindings do not exactly cover frozen slots: "
            f"missing={missing!r}, extra={extra!r}"
        )
    return [bindings_by_key[key] for key in expected_keys]


def build_pass_bundle(
    contract: Mapping[str, Any],
    *,
    terminal_action_identity_sha256s: Sequence[str],
    measurement_bindings_by_action: Optional[
        Mapping[str, Sequence[Mapping[str, Any]]]
    ] = None,
    fail_action_identity_sha256: Optional[str] = None,
) -> dict[str, Any]:
    """Exercise the real engine with fake transport and a temporary claim root."""

    bindings_by_action = measurement_bindings_by_action or {}
    included = set(dependency_closure(contract, terminal_action_identity_sha256s))
    action_items = []
    items_by_sha: dict[str, Mapping[str, Any]] = {}
    session_starts: dict[str, Mapping[str, Any]] = {}
    previous_completed = datetime(2026, 8, 8, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as temporary:
        claim_store = execution.AtomicWorkspaceClaimStore(Path(temporary))
        for entry in contract["actions"]:
            action_sha = entry["action_identity_sha256"]
            if action_sha not in included:
                continue
            snapshot = execution.load_action_snapshot(contract, entry["action_key"])
            session_id = snapshot.session["session_id"]
            usage_snapshot_at = previous_completed + timedelta(minutes=1)
            evaluated_at = previous_completed + timedelta(minutes=2)
            claimed_at = previous_completed + timedelta(minutes=3)
            protocol_completed_at = previous_completed + timedelta(minutes=4)
            completed_at = previous_completed + timedelta(minutes=5)
            profile = reviewed_limit_profile(
                contract,
                last_visible_at=previous_completed,
                snapshot_at=usage_snapshot_at,
            )
            if session_id not in session_starts:
                cold = snapshot.session["power_mode"] == "panel_cold_cycle"
                session_starts[session_id] = execution.seal_session_start(
                    {
                        "schema_version": 1,
                        "kind": execution.SESSION_START_KIND,
                        "session_id": session_id,
                        "observed_at": _timestamp(usage_snapshot_at),
                        "power_mode": snapshot.session["power_mode"],
                        "j2_initially_off": cold,
                        "measured_panel_power_off_seconds": (
                            float(snapshot.session["minimum_panel_power_off_seconds"])
                            if cold
                            else None
                        ),
                        "controller_fresh_boot_observed": cold,
                        "j2_on_before_first_action": True,
                        "supply_cv_current_normal": True,
                        "temperature_normal": True,
                        "physical_cutoff_available": True,
                        "observation_artifact_sha256": hash_text(
                            f"session-start-{session_id}"
                        ),
                    },
                    snapshot=snapshot,
                )
            session_start = session_starts[session_id]
            authorization = seal_external_authorization(
                {
                    "schema_version": 1,
                    "kind": execution.AUTHORIZATION_KIND,
                    "authorization_id": f"AUTH-{entry['action_key']}",
                    "action_identity_sha256": action_sha,
                    "execution_contract_canonical_sha256": contract["integrity"][
                        "canonical_sha256"
                    ],
                    "session_start_file_sha256": execution._sha256(session_start),
                    "issued_at": _timestamp(evaluated_at),
                    "expires_at": _timestamp(evaluated_at + timedelta(hours=1)),
                    "operator_id": "n5-structural-operator",
                    "authorization_artifact_sha256": hash_text(
                        f"authorization-artifact-{entry['action_key']}"
                    ),
                    "confirmation_sha256": hash_text(
                        f"confirmation-{entry['action_key']}"
                    ),
                    "maximum_post_requests": 1,
                    "automatic_advance_authorized": False,
                    "automatic_retry_authorized": False,
                    "automatic_recovery_authorized": False,
                }
            )
            prior_sha = entry["immediate_prior_action_identity_sha256"]
            prior_item = None if prior_sha is None else items_by_sha[prior_sha]

            def transport(_method: str, _endpoint: str, _data: bytes | None) -> object:
                return {"status": 200}

            def driver(audited: execution.AuditedTransport, frame: bytes) -> Mapping[str, Any]:
                audited.request("GET", "/api/version")
                audited.request("POST", "/api/frame", frame)
                audited.request("GET", "/api/job")
                audited.request("GET", "/api/diagnostic/report")
                return {
                    "structural_test_only": True,
                    "completed_job_artifact_sha256": hash_text(
                        f"device-evidence-{entry['action_key']}"
                    ),
                }

            receipt = execution.execute_fixed_action_once(
                contract,
                entry["action_key"],
                load_action_frame(contract, entry["action_key"]),
                limit_profile=profile,
                profile_evaluated_at=_timestamp(evaluated_at),
                authorization=authorization,
                session_start=session_start,
                runtime_gates={
                    "observed_at": _timestamp(evaluated_at),
                    "start_temperature_c": 23.0,
                    "supply_cv_current_normal": True,
                    "j2_on": True,
                    "physical_cutoff_available": True,
                    "operator_advance_artifact_sha256": hash_text(
                        f"advance-{entry['action_key']}"
                    ),
                    "runtime_evidence_sha256": hash_text(
                        f"runtime-{entry['action_key']}"
                    ),
                },
                prior_bundle=prior_item,
                attempt_id=f"attempt-{entry['order']:03d}",
                claimed_at=_timestamp(claimed_at),
                protocol_completed_at=_timestamp(protocol_completed_at),
                claim_store=claim_store,
                transport=transport,
                protocol_driver=driver,
            )
            manual = execution.seal_manual_observation(
                {
                    "schema_version": 1,
                    "kind": execution.MANUAL_OBSERVATION_KIND,
                    "execution_contract_canonical_sha256": contract["integrity"][
                        "canonical_sha256"
                    ],
                    "attempt_id": f"attempt-{entry['order']:03d}",
                    "action_key": entry["action_key"],
                    "action_identity_sha256": action_sha,
                    "protocol_evidence_file_sha256": receipt[
                        "protocol_evidence_file_sha256"
                    ],
                    "observed_at": _timestamp(completed_at),
                    "source_observation_artifact_sha256": hash_text(
                        f"manual-observation-{entry['action_key']}"
                    ),
                    "visual_pass": action_sha != fail_action_identity_sha256,
                    "electrical_pass": True,
                    "thermal_pass": True,
                    "measurement_pass": True,
                    "continuity": execution.expected_continuity(
                        contract, entry["action_key"]
                    ),
                    "measurement_bindings": _measurement_bindings_in_frozen_order(
                        action_sha,
                        snapshot.measurement_slots,
                        bindings_by_action,
                    ),
                    "notes": "structural offline test only",
                },
                contract=contract,
                action_key=entry["action_key"],
                attempt_id=f"attempt-{entry['order']:03d}",
                protocol_evidence_file_sha256=receipt[
                    "protocol_evidence_file_sha256"
                ],
            )
            item = execution.finalize_protocol_receipt(
                contract,
                receipt,
                manual,
                completed_at=_timestamp(completed_at),
            )
            action_items.append(item)
            items_by_sha[action_sha] = item
            previous_completed = completed_at
    cut_sessions = sorted(
        {
            summary["session_id"]
            for item in action_items
            for summary in [execution._validate_action_item(contract, item)]
            if summary["plan_class"] == "formal_transition"
            or summary["state"] != "PASS"
        }
    )
    return execution.build_finalized_bundle(
        contract,
        action_items,
        list(session_starts.values()),
        finalized_at=_timestamp(previous_completed + timedelta(minutes=1)),
        j2_cut_session_ids=cut_sessions,
    )
