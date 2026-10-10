from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = (
    REPO_ROOT / "tools" / "good_display_gdep073e01_source_binary_contract_audit.py"
)
SPEC = importlib.util.spec_from_file_location("gdep073e01_contract_audit", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load GDEP073E01 source/binary contract audit")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


HEADER = """
#define EPD_WIDTH 4
#define EPD_HEIGHT 3

//8bit
#define Black 0x00
#define White 0x11
#define Green 0x66
#define Blue 0x55
#define Red 0x33
#define Yellow 0x22
#define Clean 0x77

//4bit
#define black 0x00
#define white 0x01
#define green 0x06
#define blue 0x05
#define red 0x03
#define yellow 0x02
#define clean 0x07

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
#define DTM 0x10
"""


INIT = r"""
void EPD_init(void)
{
  EPD_W21_WriteCMD(0xAA);
  EPD_W21_WriteDATA(0x49); EPD_W21_WriteDATA(0x55);
  EPD_W21_WriteDATA(0x20); EPD_W21_WriteDATA(0x08);
  EPD_W21_WriteDATA(0x09); EPD_W21_WriteDATA(0x18);
  EPD_W21_WriteCMD(PWRR); EPD_W21_WriteDATA(0x3F);
  EPD_W21_WriteCMD(PSR); EPD_W21_WriteDATA(0x5F); EPD_W21_WriteDATA(0x69);
  EPD_W21_WriteCMD(POFS); EPD_W21_WriteDATA(0x00);
  EPD_W21_WriteDATA(0x54); EPD_W21_WriteDATA(0x00); EPD_W21_WriteDATA(0x44);
  EPD_W21_WriteCMD(BTST1); EPD_W21_WriteDATA(0x40);
  EPD_W21_WriteDATA(0x1F); EPD_W21_WriteDATA(0x1F); EPD_W21_WriteDATA(0x2C);
  EPD_W21_WriteCMD(BTST2); EPD_W21_WriteDATA(0x6F);
  EPD_W21_WriteDATA(0x1F); EPD_W21_WriteDATA(0x17); EPD_W21_WriteDATA(0x49);
  EPD_W21_WriteCMD(BTST3); EPD_W21_WriteDATA(0x6F);
  EPD_W21_WriteDATA(0x1F); EPD_W21_WriteDATA(0x1F); EPD_W21_WriteDATA(0x22);
  EPD_W21_WriteCMD(PLL); EPD_W21_WriteDATA(0x08);
  EPD_W21_WriteCMD(CDI); EPD_W21_WriteDATA(0x3F);
  EPD_W21_WriteCMD(TCON); EPD_W21_WriteDATA(0x02); EPD_W21_WriteDATA(0x00);
  EPD_W21_WriteCMD(TRES); EPD_W21_WriteDATA(0x03);
  EPD_W21_WriteDATA(0x20); EPD_W21_WriteDATA(0x01); EPD_W21_WriteDATA(0xE0);
  EPD_W21_WriteCMD(T_VDCS); EPD_W21_WriteDATA(0x01);
  EPD_W21_WriteCMD(PWS); EPD_W21_WriteDATA(0x2F);
  EPD_W21_WriteCMD(0x04);
}
"""


COLOR_GET = r"""
unsigned Color_get(unsigned char color)
{
  unsigned datas;
  switch(color)
  {
    case 0x00: datas = 0x00; break;
    case 0xff: datas = 0x01; break;
    case 0xfc: datas = 0x02; break;
    case 0xE0: datas = 0x03; break;
    case 0x03: datas = 0x05; break;
    case 0x1c: datas = 0x06; break;
    default: datas = 0x00; break;
  }
  return datas;
}
"""


PICTURE_DISPLAY = r"""
void PIC_display(const unsigned char* picData)
{
  unsigned int i,j,k;
  unsigned char temp1,temp2,data_H,data_L,data;
  EPD_W21_WriteCMD(0x10);
  for(i=0;i<3;i++)
  {
    k=0;
    for(j=0;j<4/2;j++)
    {
      temp1=picData[i*4+k++];
      temp2=picData[i*4+k++];
      data_H=Color_get(temp1)<<4;
      data_L=Color_get(temp2);
      data=data_H|data_L;
      EPD_W21_WriteDATA(data);
    }
  }
  EPD_W21_WriteCMD(0x12);
  EPD_W21_WriteDATA(0x00);
}
"""


def _solid(name: str, value: int) -> str:
    return f"""
void {name}(void)
{{
  unsigned long i;
  EPD_W21_WriteCMD(DTM);
  for(i=0;i<6;i++)
  {{
    EPD_W21_WriteDATA(0x{value:02X});
  }}
}}
"""


CPP = (
    INIT
    + COLOR_GET
    + PICTURE_DISPLAY
    + "".join(
        _solid(name, value) for name, value in audit.EXPECTED_SOLID_FUNCTIONS.items()
    )
)

SKETCH = "\n".join(f"{name}();" for name in audit.EXPECTED_DEMO_CALLS)
IMAGE = """const unsigned char gImage_1[12] = {
0X00,0XFF,0XFC,0XE0,0X03,0X1C,
0X00,0XFF,0XFC,0XE0,0X03,0X1C,
};
"""


def _source_zip(overrides: dict[str, str] | None = None) -> bytes:
    members = {
        audit.SOURCE_CPP: CPP,
        audit.SOURCE_HEADER: HEADER,
        audit.SOURCE_SPI_CPP: "// SPI fixture\n",
        audit.SOURCE_SPI_HEADER: "// SPI header fixture\n",
        audit.SOURCE_SKETCH: SKETCH,
        audit.SOURCE_IMAGE: IMAGE,
    }
    members.update(overrides or {})
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(audit.ROOT, b"")
        for name in audit.EXPECTED_MEMBER_IDENTITIES:
            archive.writestr(name, members[name].encode("latin-1"))
    return output.getvalue()


def _trace() -> list[dict[str, str]]:
    return [
        {"command": f"0x{command:02x}", "data_hex": bytes(data).hex()}
        for command, data in audit.EXPECTED_INIT_TRACE
    ]


def _cross_report(*, code4: bool = False) -> bytes:
    mapping = dict(audit.EXPECTED_BINARY_TAG_TO_NATIVE)
    if code4:
        mapping[29] = 4
    value = {
        "schema_version": 1,
        "kind": audit.EXPECTED_CROSS_REPORT_KIND,
        "base_official_bundle": {"zip_sha256": "fixture-bundle"},
        "cross_image_findings": {
            "panel_geometry": {"height": 3, "width": 4},
            "unpacked_tag_frame_bytes": 12,
            "packed_frame_bytes": 6,
            "unpacked_tag_to_panel_code": {
                str(tag): code for tag, code in mapping.items()
            },
        },
        "images": {
            "GDEP073E01wifi.bin": {"typed_init_trace": _trace()},
            "SD.bin": {"typed_init_trace": _trace()},
            "usb.bin": {"typed_init_trace": _trace()},
        },
        "runtime_waveform_boundary": {
            "dual_controller_delivery_recovered": False,
            "runtime_lut_length_2508_recovered": False,
            "runtime_lut_length_704_recovered": False,
            "runtime_waveform_abi_recovered": False,
            "typed_command_0x20_recovered": False,
            "typed_command_0x21_recovered": False,
        },
        "safety": {
            "device_network_accessed": False,
            "display_refreshed": False,
            "flash_written": False,
            "hardware_accessed": False,
            "offline_static_analysis_only": True,
            "serial_or_com_accessed": False,
        },
    }
    return (json.dumps(value, sort_keys=True) + "\n").encode()


class GDEP073E01SourceBinaryContractAuditTests(unittest.TestCase):
    def test_recovers_six_color_contract_and_emits_metadata_only(self) -> None:
        report = audit.build_report(
            _source_zip(),
            _cross_report(),
            enforce_pins=False,
            network_accessed=False,
        )
        comparison = report["identity_pinned_comparison"]
        self.assertEqual(comparison["source_native_codes"], [0, 1, 2, 3, 5, 6])
        self.assertEqual(comparison["binary_native_codes"], [0, 1, 2, 3, 5, 6])
        self.assertTrue(comparison["native_code_sets_exactly_equal"])
        self.assertFalse(comparison["input_tag_sets_equal"])

        header = report["official_2024_source"]["header_contract"]
        self.assertFalse(header["native_code4_declared_as_color"])
        self.assertEqual(header["native_code7_symbol"], "clean")
        color_get = report["official_2024_source"]["Color_get"]
        self.assertFalse(color_get["native_code4_emitted"])
        self.assertFalse(color_get["native_code7_emitted"])
        self.assertEqual(
            report["official_2024_source"]["image_h_tag_aggregate"][
                "distinct_tag_count"
            ],
            6,
        )
        self.assertFalse(report["safety"]["hardware_accessed"])
        self.assertFalse(report["safety"]["serial_or_com_accessed"])
        self.assertEqual(report["safety"]["visible_refreshes"], 0)

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertLess(len(serialized), 30_000)
        self.assertNotIn("0X00,0XFF,0XFC", serialized)
        self.assertNotIn("void EPD_init", serialized)
        self.assertFalse(report["metadata_only"]["source_member_contents_emitted"])
        self.assertFalse(report["metadata_only"]["panel_payload_emitted"])

    def test_rejects_header_code4_color_addition(self) -> None:
        changed = HEADER.replace(
            "#define clean 0x07",
            "#define orange 0x04\n#define clean 0x07",
        )
        with self.assertRaisesRegex(audit.AuditError, "4-bit color contract"):
            audit.build_report(
                _source_zip({audit.SOURCE_HEADER: changed}),
                _cross_report(),
                enforce_pins=False,
            )

    def test_rejects_image_tag_outside_color_get_set(self) -> None:
        changed = IMAGE.replace("0X00", "0X44", 1)
        with self.assertRaisesRegex(audit.AuditError, "image tag set"):
            audit.build_report(
                _source_zip({audit.SOURCE_IMAGE: changed}),
                _cross_report(),
                enforce_pins=False,
            )

    def test_rejects_binary_code_set_drift(self) -> None:
        with self.assertRaisesRegex(audit.AuditError, "binary six-tag mapping"):
            audit.build_report(
                _source_zip(),
                _cross_report(code4=True),
                enforce_pins=False,
            )

    def test_identity_enforcement_rejects_unpinned_source_zip(self) -> None:
        with self.assertRaisesRegex(audit.AuditError, "ZIP identity"):
            audit.build_report(
                _source_zip(),
                _cross_report(),
                enforce_pins=True,
            )

    def test_fetcher_visits_only_the_one_pinned_vendor_url(self) -> None:
        visited: list[str] = []

        def fake_fetch(url: str) -> bytes:
            visited.append(url)
            return b"fixture"

        self.assertEqual(audit.fetch_pinned_source_zip(fake_fetch), b"fixture")
        self.assertEqual(visited, [audit.SOURCE_ZIP_URL])
        with self.assertRaisesRegex(audit.AuditError, "single pinned"):
            audit._validate_source_url("https://example.com/source.zip")

    def test_cli_requires_explicit_network_or_local_source(self) -> None:
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
        self.assertIn("metadata only; no device I/O", result.stdout)


if __name__ == "__main__":
    unittest.main()
