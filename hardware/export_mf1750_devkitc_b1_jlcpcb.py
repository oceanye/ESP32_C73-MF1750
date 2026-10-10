"""Export and verify the complete JLCPCB package for MF1750 Rev B1.

The verified B1 PCB/SCH remain immutable inputs.  A temporary fabrication
variant removes paste apertures from DNP footprints before plotting, so R15 is
absent from the stencil while R16 remains fitted.  The script emits distinct
JLCPCB upload files plus engineering support evidence and fails closed on any
board, drill, paste, BOM, CPL, or hash-contract drift.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
SOURCE_DIR = HARDWARE / "mf1750_devkitc_b1_single_power_layer"
PROJECT = "mf1750_devkitc_b1_single_power_layer"
BOARD = SOURCE_DIR / f"{PROJECT}.kicad_pcb"
SCHEMATIC = SOURCE_DIR / f"{PROJECT}.kicad_sch"
SOURCE_BOM = HARDWARE / "mf1750_devkitc_compact" / "bom_reference.csv"
OUTPUT = HARDWARE / "mf1750_devkitc_b1_jlcpcb"
UPLOAD = OUTPUT / "upload"
SUPPORT = OUTPUT / "support"
GERBER = OUTPUT / "gerber_files"
PROJECT_ARCHIVE = OUTPUT / "project_source"
PRODUCTION_FOOTPRINTS = HARDWARE / "mf1750_production_v1" / "MF1750_Production.pretty"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
KICAD_PYTHON = Path(r"C:\Program Files\KiCad\10.0\bin\python.exe")

GERBER_ZIP = UPLOAD / "JLCPCB_PCB_MF1750_DEVKITC_B1_4L.zip"
SMT_BOM = UPLOAD / "JLCPCB_BOM_MF1750_DEVKITC_B1_SMT.csv"
SMT_CPL = UPLOAD / "JLCPCB_CPL_MF1750_DEVKITC_B1_SMT.csv"
SUPPORT_ZIP = OUTPUT / "JLCPCB_SUPPORT_MF1750_DEVKITC_B1.zip"
PROJECT_ZIP = OUTPUT / "MF1750_DEVKITC_B1_KICAD_SOURCE.zip"

GERBER_LAYERS = (
    "F.Cu",
    "In1.Cu",
    "In2.Cu",
    "B.Cu",
    "F.Mask",
    "B.Mask",
    "F.Paste",
    "F.SilkS",
    "B.SilkS",
    "Edge.Cuts",
)
EXPECTED_GERBERS = {
    f"{PROJECT}-F_Cu.gtl": "top copper / L1",
    f"{PROJECT}-In1_Cu.g1": "ground plane / L2",
    f"{PROJECT}-In2_Cu.g2": "power routing / L3",
    f"{PROJECT}-B_Cu.gbl": "bottom copper / L4",
    f"{PROJECT}-F_Mask.gts": "top solder mask",
    f"{PROJECT}-B_Mask.gbs": "bottom solder mask",
    f"{PROJECT}-F_Paste.gtp": "top paste; R15 removed",
    f"{PROJECT}-Top Silkscreen.gto": "top silkscreen",
    f"{PROJECT}-Bottom Silkscreen.gbo": "bottom silkscreen",
    f"{PROJECT}-Edge_Cuts.gm1": "single board outline",
    f"{PROJECT}-PTH.drl": "plated drill",
    f"{PROJECT}-NPTH.drl": "non-plated drill",
}
EXPECTED_DRILL_COUNTS = {
    "PTH": {0.300: 75, 0.750: 2, 0.800: 44},
    "NPTH": {2.500: 2},
}
PASTE_FLASH_COUNT = 144
FIT_SMT_COUNT = 46
UNIQUE_LCSC_COUNT = 16
JLC_STACKUP = "JLC04161H-7628"

MANUAL_REFS = {"J2", "J3"}
NON_ASSEMBLY_REFS = {"H1", "H2", *(f"TP{i}" for i in range(1, 11))}
ORIENTATION_CHECKS = {
    "J1": "pin 1 is the leftmost signal pad in assembled-board top view; cable exits top edge",
    "D1": "pad1/K=VPH; body rotation 180 deg",
    "D2": "pad1/K=GND; body rotation 180 deg",
    "D3": "pad1/K=NEG_PUMP_H; body rotation 0 deg",
    "D4": "pad1/K=SW_C; body rotation 0 deg",
    "Q1": "SI1308EDL: pad1=GDRH/G, pad2=RESEH/S, pad3=SW_H/D; rotation 90 deg",
    "Q2": "AO3401A: pad1=GDRC/G, pad2=V_B/S, pad3=SW_C/D; rotation 0 deg",
    "R16": "FIT; independent CS2 to SL_CSB",
    "R15": "DNP; no BOM/CPL/paste aperture",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_cli(*args: str) -> None:
    subprocess.run([str(KICAD_CLI), *args], cwd=ROOT, check=True)


def ref_key(ref: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z]+)(\d+)(.*)", ref)
    if not match:
        return ref, -1, ""
    return match.group(1), int(match.group(2)), match.group(3)


def clean_output() -> None:
    if not OUTPUT.exists():
        return
    resolved = OUTPUT.resolve()
    hardware_root = HARDWARE.resolve()
    if resolved == hardware_root or hardware_root not in resolved.parents:
        raise SystemExit(f"Refusing to clear unexpected path: {resolved}")
    shutil.rmtree(resolved)


def make_fabrication_variant(temp_dir: Path) -> Path:
    board = pcbnew.LoadBoard(str(BOARD))
    if board is None:
        raise SystemExit(f"Cannot load {BOARD}")
    if board.GetCopperLayerCount() != 4:
        raise SystemExit("Canonical board is not four-layer")
    if not board.IsLayerEnabled(pcbnew.F_Paste):
        raise SystemExit("Canonical board does not enable F.Paste")
    if not board.FindFootprintByReference("R15").IsDNP():
        raise SystemExit("R15 is no longer DNP")
    if board.FindFootprintByReference("R16").IsDNP():
        raise SystemExit("R16 is no longer FIT")

    removed = []
    for footprint in board.GetFootprints():
        if not footprint.IsDNP():
            continue
        for pad in footprint.Pads():
            layers = pad.GetLayerSet()
            before = layers.Contains(pcbnew.F_Paste) or layers.Contains(pcbnew.B_Paste)
            layers.RemoveLayer(pcbnew.F_Paste)
            layers.RemoveLayer(pcbnew.B_Paste)
            pad.SetLayerSet(layers)
            if before:
                removed.append((footprint.GetReference(), pad.GetNumber()))
    if sorted(removed) != [("R15", "1"), ("R15", "2")]:
        raise SystemExit(f"Unexpected DNP paste apertures removed: {removed}")

    plot = board.GetPlotOptions()
    plot.SetCreateGerberJobFile(False)
    plot.SetUseGerberProtelExtensions(True)
    plot.SetUseGerberX2format(True)
    plot.SetGerberPrecision(6)
    board.SetPlotOptions(plot)
    variant = temp_dir / f"{PROJECT}.kicad_pcb"
    pcbnew.SaveBoard(str(variant), board)
    return variant


def fitted_smt_footprints(board: pcbnew.BOARD) -> dict[str, pcbnew.FOOTPRINT]:
    result = {}
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        if (
            footprint.IsDNP()
            or footprint.HasThroughHolePads()
            or ref in MANUAL_REFS
            or ref in NON_ASSEMBLY_REFS
        ):
            continue
        if footprint.GetLayer() != pcbnew.F_Cu:
            raise SystemExit(f"Unverified bottom-side SMT rotation: {ref}")
        result[ref] = footprint
    if len(result) != FIT_SMT_COUNT:
        raise SystemExit(f"Expected {FIT_SMT_COUNT} FIT SMT refs; found {len(result)}")
    if "R16" not in result or "R15" in result:
        raise SystemExit("Population contract failed: R16 FIT / R15 DNP")
    return result


def load_reference_bom() -> dict[str, dict[str, str]]:
    with SOURCE_BOM.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    result = {row["Designator"]: row for row in rows if "," not in row["Designator"]}
    if len(rows) != 60 or len(result) != 59:
        raise SystemExit("Reference BOM cardinality drift")
    return result


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        csv.writer(handle).writerows(rows)


def make_smt_bom_and_cpl(board: pcbnew.BOARD) -> tuple[set[str], set[str]]:
    footprints = fitted_smt_footprints(board)
    reference = load_reference_bom()
    groups: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    audit_rows = [
        [
            "Designator",
            "Comment",
            "Footprint",
            "LCSC Part #",
            "Manufacturer",
            "MPN",
            "Assembly",
            "Note",
        ]
    ]
    for ref in sorted(footprints, key=ref_key):
        row = reference.get(ref)
        if row is None:
            raise SystemExit(f"Missing BOM mapping for {ref}")
        if row["DNP"] != "No" or not re.fullmatch(r"C\d+", row["LCSC Part #"]):
            raise SystemExit(f"Invalid fitted SMT BOM mapping for {ref}: {row}")
        footprint = footprints[ref]
        if row["Footprint"] != footprint.GetFPID().GetUniStringLibId():
            raise SystemExit(f"Footprint mismatch for {ref}")
        key = (row["Value"], row["Footprint"], row["LCSC Part #"], row["MPN"])
        groups[key].append(ref)
        audit_rows.append(
            [
                ref,
                row["Value"],
                row["Footprint"],
                row["LCSC Part #"],
                row["Manufacturer"],
                row["MPN"],
                "SMT FIT",
                row["Note"],
            ]
        )

    if len(groups) != UNIQUE_LCSC_COUNT:
        raise SystemExit(
            f"Expected {UNIQUE_LCSC_COUNT} unique SMT lines; found {len(groups)}"
        )
    bom_rows = [["Comment", "Designator", "Footprint", "LCSC Part #"]]
    for (value, footprint, lcsc, _mpn), refs in sorted(
        groups.items(), key=lambda item: ref_key(sorted(item[1], key=ref_key)[0])
    ):
        ordered_refs = sorted(refs, key=ref_key)
        bom_rows.append([value, ",".join(ordered_refs), footprint, lcsc])
    write_csv(SMT_BOM, bom_rows)
    write_csv(SUPPORT / "BOM_SMT_AUDIT_EXPANDED.csv", audit_rows)

    cpl_rows = [["Designator", "Mid X", "Mid Y", "Rotation", "Layer"]]
    for ref in sorted(footprints, key=ref_key):
        footprint = footprints[ref]
        position = footprint.GetPosition()
        cpl_rows.append(
            [
                ref,
                f"{pcbnew.ToMM(position.x):.4f}mm",
                f"{-pcbnew.ToMM(position.y):.4f}mm",
                f"{footprint.GetOrientationDegrees() % 360.0:.2f}",
                "Top",
            ]
        )
    write_csv(SMT_CPL, cpl_rows)

    bom_refs = {ref for row in bom_rows[1:] for ref in row[1].split(",") if ref}
    cpl_refs = {row[0] for row in cpl_rows[1:]}
    if bom_refs != cpl_refs or bom_refs != set(footprints):
        raise SystemExit("BOM/CPL/PCB fitted SMT reference sets differ")
    return bom_refs, cpl_refs


def make_manual_and_dnp_files(board: pcbnew.BOARD) -> None:
    reference = load_reference_bom()
    manual_rows = [
        [
            "Designator",
            "Value",
            "Manufacturer",
            "MPN / suggested part",
            "LCSC Part #",
            "Assembly",
            "Note",
        ]
    ]
    for ref in ("J2", "J3"):
        row = reference[ref]
        suggested_lcsc = ""
        suggested = row["MPN"]
        note = row["Note"]
        if ref == "J2":
            suggested_lcsc = (
                "C7500786 (candidate only; verify 0.80 mm finished-hole fit)"
            )
            suggested = "2x XUNPU FH2.54-09-22PZD + ESP32-S3-DevKitC-1-N16R8"
            note += "; JLC wave-solder candidate uses 8.5 mm body and 3.2 mm pins, not yet Z-envelope qualified"
        manual_rows.append(
            [
                ref,
                row["Value"],
                row["Manufacturer"],
                suggested,
                suggested_lcsc,
                "MANUAL / NOT IN SMT BOM OR CPL",
                note,
            ]
        )
    write_csv(SUPPORT / "BOM_MANUAL_THT.csv", manual_rows)

    r15 = board.FindFootprintByReference("R15")
    dnp_rows = [["Designator", "Value", "Reason", "Paste aperture"]]
    dnp_rows.append(
        [
            "R15",
            r15.GetValue(),
            "DNP; R16 is the verified fitted CS2-to-SL_CSB strap; never fit both",
            "removed from fabrication variant",
        ]
    )
    write_csv(SUPPORT / "DNP_LIST.csv", dnp_rows)


def parse_drill(path: Path) -> dict[float, int]:
    tools: dict[str, float] = {}
    counts: Counter[str] = Counter()
    active = None
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"T(\d+)C([0-9.]+)", line)
        if match:
            tools[match.group(1)] = float(match.group(2))
            continue
        match = re.fullmatch(r"T(\d+)", line)
        if match:
            active = match.group(1)
            continue
        if active is not None and line.startswith("X"):
            counts[active] += 1
    return {tools[tool]: count for tool, count in counts.items()}


def verify_gerbers() -> dict[str, object]:
    names = {path.name for path in GERBER.iterdir() if path.is_file()}
    expected = set(EXPECTED_GERBERS)
    if names != expected:
        raise SystemExit(
            f"Gerber package set drift: missing={expected - names}, extra={names - expected}"
        )
    if any(path.suffix.lower() in {".gbrjob", ".gbp"} for path in GERBER.iterdir()):
        raise SystemExit("Gerber ZIP must not contain gbrjob or empty bottom paste")

    paste = GERBER / f"{PROJECT}-F_Paste.gtp"
    paste_text = paste.read_text(encoding="ascii")
    flashes = len(re.findall(r"D03\*", paste_text))
    if flashes != PASTE_FLASH_COUNT:
        raise SystemExit(f"Expected {PASTE_FLASH_COUNT} paste flashes; found {flashes}")
    if "%TO.C,R15*%" in paste_text or "%TO.C,R16*%" not in paste_text:
        raise SystemExit("Paste population failed: require R15 absent and R16 present")

    drills = {
        "PTH": parse_drill(GERBER / f"{PROJECT}-PTH.drl"),
        "NPTH": parse_drill(GERBER / f"{PROJECT}-NPTH.drl"),
    }
    if drills != EXPECTED_DRILL_COUNTS:
        raise SystemExit(f"Drill contract drift: {drills}")

    edge = GERBER / f"{PROJECT}-Edge_Cuts.gm1"
    edge_text = edge.read_text(encoding="ascii")
    if edge_text.count("D02*") != 1 or edge_text.count("D01*") != 4:
        raise SystemExit("Edge Gerber is not one four-segment closed rectangle")
    return {
        "files": {name: EXPECTED_GERBERS[name] for name in sorted(expected)},
        "top_paste_flashes": flashes,
        "paste_r15_present": False,
        "paste_r16_present": True,
        "drill_tools_and_counts": drills,
        "board_outline_mm": [62.0, 58.0],
    }


def make_docs(board: pcbnew.BOARD, gerber_audit: dict[str, object]) -> None:
    orientation_rows = [["Designator", "Rotation", "Top-side verification"]]
    for ref, note in ORIENTATION_CHECKS.items():
        footprint = board.FindFootprintByReference(ref)
        orientation_rows.append(
            [
                ref,
                f"{footprint.GetOrientationDegrees() % 360.0:.2f}",
                note,
            ]
        )
    write_csv(SUPPORT / "ORIENTATION_CHECKLIST.csv", orientation_rows)

    (OUTPUT / "README_ORDER.md").write_text(
        f"""# MF1750 DevKitC Rev B1 — 嘉立创下单与 SMT 交付说明

## 三个上传文件

1. PCB/Gerber 栏只上传 `upload/{GERBER_ZIP.name}`。
2. BOM 栏只上传 `upload/{SMT_BOM.name}`。
3. CPL/坐标栏只上传 `upload/{SMT_CPL.name}`。

`{SUPPORT_ZIP.name}`、`support/` 与 `{PROJECT_ZIP.name}` 是审计/装配支持资料，
不要上传到上述三个自动解析栏。

## PCB 下单参数

- 单板 `62 x 58 mm`，FR-4，4 层，成品厚度 1.6 mm。
- 指定嘉立创 `JLC04161H-7628` 叠层：L1/L4 外铜 1 oz，L2/L3 内铜 0.5 oz；
  本设计不声明受控阻抗。
- 层用途：L1=器件/信号/局部功率，L2=连续 GND，L3=3V3/EPD_3V3/V_B，
  L4=信号与回流。
- 绿色阻焊、白色丝印；表面处理固定为 `ENIG (1U)`，不得在下单时临时
  改为 HASL。J1 是 0.50 mm pitch FPC，本选择用于保持细间距焊盘平整度。
- PTH/NPTH 必须分开解析；本包为 PTH 121 孔、NPTH 2 孔。
- 上传的 Gerber/BOM/CPL 都是单板数据。若由嘉立创拼板，选择
  `Single Piece, please help me repeat the data`，不得选 `Complete File`。
- PCBA 下单要求嘉立创添加至少 5 mm 工艺边、fiducials 和 tooling holes；
  不要缩放或改写 62 x 58 mm 功能板框。
- **已知 PCBA 条款偏离：**按器件本体/F.Fab 几何，J1 到上边约 1.47 mm、
  C6 到右边约 1.25 mm、C15 到右边约 2.25 mm，低于嘉立创一般
  `component body to board edge >= 2.5 mm` 要求。工艺边不会自动消除
  它们到成品功能板边的偏离。必须由嘉立创 PCBA 工程对**该精确拼板和
  贴装方案**给出明确接受；若未接受，停止下单并改版，或重新生成
  将受影响器件改为手焊的 BOM/CPL。仅裸板 Gerber 预览/在线 DFM 通过
  不构成放行。

## SMT 合同

- 单面 Top SMT：46 个 FIT 位号，16 个唯一 LCSC 料号；BOM 与 CPL 位号集相同。
- `R16=FIT`、`R15=DNP`，禁止同时安装。钢网已移除 R15 两个开口，保留 R16。
- J2、J3 不在 SMT BOM/CPL：按 `support/BOM_MANUAL_THT.csv` 手工装配。
- J2 当前 PCB 为 0.80 mm finished holes。候选 `C7500786` 是 1x22、2.54 mm、
  8.5 mm 高、3.2 mm 尾针的波峰焊母座；在确认尾针截面能穿过 0.80 mm 成品孔、
  两排 22.86 mm 间距与 DevKit Z 包络前，不得让嘉立创代装 J2。

## 上传后必须人工确认

- 逐件核对 J1 pin1、D1-D4 阴极、Q1/Q2 pin1 与
  `support/ORIENTATION_CHECKLIST.csv`/装配图一致。
- 确认系统显示 R16 贴装、R15 不贴；所有 46 个 BOM/CPL 位号均成功匹配。
- 重新核对 LCSC 型号、封装、库存与 Basic/Extended 状态；库存是下单时状态，
  不能由本地导出包保证。
- 预览确认两个内层未交换：L2=GND，L3=电源。
- 本地 ERC/DRC 是前置检查，不是嘉立创 DFM/CAM 通过证明。必须再完成
  PCBA DFM、CAM 生产稿和贴装预览审批，特别检查丝印/阻焊裁剪。
- 选择“确认生产稿/Confirm production file”，人工看完厂家 CAM 后再批准生产。

## 官方下单口径

- KiCad BOM/CPL：https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad
- PCBA 条款：https://jlcpcb.com/help/article/terms-and-conditions-of-jlcpcb-assembly-service
- 工艺边/fiducials：https://jlcpcb.com/help/article/how-to-add-edge-rails-fiducials-for-pcb-assembly-order
- 拼板 BOM/CPL 选项：https://jlcpcb.com/help/article/common-bom-and-cpl-matching-issues-and-explanations
- 表面处理：https://jlcpcb.com/help/article/jlcpcb-surface-finish

## 首板限制

这是可上传的工程首板加工包，不是已经完成实物资格认证的量产放行。收到板后仍需
执行：裸板短路/连续性检查；先不插屏限流上电；核对全部 MF-1750 电源轨、纹波与
温升；确认 R16 实装/R15 空位；最后才接 FPC 和屏幕。双电源域 GPIO 没有 Ioff
隔离，继续遵守 USB 先上、J3 后上；J3 先断、USB 后拔，J3 关闭时 GPIO 高阻。

机器审计摘要：`{json.dumps(gerber_audit, ensure_ascii=False, sort_keys=True)}`
""",
        encoding="utf-8",
    )

    (SUPPORT / "STACKUP_AND_FAB_NOTES.md").write_text(
        f"""# Stackup and fabrication notes

- Order stackup: `{JLC_STACKUP}`, 4 layers, nominal 1.6 mm.
- Surface finish: ENIG, 1 microinch option; do not substitute HASL at order time.
- L1 F.Cu: 0.035 mm / 1 oz.
- Prepreg: 7628, nominal 0.2104 mm.
- L2 In1.Cu: 0.0152 mm / 0.5 oz, solid GND plane.
- Core: nominal 1.065 mm.
- L3 In2.Cu: 0.0152 mm / 0.5 oz, power routing.
- Prepreg: 7628, nominal 0.2104 mm.
- L4 B.Cu: 0.035 mm / 1 oz.
- Finished thickness: 1.6 mm nominal; no controlled-impedance claim.
- Ordinary through vias only; 0.30 mm drill / 0.60 mm pad for routed vias.
- Add >=5 mm assembly rails, fiducials, and tooling holes at JLCPCB panelization.
- Gerber job file is deliberately excluded so an inferred KiCad dielectric model cannot
  override the explicit order stackup above.
""",
        encoding="utf-8",
    )


def export_support_files(variant: Path) -> None:
    (SUPPORT / "drill_maps").mkdir(parents=True, exist_ok=True)
    run_cli(
        "pcb",
        "export",
        "drill",
        "-o",
        str(SUPPORT / "drill_maps"),
        "--format",
        "excellon",
        "--drill-origin",
        "absolute",
        "--excellon-zeros-format",
        "decimal",
        "--excellon-oval-format",
        "route",
        "--excellon-units",
        "mm",
        "--excellon-separate-th",
        "--generate-map",
        "--map-format",
        "pdf",
        "--generate-report",
        "--report-path",
        str(SUPPORT / "drill_report.txt"),
        str(variant),
    )
    run_cli(
        "pcb", "export", "ipcd356", "-o", str(SUPPORT / "netlist.ipc"), str(variant)
    )
    run_cli(
        "pcb",
        "export",
        "stats",
        "--format",
        "json",
        "--units",
        "mm",
        "-o",
        str(SUPPORT / "board_statistics.json"),
        str(variant),
    )
    run_cli(
        "sch", "export", "pdf", "-o", str(SUPPORT / "schematic.pdf"), str(SCHEMATIC)
    )
    for side in ("top", "bottom"):
        run_cli(
            "pcb",
            "render",
            "-o",
            str(SUPPORT / f"assembly_{side}.png"),
            "--side",
            side,
            "--background",
            "opaque",
            "--quality",
            "high",
            "--width",
            "1800",
            "--height",
            "1600",
            str(variant),
        )
    run_cli(
        "pcb",
        "export",
        "pdf",
        "--mode-single",
        "--black-and-white",
        "--drill-shape-opt",
        "2",
        "-l",
        "F.Fab,F.SilkS,Edge.Cuts",
        "--sketch-pads-on-fab-layers",
        "--crossout-DNP-footprints-on-fab-layers",
        "-o",
        str(SUPPORT / "assembly_top.pdf"),
        str(variant),
    )
    run_cli(
        "pcb",
        "export",
        "pdf",
        "--mode-single",
        "--black-and-white",
        "--mirror",
        "--drill-shape-opt",
        "2",
        "-l",
        "B.Fab,B.SilkS,Edge.Cuts",
        "--sketch-pads-on-fab-layers",
        "--crossout-DNP-footprints-on-fab-layers",
        "-o",
        str(SUPPORT / "assembly_bottom_mirrored.pdf"),
        str(variant),
    )
    shutil.copy2(SOURCE_DIR / "erc_final.rpt", SUPPORT / "ERC_zero.rpt")
    shutil.copy2(SOURCE_DIR / "drc_final.rpt", SUPPORT / "DRC_zero.rpt")
    shutil.copy2(SOURCE_DIR / "design_audit.json", SUPPORT / "design_audit.json")
    shutil.copy2(
        SOURCE_DIR / "verification_manifest.json",
        SUPPORT / "PRE_EXPORT_SOURCE_VERIFICATION.json",
    )
    (SUPPORT / "PRE_EXPORT_SOURCE_AUDIT_NOTE.md").write_text(
        "# Pre-export source audit\n\n"
        "`PRE_EXPORT_SOURCE_VERIFICATION.json` is the exact historical B1 source "
        "verification record created before this Gerber/drill package existed.  Its "
        "legacy `No Gerber/drill manufacturing package is released` limit is "
        "superseded only by this export package's `MANIFEST.json`, "
        "`SHA256SUMS.txt`, and `README_ORDER.md`; all remaining source limits still "
        "apply.\n",
        encoding="utf-8",
    )


def zip_directory(
    directory: Path, archive: Path, *, exclude: set[Path] | None = None
) -> None:
    exclude = {path.resolve() for path in (exclude or set())}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.resolve() not in exclude:
                handle.write(path, path.relative_to(directory).as_posix())


def make_project_archive() -> None:
    PROJECT_ARCHIVE.mkdir(parents=True, exist_ok=True)
    for path in (
        BOARD,
        SCHEMATIC,
        SOURCE_DIR / f"{PROJECT}.kicad_pro",
        SOURCE_DIR / "sym-lib-table",
        SOURCE_DIR / "mf1750_local.kicad_sym",
        SOURCE_DIR / "README.md",
        SOURCE_BOM,
    ):
        shutil.copy2(path, PROJECT_ARCHIVE / path.name)
    shutil.copytree(
        SOURCE_DIR / "MF1750_Compact.pretty",
        PROJECT_ARCHIVE / "MF1750_Compact.pretty",
    )
    shutil.copytree(
        PRODUCTION_FOOTPRINTS,
        PROJECT_ARCHIVE / "MF1750_Production.pretty",
    )
    (PROJECT_ARCHIVE / "fp-lib-table").write_text(
        "(fp_lib_table\n"
        '\t(lib (name "MF1750_Compact") (type "KiCad") '
        '(uri "${KIPRJMOD}/MF1750_Compact.pretty") (options "") '
        '(descr "Compact carrier local footprints"))\n'
        '\t(lib (name "MF1750_Production") (type "KiCad") '
        '(uri "${KIPRJMOD}/MF1750_Production.pretty") (options "") '
        '(descr "Bundled verified MF1750 FPC and inductor footprints"))\n'
        ")\n",
        encoding="utf-8",
    )
    archive_schematic = PROJECT_ARCHIVE / SCHEMATIC.name
    archive_board = PROJECT_ARCHIVE / BOARD.name
    archive_erc = PROJECT_ARCHIVE / "source_archive_erc.rpt"
    archive_drc = PROJECT_ARCHIVE / "source_archive_drc.rpt"
    run_cli(
        "sch",
        "erc",
        "--severity-all",
        "--exit-code-violations",
        "-o",
        str(archive_erc),
        str(archive_schematic),
    )
    run_cli(
        "pcb",
        "drc",
        "--severity-all",
        "--schematic-parity",
        "--exit-code-violations",
        "-o",
        str(archive_drc),
        str(archive_board),
    )
    if "0  Errors 0  Warnings" not in archive_erc.read_text(encoding="utf-8"):
        raise SystemExit("Self-contained source archive ERC is not clean")
    archive_drc_text = archive_drc.read_text(encoding="utf-8")
    for contract in (
        "** Found 0 DRC violations **",
        "** Found 0 unconnected pads **",
        "** Found 0 Footprint errors **",
    ):
        if contract not in archive_drc_text:
            raise SystemExit(f"Self-contained source archive DRC failed: {contract}")
    zip_directory(PROJECT_ARCHIVE, PROJECT_ZIP)


def write_manifest(gerber_audit: dict[str, object], refs: set[str]) -> None:
    paths = [path for path in OUTPUT.rglob("*") if path.is_file()]
    paths = [
        path
        for path in paths
        if path.name not in {"MANIFEST.json", "SHA256SUMS.txt"} and path != SUPPORT_ZIP
    ]
    files = {
        path.relative_to(OUTPUT).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(paths)
    }
    manifest = {
        "schema": 1,
        "project": PROJECT,
        "revision": "B1-4L-JLCPCB-ENGINEERING-FIRST-ARTICLE",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "pcb_sha256": sha256(BOARD),
            "schematic_sha256": sha256(SCHEMATIC),
            "reference_bom_sha256": sha256(SOURCE_BOM),
        },
        "checks": {
            "erc_errors": 0,
            "erc_warnings": 0,
            "drc_violations": 0,
            "unconnected_pads": 0,
            "schematic_parity_errors": 0,
            "gerber_files": len(EXPECTED_GERBERS),
            "fit_smt_refs": len(refs),
            "unique_lcsc_parts": UNIQUE_LCSC_COUNT,
            "bom_cpl_reference_sets_identical": True,
            "r16_fit_r15_dnp": True,
        },
        "fabrication": {
            "board_mm": [62.0, 58.0],
            "layers": 4,
            "stackup": JLC_STACKUP,
            "finished_thickness_mm": 1.6,
            "outer_copper_oz": 1.0,
            "inner_copper_oz": 0.5,
            "controlled_impedance": False,
            "surface_finish": "ENIG_1U",
            "gerber_audit": gerber_audit,
        },
        "hard_holds": [
            "J1/C6/C15 body-to-functional-edge distances are about 1.47/1.25/2.25 mm, below JLCPCB's general 2.5 mm PCBA term; explicit JLCPCB PCBA engineering acceptance of the exact panel and placement is mandatory.",
            "Online bare-board Gerber/DFM preview alone does not release the known edge-distance deviation.",
            "JLC upload preview must confirm J1, D1-D4, Q1/Q2 orientation and R16 FIT/R15 DNP.",
            "J2 socket remains manual until 0.80 mm finished-hole and N16R8 Z-envelope fit are measured.",
            "LCSC stock and exact part matching must be reconfirmed at order time.",
        ],
        "files": files,
    }
    manifest_path = OUTPUT / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    sums = []
    for path in sorted([*paths, manifest_path]):
        sums.append(f"{sha256(path)}  {path.relative_to(OUTPUT).as_posix()}")
    (OUTPUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")

    zip_directory(
        OUTPUT,
        SUPPORT_ZIP,
        exclude={GERBER_ZIP, SMT_BOM, SMT_CPL, SUPPORT_ZIP},
    )
    key_paths = (GERBER_ZIP, SMT_BOM, SMT_CPL, SUPPORT_ZIP, PROJECT_ZIP)
    (OUTPUT / "PACKAGE_HASHES.txt").write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(OUTPUT).as_posix()}\n"
            for path in key_paths
        ),
        encoding="ascii",
    )


def verify_final_archives(refs: set[str]) -> None:
    with zipfile.ZipFile(GERBER_ZIP) as handle:
        names = set(handle.namelist())
        if names != set(EXPECTED_GERBERS):
            raise SystemExit("Gerber upload ZIP content drift")
        if any(
            "gbrjob" in name.lower() or name.lower().endswith(".gbp") for name in names
        ):
            raise SystemExit(
                "Gerber upload ZIP contains forbidden metadata/empty paste"
            )
        if any("/" in name or "\\" in name for name in names):
            raise SystemExit("Gerber upload ZIP must have a flat root")
    with SMT_BOM.open(newline="", encoding="utf-8-sig") as handle:
        bom_rows = list(csv.DictReader(handle))
    with SMT_CPL.open(newline="", encoding="utf-8-sig") as handle:
        cpl_rows = list(csv.DictReader(handle))
    if len(bom_rows) != UNIQUE_LCSC_COUNT or len(cpl_rows) != FIT_SMT_COUNT:
        raise SystemExit("Final BOM/CPL row count drift")
    bom_refs = {ref for row in bom_rows for ref in row["Designator"].split(",")}
    cpl_refs = {row["Designator"] for row in cpl_rows}
    if bom_refs != cpl_refs or bom_refs != refs:
        raise SystemExit("Final BOM/CPL reference set mismatch")
    if "R15" in refs or "R16" not in refs:
        raise SystemExit("Final population drift")


def main() -> None:
    if not KICAD_CLI.exists() or not KICAD_PYTHON.exists():
        raise SystemExit("KiCad 10.0 CLI/Python is required")
    if list(SOURCE_DIR.glob("~*.lck")):
        raise SystemExit("Close KiCad before exporting")
    clean_output()
    for directory in (UPLOAD, SUPPORT, GERBER, PROJECT_ARCHIVE):
        directory.mkdir(parents=True, exist_ok=True)

    # Re-run the authoritative verifier before deriving any manufacturing data.
    subprocess.run(
        [
            str(KICAD_PYTHON),
            str(HARDWARE / "verify_mf1750_devkitc_b1_single_power_layer.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    with tempfile.TemporaryDirectory(prefix="mf1750_b1_jlcpcb_") as temp_name:
        variant = make_fabrication_variant(Path(temp_name))
        run_cli(
            "pcb",
            "export",
            "gerbers",
            "-o",
            str(GERBER),
            "-l",
            ",".join(GERBER_LAYERS),
            "--subtract-soldermask",
            str(variant),
        )
        run_cli(
            "pcb",
            "export",
            "drill",
            "-o",
            str(GERBER),
            "--format",
            "excellon",
            "--drill-origin",
            "absolute",
            "--excellon-zeros-format",
            "decimal",
            "--excellon-oval-format",
            "route",
            "--excellon-units",
            "mm",
            "--excellon-separate-th",
            str(variant),
        )
        # KiCad may create a job file despite board plot options on some builds;
        # it is excluded because the canonical board has no fabricator-qualified
        # dielectric stackup and JLC04161H-7628 is specified separately.
        for stale in GERBER.glob("*.gbrjob"):
            stale.unlink()
        for empty_bottom_paste in GERBER.glob("*.gbp"):
            empty_bottom_paste.unlink()
        gerber_audit = verify_gerbers()
        with zipfile.ZipFile(
            GERBER_ZIP, "w", compression=zipfile.ZIP_DEFLATED
        ) as handle:
            for path in sorted(GERBER.iterdir()):
                handle.write(path, path.name)

        canonical_board = pcbnew.LoadBoard(str(BOARD))
        refs, _ = make_smt_bom_and_cpl(canonical_board)
        make_manual_and_dnp_files(canonical_board)
        export_support_files(variant)
        make_docs(canonical_board, gerber_audit)

    make_project_archive()
    write_manifest(gerber_audit, refs)
    verify_final_archives(refs)
    print(
        json.dumps(
            {
                "status": "PASS_ENGINEERING_FIRST_ARTICLE_PACKAGE",
                "gerber_zip": str(GERBER_ZIP),
                "smt_bom": str(SMT_BOM),
                "smt_cpl": str(SMT_CPL),
                "support_zip": str(SUPPORT_ZIP),
                "pcb_sha256": sha256(BOARD),
                "gerber_zip_sha256": sha256(GERBER_ZIP),
                "smt_refs": len(refs),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
