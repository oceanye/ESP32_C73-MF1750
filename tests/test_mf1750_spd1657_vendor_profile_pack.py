from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "mf1750_spd1657_vendor_profile_pack.py"
SPEC = importlib.util.spec_from_file_location("spd1657_vendor_profile_pack", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load SPD1657 vendor-profile packer")
profile_pack = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = profile_pack
SPEC.loader.exec_module(profile_pack)


EXPECTED = {
    "WF20_25": {
        "source": "0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821",
        "wrapper": "97efcac1cbc6604a52b942a00b13df349530e152fd28063ed9eda94a36e2dcc5",
        "plaintext": "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f",
        "header": "2fc6ab4de405835d9a5ff93a19adb03e277d0dece9df87a88c467a07bcb801af",
        "r20": "3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26",
        "include": "8009f2c5523bd4c592474cc15e6b0b4a8b0a74053a09e69d4926d9f5abffb626",
    },
    "WF23_25": {
        "source": "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d",
        "wrapper": "d01caa5581b69ab82d7bb34175d21220e4c08582eb55ce5f9f6391700cd6ebb4",
        "plaintext": "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8",
        "header": "082e520524ebe6c5667d778a1c51407a37d459cc34f8db76b54ba26e93732185",
        "r20": "2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb",
        "include": "ee289bc89e9f76f936ca5f2dd0c503f8cc8c8d786c01fc26615c33b9251cb9ff",
    },
}
R21_SHA256 = "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
GENERATED = {
    "WF20_25": REPO_ROOT / "src" / "generated" / "spd1657_wf20_25_empirical_h3.inc",
    "WF23_25": REPO_ROOT / "src" / "generated" / "spd1657_wf23_25_empirical_h3.inc",
}


def _cpp_array(rendered: bytes, name: str) -> bytes:
    text = rendered.decode("ascii")
    match = re.search(
        rf"\b{re.escape(name)}\s*\[\d+\]\s*=\s*\{{(.*?)\}};",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing C++ array: {name}")
    return bytes(
        int(value, 16)
        for value in re.findall(r"\b0x([0-9A-Fa-f]{2})\b", match.group(1))
    )


class Spd1657VendorProfilePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.materials = {
            profile_id: profile_pack.load_profile(profile_id)
            for profile_id in sorted(EXPECTED)
        }

    def test_both_vendor_profiles_have_exact_frozen_identities(self) -> None:
        self.assertEqual(set(self.materials), {"WF20_25", "WF23_25"})
        for profile_id, material in self.materials.items():
            expected = EXPECTED[profile_id]
            self.assertEqual(material.spec.source_sha256, expected["source"])
            self.assertEqual(material.wrapper_sha256, expected["wrapper"])
            self.assertEqual(
                profile_pack._sha256(material.plaintext), expected["plaintext"]
            )
            self.assertEqual(profile_pack._sha256(material.header), expected["header"])
            self.assertEqual(profile_pack._sha256(material.r20), expected["r20"])
            self.assertEqual(len(material.plaintext), 800)
            self.assertEqual(len(material.header), 7)
            self.assertEqual(material.plaintext[799], 0)

    def test_h3_include_contains_exact_bounded_segments_and_metadata(self) -> None:
        for profile_id, material in self.materials.items():
            rendered = profile_pack.render_include(material)
            self.assertEqual(_cpp_array(rendered, "kDecodedHeader"), material.header)
            self.assertEqual(
                _cpp_array(rendered, "kPowerPayload"), material.power_payload
            )
            self.assertEqual(_cpp_array(rendered, "kPllPayload"), material.pll_payload)
            self.assertEqual(_cpp_array(rendered, "kR20Payload"), material.r20)
            r21 = _cpp_array(rendered, "kR21Payload")
            self.assertEqual(r21, b"\xff" * 704)
            self.assertEqual(profile_pack._sha256(r21), R21_SHA256)
            self.assertEqual(
                profile_pack._sha256(rendered), EXPECTED[profile_id]["include"]
            )
            text = rendered.decode("ascii")
            self.assertIn("kEmpiricalH3 = true", text)
            self.assertIn("kLiveAuthorized = false", text)
            self.assertIn("kProfileAutoSelected = false", text)
            self.assertIn("kContainsHardwareIo = false", text)
            self.assertIn("static_assert(sizeof(kR20Payload)", text)
            self.assertIn("static_assert(sizeof(kR21Payload)", text)

    def test_profile_selection_is_required_and_has_no_default(self) -> None:
        with self.assertRaises(profile_pack.ProfilePackError):
            profile_pack.load_profile("")
        profile_action = next(
            action
            for action in profile_pack.build_parser()._actions
            if action.dest == "profile"
        )
        self.assertTrue(profile_action.required)
        self.assertIsNone(profile_action.default)
        self.assertEqual(set(profile_action.choices), {"WF20_25", "WF23_25"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist.inc"
            completed = subprocess.run(
                [sys.executable, str(TOOL_PATH), "--output", str(output)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(output.exists())

    def test_wrapped_key_bounds_are_checked_before_indexing(self) -> None:
        with self.assertRaises(profile_pack.ProfilePackError):
            profile_pack._recover_wrapped_key(b"\x00" * 801, 40)
        oversized = bytearray(b"\x00" * 842)
        oversized[800:802] = (0xFFFF).to_bytes(2, "big")
        with self.assertRaises(profile_pack.ProfilePackError):
            profile_pack._recover_wrapped_key(bytes(oversized), 40)
        with self.assertRaises(profile_pack.ProfilePackError):
            profile_pack._recover_wrapped_key(b"\x00" * 1702, 900)

    def test_repeated_generation_is_byte_identical(self) -> None:
        for profile_id, material in self.materials.items():
            first = profile_pack.render_include(material)
            second = profile_pack.render_include(profile_pack.load_profile(profile_id))
            self.assertEqual(first, second)

    def test_checked_in_includes_are_exact_regenerations(self) -> None:
        for profile_id, material in self.materials.items():
            generated = GENERATED[profile_id].read_bytes()
            self.assertEqual(generated, profile_pack.render_include(material))
            self.assertEqual(
                profile_pack._sha256(generated), EXPECTED[profile_id]["include"]
            )

    def test_cli_json_emits_only_target_identity_and_no_sensitive_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixed.inc"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL_PATH),
                    "--profile",
                    "WF23_25",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(
                set(report),
                {
                    "empirical_h3",
                    "kind",
                    "live_authorized",
                    "profile_id",
                    "schema_version",
                    "target_file",
                },
            )
            self.assertEqual(set(report["target_file"]), {"bytes", "path", "sha256"})
            self.assertEqual(report["profile_id"], "WF23_25")
            self.assertTrue(report["empirical_h3"])
            self.assertFalse(report["live_authorized"])
            self.assertEqual(
                output.read_bytes(),
                profile_pack.render_include(self.materials["WF23_25"]),
            )
            lowered = completed.stdout.lower()
            self.assertNotIn("plaintext", lowered)
            self.assertNotIn("payload", lowered)
            self.assertNotIn("recovered_key", lowered)
            self.assertNotIn("customer_key", lowered)

    def test_wrong_source_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "changed"
            changed.write_bytes(b"not vendor evidence")
            with self.assertRaises(profile_pack.ProfilePackError):
                profile_pack._read_exact(
                    changed,
                    EXPECTED["WF20_25"]["source"],
                    "changed fixture",
                )


if __name__ == "__main__":
    unittest.main()
