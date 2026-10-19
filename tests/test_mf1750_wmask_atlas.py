from __future__ import annotations

from pathlib import Path
import unittest

from tools import mf1750_wmask_atlas as tool


def _cell(mask: str, input_index: int, label: str | None = None) -> tool.CellSpec:
    return tool.CellSpec(
        Path("batch"), label or mask, mask, "stem", "t0", input_index
    )


class WmaskAtlasFamilyLabelTests(unittest.TestCase):
    def test_record_subset_labels_are_registered_family_labels(self) -> None:
        self.assertEqual(
            tool.RECORD_SUBSET_FAMILY_LABELS,
            frozenset({"0E_R0R1", "0E_R0R2", "0E_R0R3"}),
        )
        for label in sorted(tool.RECORD_SUBSET_FAMILY_LABELS):
            with self.subTest(label=label):
                self.assertIn(label, tool.FAMILY_LABELS)

    def test_record_subset_labels_are_not_interpreted_as_hex_masks(self) -> None:
        for index, label in enumerate(sorted(tool.RECORD_SUBSET_FAMILY_LABELS)):
            with self.subTest(label=label):
                tier = tool._mask_sort_key(_cell(label, index))[0]
                self.assertNotEqual(tier, 0)
                self.assertEqual(tier, 3)

    def test_sort_order_numeric_grayext_single_pair_then_reference(self) -> None:
        masks = [
            "00", "01", "02", "03", "04", "05", "06", "07",
            "08", "09", "0A", "0B", "0C", "0D", "0E", "0F", "1F",
            "1E", "1C", "1D",
            "0E_R0", "0E_R1", "0E_R2", "0E_R3",
            "0E_R0R1", "0E_R0R2", "0E_R0R3",
            "REF",
        ]
        cells = [_cell(mask, index) for index, mask in enumerate(masks)]
        ordered = [cell.mask for cell in sorted(cells, key=tool._mask_sort_key)]
        self.assertEqual(ordered, masks)

    def test_numeric_masks_sort_by_value_not_input_order(self) -> None:
        cells = [_cell("0F", 0), _cell("01", 1), _cell("0x0e", 2)]
        ordered = [cell.mask for cell in sorted(cells, key=tool._mask_sort_key)]
        self.assertEqual(ordered, ["01", "0x0e", "0F"])

    def test_family_tiers_retain_input_order(self) -> None:
        cells = [
            _cell("0E_R0R3", 0),
            _cell("0E_R0R1", 1),
            _cell("1D", 2),
            _cell("1E", 3),
            _cell("0E_R3", 4),
            _cell("0E_R0", 5),
        ]
        ordered = [cell.mask for cell in sorted(cells, key=tool._mask_sort_key)]
        self.assertEqual(ordered, ["1D", "1E", "0E_R3", "0E_R0", "0E_R0R3", "0E_R0R1"])

    def test_reference_sorts_after_record_pairs(self) -> None:
        cells = [_cell("REF", 0), _cell("0E_R0R2", 1)]
        ordered = [cell.mask for cell in sorted(cells, key=tool._mask_sort_key)]
        self.assertEqual(ordered, ["0E_R0R2", "REF"])


class WmaskAtlasCellParseTests(unittest.TestCase):
    def test_parse_cell_accepts_record_pair_mask(self) -> None:
        spec = tool._parse_cell(
            ".test-output/hardware/WF_WMASK_0E_R0R1_20261019_V1|0E_R0R1|0E_R0R1|03-0e-r0r1",
            0,
        )
        self.assertEqual(spec.label, "0E_R0R1")
        self.assertEqual(spec.mask, "0E_R0R1")
        self.assertEqual(spec.stem, "03-0e-r0r1")
        self.assertEqual(spec.time, "t0")

    def test_parse_cell_rejects_malformed_time(self) -> None:
        with self.assertRaises(tool.AtlasError):
            tool._parse_cell("batch|0E_R0R1|0E_R0R1|03-0e-r0r1|zero", 0)

    def test_parse_cell_rejects_empty_fields(self) -> None:
        with self.assertRaises(tool.AtlasError):
            tool._parse_cell("batch|0E_R0R1||03-0e-r0r1", 0)


if __name__ == "__main__":
    unittest.main()
