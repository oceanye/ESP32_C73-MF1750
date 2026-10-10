#!/usr/bin/env python3
"""One-action runner for the fixed six-step blue-history campaign.

The runner never flashes firmware and never chains visible actions.  Each
invocation permanently claims exactly one ordinal before ARM/EXECUTE.
"""

from __future__ import annotations

from typing import Sequence

import mf1750_ec5_otp_transition_matrix_recheck_once as runner


runner.BUILD_TAG = "MF1750_EC5_BLUE_HISTORY_FOCUSED_V1_2026-08-20"
runner.TEST_ID = "EC5-BLUE-HISTORY-FOCUSED-V1"
runner.CAMPAIGN_ID = "EC5_BLUE_HISTORY_FOCUSED_CAMPAIGN_V1"
runner.DEVICE_API_VERSION = "MF1750_EC5_BLUE_HISTORY_FOCUSED_DEVICE_V1"
runner.IDENTITY_REVISION = "blue-history-focused-v1"
runner.CONTRACT_ID = (
    "3d3de39d4630fc5e6203f6403f35256a32c4b8cf005f1d5c879ef59b630a678d"
)
runner.CLASSIFICATION = "FACTORY_OTP_FIXED_BLUE_HISTORY_16_RECIPE_NO_RUNTIME_LUT"
runner.DEVICE_KIND_PREFIX = "mf1750-ec5-blue-history-focused"
runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-blue-history-focused"
runner.NVS_NAMESPACE = "mf1750_bhf1"
runner.NVS_KEY = "cursor_v1"
runner.FIRMWARE_SHA256 = (
    "881cec3fc1ace54980987ad27f3a0dd7170e07fd54f08bc92a9d08634a2337b9"
)
runner.FIRMWARE_BYTES = 789408
runner.ENDPOINTS = {
    name: f"/api/ec5/blue-history-focused/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
runner.ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_BLUE_HISTORY_FOCUSED_ACTION"
runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_FACTORY_OTP_BLUE_HISTORY_FOCUSED_ACTION_ONCE"
)

runner.DESCRIPTOR_IDS = (
    "7f3115729885e1c04957f0b45d382fa0299cf2bf7bcf5cb253a43d226b94ad83",
    "055d40162a5c511d042df3ef9a156f041874e556d900854150d6286586b29d95",
    "d6e0c9e849a8cc3b8d5303a2c121fbe614facec57bf4e8a1ba56c583d5194ae6",
    "bd45164d312a1bd713a9fb50b040c6d118def395156bb3052bdcc620b7ed0d36",
    "5a55764ef440644a52848149c70742f7d7a14db6aadcadd1f6d9ecfa3e2b0bd0",
    "34f27cf6f8c0b1d8a86030fbe85d29aaefc1691e9d4db006753b9087cae117d9",
)
runner.ACTION_IDS = (
    "bd2cc213997298f425e31747b25e3b42fc6b598154998b659d5b5b090865d1d4",
    "b91ffe5a8157e2351017bb2cdf58076bebf3fbb4ccd46df8129d8a54deee7931",
    "3e06f8c30050f905a61c65e0a8549562e06108f44a4cc245d70cff469a36b68c",
    "c98a2d296e505338f715f0d08f3f0320d7bcd33c0d9ad5cc29d990074ab57ff3",
    "da351c575d0c5ba340141b993da4d833f6b97e2e50cb911c87e4069fdffb33ae",
    "d416eef5239b6349ead14d1afac0d62871309d947e77cdadadc8be229990d4a0",
)

_WHITE_FRAME = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
_WHITE_DTM = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
_PRIMER_HIST = [56320, 220160, 56320, 56320, 56320, 56320, 56320, 56320]
_TARGET_HIST = [0, 163840, 0, 0, 225280, 0, 0, 225280]
_WHITE_HIST = [0, 614400, 0, 0, 0, 0, 0, 0]

runner.ACTIONS = (
    {
        "ordinal": 1,
        "descriptor_id": runner.DESCRIPTOR_IDS[0],
        "action_id": runner.ACTION_IDS[0],
        "prior_static_action_id": None,
        "role": "A_PRIMER_SOURCE_CODES_0_TO_7",
        "round": 1,
        "branch": "A_PRIMER_CS1_TARGET4_CS2_TARGET7",
        "frame_sha256": "6fef23f683694f434b3cb06209a5e77d458248b46c7a9c49932c503b725f9527",
        "cs1_dtm_sha256": "f99960532731f22224ad88302f9518cc6d15c159a40e3116f52ab7f23e658980",
        "cs2_dtm_sha256": "f99960532731f22224ad88302f9518cc6d15c159a40e3116f52ab7f23e658980",
        "transport_code_histogram": _PRIMER_HIST,
    },
    {
        "ordinal": 2,
        "descriptor_id": runner.DESCRIPTOR_IDS[1],
        "action_id": runner.ACTION_IDS[1],
        "prior_static_action_id": runner.ACTION_IDS[0],
        "role": "A_TARGET_BLUE_CODES_4_AND_7",
        "round": 1,
        "branch": "A_TARGET_CS1_CODE4_CS2_CODE7",
        "frame_sha256": "b5350449a22c5a77315c5e2148aa3a84a9b84411445579f349c8f888f1fe6a5a",
        "cs1_dtm_sha256": "faecfc32d3f9a1f3d5ea82a5f81754bb281e0245dc2d4da8de9011aba4395e94",
        "cs2_dtm_sha256": "962d9e8d678e7626837a08f69c25998206056201744c138d39fbd4c7bf8efa29",
        "transport_code_histogram": _TARGET_HIST,
    },
    {
        "ordinal": 3,
        "descriptor_id": runner.DESCRIPTOR_IDS[2],
        "action_id": runner.ACTION_IDS[2],
        "prior_static_action_id": runner.ACTION_IDS[1],
        "role": "A_WHITE_RECOVERY",
        "round": 1,
        "branch": "A_FACTORY_OTP_WHITE_RECOVERY",
        "frame_sha256": _WHITE_FRAME,
        "cs1_dtm_sha256": _WHITE_DTM,
        "cs2_dtm_sha256": _WHITE_DTM,
        "transport_code_histogram": _WHITE_HIST,
    },
    {
        "ordinal": 4,
        "descriptor_id": runner.DESCRIPTOR_IDS[3],
        "action_id": runner.ACTION_IDS[3],
        "prior_static_action_id": runner.ACTION_IDS[2],
        "role": "A_PRIME_PRIMER_SOURCE_CODES_7_TO_0",
        "round": 2,
        "branch": "A_PRIME_PRIMER_CS1_TARGET7_CS2_TARGET4",
        "frame_sha256": "2d43f6da6ebdf58afaceff41c2359d7c82f336884df5f8fcf3d52574f8d8c186",
        "cs1_dtm_sha256": "2c25744b8e0df4cf6f0cc7b2a9bbfa3052c96eda4900ae48a1ba67bf75b2162f",
        "cs2_dtm_sha256": "2c25744b8e0df4cf6f0cc7b2a9bbfa3052c96eda4900ae48a1ba67bf75b2162f",
        "transport_code_histogram": _PRIMER_HIST,
    },
    {
        "ordinal": 5,
        "descriptor_id": runner.DESCRIPTOR_IDS[4],
        "action_id": runner.ACTION_IDS[4],
        "prior_static_action_id": runner.ACTION_IDS[3],
        "role": "A_PRIME_TARGET_BLUE_CODES_7_AND_4",
        "round": 2,
        "branch": "A_PRIME_TARGET_CS1_CODE7_CS2_CODE4",
        "frame_sha256": "1c547c7e4f18c7712450866dfe50e2afff069cd12901d39a343af83281e3f72c",
        "cs1_dtm_sha256": "962d9e8d678e7626837a08f69c25998206056201744c138d39fbd4c7bf8efa29",
        "cs2_dtm_sha256": "faecfc32d3f9a1f3d5ea82a5f81754bb281e0245dc2d4da8de9011aba4395e94",
        "transport_code_histogram": _TARGET_HIST,
    },
    {
        "ordinal": 6,
        "descriptor_id": runner.DESCRIPTOR_IDS[5],
        "action_id": runner.ACTION_IDS[5],
        "prior_static_action_id": runner.ACTION_IDS[4],
        "role": "A_PRIME_WHITE_RECOVERY",
        "round": 2,
        "branch": "A_PRIME_FACTORY_OTP_WHITE_RECOVERY",
        "frame_sha256": _WHITE_FRAME,
        "cs1_dtm_sha256": _WHITE_DTM,
        "cs2_dtm_sha256": _WHITE_DTM,
        "transport_code_histogram": _WHITE_HIST,
    },
)

runner.DEFAULT_CLAIMS = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_blue_history_focused_claims"
)
runner.DEFAULT_OUTPUT = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_BLUE_HISTORY_FOCUSED_20260820_V1"
)


def main(argv: Sequence[str] | None = None) -> int:
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
