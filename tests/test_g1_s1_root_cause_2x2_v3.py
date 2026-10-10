from __future__ import annotations

from copy import deepcopy
import importlib
import io
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
from typing import Mapping
import unittest
from unittest import mock
import urllib.request

from host.epd_frame import HEIGHT, WIDTH
from host.visible_refresh_campaign import seal_limit_profile
from tools import g1_s1_root_cause_2x2_candidate as v2
from tools import g1_s1_root_cause_2x2_v3 as v3


V2_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / ".test-output"
    / "hardware"
    / "G1S1_ROOT_CAUSE_2X2_OFFLINE_20260807_V2"
)


def _independent_transition(
    prior: bytes, final: bytes, *, x0: int = 0, x1: int = WIDTH
) -> tuple[tuple[int, ...], ...]:
    ranks = {code: index for index, code in enumerate(v3.PHYSICAL_CODE_ORDER)}
    matrix = [[0] * 6 for _ in range(6)]
    for y_value in range(HEIGHT):
        row = y_value * WIDTH
        for x_value in range(x0, x1):
            position = row + x_value
            matrix[ranks[prior[position]]][ranks[final[position]]] += 1
    return tuple(tuple(row) for row in matrix)


def _independent_metrics(codes: bytes) -> dict[str, int]:
    left = 0
    right = 0
    seam = 0
    boundary = 0
    for y_value in range(HEIGHT):
        row = y_value * WIDTH
        for x_value in range(WIDTH):
            position = row + x_value
            code = codes[position]
            different_neighbour = False
            if x_value + 1 < WIDTH:
                different = code != codes[position + 1]
                different_neighbour |= different
                if different:
                    if x_value == WIDTH // 2 - 1:
                        seam += 1
                    elif x_value < WIDTH // 2:
                        left += 1
                    else:
                        right += 1
            if x_value and code != codes[position - 1]:
                different_neighbour = True
            if y_value + 1 < HEIGHT:
                different = code != codes[position + WIDTH]
                different_neighbour |= different
                if different:
                    if x_value < WIDTH // 2:
                        left += 1
                    else:
                        right += 1
            if y_value and code != codes[position - WIDTH]:
                different_neighbour = True
            boundary += different_neighbour
    return {
        "total_four_neighbour_edges": left + right + seam,
        "internal_left_edges": left,
        "internal_right_edges": right,
        "boundary_pixels": boundary,
        "controller_seam": seam,
    }


class RootCause2x2V3ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = v3.build_v3_artifacts()
        cls.manifest = cls.artifacts.manifest
        cls.proof = cls.artifacts.proof
        cls.prior, _ = v3.low_spatial.generate_diagnostic_codes()

    def _p0_campaign(
        self,
    ) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
        panel = {
            "model": "MF1750-C73",
            "serial": "PANEL-N4-V3",
            "board_id": "ESP32-C73",
            "pcb_revision": "rev-a",
        }
        firmware = {
            "source_commit": "1" * 40,
            "build_tag": "offline-n4-v3-test",
            "binary_sha256": "2" * 64,
            "driver_api": "mf1750-http-v1",
        }
        with mock.patch.object(
            v3, "build_v3_artifacts", return_value=self.artifacts
        ):
            campaign = v3.compile_p0_campaign(
                panel=panel,
                firmware=firmware,
                minimum_interval_seconds=20,
                planned_cooldown_seconds=60,
            )
        return campaign, panel, firmware

    def test_frozen_manifest_proof_and_all_asset_hashes(self) -> None:
        self.assertEqual(
            v3._sha256(self.artifacts.manifest_bytes),
            v3.EXPECTED_MANIFEST_FILE_SHA256,
        )
        self.assertEqual(
            self.manifest["manifest_integrity"]["canonical_sha256"],
            v3.EXPECTED_MANIFEST_CANONICAL_SHA256,
        )
        self.assertEqual(
            v3._sha256(self.artifacts.proof_bytes), v3.EXPECTED_PROOF_FILE_SHA256
        )
        self.assertEqual(
            self.proof["proof_integrity"]["canonical_sha256"],
            v3.EXPECTED_PROOF_CANONICAL_SHA256,
        )
        self.assertEqual(set(self.artifacts.files()), v3.REQUIRED_FILES)
        for name in v3.VARIANT_NAMES:
            variant = self.artifacts.variants[name]
            record = self.manifest["variants"][name]
            self.assertEqual(v3._sha256(variant.frame), record["frame"]["sha256"])
            self.assertEqual(
                v3._sha256(variant.codes), record["frame"]["codes_sha256"]
            )
            self.assertEqual(
                v3._sha256(variant.strict_png), record["strict_preview"]["sha256"]
            )
            self.assertEqual(len(variant.frame), 307200)

    def test_contact_sheet_is_four_strict_cells_with_frozen_layout(self) -> None:
        png = self.artifacts.contact_png
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (v3.CONTACT_WIDTH, v3.CONTACT_HEIGHT))
        self.assertEqual(
            v3._sha256(png), self.manifest["contact_sheet"]["sha256"]
        )
        self.assertEqual(
            self.manifest["contact_sheet"]["layout_xy"], v3.CONTACT_LAYOUT
        )

    def test_independent_oracle_proves_global_and_half_transition_invariants(self) -> None:
        for name in v3.VARIANT_NAMES:
            with self.subTest(name=name):
                codes = self.artifacts.variants[name].codes
                load = name.split("-", 1)[1]
                expected_halves = (
                    (v2.BALANCED_LEFT_MATRIX, v2.BALANCED_RIGHT_MATRIX)
                    if load == "balanced"
                    else (v2.UNBALANCED_LEFT_MATRIX, v2.UNBALANCED_RIGHT_MATRIX)
                )
                self.assertEqual(
                    _independent_transition(self.prior, codes),
                    v3.GLOBAL_TRANSITION_MATRIX,
                )
                self.assertEqual(
                    _independent_transition(self.prior, codes, x0=0, x1=WIDTH // 2),
                    expected_halves[0],
                )
                self.assertEqual(
                    _independent_transition(
                        self.prior, codes, x0=WIDTH // 2, x1=WIDTH
                    ),
                    expected_halves[1],
                )
                changed = sum(old != new for old, new in zip(self.prior, codes))
                self.assertEqual(changed, v3.EXPECTED_CHANGED_PIXELS)
                self.assertEqual(
                    tuple(codes.count(code) for code in v3.PHYSICAL_CODE_ORDER),
                    v3.GLOBAL_COUNTS,
                )

    def test_B_half_load_effect_and_half_changed_are_exact_across_A(self) -> None:
        expected_changed = {
            "balanced": (242_219, 243_695),
            "unbalanced": (235_820, 250_094),
        }
        for load, expected_l1 in (("balanced", 4), ("unbalanced", 186_896)):
            high = self.manifest["variants"][f"high-{load}"]
            low = self.manifest["variants"][f"low-{load}"]
            self.assertEqual(high["counts"], low["counts"])
            self.assertEqual(
                high["transitions_from_map_prior"],
                low["transitions_from_map_prior"],
            )
            self.assertEqual(high["counts"]["half_imbalance_l1"], expected_l1)
            transition = high["transitions_from_map_prior"]
            self.assertEqual(
                (transition["changed_left"], transition["changed_right"]),
                expected_changed[load],
            )

    def test_preregistered_metric_vector_is_independently_exact_within_A(self) -> None:
        by_level = {}
        for name in v3.VARIANT_NAMES:
            with self.subTest(name=name):
                independent = _independent_metrics(self.artifacts.variants[name].codes)
                recorded = self.manifest["variants"][name][
                    "preregistered_spatial_metrics"
                ]
                self.assertEqual(independent, recorded)
                self.assertEqual(
                    recorded["total_four_neighbour_edges"],
                    recorded["internal_left_edges"]
                    + recorded["internal_right_edges"]
                    + recorded["controller_seam"],
                )
                by_level.setdefault(name.split("-", 1)[0], []).append(recorded)
        self.assertEqual(by_level["high"][0], by_level["high"][1])
        self.assertEqual(by_level["low"][0], by_level["low"][1])
        self.assertGreater(
            by_level["high"][0]["total_four_neighbour_edges"],
            10 * by_level["low"][0]["total_four_neighbour_edges"],
        )

    def test_solver_is_bounded_deterministic_and_replays_to_frozen_outputs(self) -> None:
        for spatial in ("high", "low"):
            with self.subTest(spatial=spatial):
                base_unbalanced = v2.generate_variant_codes(
                    self.prior, spatial=spatial, load="unbalanced"
                )
                base_balanced = v2.generate_variant_codes(
                    self.prior, spatial=spatial, load="balanced"
                )
                unbalanced, balanced, certificate = v3._joint_solve_level(
                    self.prior,
                    spatial=spatial,
                    unbalanced_codes=base_unbalanced,
                    balanced_codes=base_balanced,
                )
                self.assertEqual(
                    unbalanced,
                    self.artifacts.variants[f"{spatial}-unbalanced"].codes,
                )
                self.assertEqual(
                    balanced,
                    self.artifacts.variants[f"{spatial}-balanced"].codes,
                )
                self.assertEqual(certificate, self.proof["solver"]["levels"][spatial])
                self.assertLessEqual(
                    certificate["proposals_used"], v3.SOLVER_MAX_PROPOSALS
                )
                self.assertEqual(certificate["final_objective"], 0)

    def test_solver_budget_exhaustion_fails_closed(self) -> None:
        base_unbalanced = v2.generate_variant_codes(
            self.prior, spatial="low", load="unbalanced"
        )
        base_balanced = v2.generate_variant_codes(
            self.prior, spatial="low", load="balanced"
        )
        with mock.patch.object(v3, "SOLVER_MAX_PROPOSALS", 1):
            with self.assertRaisesRegex(v3.V3FactorialError, "exhausted"):
                v3._joint_solve_level(
                    self.prior,
                    spatial="low",
                    unbalanced_codes=base_unbalanced,
                    balanced_codes=base_balanced,
                )

    def test_claim_is_narrow_and_all_other_metric_residuals_are_disclosed(self) -> None:
        classification = self.manifest["classification"]
        self.assertTrue(classification["strict_selected_metric_orthogonality_proven"])
        self.assertFalse(classification["strict_metric_orthogonality_proven"])
        self.assertFalse(
            classification["all_reported_spatial_metrics_orthogonality_proven"]
        )
        for spatial in ("high", "low"):
            residual = self.proof["non_preregistered_residual_audit"][spatial]
            self.assertFalse(residual["all_non_preregistered_metrics_exact"])
            self.assertFalse(residual["seam_pair_matrix_exact"])
            self.assertGreater(residual["seam_pair_matrix_cellwise_l1"], 0)

    def test_old_v2_is_rejected_by_the_v3_strict_gate(self) -> None:
        old_manifest = json.loads((V2_DIRECTORY / "manifest.json").read_text("utf-8"))
        with self.assertRaisesRegex(v3.V3FactorialError, "including V2"):
            v3.validate_strict_manifests(old_manifest, self.proof)
        with self.assertRaisesRegex(v3.V3FactorialError, "file set"):
            v3.validate_v3_directory(V2_DIRECTORY)
        self.assertEqual(
            v3._sha256((V2_DIRECTORY / "manifest.json").read_bytes()),
            v2.EXPECTED_MANIFEST_FILE_SHA256,
        )

    def test_tamper_and_resigned_tolerance_or_authorization_are_rejected(self) -> None:
        proof = deepcopy(self.proof)
        proof.pop("proof_integrity")
        proof["preregistration"]["required_absolute_tolerance_by_metric"][
            "boundary_pixels"
        ] = 1
        proof = v3._seal(proof, field="proof_integrity", scope=v3.PROOF_HASH_SCOPE)
        with self.assertRaisesRegex(v3.V3FactorialError, "use tolerance"):
            v3.validate_strict_manifests(self.manifest, proof)

        manifest = deepcopy(self.manifest)
        manifest.pop("manifest_integrity")
        manifest["classification"]["upload_authorized"] = True
        manifest = v3._seal(
            manifest, field="manifest_integrity", scope=v3.MANIFEST_HASH_SCOPE
        )
        with self.assertRaisesRegex(v3.V3FactorialError, "offline-only"):
            v3.validate_strict_manifests(manifest, self.proof)

    def test_classification_transport_and_proof_are_zero_io(self) -> None:
        self.assertEqual(
            self.manifest["transport"],
            {
                "mode": "offline",
                "endpoint": None,
                "method": None,
                "device_io_performed": False,
                "network_io_performed": False,
                "refresh_runner_implemented": False,
                "claim_created": False,
                "authorization_created": False,
                "upload_authorized": False,
            },
        )
        decision = self.proof["decision"]
        self.assertFalse(decision["claim_created"])
        self.assertFalse(decision["authorization_created"])
        self.assertFalse(decision["network_io_performed"])
        self.assertFalse(decision["device_io_performed"])
        self.assertFalse(decision["upload_authorized"])

    def test_p0_compiles_four_independent_map_to_cell_sessions(self) -> None:
        campaign, panel, firmware = self._p0_campaign()
        with mock.patch.object(v3, "build_v3_artifacts", return_value=self.artifacts):
            replay = v3.compile_p0_campaign(
                panel=panel,
                firmware=firmware,
                minimum_interval_seconds=20,
                planned_cooldown_seconds=60,
            )
        self.assertEqual(campaign, replay)
        self.assertEqual(len(campaign["sessions"]), 4)
        self.assertEqual(len(campaign["actions"]), 8)
        self.assertEqual(
            [session["cell_id"] for session in campaign["sessions"]],
            list(v3.CAMPAIGN_CELL_ORDER),
        )
        actions = campaign["actions"]
        for index, cell_name in enumerate(v3.CAMPAIGN_CELL_ORDER):
            primer, target = actions[2 * index : 2 * index + 2]
            self.assertEqual(primer["identity"]["cell_id"], cell_name)
            self.assertIsNone(primer["identity"]["prior"])
            self.assertEqual(
                target["identity"]["prior"]["action_identity_sha256"],
                primer["action_identity_sha256"],
            )
            self.assertEqual(
                target["identity"]["frame"]["sha256"],
                self.manifest["variants"][cell_name]["frame"]["sha256"],
            )
            self.assertFalse(target["identity"]["automatic_retry"])
            self.assertFalse(target["identity"]["automatic_recovery"])
            self.assertTrue(target["claim"]["create_before_network"])

    def test_p0_describe_only_keeps_targets_blocked_until_each_map_pass(self) -> None:
        campaign, panel, firmware = self._p0_campaign()
        allowlist = []
        for action in campaign["actions"]:
            identity = action["identity"]
            allowlist.append(
                {
                    "action_id": identity["action_id"],
                    "action_identity_sha256": action["action_identity_sha256"],
                    "method": "POST",
                    "endpoint": identity["request"]["endpoint"],
                    "frame_sha256": identity["frame"]["sha256"],
                    "maximum_uses": 1,
                }
            )
        profile = seal_limit_profile(
            {
                "schema_version": 1,
                "kind": "mf1750-visible-refresh-limit-profile",
                "profile_id": "n4-v3-test-profile",
                "profile_version": "1.0.0",
                "panel": panel,
                "firmware": firmware,
                "action_allowlist": allowlist,
                "limits": {
                    "maximum_campaign_visible_refreshes": 8,
                    "maximum_session_visible_refreshes": 2,
                    "maximum_consecutive_visible_refreshes": 2,
                    "minimum_interval_seconds": 20,
                    "minimum_cooldown_seconds": 60,
                    "minimum_start_temperature_c": 10,
                    "maximum_start_temperature_c": 40,
                    "maximum_post_refresh_temperature_c": 45,
                },
                "usage": {
                    "cumulative_visible_refresh_count": 0,
                    "session_visible_refresh_count": 0,
                    "consecutive_visible_refresh_count": 0,
                    "last_visible_refresh_completed_at": None,
                    "snapshot_at": "2026-08-07T23:55:00Z",
                    "evidence_sha256": "3" * 64,
                },
                "validity": {
                    "valid_from": "2026-08-07T00:00:00Z",
                    "expires_at": "2026-09-01T00:00:00Z",
                },
                "review": {
                    "approved": True,
                    "reviewer_id": "offline-test",
                    "reviewed_at": "2026-08-06T00:00:00Z",
                    "review_artifact_sha256": "4" * 64,
                },
            }
        )
        description = v3.describe_p0_campaign_offline(
            campaign,
            limit_profile=profile,
            evaluated_at="2026-08-08T00:00:00Z",
        )
        self.assertFalse(description["hardware_ready"])
        self.assertFalse(description["claim_created"])
        self.assertFalse(description["authorization_created"])
        self.assertFalse(description["network_io_performed"])
        self.assertEqual(len(description["actions"]), 8)
        for index, action in enumerate(description["actions"]):
            if index % 2 == 0:
                self.assertTrue(action["contract_ready"])
            else:
                self.assertFalse(action["contract_ready"])
                self.assertIn("required_prior_result_missing", action["blockers"])


class RootCause2x2V3SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = RootCause2x2V3ContractTests.artifacts

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        for filename, payload in self.artifacts.files().items():
            (self.bundle / filename).write_bytes(payload)

    def _validate_cached(self) -> Mapping[str, object]:
        with mock.patch.object(v3, "build_v3_artifacts", return_value=self.artifacts):
            return v3.validate_v3_directory(self.bundle)

    def test_exact_file_set_and_deep_byte_validation(self) -> None:
        self.assertEqual(self._validate_cached(), self.artifacts.manifest)
        self.assertEqual({path.name for path in self.bundle.iterdir()}, v3.REQUIRED_FILES)

    def test_frame_tamper_and_extra_file_fail_closed(self) -> None:
        target = self.bundle / "high-balanced.frame.bin"
        payload = bytearray(target.read_bytes())
        payload[0] ^= 0x11
        target.write_bytes(payload)
        with self.assertRaisesRegex(v3.V3FactorialError, "differs from regeneration"):
            self._validate_cached()
        target.write_bytes(self.artifacts.files()["high-balanced.frame.bin"])
        (self.bundle / "extra.txt").write_text("no", encoding="utf-8")
        with self.assertRaisesRegex(v3.V3FactorialError, "file set"):
            self._validate_cached()

    def test_existing_output_is_never_overwritten(self) -> None:
        with self.assertRaisesRegex(v3.V3FactorialError, "already exists"):
            v3.write_v3_directory(self.bundle)

    def test_cli_has_no_device_network_or_variant_surface(self) -> None:
        for forbidden in ("--url", "--refresh", "--runner", "--force", "--variant"):
            with self.subTest(forbidden=forbidden):
                with mock.patch("sys.stderr", new=io.StringIO()):
                    with self.assertRaises(SystemExit):
                        v3.parse_args([forbidden, "x"])
        self.assertEqual(
            v3.parse_args(["--validate-dir", os.fspath(self.bundle)]).validate_dir,
            self.bundle,
        )

    def test_import_reload_performs_no_network_or_device_open(self) -> None:
        with (
            mock.patch.object(socket, "socket", side_effect=AssertionError("socket used")),
            mock.patch.object(
                urllib.request, "urlopen", side_effect=AssertionError("urlopen used")
            ),
            mock.patch.object(
                urllib.request,
                "build_opener",
                side_effect=AssertionError("opener used"),
            ),
        ):
            reloaded = importlib.reload(v3)
        self.assertEqual(reloaded.MANIFEST_KIND, v3.MANIFEST_KIND)


if __name__ == "__main__":
    unittest.main()
