"""Build the fixed, non-materializable 12-action runtime-waveform campaign."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from . import contracts


CAMPAIGN_SCHEMA_VERSION = 1
CAMPAIGN_KIND = "mf1750-runtime-waveform-placeholder-campaign"
LAYOUT_KIND = "mf1750-runtime-waveform-placeholder-layouts"
DAG_KIND = "mf1750-runtime-waveform-placeholder-action-dag"
CLASSIFICATION = "SOFTWARE_PLACEHOLDER_NOT_MATERIALIZABLE"
BUNDLE_ID = "MF1750_RUNTIME_WAVEFORM_PLACEHOLDER_CAMPAIGN_20260810_V1"

_PSEUDOCOLORS = (
    (20, 20, 20),
    (245, 245, 245),
    (245, 205, 45),
    (215, 45, 45),
    (65, 105, 225),
    (45, 115, 215),
    (45, 170, 90),
    (145, 75, 185),
)
_ACTION_DECLARATIONS = (
    (1, "k0_eight_code_atlas", "K0", "atlas", None, False),
    (2, "otp_white_recovery_after_k0", "OTP", "white", 1, False),
    (3, "c1_eight_code_atlas", "C1", "atlas", 2, False),
    (4, "otp_white_recovery_after_c1_atlas", "OTP", "white", 3, False),
    (5, "c2_eight_code_atlas", "C2", "atlas", 4, False),
    (6, "otp_white_recovery_after_c2_atlas", "OTP", "white", 5, True),
    (7, "c1_transition_primer_8x8", "C1", "transition_primer", 6, False),
    (8, "c1_transition_target_8x8", "C1", "transition_target", 7, False),
    (9, "otp_white_recovery_after_c1_matrix", "OTP", "white", 8, False),
    (10, "c2_transition_primer_8x8", "C2", "transition_primer", 9, False),
    (11, "c2_transition_target_8x8", "C2", "transition_target", 10, False),
    (12, "otp_white_recovery_final", "OTP", "white", 11, True),
)
_OUTPUT_FILES = {
    "campaign.json",
    "layout.json",
    "action-dag.json",
    "MANUAL-OBSERVATION-TEMPLATE.md",
    "preview/PSEUDOCOLOR-NOT-PHYSICAL-atlas.png",
    "preview/PSEUDOCOLOR-NOT-PHYSICAL-transition-primer.png",
    "preview/PSEUDOCOLOR-NOT-PHYSICAL-transition-target.png",
    "preview/PSEUDOCOLOR-NOT-PHYSICAL-white-recovery.png",
}


class PlaceholderCampaignError(ValueError):
    """Raised when the fixed placeholder campaign is changed or materialized."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _declaration_identity(value: Mapping[str, Any]) -> str:
    return _sha(contracts.canonical_json_bytes(value))


def build_layouts() -> dict[str, Any]:
    """Return fixed no-text atlas/matrix ROI layouts for two controllers."""

    atlas_rois: list[dict[str, Any]] = []
    for controller, x_offset, codes in (
        ("CS1", 0, tuple(range(8))),
        ("CS2", 512, tuple(reversed(range(8)))),
    ):
        for position, code in enumerate(codes):
            row, column = divmod(position, 4)
            atlas_rois.append(
                {
                    "controller": controller,
                    "transport_code": code,
                    "x": x_offset + 20 + column * 120,
                    "y": 60 + row * 260,
                    "width": 112,
                    "height": 220,
                    "contains_text": False,
                }
            )

    matrix_rois: list[dict[str, Any]] = []
    for controller, x_offset in (("CS1", 0), ("CS2", 512)):
        for old_code in range(8):
            for new_code in range(8):
                display_row = old_code if controller == "CS1" else 7 - old_code
                display_column = new_code if controller == "CS1" else 7 - new_code
                matrix_rois.append(
                    {
                        "controller": controller,
                        "old_code": old_code,
                        "new_code": new_code,
                        "x": x_offset + 32 + display_column * 56,
                        "y": 44 + display_row * 64,
                        "width": 56,
                        "height": 64,
                        "contains_text": False,
                    }
                )
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "kind": LAYOUT_KIND,
        "panel_width": 1024,
        "panel_height": 600,
        "controller_width": 512,
        "no_dither": True,
        "text_inside_roi": False,
        "pseudocolor_is_not_optical_prediction": True,
        "atlas": {
            "layout_id": "dual-controller-reversed-eight-code-atlas-v1",
            "rois": atlas_rois,
        },
        "transition_matrix": {
            "layout_id": "dual-controller-mirrored-8x8-old-to-new-v1",
            "rois": matrix_rois,
        },
    }


def build_placeholder_campaign(*, created_at: str) -> dict[str, Any]:
    """Build 12 immutable declarations without inventing profile identities."""

    try:
        contracts._timestamp(created_at, label="created_at")  # noqa: SLF001
    except contracts.RuntimeWaveformContractError as error:
        raise PlaceholderCampaignError(str(error)) from error
    actions: list[dict[str, Any]] = []
    for ordinal, label, profile_slot, layout_role, predecessor, safe_stop in _ACTION_DECLARATIONS:
        declaration = {
            "ordinal": ordinal,
            "label": label,
            "profile_slot": profile_slot,
            "layout_role": layout_role,
            "predecessor_ordinal": predecessor,
            "single_arm": True,
            "single_execute": True,
            "single_driver_call": True,
            "automatic_retry_allowed": False,
            "automatic_recovery_allowed": False,
            "safe_stop_after": safe_stop,
            "materialized": False,
            "profile_manifest_sha256": None,
            "cs1_payload_sha256": None,
            "cs2_payload_sha256": None,
            "action_identity_sha256": None,
            "visible_refresh_authorized": False,
        }
        actions.append(
            {
                **declaration,
                "declaration_identity_sha256": _declaration_identity(declaration),
            }
        )
    unsigned = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "kind": CAMPAIGN_KIND,
        "bundle_id": BUNDLE_ID,
        "created_at": created_at,
        "classification": CLASSIFICATION,
        "profile_placeholders": [
            {
                "profile_slot": "K0",
                "purpose": "otp_equivalent_runtime_baseline_placeholder",
                "profile_manifest_sha256": None,
                "payload_identity_available": False,
            },
            {
                "profile_slot": "C1",
                "purpose": "candidate_profile_one_placeholder",
                "profile_manifest_sha256": None,
                "payload_identity_available": False,
            },
            {
                "profile_slot": "C2",
                "purpose": "candidate_profile_two_placeholder",
                "profile_manifest_sha256": None,
                "payload_identity_available": False,
            },
        ],
        "recovery_profile": {
            "profile_slot": "OTP",
            "purpose": "otp_white_recovery_placeholder",
            "equivalence_proven": False,
            "recovery_validated": False,
        },
        "constraints": {
            "no_dither": True,
            "atlas_transport_code_count": 8,
            "cs1_cs2_layout": "mirrored_or_reversed",
            "matrix_roi_text_allowed": False,
            "actions_per_refresh_attempt": 1,
            "automatic_retry_allowed": False,
            "automatic_recovery_allowed": False,
            "profile_switch_cost_must_be_reported": True,
            "multi_pass_cost_must_be_reported": True,
            "target_stable_measurable_states": "10-12_research_goal_not_promise",
            "sixteen_color_exploration_deferred": True,
        },
        "actions": actions,
        "action_count": 12,
        "materialized_action_count": 0,
        "blocker_codes": [
            "REAL_DUAL_CONTROLLER_3BIT_PROFILES_MISSING",
            "K0_OTP_EQUIVALENCE_UNPROVEN",
            "RUNTIME_TO_OTP_RECOVERY_UNPROVEN",
            "TRUSTED_FORMAT_NOT_REGISTERED",
            "ELECTRICAL_LIMITS_NOT_APPROVED",
            "INDEPENDENT_REVIEW_MISSING",
        ],
        "materialized": False,
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "visible_refresh_authorized": False,
        "firmware_binary_generated": False,
        "authorization_token_generated": False,
        "hardware_io_performed": False,
        "network_io_performed": False,
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha(contracts.canonical_json_bytes(unsigned)),
            "scope": "all_top_level_fields_except_integrity",
        },
    }


def build_action_dag(campaign: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [
        {
            "ordinal": action["ordinal"],
            "label": action["label"],
            "declaration_identity_sha256": action["declaration_identity_sha256"],
            "materialized": False,
            "visible_refresh_authorized": False,
        }
        for action in campaign["actions"]
    ]
    edges = [
        {
            "from_ordinal": action["predecessor_ordinal"],
            "to_ordinal": action["ordinal"],
            "dependency": "immediate_prior_observation_and_result_required",
        }
        for action in campaign["actions"]
        if action["predecessor_ordinal"] is not None
    ]
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "kind": DAG_KIND,
        "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "nodes": nodes,
        "edges": edges,
        "root_ordinals": [1],
        "safe_stop_ordinals": [6, 12],
        "automatic_branching": False,
        "materialized": False,
        "visible_refresh_authorized": False,
    }


def _manual_template(campaign: Mapping[str, Any]) -> str:
    rows = [
        "| Ordinal | Action | Materialized | Authorization | Visual observation | Electrical/thermal | Verdict |",
        "|---:|---|---|---|---|---|---|",
    ]
    for action in campaign["actions"]:
        rows.append(
            f"| {action['ordinal']} | `{action['label']}` | false | false |  |  | BLOCKED |"
        )
    return "\n".join(
        [
            "# Runtime waveform 12-action 人工记录模板",
            "",
            "> 纯软件占位模板；不得据此授权、物化、刷写或刷新。Pseudocolor 不是物理颜色预测。",
            "",
            "- K0/C1/C2 payload/profile identity：缺失",
            "- `materialized=false`；`visible_refresh_authorized=false`",
            "- 每动作仅允许单 ARM / 单 EXECUTE / 单 driver call；禁止自动重试或恢复",
            "- Ordinal 6 为第一 safe stop；ordinal 12 为最终 safe stop",
            "",
            *rows,
            "",
        ]
    )


def _render_preview(layouts: Mapping[str, Any], role: str) -> Image.Image:
    image = Image.new("RGB", (1024, 600), _PSEUDOCOLORS[1])
    pixels = image.load()
    if role == "white":
        return image
    rois = (
        layouts["atlas"]["rois"]
        if role == "atlas"
        else layouts["transition_matrix"]["rois"]
    )
    for roi in rois:
        if role == "atlas":
            code = roi["transport_code"]
        elif role == "transition_primer":
            code = roi["old_code"]
        else:
            code = roi["new_code"]
        color = _PSEUDOCOLORS[code]
        for y in range(roi["y"], roi["y"] + roi["height"]):
            for x in range(roi["x"], roi["x"] + roi["width"]):
                pixels[x, y] = color
    return image


def validate_placeholder_campaign(campaign: Mapping[str, Any]) -> dict[str, Any]:
    """Validate fixed order, null materialization identities, and integrity."""

    expected = build_placeholder_campaign(created_at=campaign.get("created_at", ""))
    if campaign != expected:
        raise PlaceholderCampaignError("placeholder campaign differs from the frozen contract")
    return {
        "valid": True,
        "action_count": 12,
        "materialized_action_count": 0,
        "safe_stop_ordinals": [6, 12],
        "visible_refresh_authorized": False,
    }


def write_placeholder_bundle(output_dir: Path, *, created_at: str) -> dict[str, Any]:
    """Exclusively create deterministic JSON/PNG/Markdown placeholder assets."""

    output_dir = Path(output_dir)
    if output_dir.exists():
        raise PlaceholderCampaignError("output directory already exists")
    output_dir.mkdir(parents=True)
    preview_dir = output_dir / "preview"
    preview_dir.mkdir()

    campaign = build_placeholder_campaign(created_at=created_at)
    layouts = build_layouts()
    dag = build_action_dag(campaign)
    (output_dir / "campaign.json").write_bytes(contracts.canonical_json_bytes(campaign))
    (output_dir / "layout.json").write_bytes(contracts.canonical_json_bytes(layouts))
    (output_dir / "action-dag.json").write_bytes(contracts.canonical_json_bytes(dag))
    (output_dir / "MANUAL-OBSERVATION-TEMPLATE.md").write_text(
        _manual_template(campaign), encoding="utf-8", newline="\n"
    )
    preview_names = {
        "atlas": "PSEUDOCOLOR-NOT-PHYSICAL-atlas.png",
        "transition_primer": "PSEUDOCOLOR-NOT-PHYSICAL-transition-primer.png",
        "transition_target": "PSEUDOCOLOR-NOT-PHYSICAL-transition-target.png",
        "white": "PSEUDOCOLOR-NOT-PHYSICAL-white-recovery.png",
    }
    for role, filename in preview_names.items():
        _render_preview(layouts, role).save(preview_dir / filename, format="PNG")

    hashes = {
        str(path.relative_to(output_dir)).replace("\\", "/"): {
            "bytes": path.stat().st_size,
            "sha256": _sha(path.read_bytes()),
        }
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    }
    sums = {
        "schema_version": 1,
        "kind": "mf1750-runtime-waveform-placeholder-bundle-sha256sums",
        "bundle_id": BUNDLE_ID,
        "files": hashes,
        "firmware_binary_generated": False,
        "visible_refresh_authorized": False,
    }
    (output_dir / "SHA256SUMS.json").write_bytes(contracts.canonical_json_bytes(sums))
    return validate_placeholder_bundle_directory(output_dir)


def _load_exact_json(path: Path) -> Any:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if payload != contracts.canonical_json_bytes(value):
        raise PlaceholderCampaignError(f"{path.name} is not canonical JSON")
    return value


def validate_placeholder_bundle_directory(output_dir: Path) -> dict[str, Any]:
    """Deep-check the generated files without hardware, serial, or network I/O."""

    output_dir = Path(output_dir)
    actual_files = {
        str(path.relative_to(output_dir)).replace("\\", "/")
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    expected_files = _OUTPUT_FILES | {"SHA256SUMS.json"}
    if actual_files != expected_files:
        raise PlaceholderCampaignError("placeholder bundle file set differs")
    forbidden = [path for path in actual_files if Path(path).suffix.lower() in {".bin", ".elf"}]
    if forbidden:
        raise PlaceholderCampaignError("placeholder bundle contains firmware artifacts")
    campaign = _load_exact_json(output_dir / "campaign.json")
    validate_placeholder_campaign(campaign)
    layouts = _load_exact_json(output_dir / "layout.json")
    if layouts != build_layouts():
        raise PlaceholderCampaignError("placeholder layouts differ")
    dag = _load_exact_json(output_dir / "action-dag.json")
    if dag != build_action_dag(campaign):
        raise PlaceholderCampaignError("placeholder action DAG differs")
    sums = _load_exact_json(output_dir / "SHA256SUMS.json")
    if sums["firmware_binary_generated"] is not False:
        raise PlaceholderCampaignError("placeholder bundle claims a firmware binary")
    for relative, identity in sums["files"].items():
        path = output_dir / relative
        payload = path.read_bytes()
        if len(payload) != identity["bytes"] or _sha(payload) != identity["sha256"]:
            raise PlaceholderCampaignError(f"bundle file identity differs: {relative}")
    for path in (output_dir / "preview").glob("*.png"):
        with Image.open(path) as preview:
            if preview.size != (1024, 600) or preview.mode != "RGB":
                raise PlaceholderCampaignError(f"preview geometry differs: {path.name}")
    return {
        "schema_version": 1,
        "kind": "mf1750-runtime-waveform-placeholder-bundle-validation",
        "valid": True,
        "bundle_id": BUNDLE_ID,
        "campaign_canonical_sha256": campaign["integrity"]["canonical_sha256"],
        "file_count": len(actual_files),
        "action_count": campaign["action_count"],
        "materialized_action_count": 0,
        "firmware_binary_generated": False,
        "hardware_execution_eligible": False,
        "execution_ready": False,
        "visible_refresh_authorized": False,
        "hardware_io_performed": False,
        "network_io_performed": False,
    }
