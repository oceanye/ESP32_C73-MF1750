from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "tools" / "gxepd2_gdep073e01_source_audit.py"
SPEC = importlib.util.spec_from_file_location("gxepd2_source_audit", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load GxEPD2 source audit")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


DEFINES = """
#define PSR 0x00
#define PWRR 0x01
#define PON 0x04
#define POFS 0x03
#define BTST1 0x05
#define BTST2 0x06
#define BTST3 0x08
#define PLL 0x30
#define CDI 0x50
#define TCON 0x60
#define TRES 0x61
#define T_VDCS 0x84
#define PWS 0xE3
"""


CURRENT_SOURCE = (
    DEFINES
    + r"""
void X::_InitDisplay()
{
  _writeCommand(0xAA);
  _writeData(0x49); _writeData(0x55); _writeData(0x20);
  _writeData(0x08); _writeData(0x09); _writeData(0x18);
  _writeCommand(PWRR); _writeData(0x3F);
  _writeCommand(PSR); _writeData(0x5F); _writeData(0x69);
  _writeCommand(POFS); _writeData(0x00); _writeData(0x54);
  _writeData(0x00); _writeData(0x44);
  _writeCommand(BTST1); _writeData(0x40); _writeData(0x1F);
  _writeData(0x1F); _writeData(0x2C);
  _writeCommand(BTST2); _writeData(0x6F); _writeData(0x1F);
  _writeData(0x17); _writeData(0x49);
  _writeCommand(BTST3); _writeData(0x6F); _writeData(0x1F);
  _writeData(0x1F); _writeData(0x22);
  _writeCommand(PLL); _writeData(0x08);
  _writeCommand(CDI); _writeData(0x3F);
  _writeCommand(TCON); _writeData(0x02); _writeData(0x00);
  _writeCommand(TRES); _writeData(0x03); _writeData(0x20);
  _writeData(0x01); _writeData(0xE0);
  _writeCommand(T_VDCS); _writeData(0x01);
  _writeCommand(PWS); _writeData(0x2F);
  _PowerOn();
}
void X::_PowerOn() { _writeCommand(0x04); }
void X::refresh(int16_t x, int16_t y, int16_t w, int16_t h)
{
  _PowerOn();
  if (usePartialUpdate) _setPartialRamArea(x, y, w, h);
  else _setPartialRamArea(0, 0, WIDTH, HEIGHT);
  _writeCommand(0x50); _writeData(0xFF);
  _writeCommand(0x12); _writeData(0x00);
  delay(1);
  _waitWhileBusy("_refresh", full_refresh_time);
}
void X::writeNative(const uint8_t* data1, const uint8_t* data2,
                    int16_t x, int16_t y, int16_t w, int16_t h)
{
  _setPartialRamArea(x, y, w, h);
  _writeCommand(0x10);
  _startTransfer();
  _transfer(data1[0]);
  _endTransfer();
}
void X::_setPartialRamArea(unsigned x, unsigned y, unsigned w, unsigned h)
{
  unsigned xe = x + w - 1;
  unsigned ye = y + h;
  _writeCommand(0x83);
  _writeData(x / 256); _writeData(x % 256);
  _writeData(xe / 256); _writeData(xe % 256);
  _writeData(y / 256); _writeData(y % 256);
  _writeData(ye / 256); _writeData(ye % 256); _writeData(0x01);
}
unsigned X::_colorOfDemoBitmap(unsigned from, int mode)
{
  switch (mode) {
    case 0: {
      switch (from) {
        case 0xFF: return (0x01); // white
        case 0xFC: return (0x02); // yellow
        case 0xF1: return (0x04); // orange
        case 0xE5: return (0x03); // red
        case 0x4B: return (0x05); // blue
        case 0x39: return (0x06); // green
        case 0x00: return (0x00); // black
      }
    }
    case 1: { return 0; }
  }
}
unsigned X::_convert_to_native(unsigned data)
{
  switch (data & 7) {
    case 0x00 : result |= 0x00 << 4; break; // black
    case 0x01 : result |= 0x01 << 4; break; // white
    case 0x02 : result |= 0x06 << 4; break; // green
    case 0x03 : result |= 0x05 << 4; break; // blue
    case 0x04 : result |= 0x03 << 4; break; // red
    case 0x05 : result |= 0x02 << 4; break; // yellow
    case 0x06 : result |= 0x04 << 4; break; // orange
    case 0x07 : result |= 0x07 << 4; break; // white
  }
}
"""
)

PREVIOUS_SOURCE = (
    CURRENT_SOURCE.replace("return (0x02); // yellow", "return (0x05); // yellow")
    .replace("return (0x04); // orange", "return (0x06); // orange")
    .replace("return (0x03); // red", "return (0x04); // red")
    .replace("return (0x05); // blue", "return (0x03); // blue")
    .replace("return (0x06); // green", "return (0x02); // green")
)

HEADER = """
// Controller: unknown
static const uint16_t WIDTH = 800;
static const uint16_t HEIGHT = 480;
static const bool hasColor = true;
static const bool hasPartialUpdate = true;
static const bool usePartialUpdate = true;
static const bool hasFastPartialUpdate = false;
static const uint16_t full_refresh_time = 15000;
static const uint16_t partial_refresh_time = 15000;
GxEPD2_730c_GDEP073E01(int16_t cs, int16_t dc, int16_t rst, int16_t busy);
"""


class GxEPD2SourceAuditTests(unittest.TestCase):
    def test_parser_recovers_trace_mapping_and_bounded_negative(self) -> None:
        blobs = {
            "current_source": CURRENT_SOURCE.encode(),
            "current_header": HEADER.encode(),
            "current_properties": b"name=GxEPD2\nversion=1.6.9\n",
            "previous_source": PREVIOUS_SOURCE.encode(),
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            report = audit.build_report(
                blobs,
                cross_image_report=Path(temp_dir) / "absent.json",
                enforce_pins=False,
                network_accessed=False,
            )
        self.assertTrue(report["typed_init"]["matches_expected"])
        self.assertTrue(report["panel_scope"]["has_partial_update"])
        self.assertTrue(report["panel_scope"]["use_partial_update"])
        self.assertFalse(report["panel_scope"]["has_fast_partial_update"])
        self.assertEqual(report["panel_scope"]["full_refresh_time_ms"], 15000)
        self.assertEqual(report["panel_scope"]["partial_refresh_time_ms"], 15000)
        self.assertEqual(
            report["native_color_mapping"]["current_code4_source_label"],
            "orange",
        )
        self.assertTrue(report["native_color_mapping"]["mapping_changed_between_tags"])
        self.assertEqual(report["partial_refresh"]["command"], 0x83)
        self.assertEqual(report["partial_refresh"]["data_expression_count"], 9)
        self.assertTrue(report["partial_refresh"]["powers_on_before_refresh"])
        self.assertTrue(report["partial_refresh"]["selects_requested_window"])
        self.assertTrue(report["partial_refresh"]["border_floating_cdi_ff"])
        self.assertTrue(report["partial_refresh"]["display_refresh_command_0x12"])
        self.assertTrue(report["partial_refresh"]["waits_with_full_refresh_timeout"])
        self.assertTrue(
            report["partial_refresh"]["native_dtm_starts_transfer_immediately"]
        )
        self.assertEqual(report["partial_refresh"]["native_dtm_prefix_bytes"], 0)
        self.assertFalse(report["partial_refresh"]["advertised_as_fast"])
        self.assertTrue(
            report["partial_refresh"]["advertised_partial_equals_full_time"]
        )
        boundary = report["runtime_waveform_boundary"]
        self.assertFalse(boundary["typed_command_0x20_present"])
        self.assertFalse(boundary["typed_command_0x21_present"])
        self.assertFalse(boundary["typed_command_0xe9_present"])
        self.assertFalse(boundary["runtime_waveform_abi_recovered"])
        self.assertFalse(report["safety"]["hardware_accessed"])
        self.assertFalse(report["safety"]["network_accessed"])
        self.assertEqual(report["safety"]["visible_refreshes"], 0)

    def test_fetcher_is_limited_to_pinned_urls(self) -> None:
        visited: list[str] = []

        def fake_fetch(url: str) -> bytes:
            visited.append(url)
            return url.encode()

        blobs = audit.fetch_pinned_blobs(fake_fetch)
        self.assertEqual(visited, list(audit.URLS.values()))
        self.assertEqual(set(blobs), set(audit.URLS))
        self.assertTrue(
            all(
                audit.CURRENT_COMMIT in url or audit.PREVIOUS_COMMIT in url
                for url in visited
            )
        )

    def test_present_cross_image_report_must_match_pinned_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cross.json"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(audit.AuditError, "SHA-256"):
                audit._cross_image_facts(path, [])

    def test_cli_requires_explicit_network_or_all_local_inputs(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--allow-network", result.stderr)

    def test_cli_help_is_ascii_safe(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="ascii",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no device I/O", result.stdout)


if __name__ == "__main__":
    unittest.main()
