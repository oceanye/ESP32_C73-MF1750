"""Export and verify the complete JLCPCB package for MF1750 Rev B2.

The verified B2 PCB/SCH remain immutable inputs.  A temporary fabrication
variant removes paste apertures from DNP footprints before plotting, so R15 is
absent from the stencil while R16 remains fitted.  The script emits distinct
JLCPCB upload files plus engineering support evidence and fails closed on any
board, drill, paste, BOM, CPL, or hash-contract drift.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
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
SOURCE_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
PROJECT = "mf1750_devkitc_b2_pcba_margin"
BOARD = SOURCE_DIR / f"{PROJECT}.kicad_pcb"
SCHEMATIC = SOURCE_DIR / f"{PROJECT}.kicad_sch"
SOURCE_BOM = HARDWARE / "mf1750_devkitc_compact" / "bom_reference.csv"
OUTPUT = HARDWARE / "mf1750_devkitc_b2_jlcpcb"
UPLOAD = OUTPUT / "upload"
SUPPORT = OUTPUT / "support"
GERBER = OUTPUT / "gerber_files"
PROJECT_ARCHIVE = OUTPUT / "project_source"
PRODUCTION_FOOTPRINTS = SOURCE_DIR / "MF1750_Production.pretty"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
KICAD_PYTHON = Path(r"C:\Program Files\KiCad\10.0\bin\python.exe")

GERBER_ZIP = UPLOAD / "JLCPCB_PCB_MF1750_DEVKITC_B2_4L.zip"
SMT_BOM = UPLOAD / "JLCPCB_BOM_MF1750_DEVKITC_B2_SMT.csv"
SMT_CPL = UPLOAD / "JLCPCB_CPL_MF1750_DEVKITC_B2_SMT.csv"
SUPPORT_ZIP = OUTPUT / "JLCPCB_SUPPORT_MF1750_DEVKITC_B2.zip"
PROJECT_ZIP = OUTPUT / "MF1750_DEVKITC_B2_KICAD_SOURCE.zip"
PACKAGE_CONFIG = OUTPUT / "package_audit_config.json"
PACKAGE_AUDIT = HARDWARE / "mf1750_devkitc_b2_jlcpcb_package_audit.json"
SKILL_DIR = ROOT / ".codex" / "skills" / "jlcpcb-kicad-handoff"
PACKAGE_AUDITOR = SKILL_DIR / "scripts" / "audit_jlcpcb_package.py"
PROJECT_VERIFIER = HARDWARE / "verify_mf1750_devkitc_b2_pcba_margin.py"

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
BOARD_SIZE_MM = [65.0, 60.5]
FROZEN_SOURCE_SHA256 = {
    BOARD.name: "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238",
    SCHEMATIC.name: "bc3116580b1e055db15e383569ad60db626e65aac225917c62b3a72120e703eb",
    f"{PROJECT}.kicad_pro": "fcd393069f22846615113f8296d6553c5ffeee8ba507b7475f81baae9fe4aa27",
}

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


def require_frozen_source() -> None:
    for name, expected in FROZEN_SOURCE_SHA256.items():
        path = SOURCE_DIR / name
        actual = sha256(path)
        if actual != expected:
            raise SystemExit(f"Frozen B2 source drift: {path} -> {actual}")


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
    variant = temp_dir / f"{PROJECT}.kicad_pcb"
    report = SUPPORT / "variant-provenance.json"
    subprocess.run(
        [
            str(KICAD_PYTHON),
            str(SKILL_DIR / "scripts" / "prepare_dnp_paste_variant.py"),
            "--input",
            str(BOARD),
            "--output",
            str(variant),
            "--expect-dnp",
            "R15",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        check=True,
    )
    evidence = json.loads(report.read_text(encoding="utf-8"))
    removed = evidence.get("removed_paste_apertures", [])
    if evidence.get("status") != "PASS" or [
        (item.get("reference"), item.get("pad")) for item in removed
    ] != [("R15", "1"), ("R15", "2")]:
        raise SystemExit(f"DNP variant helper contract failed: {evidence}")
    board = pcbnew.LoadBoard(str(variant))
    if board is None or board.FindFootprintByReference("R16").IsDNP():
        raise SystemExit("Temporary variant lost fitted R16")
    plot = board.GetPlotOptions()
    plot.SetCreateGerberJobFile(False)
    plot.SetUseGerberProtelExtensions(True)
    plot.SetUseGerberX2format(True)
    plot.SetGerberPrecision(6)
    board.SetPlotOptions(plot)
    pcbnew.SaveBoard(str(variant), board)
    evidence["export_variant_sha256"] = sha256(variant)
    evidence["canonical_board_sha256_after_variant"] = sha256(BOARD)
    evidence["plot_options"] = {
        "gerber_job_file": False,
        "protel_extensions": True,
        "gerber_x2": True,
        "precision": 6,
    }
    report.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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
    write_csv(SUPPORT / "MANUAL_ASSEMBLY.csv", manual_rows)

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

    population_rows = [["Designator", "Class", "Assembly side", "Rationale"]]
    fitted = fitted_smt_footprints(board)
    for ref in sorted(fitted, key=ref_key):
        population_rows.append([ref, "FIT_SMT", "Top", "JLCPCB SMT BOM/CPL"])
    population_rows.append(["R15", "DNP", "Top", "mutually exclusive with fitted R16"])
    for ref in sorted(MANUAL_REFS, key=ref_key):
        population_rows.append([ref, "MANUAL", "THT", "excluded from SMT BOM/CPL"])
    for ref in sorted(NON_ASSEMBLY_REFS, key=ref_key):
        population_rows.append([ref, "NON_ASSEMBLY", "N/A", "mechanical/test point"])
    write_csv(SUPPORT / "POPULATION_CONTRACT.csv", population_rows)


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
        "board_outline_mm": BOARD_SIZE_MM,
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
        f"""# MF1750 DevKitC Rev B2 — 嘉立创下单与 SMT 交付说明

## 三个上传文件

1. PCB/Gerber 栏只上传 `upload/{GERBER_ZIP.name}`。
2. BOM 栏只上传 `upload/{SMT_BOM.name}`。
3. CPL/坐标栏只上传 `upload/{SMT_CPL.name}`。

`{SUPPORT_ZIP.name}`、`support/` 与 `{PROJECT_ZIP.name}` 是审计/装配支持资料，
不要上传到上述三个自动解析栏。

## PCB 下单参数

- 单板 `65 x 60.5 mm`，FR-4，4 层，成品厚度 1.6 mm。
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
  不要缩放或改写 65 x 60.5 mm 功能板框。
- **功能边距短板已经移除：**板级审计按每个 FIT SMT 的 F.Fab 本体测量，
  到成品功能 Edge.Cuts 的最小距离为 3.55 mm（C0 左侧），高于 2.5 mm
  本地基线；Courtyard 最小值 2.995 mm。即使作分析用途的 0.4 mm 向内
  工艺余量，本体仍为 3.15 mm、Courtyard 为 2.595 mm。因此没有需要
  厂家特批的器件本体边距偏离，外部工程边距例外状态为 NOT_APPLICABLE。
- 这不替代首板机械核对：J1/FPC 出线与分板、J3 侧向插接、J2 孔径和
  Z 包络、DevKitC 天线与新增 FR4/keepout、机壳/安装仍为实物 hold。

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

这是本地证据已通过、可进入上传审核的工程首板加工包，不是已经完成厂家或实物
资格认证的量产放行。在线 Gerber/CAM、BOM/CPL 解析、库存、旋转/极性仍为 PENDING。
收到板后仍需
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
    shutil.copy2(
        SUPPORT / "STACKUP_AND_FAB_NOTES.md",
        SUPPORT / "FAB_AND_STACKUP_DECISIONS.md",
    )
    (SUPPORT / "ORDER_CHECKLIST.md").write_text(
        "# Upload/order checklist\n\n"
        "- [ ] Upload only the Gerber ZIP, BOM CSV, and CPL CSV in `upload/`.\n"
        "- [ ] Confirm 65 x 60.5 mm, 4 layers, 1.6 mm, JLC04161H-7628, outer 1 oz / inner 0.5 oz.\n"
        "- [ ] Confirm ENIG 1U, green mask, white silkscreen, PTH/NPTH separation.\n"
        "- [ ] Confirm L2=GND and L3=power; do not accept an inferred Gerber-job stackup.\n"
        "- [ ] Confirm all 46 SMT refs and 16 LCSC lines; R16 FIT, R15 absent.\n"
        "- [ ] Review J1, D1-D4, Q1/Q2 orientation, pin 1, side, and rotation.\n"
        "- [ ] Recheck live stock, substitutions, CAM/DFM, paste, and production files.\n"
        "- [ ] Preserve mechanical first-article holds for J1/FPC, J3, J2, antenna, and enclosure.\n",
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
    shutil.copy2(SOURCE_DIR / "board_audit.json", SUPPORT / "board-audit.json")
    shutil.copy2(
        SOURCE_DIR / "board_audit_config.json", SUPPORT / "board-audit-config.json"
    )
    shutil.copy2(
        SOURCE_DIR / "derivation_audit.json", SUPPORT / "derivation-audit.json"
    )
    shutil.copy2(
        SOURCE_DIR / "verification_manifest.json",
        SUPPORT / "PRE_EXPORT_SOURCE_VERIFICATION.json",
    )
    (SUPPORT / "PRE_EXPORT_SOURCE_AUDIT_NOTE.md").write_text(
        "# Pre-export source audit\n\n"
        "`PRE_EXPORT_SOURCE_VERIFICATION.json` binds the exact verified B2 canonical "
        "source used by this export.  Its local evidence gate is PASS, while live "
        "portal/CAM/stock/placement review remains PENDING.  The functional-edge "
        "shortfall is removed; the listed J1/J3/J2/antenna/enclosure physical holds "
        "remain first-article checks.\n",
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
        SOURCE_DIR / "fp-lib-table",
        SOURCE_DIR / "mf1750_local.kicad_sym",
        SOURCE_DIR / "README.md",
        SOURCE_DIR / "board_audit_config.json",
        SOURCE_DIR / "derivation_audit.json",
        HARDWARE / "build_mf1750_devkitc_b2_pcba_margin.py",
        PROJECT_VERIFIER,
        Path(__file__),
        HARDWARE / "export_mf1750_devkitc_b2_jlcpcb.py",
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
    release_tools = PROJECT_ARCHIVE / "release_tools"
    release_tools.mkdir()
    for path in (
        SKILL_DIR / "scripts" / "audit_kicad_jlcpcb.py",
        SKILL_DIR / "scripts" / "prepare_dnp_paste_variant.py",
        SKILL_DIR / "scripts" / "generate_jlcpcb_bom_cpl.py",
        SKILL_DIR / "scripts" / "audit_jlcpcb_package.py",
    ):
        shutil.copy2(path, release_tools / path.name)
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
    for transient in PROJECT_ARCHIVE.glob("*.kicad_prl"):
        transient.unlink()
    if any(
        path.name.startswith("~")
        or path.suffix.casefold() in {".kicad_prl", ".bak", ".tmp"}
        for path in PROJECT_ARCHIVE.rglob("*")
        if path.is_file()
    ):
        raise SystemExit("Source archive staging contains GUI or temporary state")
    zip_directory(PROJECT_ARCHIVE, PROJECT_ZIP)


def verify_fresh_source_zip() -> None:
    with tempfile.TemporaryDirectory(prefix="mf1750_b2_source_extract_") as temp_name:
        extracted = Path(temp_name) / "source"
        extracted.mkdir()
        with zipfile.ZipFile(PROJECT_ZIP) as handle:
            names = handle.namelist()
            if any(
                Path(name).is_absolute() or ".." in Path(name).parts for name in names
            ):
                raise SystemExit("Unsafe path in source ZIP")
            if any(
                Path(name).name.startswith("~")
                or Path(name).suffix.casefold() in {".kicad_prl", ".bak", ".tmp"}
                for name in names
            ):
                raise SystemExit("Source ZIP contains GUI or temporary state")
            handle.extractall(extracted)
        erc = Path(temp_name) / "fresh_extract_erc.rpt"
        drc = Path(temp_name) / "fresh_extract_drc.rpt"
        board_audit = Path(temp_name) / "fresh_extract_board_audit.json"
        run_cli(
            "sch",
            "erc",
            "--severity-all",
            "--exit-code-violations",
            "-o",
            str(erc),
            str(extracted / SCHEMATIC.name),
        )
        run_cli(
            "pcb",
            "drc",
            "--severity-all",
            "--schematic-parity",
            "--exit-code-violations",
            "-o",
            str(drc),
            str(extracted / BOARD.name),
        )
        audit_completed = subprocess.run(
            [
                str(KICAD_PYTHON),
                str(extracted / "release_tools" / "audit_kicad_jlcpcb.py"),
                str(extracted / BOARD.name),
                str(extracted / "board_audit_config.json"),
                str(board_audit),
            ],
            cwd=extracted,
            text=True,
            capture_output=True,
            check=False,
        )
        if audit_completed.returncode != 0:
            raise SystemExit(
                "Fresh-extracted bundled board audit failed: "
                f"{audit_completed.stdout}{audit_completed.stderr}"
            )
        board_audit_result = json.loads(board_audit.read_text(encoding="utf-8"))
        if board_audit_result.get("status") != "PASS":
            raise SystemExit("Fresh-extracted bundled board audit did not PASS")
        erc_text = erc.read_text(encoding="utf-8")
        drc_text = drc.read_text(encoding="utf-8")
        if "0  Errors 0  Warnings" not in erc_text:
            raise SystemExit("Fresh-extracted source ZIP ERC is not clean")
        for contract in (
            "** Found 0 DRC violations **",
            "** Found 0 unconnected pads **",
            "** Found 0 Footprint errors **",
        ):
            if contract not in drc_text:
                raise SystemExit(f"Fresh-extracted source ZIP DRC failed: {contract}")
        result = {
            "schema": 1,
            "status": "PASS",
            "source_zip": PROJECT_ZIP.relative_to(OUTPUT).as_posix(),
            "source_zip_sha256": sha256(PROJECT_ZIP),
            "members": len(names),
            "erc_errors": 0,
            "erc_warnings": 0,
            "drc_violations": 0,
            "unconnected_pads": 0,
            "schematic_parity_errors": 0,
            "bundled_board_audit": "PASS",
            "body_to_functional_edge_minimum_mm": board_audit_result["checks"][
                "body_edge"
            ]["observed_minimum_clearance_mm"],
            "canonical_pcb_sha256": sha256(extracted / BOARD.name),
            "canonical_schematic_sha256": sha256(extracted / SCHEMATIC.name),
        }
        (SUPPORT / "SOURCE_ZIP_EXTRACTION_VERIFICATION.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


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
        "revision": "B2-4L-PCBA-EDGE-JLCPCB-ENGINEERING-FIRST-ARTICLE",
        "release_class": "ENGINEERING_FIRST_ARTICLE_READY_FOR_UPLOAD_REVIEW",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tool_versions": {
            "kicad_cli": pcbnew.Version(),
            "kicad_python": platform.python_version(),
            "pcbnew": pcbnew.Version(),
            "exporter_schema": 1,
        },
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
            "board_mm": BOARD_SIZE_MM,
            "layers": 4,
            "stackup": JLC_STACKUP,
            "finished_thickness_mm": 1.6,
            "outer_copper_oz": 1.0,
            "inner_copper_oz": 0.5,
            "controlled_impedance": False,
            "surface_finish": "ENIG_1U",
            "gerber_audit": gerber_audit,
        },
        "population": {
            "fit_smt_count": 46,
            "dnp_count": 1,
            "manual_count": 2,
            "nonassembly_count": 12,
            "evidence": "support/POPULATION_CONTRACT.csv",
        },
        "margins_mm": {
            "body_to_functional_edge_minimum": 3.55,
            "body_minimum_location": {"reference": "C0", "side": "left"},
            "courtyard_to_functional_edge_minimum": 2.995,
            "local_baseline": 2.5,
            "functional_edge_shortfall": False,
            "evidence": "support/board-audit.json",
        },
        "gates": {
            "local_evidence": {
                "status": "PASS",
                "evidence": [
                    "support/ERC_zero.rpt",
                    "support/DRC_zero.rpt",
                    "support/board-audit.json",
                    "support/variant-provenance.json",
                    "support/POPULATION_CONTRACT.csv",
                    "support/SOURCE_ZIP_EXTRACTION_VERIFICATION.json",
                ],
            },
            "online_recheck": {
                "status": "PENDING",
                "holds": [
                    "portal Gerber/CAM interpretation",
                    "live LCSC stock and package matching",
                    "placement side/rotation/polarity preview",
                ],
            },
            "external_engineering": {
                "status": "NOT_APPLICABLE",
                "rationale": "All fitted SMT F.Fab bodies are at least 3.55 mm from finished functional Edge.Cuts, so there is no sub-2.5 mm body-margin deviation requiring an exception.",
            },
        },
        "hard_holds": [
            "Online portal Gerber/CAM, stock, BOM/CPL parsing, side, rotation, pin-1 and polarity review remains PENDING.",
            "JLC upload preview must confirm J1, D1-D4, Q1/Q2 orientation and R16 FIT/R15 DNP.",
            "J1/FPC cable exit and connector-edge/depanelization mechanics require physical first-article review.",
            "J3 side-entry connector and cable clearance require physical first-article review.",
            "J2 socket remains manual until 0.80 mm finished-hole and N16R8 Z-envelope fit are measured.",
            "DevKitC antenna performance with the enlarged FR4 and four-layer keepout requires physical RF review.",
            "Enclosure, mounting, and full physical first-article fit remain unverified.",
            "LCSC stock and exact part matching must be reconfirmed at order time.",
        ],
        "manifest_exclusions": {
            "MANIFEST.json": "self",
            "SHA256SUMS.txt": "checksum list",
            "PACKAGE_HASHES.txt": "operator index generated after immutable artifact hashes",
            SUPPORT_ZIP.name: "support archive contains MANIFEST/SHA evidence and is bound by PACKAGE_HASHES.txt to avoid circular hashing",
        },
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


def write_package_audit_config() -> None:
    escaped = re.escape(PROJECT)
    required_suffixes = [
        "-F_Cu[.]gtl",
        "-In1_Cu[.]g1",
        "-In2_Cu[.]g2",
        "-B_Cu[.]gbl",
        "-F_Mask[.]gts",
        "-B_Mask[.]gbs",
        "-F_Paste[.]gtp",
        "-Top Silkscreen[.]gto",
        "-Bottom Silkscreen[.]gbo",
        "-Edge_Cuts[.]gm1",
        "-PTH[.]drl",
        "-NPTH[.]drl",
    ]
    config = {
        "upload_dir": "upload",
        "gerber_zip": GERBER_ZIP.relative_to(OUTPUT).as_posix(),
        "bom_csv": SMT_BOM.relative_to(OUTPUT).as_posix(),
        "cpl_csv": SMT_CPL.relative_to(OUTPUT).as_posix(),
        "manifest": "MANIFEST.json",
        "sha256sums": "SHA256SUMS.txt",
        "package_hashes": "PACKAGE_HASHES.txt",
        "bom_headers": ["Comment", "Designator", "Footprint", "LCSC Part #"],
        "cpl_headers": ["Designator", "Mid X", "Mid Y", "Rotation", "Layer"],
        "designator_header": "Designator",
        "comment_header": "Comment",
        "footprint_header": "Footprint",
        "lcsc_header": "LCSC Part #",
        "lcsc_pattern": "C[1-9][0-9]*",
        "designator_pattern": "[A-Za-z][A-Za-z0-9_]*[0-9][A-Za-z0-9_]*",
        "cpl_x_header": "Mid X",
        "cpl_y_header": "Mid Y",
        "cpl_rotation_header": "Rotation",
        "cpl_side_header": "Layer",
        "allowed_cpl_sides": ["Top"],
        "gerber_required_patterns": [
            f"^{escaped}{suffix}$" for suffix in required_suffixes
        ],
        "allow_extra_csv_columns": False,
        "audit_all_zip_files": True,
        "require_all_zips_in_package_hashes": True,
        "require_manifest_in_sha256sums": True,
        "require_manifest_files_in_sha256sums": True,
    }
    PACKAGE_CONFIG.write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_package_audit() -> dict[str, object]:
    completed = subprocess.run(
        [
            "python",
            str(PACKAGE_AUDITOR),
            str(OUTPUT),
            "--config",
            str(PACKAGE_CONFIG),
            "--pretty",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    PACKAGE_AUDIT.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise SystemExit(
            f"Skill package audit failed (exit {completed.returncode}): "
            f"{completed.stdout}{completed.stderr}"
        )
    result = json.loads(completed.stdout)
    if result.get("status") != "PASS":
        raise SystemExit(f"Skill package audit did not PASS: {result}")
    return result


def main() -> None:
    if not KICAD_CLI.exists() or not KICAD_PYTHON.exists():
        raise SystemExit("KiCad 10.0 CLI/Python is required")
    if list(SOURCE_DIR.glob("~*.lck")):
        raise SystemExit("Close KiCad before exporting")
    require_frozen_source()
    clean_output()
    for directory in (UPLOAD, SUPPORT, GERBER, PROJECT_ARCHIVE):
        directory.mkdir(parents=True, exist_ok=True)

    # Re-run the authoritative verifier before deriving any manufacturing data.
    subprocess.run(
        [
            str(KICAD_PYTHON),
            str(PROJECT_VERIFIER),
        ],
        cwd=ROOT,
        check=True,
    )

    require_frozen_source()
    with tempfile.TemporaryDirectory(prefix="mf1750_b2_jlcpcb_") as temp_name:
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
    verify_fresh_source_zip()
    write_package_audit_config()
    require_frozen_source()
    write_manifest(gerber_audit, refs)
    verify_final_archives(refs)
    package_audit = run_package_audit()
    require_frozen_source()
    print(
        json.dumps(
            {
                "status": "PASS_ENGINEERING_FIRST_ARTICLE_READY_FOR_UPLOAD_REVIEW",
                "gerber_zip": str(GERBER_ZIP),
                "smt_bom": str(SMT_BOM),
                "smt_cpl": str(SMT_CPL),
                "support_zip": str(SUPPORT_ZIP),
                "pcb_sha256": sha256(BOARD),
                "gerber_zip_sha256": sha256(GERBER_ZIP),
                "smt_refs": len(refs),
                "unique_lcsc": UNIQUE_LCSC_COUNT,
                "body_edge_minimum_mm": 3.55,
                "online_gate": "PENDING",
                "external_margin_exception": "NOT_APPLICABLE",
                "package_audit": package_audit.get("status"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
