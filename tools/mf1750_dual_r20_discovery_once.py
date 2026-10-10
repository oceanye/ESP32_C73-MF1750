#!/usr/bin/env python3
"""One-shot dual-controller R20 discovery with discovery-first branching.

H20 and H23 each expose one fixed eight-code atlas plus a separately flashed
factory-OTP white recovery.  A no-new-colour operator decision permits white
recovery and then the next candidate.  A suspected-new-colour decision blocks
the next candidate and reserves left/right swap replication for a later,
separately built image.  This tool never flashes firmware or controls power.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_physical_once as physical
from tools.mf1750_ec5_runtime_lut_compiled_identity import _binary_elf_link


BASE_RELEASE = Path(
    ".test-output/hardware/MF1750_EC5_EMPIRICAL_H3_RELEASES_20260812_V7/"
    "WF20_25-release.json"
)
BASE_RELEASE_SHA256 = (
    "323edaf20ddc60e1302b7df7217320ddb19c2c3ab47cad14409888469ec4809e"
)
INCLUDE_PAIR_SHA256 = (
    "86981885b2d4a0eece7060d843eaed3f942cfc62c6046620130b3c83bd58290f"
)
MONITORS = contract.OPERATOR_MONITORING_CONFIRMATION
NO_NEW = "no_new_color"
SUSPECTED_NEW = "suspected_new_color"


@dataclass(frozen=True)
class Image:
    binary: Path
    elf: Path
    binary_sha256: str
    elf_sha256: str
    build_tag: str
    test_id: str
    environment: str
    nvs_namespace: str
    descriptor_id: str
    action_id: str
    role: str


@dataclass(frozen=True)
class Candidate:
    key: str
    profile_id: str
    global_header: str
    campaign_id: str
    contract_id: str
    release_id: str
    treatment: Image
    recovery: Image
    electrical: Mapping[str, Any]


def _image(
    *,
    binary: str,
    elf: str,
    binary_sha256: str,
    elf_sha256: str,
    build_tag: str,
    test_id: str,
    environment: str,
    nvs_namespace: str,
    descriptor_id: str,
    action_id: str,
    role: str,
) -> Image:
    return Image(
        Path(binary),
        Path(elf),
        binary_sha256,
        elf_sha256,
        build_tag,
        test_id,
        environment,
        nvs_namespace,
        descriptor_id,
        action_id,
        role,
    )


CANDIDATES = {
    "H20": Candidate(
        key="H20",
        profile_id="WF20_HEADER__CS1_WF20_R20__CS2_WF23_R20",
        global_header="WF20_25",
        campaign_id="EC5_DUAL_R20_DISCOVERY_20260821",
        contract_id="a647e7ee13e806fef53aad0d9f1a10483b498950f1c9c3e232dcd2349c4965d2",
        release_id=hashlib.sha256(b"dual-r20-h20-release-v1").hexdigest(),
        treatment=_image(
            binary=".pio/build-dual-r20-h20/ec5_dual_r20_h20/firmware.bin",
            elf=".pio/build-dual-r20-h20/ec5_dual_r20_h20/firmware.elf",
            binary_sha256="315bffd51a4d8279f96e109adf3a5864b3945f8ce3091b4868fa72f0c956a98e",
            elf_sha256="2c2d9f44537340b094d18e9111908a26b490c741d9bee6cc87823736c2e83919",
            build_tag="MF1750_EC5_DUAL_R20_H20_DISCOVERY_V1_2026-08-21",
            test_id="EC5-DUAL-R20-DISCOVERY-H20-V1",
            environment="ec5_dual_r20_h20",
            nvs_namespace="dr20h20_0821",
            descriptor_id="ba996ea441c31a9a2c715b574449022e6dcba12b63aa98042aa4cacbb9ead990",
            action_id="f00619964239d010ba9bfb210b65edc6888d3bceba8587953c2cf431ef7ec79b",
            role="DUAL_R20_H20_DISCOVERY_ATLAS",
        ),
        recovery=_image(
            binary=".pio/build-dual-r20-h20-white/ec5_dual_r20_h20_white/firmware.bin",
            elf=".pio/build-dual-r20-h20-white/ec5_dual_r20_h20_white/firmware.elf",
            binary_sha256="d042c9127e00c2f64e68390fbd57d0295fa46987b4bd6bee29a571286fd3585a",
            elf_sha256="5d3860694c7574a0fb8ff1199359d8e11c199ed63347bc2fadb848427fb0ed55",
            build_tag="MF1750_EC5_DUAL_R20_H20_WHITE_V1_2026-08-21",
            test_id="EC5-FACTORY-OTP-WHITE-RECOVERY-V1",
            environment="ec5_dual_r20_h20_white",
            nvs_namespace="dr20w_0821",
            descriptor_id="40fbb9fabf3a6d349ff59afd33ec7aa5c766feb65c0e731c4a3a190190cac8d7",
            action_id="ec6021edf5588e203146a8b1cd66a6a85e6fe1de957225cfe639ed107e764d46",
            role=contract.ROLE_WHITE,
        ),
        electrical={
            "gate_positive_mv": 20000,
            "gate_negative_mv": -20000,
            "full_source_positive_mv": 15000,
            "full_source_negative_mv": -15000,
            "intermediate_source_mv": {
                "vsh_lv": 6500,
                "vsl_lv": -8200,
                "vsh_lv2": 8000,
                "vsl_lv2": -8800,
            },
            "frame_rate_hz": 43,
            "vcom_written_or_swept": False,
            "panel_fpl_or_film_lot_qualified": False,
        },
    ),
    "H23": Candidate(
        key="H23",
        profile_id="WF23_HEADER__CS1_WF20_R20__CS2_WF23_R20",
        global_header="WF23_25",
        campaign_id="EC5_DUAL_R20_DISCOVERY_H23_20260821",
        contract_id="4cfb5a121c630afac36f2570516c540edb30658689e3c492d74d2ce9c2732552",
        release_id=hashlib.sha256(b"dual-r20-h23-release-v1").hexdigest(),
        treatment=_image(
            binary=".pio/build-dual-r20-h23/ec5_dual_r20_h23/firmware.bin",
            elf=".pio/build-dual-r20-h23/ec5_dual_r20_h23/firmware.elf",
            binary_sha256="87bb4ae4cfe89b655e6b85138a6ecf2391e25b00fe758a0a3ad9124bd38ac184",
            elf_sha256="89d415f88a3315ae7f3e7979e7f6f3f2f64fbbc563953571fbf3214118cac14d",
            build_tag="MF1750_EC5_DUAL_R20_H23_DISCOVERY_V1_2026-08-21",
            test_id="EC5-DUAL-R20-DISCOVERY-H23-V1",
            environment="ec5_dual_r20_h23",
            nvs_namespace="dr20h23_0821",
            descriptor_id="4cbd9393362a0c756edbb099ca6c952791da583267745fc6e537412557e67bae",
            action_id="05316eb5a3ade5f55ca593885408c11473663339256bf7862ad76f0e917f3d7a",
            role="DUAL_R20_H23_DISCOVERY_ATLAS",
        ),
        recovery=_image(
            binary=".pio/build-dual-r20-h23-white/ec5_dual_r20_h23_white/firmware.bin",
            elf=".pio/build-dual-r20-h23-white/ec5_dual_r20_h23_white/firmware.elf",
            binary_sha256="f25f00f55c979272b7d01dd3b5f67b86b6b27150c0f35333e4a60e7fee59fc43",
            elf_sha256="ba2bf9e1807ca2fce4870990a8b2d81a73cc0736abbbf97cb7fadcb5588b4ff5",
            build_tag="MF1750_EC5_DUAL_R20_H23_WHITE_V1_2026-08-21",
            test_id="EC5-FACTORY-OTP-WHITE-RECOVERY-V1",
            environment="ec5_dual_r20_h23_white",
            nvs_namespace="dr23w_0821",
            descriptor_id="6fccec274e1b08d50531004bcd792276a814ec05fecf37734f406317dc34658e",
            action_id="7be31906a639fa1433a76123b55183eac57aad2ab929ed7c7888b4ab807704d3",
            role=contract.ROLE_WHITE,
        ),
        electrical={
            "gate_positive_mv": 20000,
            "gate_negative_mv": -20000,
            "full_source_positive_mv": 15000,
            "full_source_negative_mv": -15000,
            "intermediate_source_mv": {
                "vsh_lv": 7200,
                "vsl_lv": -8400,
                "vsh_lv2": 8200,
                "vsl_lv2": -9800,
            },
            "frame_rate_hz": 43,
            "vcom_written_or_swept": False,
            "panel_fpl_or_film_lot_qualified": False,
        },
    ),
}


class DualR20Error(ValueError):
    """A candidate artifact, decision, or progression gate differs."""


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path, wanted: str, label: str) -> None:
    if not path.is_file() or path.is_symlink() or _sha_file(path) != wanted:
        raise DualR20Error(f"{label} absent, unsafe, or SHA-256 differs")


def _marker(candidate: Candidate, image: Image) -> str:
    role = "OTP_WHITE" if image.role == contract.ROLE_WHITE else "RUNTIME"
    return (
        f"MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE={candidate.profile_id}|"
        f"ROLE={role}|SHA256={image.descriptor_id}"
    )


def validate_artifacts(candidate: Candidate) -> None:
    _require_file(BASE_RELEASE, BASE_RELEASE_SHA256, "base release")
    for label, image in (("treatment", candidate.treatment), ("recovery", candidate.recovery)):
        _require_file(image.binary, image.binary_sha256, f"{candidate.key} {label} BIN")
        _require_file(image.elf, image.elf_sha256, f"{candidate.key} {label} ELF")
        binary = image.binary.read_bytes()
        elf = image.elf.read_bytes()
        _binary_elf_link(binary, elf)
        marker = _marker(candidate, image).encode("ascii")
        if elf.count(marker) != 1 or binary.count(marker) != 1:
            raise DualR20Error(f"{candidate.key} {label} descriptor marker differs")
        required = (
            candidate.profile_id,
            candidate.campaign_id,
            candidate.contract_id,
            image.build_tag,
            image.test_id,
            image.environment,
            image.nvs_namespace,
            image.descriptor_id,
            image.action_id,
        )
        if any(token.encode("ascii") not in elf for token in required):
            raise DualR20Error(f"{candidate.key} {label} compiled identity differs")
    pair = (
        Path("src/generated/spd1657_wf20_25_empirical_h3.inc").read_bytes()
        + Path("src/generated/spd1657_wf23_25_empirical_h3.inc").read_bytes()
    )
    if hashlib.sha256(pair).hexdigest() != INCLUDE_PAIR_SHA256:
        raise DualR20Error("generated include pair SHA-256 differs")


def load_context(candidate: Candidate) -> physical.ReleaseContext:
    validate_artifacts(candidate)
    base = physical.load_release(BASE_RELEASE)
    root = copy.deepcopy(base.root)
    root.update(
        {
            "profile_id": candidate.profile_id,
            "campaign_id": candidate.campaign_id,
            "contract_id": candidate.contract_id,
            "release_id": candidate.release_id,
        }
    )
    profile = root["profile_contract"]
    profile.update(
        {
            "profile_id": candidate.profile_id,
            "campaign_id": candidate.campaign_id,
            "contract_id": candidate.contract_id,
            "requested_electrical_metadata": dict(candidate.electrical),
            "vendor_filename_numeric_tokens": (
                [20, 25] if candidate.key == "H20" else [23, 25]
            ),
            "generated_include": {
                "relative_path": "WF20+WF23 generated include pair",
                "sha256": INCLUDE_PAIR_SHA256,
            },
        }
    )
    images = (candidate.treatment, candidate.recovery)
    for ordinal, image in enumerate(images, 1):
        action = next(item for item in profile["actions"] if item["ordinal"] == ordinal)
        action.update(
            {
                "profile_id": candidate.profile_id,
                "campaign_id": candidate.campaign_id,
                "environment": image.environment,
                "nvs_namespace": image.nvs_namespace,
                "hardware_action_id": image.action_id,
                "transaction_descriptor_sha256": image.descriptor_id,
                "role": image.role,
            }
        )
        binding = next(
            item for item in root["action_artifact_bindings"] if item["ordinal"] == ordinal
        )
        binding.update(
            {
                "build_tag": image.build_tag,
                "test_id": image.test_id,
                "campaign_id": candidate.campaign_id,
                "environment": image.environment,
                "nvs_namespace": image.nvs_namespace,
                "hardware_action_id": image.action_id,
                "transaction_descriptor_sha256": image.descriptor_id,
                "firmware_binary_sha256": image.binary_sha256,
                "firmware_elf_sha256": image.elf_sha256,
                "generated_include_sha256": INCLUDE_PAIR_SHA256 if ordinal == 1 else None,
                "role": image.role,
            }
        )
    return physical.ReleaseContext(root=root, release_file=BASE_RELEASE.resolve())


@contextmanager
def _physical_overrides(candidate: Candidate):
    original_marker = contract.compiled_descriptor_marker
    original_version = physical._expect_version  # noqa: SLF001

    def marker(profile_id: str, role: str) -> str:
        if profile_id == candidate.profile_id:
            image = candidate.recovery if role == contract.ROLE_WHITE else candidate.treatment
            return _marker(candidate, image)
        return original_marker(profile_id, role)

    def expect_version(
        value: Mapping[str, Any], context: physical.ReleaseContext, ordinal: int
    ) -> None:
        if ordinal == 1:
            profile = value.get("profile")
            if not isinstance(profile, Mapping) or (
                profile.get("compiled_profile_count") != 2
                or profile.get("global_header_profile") != candidate.global_header
                or profile.get("cs1_r20_profile") != "WF20_25"
                or profile.get("cs2_r20_profile") != "WF23_25"
            ):
                raise physical.PhysicalOnceError("dual-profile version mapping differs")
            adjusted = copy.deepcopy(value)
            adjusted["profile"]["compiled_profile_count"] = 1
            original_version(adjusted, context, ordinal)
            return
        original_version(value, context, ordinal)

    contract.compiled_descriptor_marker = marker
    physical._expect_version = expect_version  # noqa: SLF001
    try:
        yield
    finally:
        contract.compiled_descriptor_marker = original_marker
        physical._expect_version = original_version  # noqa: SLF001


def describe() -> dict[str, Any]:
    for candidate in CANDIDATES.values():
        validate_artifacts(candidate)
    return {
        "schema_version": 1,
        "kind": "mf1750-dual-r20-discovery-first-plan",
        "candidate_order": ["H20", "H23"],
        "per_candidate_visible_atlas_refreshes": 1,
        "per_candidate_outcomes": 16,
        "single_pixel_codes_per_controller": 8,
        "spatial_dithering": False,
        "partial_refresh": False,
        "mid_refresh_power_cut": False,
        "spi_hz": 1_000_000,
        "decision_policy": {
            NO_NEW: "white_recovery_then_next_candidate",
            SUSPECTED_NEW: "white_recovery_then_left_right_swap_replication",
            "brightness_only": NO_NEW,
        },
        "swap_image_prebuilt": False,
        "automatic_chaining": False,
        "retry": False,
        "device_requests": 0,
        "visible_refreshes": 0,
        "candidates": {
            key: {
                "profile_id": item.profile_id,
                "global_header": item.global_header,
                "cs1_r20": "WF20_25",
                "cs2_r20": "WF23_25",
                "treatment_bin_sha256": item.treatment.binary_sha256,
                "recovery_bin_sha256": item.recovery.binary_sha256,
            }
            for key, item in CANDIDATES.items()
        },
    }


def _successful_result(path: Path, candidate: Candidate, ordinal: int) -> Mapping[str, Any]:
    value = physical._read_json(path, label="physical result")  # noqa: SLF001
    physical._validate_seal(value, label="physical result")  # noqa: SLF001
    image = candidate.treatment if ordinal == 1 else candidate.recovery
    if (
        value.get("kind") != physical.RESULT_KIND
        or value.get("profile_id") != candidate.profile_id
        or value.get("ordinal") != ordinal
        or value.get("hardware_action_id") != image.action_id
        or value.get("outcome") != "success"
        or value.get("visible_refreshes") != 1
        or value.get("retry_allowed") is not False
    ):
        raise DualR20Error("physical result does not prove the required action")
    return value


def record_decision(
    candidate: Candidate,
    treatment_result: Path,
    outcome: str,
    notes: str,
) -> dict[str, Any]:
    result = _successful_result(treatment_result, candidate, 1)
    next_step = (
        "WHITE_RECOVERY_THEN_NEXT_CANDIDATE"
        if outcome == NO_NEW
        else "WHITE_RECOVERY_THEN_LEFT_RIGHT_SWAP_REPLICATION"
    )
    return physical._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-dual-r20-operator-colour-decision",
            "candidate": candidate.key,
            "profile_id": candidate.profile_id,
            "treatment_result_sha256": contract.sha256(treatment_result.read_bytes()),
            "treatment_claim_file_sha256": result["claim_file_sha256"],
            "outcome": outcome,
            "notes": notes,
            "new_colour_claim_is_instrumentally_verified": False,
            "next_step": next_step,
            "left_right_swap_required": outcome == SUSPECTED_NEW,
            "next_unswapped_candidate_allowed": outcome == NO_NEW,
        }
    )


def _decision(path: Path, candidate: Candidate) -> Mapping[str, Any]:
    value = physical._read_json(path, label="operator colour decision")  # noqa: SLF001
    physical._validate_seal(value, label="operator colour decision")  # noqa: SLF001
    if (
        value.get("kind") != "mf1750-dual-r20-operator-colour-decision"
        or value.get("candidate") != candidate.key
        or value.get("profile_id") != candidate.profile_id
        or value.get("outcome") not in (NO_NEW, SUSPECTED_NEW)
    ):
        raise DualR20Error("operator colour decision differs")
    return value


def _check_progression(args: argparse.Namespace, candidate: Candidate) -> None:
    if args.ordinal == 2:
        if args.decision is None:
            raise DualR20Error("white recovery requires this candidate's decision file")
        _decision(args.decision, candidate)
    if candidate.key == "H23" and args.ordinal == 1:
        if args.prior_decision is None or args.prior_recovery_result is None:
            raise DualR20Error("H23 requires H20 no-new decision and H20 white result")
        prior = CANDIDATES["H20"]
        decision = _decision(args.prior_decision, prior)
        if decision["outcome"] != NO_NEW:
            raise DualR20Error("H20 suspected-new result blocks H23; build swap replication")
        _successful_result(args.prior_recovery_result, prior, 2)


def _diagnose(args: argparse.Namespace, candidate: Candidate) -> dict[str, Any]:
    context = load_context(candidate)
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    screen = physical.SCREEN_INITIAL if args.ordinal == 1 else physical.SCREEN_RECOVERY
    with _physical_overrides(candidate):
        return physical.diagnose_j2_off(
            context,
            args.ordinal,
            operator_temperature_c=args.temperature_c,
            operator_screen_state=screen,
            operator_j2_state="OFF",
            operator_monitoring_state=MONITORS,
            requester=requester,
        )


def _run(args: argparse.Namespace, candidate: Candidate) -> dict[str, Any]:
    _check_progression(args, candidate)
    context = load_context(candidate)
    diagnostic = physical._read_json(args.diagnostic, label="J2-OFF diagnostic")  # noqa: SLF001
    requester = physical._http_requester(args.base_url, args.timeout_s)  # noqa: SLF001
    with _physical_overrides(candidate):
        authorization = physical.required_authorization(
            context, args.ordinal, args.temperature_c, diagnostic
        )
        return physical.run_once(
            context,
            args.ordinal,
            operator_temperature_c=args.temperature_c,
            operator_j2_state="ON",
            operator_monitoring_state=MONITORS,
            authorization=authorization,
            diagnostic=diagnostic,
            requester=requester,
            claim_registry=args.claim_registry,
            poll_count=args.poll_count,
            poll_interval_seconds=args.poll_interval_seconds,
        )


def _common_live(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate", choices=tuple(CANDIDATES), required=True)
    parser.add_argument("--ordinal", type=int, choices=(1, 2), required=True)
    parser.add_argument("--temperature-c", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout-s", type=float, default=10.0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe")
    diagnose = commands.add_parser("diagnose")
    _common_live(diagnose)
    diagnose.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    _common_live(run)
    run.add_argument("--diagnostic", type=Path, required=True)
    run.add_argument("--decision", type=Path)
    run.add_argument("--prior-decision", type=Path)
    run.add_argument("--prior-recovery-result", type=Path)
    run.add_argument("--claim-registry", type=Path, required=True)
    run.add_argument("--poll-count", type=int, default=10)
    run.add_argument("--poll-interval-seconds", type=float, default=5.0)
    run.add_argument("--output", type=Path, required=True)
    record = commands.add_parser("record")
    record.add_argument("--candidate", choices=tuple(CANDIDATES), required=True)
    record.add_argument("--treatment-result", type=Path, required=True)
    record.add_argument("--outcome", choices=(NO_NEW, SUSPECTED_NEW), required=True)
    record.add_argument("--notes", default="")
    record.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "describe":
            report = describe()
        elif args.command == "record":
            report = record_decision(
                CANDIDATES[args.candidate], args.treatment_result, args.outcome, args.notes
            )
            physical._write_new(args.output, report, label="colour decision")  # noqa: SLF001
        elif args.command == "diagnose":
            report = _diagnose(args, CANDIDATES[args.candidate])
            physical._write_new(args.output, report, label="J2-OFF diagnostic")  # noqa: SLF001
        else:
            report = _run(args, CANDIDATES[args.candidate])
            physical._write_new(args.output, report, label="physical result")  # noqa: SLF001
    except (DualR20Error, physical.PhysicalOnceError) as error:
        print(f"dual-R20 error: {error}")
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
