#!/usr/bin/env python3
"""Build and deeply verify production MF-1750 visible-refresh limit profiles.

All commands are offline.  They never discover or contact a device, create a
claim or authorization, upload firmware, or perform a visible refresh.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign.production_profile import (  # noqa: E402
    ProductionProfileError,
    SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
    build_supervised_experimental_policy_template,
    compile_production_draft_from_files,
    create_production_approval,
    describe_production_profile,
    publish_approval_bundle,
    publish_new_json,
    validate_production_profile,
    verify_mf1750_a1_source_document,
)


def _add_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--firmware-binary", type=Path, required=True)
    authority = parser.add_mutually_exclusive_group(required=True)
    authority.add_argument(
        "--limit-authority",
        dest="supplier_limits",
        type=Path,
        help="supplier limits or a supervised experimental process policy",
    )
    authority.add_argument(
        "--supplier-limits",
        dest="supplier_limits",
        type=Path,
        help="legacy alias for --limit-authority",
    )
    parser.add_argument("--usage-evidence", type=Path, required=True)


def _add_validation_inputs(parser: argparse.ArgumentParser) -> None:
    _add_sources(parser)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--review-artifact", type=Path)
    parser.add_argument("--review-key", type=Path)
    parser.add_argument("--evaluated-at")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    policy_template = subparsers.add_parser(
        "policy-template",
        help=(
            "publish an incomplete approved=false-equivalent supervised policy "
            "worksheet; no numeric limits are selected"
        ),
    )
    policy_template.add_argument("--issuer", required=True)
    policy_template.add_argument("--policy-id", required=True)
    policy_template.add_argument("--issued-at", required=True)
    policy_template.add_argument("--panel-model", required=True)
    policy_template.add_argument(
        "--source-document",
        type=Path,
        required=True,
        help="exact local MF-1750 A1 PDF; bytes are safely read and SHA-256 verified",
    )
    policy_template.add_argument("--output", type=Path, required=True)

    draft = subparsers.add_parser(
        "draft", help="compile a canonical approved=false profile from real files"
    )
    _add_sources(draft)
    draft.add_argument("--profile-id", required=True)
    draft.add_argument("--profile-version", required=True)
    draft.add_argument("--output", type=Path, required=True)

    approve = subparsers.add_parser(
        "approve", help="authenticate an exact draft and publish a reviewed pair"
    )
    _add_sources(approve)
    approve.add_argument("--draft-profile", type=Path, required=True)
    approve.add_argument("--reviewer-id", required=True)
    approve.add_argument("--reviewed-at", required=True)
    approve.add_argument("--review-key", type=Path, required=True)
    approve.add_argument("--review-artifact-output", type=Path, required=True)
    approve.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate", help="deeply validate all source bytes and review authentication"
    )
    _add_validation_inputs(validate)

    describe = subparsers.add_parser(
        "describe", help="read-only validation plus a time-specific readiness decision"
    )
    _add_validation_inputs(describe)
    describe.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit 3 when the deeply valid profile is not currently ready",
    )
    return parser.parse_args(argv)


def _validation_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "profile_file": args.profile,
        "campaign_file": args.campaign,
        "firmware_binary_file": args.firmware_binary,
        "supplier_limits_file": args.supplier_limits,
        "usage_evidence_file": args.usage_evidence,
        "review_artifact_file": args.review_artifact,
        "reviewer_key_file": args.review_key,
        "evaluated_at": args.evaluated_at,
    }


def _summary_base(command: str) -> dict[str, object]:
    return {
        "command": command,
        "network_io_performed": False,
        "device_io_performed": False,
        "claim_created": False,
        "authorization_created": False,
        "visible_refresh_performed": False,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "policy-template":
            source_document = verify_mf1750_a1_source_document(
                args.source_document
            )
            policy = build_supervised_experimental_policy_template(
                issuer=args.issuer,
                policy_id=args.policy_id,
                issued_at=args.issued_at,
                panel_model=args.panel_model,
            )
            file_sha = publish_new_json(
                args.output,
                policy,
                label="supervised experimental process policy template output",
            )
            result = {
                **_summary_base(args.command),
                "output": str(args.output),
                "kind": SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND,
                "not_a_supplier_rating": True,
                "approved": False,
                "execution_eligible": False,
                "numeric_limit_values_selected": False,
                "field_provenance_classifications_selected": False,
                "source_document_sha256": source_document.sha256,
                "source_document_bytes": len(source_document.payload),
                "file_sha256": file_sha,
            }
        elif args.command == "draft":
            profile = compile_production_draft_from_files(
                campaign_file=args.campaign,
                firmware_binary_file=args.firmware_binary,
                supplier_limits_file=args.supplier_limits,
                usage_evidence_file=args.usage_evidence,
                profile_id=args.profile_id,
                profile_version=args.profile_version,
            )
            file_sha = publish_new_json(
                args.output, profile, label="production draft output"
            )
            result = {
                **_summary_base(args.command),
                "output": str(args.output),
                "approved": False,
                "action_allowlist_count": len(profile["action_allowlist"]),
                "profile_canonical_sha256": profile["integrity"]["canonical_sha256"],
                "profile_file_sha256": file_sha,
            }
        elif args.command == "approve":
            bundle = create_production_approval(
                draft_profile_file=args.draft_profile,
                campaign_file=args.campaign,
                firmware_binary_file=args.firmware_binary,
                supplier_limits_file=args.supplier_limits,
                usage_evidence_file=args.usage_evidence,
                reviewer_id=args.reviewer_id,
                reviewed_at=args.reviewed_at,
                reviewer_key_file=args.review_key,
            )
            review_sha, profile_sha = publish_approval_bundle(
                bundle,
                review_artifact_output=args.review_artifact_output,
                profile_output=args.output,
            )
            result = {
                **_summary_base(args.command),
                "output": str(args.output),
                "review_artifact_output": str(args.review_artifact_output),
                "approved": True,
                "profile_canonical_sha256": bundle.profile["integrity"][
                    "canonical_sha256"
                ],
                "profile_file_sha256": profile_sha,
                "review_artifact_file_sha256": review_sha,
                "review_key_id": bundle.review_artifact["authentication"]["key_id"],
            }
        elif args.command == "validate":
            report = validate_production_profile(**_validation_kwargs(args))
            result = {**_summary_base(args.command), **report}
        else:
            if args.evaluated_at is None:
                raise ProductionProfileError("describe requires --evaluated-at")
            report = describe_production_profile(**_validation_kwargs(args))
            result = {**_summary_base(args.command), **report}
    except ProductionProfileError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    if (
        args.command == "describe"
        and args.require_ready
        and result["production_ready"] is not True
    ):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "parse_args"]
