from __future__ import annotations

from pathlib import Path
import re
import unittest

from host.runtime_waveform import l535_table_builder as builder
from tools import mf1750_wf_wmask_build as tool


class WfWmaskGrayExtTests(unittest.TestCase):
    def test_low_4bit_generated_outputs_remain_byte_identical(self) -> None:
        for mask in tool.PENDING_MASKS:
            with self.subTest(mask=tool.mask_label(mask)):
                report, rendered = tool.build_offline_variant(mask)
                self.assertNotIn("family_label", report)
                self.assertFalse(any(
                    "kAddWhiteRecords0To3" in content for content in rendered.values()
                ))
                for kind, path in tool.source_paths(mask).items():
                    self.assertEqual(path.read_bytes(), rendered[kind].encode("utf-8"), kind)
                self.assertEqual(report["tag"], f"MF1750_WF_WMASK_{tool.mask_label(mask)}_20261018")

    def test_grayext_group_add_outputs_remain_byte_identical(self) -> None:
        for mask in tool.GRAYEXT_BASE_MASKS:
            with self.subTest(mask=tool.family_label(mask, True)):
                report, rendered = tool.build_offline_variant(mask, True)
                self.assertTrue(report["records0_3_group_add"])
                for kind, path in tool.source_paths(mask, True).items():
                    self.assertEqual(path.read_bytes(), rendered[kind].encode("utf-8"), kind)
                self.assertEqual(
                    report["tag"],
                    f"MF1750_WF_WMASK_{tool.family_label(mask, True)}_20261019",
                )

    def test_single_record_add_outputs_remain_byte_identical(self) -> None:
        for record_add in tool.SINGLE_RECORD_ADD_RECORDS:
            family = tool.family_label(0x0E, False, record_add)
            with self.subTest(family=family):
                report, rendered = tool.build_offline_variant(0x0E, False, record_add)
                self.assertEqual(report["single_record_add"], record_add)
                for kind, path in tool.source_paths(0x0E, False, record_add).items():
                    self.assertEqual(path.read_bytes(), rendered[kind].encode("utf-8"), kind)
                self.assertEqual(report["tag"], f"MF1750_WF_WMASK_{family}_20261019")

    def test_grayext_exact_records_spans_and_fixed_identities(self) -> None:
        active = builder.from_reference("active").to_bytes()
        commented = builder.from_reference("commented").to_bytes()
        for base in tool.GRAYEXT_BASE_MASKS:
            family = tool.family_label(base, True)
            with self.subTest(family=family):
                report, rendered = tool.build_offline_variant(base, True)
                expected_records = sorted(tool.GRAYEXT_VARIANTS[base]["records"])
                expected = bytearray(active)
                for record in expected_records:
                    start = 183 + 11 * record
                    expected[start:start + 11] = commented[start:start + 11]

                match = re.search(
                    r"kR20Payload\[535\]\s*=\s*\{(.*?)\};",
                    rendered["include"],
                    flags=re.S,
                )
                self.assertIsNotNone(match)
                payload = bytes(
                    int(value.strip(), 16)
                    for value in match.group(1).split(",")
                    if value.strip()
                )
                self.assertEqual(payload, bytes(expected))
                self.assertEqual(report["commented_records"], expected_records)
                self.assertEqual(
                    report["active_white_records"],
                    [record for record in range(8) if record not in expected_records],
                )
                self.assertEqual(
                    report["selected_spans"],
                    [[183 + 11 * record, 194 + 11 * record] for record in expected_records],
                )
                self.assertEqual(
                    report["diff_byte_count_vs_active"],
                    tool.GRAYEXT_VARIANTS[base]["diff_bytes"],
                )
                self.assertEqual(
                    report["r20_sha256"],
                    tool.GRAYEXT_VARIANTS[base]["r20_sha256"],
                )
                self.assertEqual(report["expected_r20_sha256"], report["r20_sha256"])
                self.assertEqual(report["family_label"], family)
                self.assertEqual(report["base_mask_hex"], f"0x{tool.mask_label(base)}")
                self.assertTrue(report["records0_3_group_add"])
                self.assertTrue(report["family_label_is_not_bitmask"])
                self.assertEqual(report["tag"], f"MF1750_WF_WMASK_{family}_20261019")
                self.assertEqual(
                    report["env"],
                    f"esp32-s3-devkitc-1-wf-wmask-{family.lower()}",
                )
                self.assertEqual(report["pwr_sha256"], tool.PWR_SHA256)
                self.assertEqual(report["pll_sha256"], tool.PLL_SHA256)
                self.assertEqual(report["r21_sha256"], tool.R21_SHA256)
                self.assertIn("kAddWhiteRecords0To3 = true", rendered["include"])
                self.assertIn("index >= 183 && index < 227", rendered["driver"])
                self.assertIn("not an 8-bit bitmask", rendered["driver"])
                self.assertIn(f'FW_BUILD_TAG = "{report["tag"]}"', rendered["main"])

    def test_single_record_add_exact_records_spans_and_fixed_identities(self) -> None:
        active = builder.from_reference("active").to_bytes()
        commented = builder.from_reference("commented").to_bytes()
        for record_add in tool.SINGLE_RECORD_ADD_RECORDS:
            family = tool.family_label(0x0E, False, record_add)
            with self.subTest(family=family):
                report, rendered = tool.build_offline_variant(0x0E, False, record_add)
                expected_records = sorted(tool.SINGLE_RECORD_ADD_VARIANTS[record_add]["records"])
                expected = bytearray(active)
                for record in expected_records:
                    start = 183 + 11 * record
                    expected[start:start + 11] = commented[start:start + 11]

                match = re.search(
                    r"kR20Payload\[535\]\s*=\s*\{(.*?)\};",
                    rendered["include"],
                    flags=re.S,
                )
                self.assertIsNotNone(match)
                payload = bytes(
                    int(value.strip(), 16)
                    for value in match.group(1).split(",")
                    if value.strip()
                )
                self.assertEqual(payload, bytes(expected))
                self.assertEqual(report["commented_records"], expected_records)
                self.assertEqual(
                    report["active_white_records"],
                    [record for record in range(8) if record not in expected_records],
                )
                self.assertEqual(
                    report["selected_spans"],
                    [[183 + 11 * record, 194 + 11 * record] for record in expected_records],
                )
                self.assertEqual(
                    report["diff_byte_count_vs_active"],
                    tool.SINGLE_RECORD_ADD_VARIANTS[record_add]["diff_bytes"],
                )
                self.assertEqual(
                    report["r20_sha256"],
                    tool.SINGLE_RECORD_ADD_VARIANTS[record_add]["r20_sha256"],
                )
                self.assertEqual(report["expected_r20_sha256"], report["r20_sha256"])
                self.assertEqual(report["family_label"], family)
                self.assertEqual(report["base_mask_hex"], "0x0E")
                self.assertEqual(report["single_record_add"], record_add)
                self.assertNotIn("records0_3_group_add", report)
                self.assertTrue(report["family_label_is_not_bitmask"])
                self.assertEqual(report["tag"], f"MF1750_WF_WMASK_{family}_20261019")
                self.assertEqual(
                    report["env"],
                    f"esp32-s3-devkitc-1-wf-wmask-{family.lower().replace('_', '-')}",
                )
                self.assertIn(
                    f"kAddedWhiteRecord = 0x{record_add:02X}", rendered["include"]
                )
                self.assertIn(
                    f"index >= {183 + 11 * record_add} && index < {194 + 11 * record_add}",
                    rendered["driver"],
                )
                self.assertIn("not a bitmask", rendered["driver"])
                self.assertIn(f'FW_BUILD_TAG = "{report["tag"]}"', rendered["main"])

    def test_record_subset_add_exact_records_spans_and_fixed_identities(self) -> None:
        active = builder.from_reference("active").to_bytes()
        commented = builder.from_reference("commented").to_bytes()
        for subset in tool.RECORD_SUBSET_ADD_SUBSETS:
            family = tool.family_label(0x0E, False, None, subset)
            with self.subTest(family=family):
                report, rendered = tool.build_offline_variant(0x0E, False, None, subset)
                expected_records = sorted(tool.RECORD_SUBSET_ADD_VARIANTS[subset]["records"])
                expected = bytearray(active)
                for record in expected_records:
                    start = 183 + 11 * record
                    expected[start:start + 11] = commented[start:start + 11]

                match = re.search(
                    r"kR20Payload\[535\]\s*=\s*\{(.*?)\};",
                    rendered["include"],
                    flags=re.S,
                )
                self.assertIsNotNone(match)
                payload = bytes(
                    int(value.strip(), 16)
                    for value in match.group(1).split(",")
                    if value.strip()
                )
                self.assertEqual(payload, bytes(expected))
                self.assertEqual(report["commented_records"], expected_records)
                self.assertEqual(
                    report["active_white_records"],
                    [record for record in range(8) if record not in expected_records],
                )
                self.assertEqual(
                    report["selected_spans"],
                    [[183 + 11 * record, 194 + 11 * record] for record in expected_records],
                )
                self.assertEqual(
                    report["diff_byte_count_vs_active"],
                    tool.RECORD_SUBSET_ADD_VARIANTS[subset]["diff_bytes"],
                )
                self.assertEqual(
                    report["r20_sha256"],
                    tool.RECORD_SUBSET_ADD_VARIANTS[subset]["r20_sha256"],
                )
                self.assertEqual(report["expected_r20_sha256"], report["r20_sha256"])
                self.assertEqual(report["family_label"], family)
                self.assertEqual(report["base_mask_hex"], "0x0E")
                self.assertEqual(report["record_subset_add"], list(subset))
                self.assertNotIn("records0_3_group_add", report)
                self.assertNotIn("single_record_add", report)
                self.assertTrue(report["family_label_is_not_bitmask"])
                self.assertEqual(report["tag"], f"MF1750_WF_WMASK_{family}_20261019")
                self.assertEqual(
                    report["env"],
                    f"esp32-s3-devkitc-1-wf-wmask-{family.lower().replace('_', '-')}",
                )
                self.assertIn(
                    "kAddedWhiteRecords[2] = {"
                    + ", ".join(f"0x{record:02X}" for record in subset)
                    + "}",
                    rendered["include"],
                )
                for record in subset:
                    self.assertIn(
                        f"index >= {183 + 11 * record} && index < {194 + 11 * record}",
                        rendered["driver"],
                    )
                self.assertIn("not a bitmask", rendered["driver"])
                self.assertIn(f'FW_BUILD_TAG = "{report["tag"]}"', rendered["main"])

    def test_group_add_rejects_unregistered_bases(self) -> None:
        for base in (0x01, 0x02, 0x05):
            with self.subTest(base=tool.mask_label(base)):
                with self.assertRaises(ValueError):
                    tool.build_offline_variant(base, True)

    def test_single_record_add_rejects_wrong_base_or_group_combination(self) -> None:
        with self.assertRaises(ValueError):
            tool.build_offline_variant(0x0C, False, 0)
        with self.assertRaises(ValueError):
            tool.build_offline_variant(0x0E, True, 0)

    def test_record_subset_add_rejects_wrong_base_or_combination(self) -> None:
        with self.assertRaises(ValueError):
            tool.build_offline_variant(0x0C, False, None, (0, 1))
        with self.assertRaises(ValueError):
            tool.build_offline_variant(0x0E, False, 0, (0, 1))
        with self.assertRaises(ValueError):
            tool.build_offline_variant(0x0E, True, None, (0, 1))

    def test_group_add_cli_selects_only_grayext_family(self) -> None:
        args = tool.parse_args(["--all", "--group-add"])
        self.assertTrue(args.all)
        self.assertTrue(args.group_add)
        args = tool.parse_args(["--mask", "0E", "--group-add"])
        self.assertEqual(args.mask, "0E")
        self.assertTrue(args.group_add)
        args = tool.parse_args(["--mask", "0E", "--record-add", "2"])
        self.assertEqual(args.mask, "0E")
        self.assertEqual(args.record_add, 2)
        self.assertFalse(args.group_add)
        args = tool.parse_args(["--mask", "0E", "--record-subset", "0,2"])
        self.assertEqual(args.mask, "0E")
        self.assertEqual(args.record_subset, (0, 2))
        self.assertFalse(args.group_add)
        self.assertIsNone(args.record_add)


if __name__ == "__main__":
    unittest.main()
