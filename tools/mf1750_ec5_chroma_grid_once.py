#!/usr/bin/env python3
"""One-action runner for the fixed five-step chroma-history grid campaign.

The runner never flashes firmware, controls J2, or chains visible actions.
Each invocation permanently claims exactly one ordinal before ARM/EXECUTE.
"""

from __future__ import annotations

from typing import Sequence

import mf1750_ec5_otp_transition_matrix_recheck_once as runner


runner.__doc__ = (
    "Fail-closed one-action runner for the isolated chroma-history grid. "
    "It never flashes, controls J2, or chains visible actions. Each of the "
    "five full-screen steps remains a separate operator decision."
)
runner.BUILD_TAG = "MF1750_EC5_CHROMA_GRID_V1_2026-08-21"
runner.TEST_ID = "EC5-CHROMA-GRID-V1"
runner.CAMPAIGN_ID = "EC5_CHROMA_GRID_V1"
runner.DEVICE_API_VERSION = "MF1750_EC5_CHROMA_GRID_DEVICE_V1"
runner.IDENTITY_REVISION = "chroma-grid-v1"
runner.CONTRACT_ID = (
    "ff24c93b431f4ea95eea0738c37564133c4f2e436e4d8060f7f47dad8fe55405"
)
runner.CLASSIFICATION = "FACTORY_OTP_FIXED_CHROMA_HISTORY_NO_RUNTIME_LUT"
runner.DEVICE_KIND_PREFIX = "mf1750-ec5-chroma-grid"
runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-chroma-grid"
runner.NVS_NAMESPACE = "mf1750_cg1"
runner.NVS_KEY = "cursor_v1"
runner.FIRMWARE_SHA256 = (
    "1169008766383c5296dacdb855cfb60cb260662ff11cc56b2fcbf4cc2f14818f"
)
runner.FIRMWARE_BYTES = 788656
runner.ENDPOINTS = {
    name: f"/api/ec5/chroma-grid/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
runner.ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_CHROMA_GRID_ACTION"
runner.EXECUTE_INTENT = (
    "EXECUTE_ARMED_FACTORY_OTP_CHROMA_GRID_ACTION_ONCE"
)

runner.DESCRIPTOR_IDS = (
    "032ca22f88ab82e8c6088750194b2539779f0ced441ae0ef4fdcb16a7cc91623",
    "9b0f1a15589355ce0709aa865a710b79510cde656239284f0123bb67048c8297",
    "3686f3f2f74dc89d6baf0c7d485a2f5467809067c8331ea362ae6f932a1ad2b8",
    "b995ab62097f9cbc99ddce3f9be5180060e8fbb2e8348d957816fcb3f7ea9f52",
    "abbbe570497b77842e51d66127934153589c54cdc49ac8fdcad788de0205cfb3",
)
runner.ACTION_IDS = (
    "fca6ae290e3257bfe04b7190e533e0fd94822ff69ee4e252a0b45b0ea9c9dc98",
    "97d8543a7635098cdfc797df105ad45a5292095f6632d9086181cae0114dd07a",
    "5bcc1508faacdce42759c2e20d5afaecff1691227510ce3918c26f4c7ec9ad3d",
    "9d91e22e703b4b5cd48e99f3e9fb69cd750fd55dc7f8b3d0c5c35c005206fc1f",
    "3acb67dbf1d9fa6365b602cdaadb3c29738ade62f0008bc1656dc02bccf49c8b",
)

_WHITE_FRAME = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
_WHITE_DTM = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"

runner.ACTIONS = (
    {
        "ordinal": 1,
        "descriptor_id": runner.DESCRIPTOR_IDS[0],
        "action_id": runner.ACTION_IDS[0],
        "prior_static_action_id": None,
        "role": "CHROMA_WHITE_BASELINE",
        "round": 1,
        "branch": "FACTORY_OTP_WHITE_BASELINE",
        "frame_sha256": _WHITE_FRAME,
        "cs1_dtm_sha256": _WHITE_DTM,
        "cs2_dtm_sha256": _WHITE_DTM,
        "transport_code_histogram": [0, 614400, 0, 0, 0, 0, 0, 0],
    },
    {
        "ordinal": 2,
        "descriptor_id": runner.DESCRIPTOR_IDS[1],
        "action_id": runner.ACTION_IDS[1],
        "prior_static_action_id": runner.ACTION_IDS[0],
        "role": "CHROMA_SOURCE_GRID",
        "round": 1,
        "branch": "SOURCE_0_TO_7_WHITE_GAPS",
        "frame_sha256": (
            "213d3eab11966579f8cab7577dff315897f96a72e9030a236f60ca899295b8de"
        ),
        "cs1_dtm_sha256": (
            "0eba448b460d31d3d28a6d9e6d62fa0193f6eaabe769d9fc846658c4b0ac64e2"
        ),
        "cs2_dtm_sha256": (
            "8ae4ae3058ab1ffab4152f4c2e714e88fce7a0c4ace3bf472c59b7a520119079"
        ),
        "transport_code_histogram": [
            53248,
            241664,
            53248,
            53248,
            53248,
            53248,
            53248,
            53248,
        ],
    },
    {
        "ordinal": 3,
        "descriptor_id": runner.DESCRIPTOR_IDS[2],
        "action_id": runner.ACTION_IDS[2],
        "prior_static_action_id": runner.ACTION_IDS[1],
        "role": "CHROMA_MID_GRID",
        "round": 1,
        "branch": "MID_CODES_4_AND_7",
        "frame_sha256": (
            "8047a36612272c3e5e03717b00184e151d16fe67caf972c70ff0caea88d63054"
        ),
        "cs1_dtm_sha256": (
            "c2143d36c7a2be633c6e0fa63bf2e63cc08533a428cf219e3246891e2d18b987"
        ),
        "cs2_dtm_sha256": (
            "b17caf38ae1aefcd01b63675cf0f4027850bc65c8f3f590339aa29a55c53b8cd"
        ),
        "transport_code_histogram": [0, 188416, 0, 0, 212992, 0, 0, 212992],
    },
    {
        "ordinal": 4,
        "descriptor_id": runner.DESCRIPTOR_IDS[3],
        "action_id": runner.ACTION_IDS[3],
        "prior_static_action_id": runner.ACTION_IDS[2],
        "role": "CHROMA_TARGET_GRID",
        "round": 1,
        "branch": "TARGET_CODES_2_3_5_6_AFTER_SOURCE_MID",
        "frame_sha256": (
            "c2e5289bfa44ffba8daf374edd70e34216ea13e08a3e58764feed9f13efa2036"
        ),
        "cs1_dtm_sha256": (
            "26535f9244d6af9c0899ec851cb84b469f01d949baf9602988d98c2377e1a72f"
        ),
        "cs2_dtm_sha256": (
            "3430064d6abd1273837db198e2901f20512726794b64e6f32886c5e9fbb5b57c"
        ),
        "transport_code_histogram": [
            0,
            188416,
            106496,
            106496,
            0,
            106496,
            106496,
            0,
        ],
    },
    {
        "ordinal": 5,
        "descriptor_id": runner.DESCRIPTOR_IDS[4],
        "action_id": runner.ACTION_IDS[4],
        "prior_static_action_id": runner.ACTION_IDS[3],
        "role": "CHROMA_WHITE_RECOVERY",
        "round": 1,
        "branch": "FACTORY_OTP_WHITE_RECOVERY",
        "frame_sha256": _WHITE_FRAME,
        "cs1_dtm_sha256": _WHITE_DTM,
        "cs2_dtm_sha256": _WHITE_DTM,
        "transport_code_histogram": [0, 614400, 0, 0, 0, 0, 0, 0],
    },
)

runner.DEFAULT_CLAIMS = (
    runner.REPO_ROOT / ".test-output" / "hardware" / ".mf1750_ec5_chroma_grid_claims"
)
runner.DEFAULT_OUTPUT = (
    runner.REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_CHROMA_GRID_20260821_V1"
)


def main(argv: Sequence[str] | None = None) -> int:
    return runner.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
