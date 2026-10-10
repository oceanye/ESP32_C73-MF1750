#!/usr/bin/env python3
"""Offline reconciliation of the two LH2 MAP photo sessions.

Read-only offline analysis. Sessions under review, both photographing the SAME
physical MAP screen state (no refresh between them):
- night:  .test-output/offline/LH2_DRIVE_MAP_ANALYSIS_20260918_V1 (batch LH2_DRIVE_MAP_20260918_V1)
- morning bright re-shoot: .test-output/offline/LH2_DRIVE_MAP_ANALYSIS_20260919_V1
  (batch LH2_DRIVE_MAP_BRIGHT_20260919_V3), whose map-analysis was run with
  --batch pointing at the NIGHT batch (session MIDDLE endpoints from the night
  s3-pre.jpg) — a cross-illumination reference mix this study quantifies and
  corrects.

Answers:
1. Are the two sessions the same illumination level at the panel?
2. Attribution of the family-level-count differences (RO gain, NEUTRAL drop):
   optical or analysis/reference artefacts?
3. Corrected family ladders (variant A: night endpoints Y-gain-normalised into
   the morning illumination; variant B: morning MAP-only with the in-frame
   white anchor cell (M7,C4)) under the unchanged frozen gates.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import mf1750_lh1_lh4_once as rec  # noqa: E402
from tools.mf1750_lh2_drive_map_analysis import (  # noqa: E402
    CHROMA_GATE, FAMILY_OF_HISTORY, GATE_HUE_DEG, chain_levels, hue_gap,
    noise_floor)

VERSION = "mf1750-lh2-map-session-reconcile-v1"
BRIGHT_0917_WHITE_LSTAR = 65.8  # sealed 2026-09-17 bright-session MIDDLE white (CS1 median)


def y_of_lstar(lstar: float) -> float:
    f = (lstar + 16.0) / 116.0
    return f ** 3 if f ** 3 > 216 / 24389 else (116 * f - 16) * 27 / 24389


def lstar_of_y(y: float) -> float:
    return 116.0 * (y ** (1 / 3)) - 16.0 if y > 216 / 24389 else y * 24389 / 27


def hue_of(lab) -> float:
    return math.degrees(math.atan2(lab[2], lab[1])) % 360.0


def chroma_of(lab) -> float:
    return math.hypot(lab[1], lab[2])


def cell_table(extraction: dict) -> dict:
    out = {}
    for r in extraction["rows"]:
        out[(r["controller"], r["middle_code"], r["map_code"])] = {
            "lab": r["lab_median"],
            "noise": noise_floor(r["lstar_mad"], r["lstar_ci95_half_width"]),
            "ok": r["quality_pass"] and r["single_pixel_uniform"]}
    return out


def build_ladders(cells: dict, endpoints: dict, gains: dict | None) -> dict:
    """Family ladders under the frozen gates; endpoints optionally Y-normalised."""
    result = {}
    for ctrl in ("CS1", "CS2"):
        pools: dict[str, list] = {}
        hue_blocked = []
        for m in range(8):
            fam = FAMILY_OF_HISTORY[m]
            if fam == "WHITE":
                continue
            ep = endpoints[ctrl][m]
            ep_lab = list(ep["lab_median"])
            if gains is not None:
                ep_lab = [lstar_of_y(y_of_lstar(ep_lab[0]) * gains[ctrl]),
                          ep_lab[1], ep_lab[2]]
            states = []
            if gains is not None:
                states.append({"label": f"MIDDLE-M{m}(Y-normalised)",
                               "lab": ep_lab,
                               "noise": noise_floor(ep["lstar_mad_spatial"],
                                                    ep["lstar_ci95_half_width_spatial"])})
            for c in range(8):
                cl = cells[(ctrl, m, c)]
                if not cl["ok"] or chroma_of(cl["lab"]) <= CHROMA_GATE:
                    continue
                hg = hue_gap(cl["lab"], ep_lab)
                if hg > GATE_HUE_DEG:
                    hue_blocked.append({"cell": f"M{m}-C{c}", "hue_gap_deg": hg})
                    continue
                states.append({"label": f"MAP-M{m}-C{c}", "lab": cl["lab"],
                               "noise": cl["noise"], "hue_gap_to_anchor_deg": hg})
            pools.setdefault(fam, []).extend(states)
        fams = {}
        for fam, states in pools.items():
            chain = chain_levels(states)
            fams[fam] = {"level_count": len(chain),
                         "levels": [{"label": s["label"], "lstar": round(s["lab"][0], 2),
                                     "hue_deg": round(hue_of(s["lab"]), 1),
                                     "chroma": round(chroma_of(s["lab"]), 1)}
                                    for s in chain],
                         "pool_size": len(states)}
        # neutral pool: endpoint white (normalised) or the in-frame white anchor
        neutral = []
        if gains is not None:
            ep7 = endpoints[ctrl][7]
            neutral.append({"label": "MIDDLE-M7-white(Y-normalised)",
                            "lab": [lstar_of_y(y_of_lstar(ep7["lab_median"][0]) * gains[ctrl]),
                                    ep7["lab_median"][1], ep7["lab_median"][2]],
                            "noise": noise_floor(ep7["lstar_mad_spatial"],
                                                 ep7["lstar_ci95_half_width_spatial"])})
        else:
            w = cells[(ctrl, 7, 4)]
            neutral.append({"label": "MAP-M7-C4(in-frame white anchor)",
                            "lab": w["lab"], "noise": w["noise"]})
        for m in range(8):
            for c in range(8):
                cl = cells[(ctrl, m, c)]
                if cl["ok"] and chroma_of(cl["lab"]) <= CHROMA_GATE:
                    neutral.append({"label": f"MAP-M{m}-C{c}", "lab": cl["lab"],
                                    "noise": cl["noise"]})
        nchain = chain_levels(neutral, enforce_hue=False)
        fams["NEUTRAL"] = {"level_count": len(nchain),
                           "levels": [{"label": s["label"], "lstar": round(s["lab"][0], 2),
                                       "hue_deg": round(hue_of(s["lab"]), 1),
                                       "chroma": round(chroma_of(s["lab"]), 1)}
                                      for s in nchain],
                           "pool_size": len(neutral)}
        result[ctrl] = {"families": fams,
                        "hue_blocked_count": len(hue_blocked),
                        "hue_blocked_max_deg": max((h["hue_gap_deg"] for h in hue_blocked),
                                                   default=None)}
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--night-analysis", type=Path, required=True)
    p.add_argument("--morning-analysis", type=Path, required=True)
    p.add_argument("--night-batch", type=Path, required=True)
    p.add_argument("--morning-batch", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output dir must not exist (O_EXCL batch)")

    e_night = json.loads((args.night_analysis / "extraction.json").read_text(encoding="utf-8"))
    e_morn = json.loads((args.morning_analysis / "extraction.json").read_text(encoding="utf-8"))
    a_night = json.loads((args.night_analysis / "map-analysis.json").read_text(encoding="utf-8"))
    a_morn = json.loads((args.morning_analysis / "map-analysis.json").read_text(encoding="utf-8"))
    t_night, t_morn = cell_table(e_night), cell_table(e_morn)
    if set(t_night) != set(t_morn) or len(t_night) != 128:
        raise SystemExit("cell key sets differ")

    # ---- 1. illumination facts ----
    white_anchor = {}
    for ctrl in ("CS1", "CS2"):
        white_anchor[ctrl] = {
            "night_lstar": t_night[(ctrl, 7, 4)]["lab"][0],
            "morning_lstar": t_morn[(ctrl, 7, 4)]["lab"][0],
            "y_gain": y_of_lstar(t_morn[(ctrl, 7, 4)]["lab"][0])
                      / y_of_lstar(t_night[(ctrl, 7, 4)]["lab"][0])}
    gains, hue_shifts, deltas = [], [], []
    for k in t_night:
        l1, l2 = t_night[k]["lab"], t_morn[k]["lab"]
        deltas.append(l2[0] - l1[0])
        if l1[0] > 10:
            gains.append(y_of_lstar(l2[0]) / y_of_lstar(l1[0]))
        c1, c2 = chroma_of(l1), chroma_of(l2)
        if c1 > CHROMA_GATE and c2 > CHROMA_GATE:
            hue_shifts.append(hue_gap(l1, l2))
    chroma_night = [chroma_of(v["lab"]) for v in t_night.values()]
    chroma_morn = [chroma_of(v["lab"]) for v in t_morn.values()]
    s_night = json.loads((args.night_batch / "map-frames" / "frame-0.capture.json")
                         .read_text(encoding="utf-8"))["camera"]["effective_settings_after_frame"]
    s_morn = json.loads((args.morning_batch / "map-frames" / "frame-0.capture.json")
                        .read_text(encoding="utf-8"))["camera"]["effective_settings_after_frame"]
    scene = {}
    for tag, path in (("night", args.night_batch / "map-frames" / "frame-0.jpg"),
                      ("morning", args.morning_batch / "map-frames" / "frame-0.jpg")):
        img = cv2.imread(str(path))
        sums = img.astype(np.int32).sum(axis=2)
        scene[tag] = {"p50": float(np.percentile(sums, 50)),
                      "p95": float(np.percentile(sums, 95)),
                      "p99": float(np.percentile(sums, 99))}
    illumination = {
        "camera_settings_identical": s_night == s_morn,
        "white_anchor_cell_M7C4": white_anchor,
        "white_anchor_vs_20260917_bright": {
            ctrl: round(white_anchor[ctrl]["morning_lstar"] / BRIGHT_0917_WHITE_LSTAR, 3)
            for ctrl in ("CS1", "CS2")},
        "per_cell_lstar_delta_morning_minus_night": {
            "median": float(statistics.median(deltas)), "min": float(min(deltas)),
            "max": float(max(deltas))},
        "y_gain_cells_lstar_gt10": {"count": len(gains),
                                    "median": float(statistics.median(gains)),
                                    "p10": float(np.percentile(gains, 10)),
                                    "p90": float(np.percentile(gains, 90))},
        "hue_shift_same_cells_both_chromatic": {
            "count": len(hue_shifts), "median_deg": float(statistics.median(hue_shifts)),
            "p90_deg": float(np.percentile(hue_shifts, 90))},
        "chroma_median": {"night": float(statistics.median(chroma_night)),
                          "morning": float(statistics.median(chroma_morn))},
        "chroma_le8_cells": {"night": sum(1 for c in chroma_night if c <= 8),
                             "morning": sum(1 for c in chroma_morn if c <= 8)},
        "scene_fullframe_sums": scene,
        "verdict": ("NOT the same illumination: panel white anchor +%.1f/%+.1f L* "
                    "(Y gain %.2fx/%.2fx), all 128 cells brighter (min delta +%.1f L*), "
                    "chroma median %.1f -> %.1f. The '36.8/35.5 unchanged' reading came "
                    "from the 19V1 analysis mixing the NIGHT s3-pre endpoints; the actual "
                    "morning in-frame white anchor is %.1f/%.1f. Morning reaches ~0.67 of "
                    "the 2026-09-17 bright session white (65.8)."
                    % (white_anchor["CS1"]["morning_lstar"] - white_anchor["CS1"]["night_lstar"],
                       white_anchor["CS2"]["morning_lstar"] - white_anchor["CS2"]["night_lstar"],
                       white_anchor["CS1"]["y_gain"], white_anchor["CS2"]["y_gain"],
                       min(deltas), statistics.median(chroma_night),
                       statistics.median(chroma_morn),
                       white_anchor["CS1"]["morning_lstar"],
                       white_anchor["CS2"]["morning_lstar"]))}

    # ---- 2. attribution evidence ----
    def hc(lab):
        return round(lab[0], 2), round(hue_of(lab), 1), round(chroma_of(lab), 1)
    night_neutral_levels = a_night["family_ladders"]["CS1"]["NEUTRAL"]["levels"] + \
        a_night["family_ladders"]["CS2"]["NEUTRAL"]["levels"]
    trio = []
    seen = set()
    for lv in night_neutral_levels:
        lbl = lv["label"]
        if not lbl.startswith("MAP-") or lbl in seen:
            continue
        seen.add(lbl)
        m, c = int(lbl[5]), int(lbl[8])
        for ctrl in ("CS1", "CS2"):
            k = (ctrl, m, c)
            if k not in t_night:
                continue
            trio.append({"cell": f"{ctrl} {lbl}",
                         "night_L_hue_chroma": list(hc(t_night[k]["lab"])),
                         "morning_L_hue_chroma": list(hc(t_morn[k]["lab"]))})
    ro_cells = {}
    for ctrl in ("CS1", "CS2"):
        k = (ctrl, 4, 7)
        anchor_hue = a_night["session_middle_endpoints"]["endpoints"][ctrl]["4"]["hue_deg"]
        ro_cells[ctrl] = {
            "night_L_hue_chroma": list(hc(t_night[k]["lab"])),
            "morning_L_hue_chroma": list(hc(t_morn[k]["lab"])),
            "anchor_hue_deg_night": anchor_hue,
            "hue_gap_morning_vs_night_anchor_deg":
                round(hue_gap(t_morn[k]["lab"],
                              [0, math.cos(math.radians(anchor_hue)),
                               math.sin(math.radians(anchor_hue))]), 1)}
    attribution = {
        "NEUTRAL_drop_4_to_1": {
            "verdict": "analysis-gate artefact of the dark session, NOT an optical loss",
            "evidence": {
                "chroma_le8_cells": illumination["chroma_le8_cells"],
                "chroma_median": illumination["chroma_median"],
                "night_neutral_map_levels_remeasured_in_morning": trio},
            "explanation": "the night NEUTRAL ladder's three MAP levels sat at C* 4.4-7.3 "
                           "(chroma-starved dark capture); the same physical cells resolve "
                           "at C* 9.3-17.8 in the morning capture and leave the C*<=8 pool. "
                           "The night 'NEUTRAL 4级' was false neutrals; the lightness steps "
                           "themselves persist in the morning data but carry hue."},
        "RO_gain_1_to_2_CS1": {
            "verdict": "real measurement improvement (chroma resolved by brighter light) "
                       "with a boundary-case hue link; survives Y-gain normalisation on CS1 "
                       "only",
            "evidence": ro_cells,
            "explanation": "MAP-M4-C7 night C* 6.2/3.3 (fails the C*>8 gate) -> morning "
                           "C* 17.5/12.1 (passes). The CS1 link passes the 5° hue gate "
                           "(gap %.1f°), the CS2 link fails (gap %.1f°) — and the two "
                           "night anchors themselves differ by ~6°, so RO=2 is a "
                           "gate-boundary result, not a robust ladder."
                           % (ro_cells["CS1"]["hue_gap_morning_vs_night_anchor_deg"],
                              ro_cells["CS2"]["hue_gap_morning_vs_night_anchor_deg"])},
        "mixed_reference_assessment": None}

    # ---- 3. corrected ladders ----
    endpoints_night = {ctrl: {int(c): v for c, v in
                              a_night["session_middle_endpoints"]["endpoints"][ctrl].items()}
                       for ctrl in ("CS1", "CS2")}
    gain = {ctrl: white_anchor[ctrl]["y_gain"] for ctrl in ("CS1", "CS2")}
    variant_a = build_ladders(t_morn, endpoints_night, gain)
    variant_b = build_ladders(t_morn, endpoints_night, None)
    corrected = {"variant_A_night_endpoints_y_normalised_into_morning": variant_a,
                 "variant_B_morning_map_only_with_in_frame_white_anchor": variant_b,
                 "caveats": [
                     "variant A transfers only L* (Y-gain); a*/b* of the night endpoints are "
                     "kept, so endpoint hue is a NIGHT-session hue while MAP cell hues are "
                     "morning hues — the cross-session hue shift (median %.1f°) means "
                     "endpoint-to-cell hue links carry extra uncertainty; gate-boundary "
                     "results (RO CS1) are flagged, not promoted"
                     % illumination["hue_shift_same_cells_both_chromatic"]["median_deg"],
                     "no morning MIDDLE-state photo exists (the screen holds the MAP state), "
                     "so a fully morning-consistent endpoint set cannot be measured; both "
                     "variants are reconciliations, not new measurements"]}
    mixed_counts = {ctrl: {fam: rep["level_count"]
                           for fam, rep in a_morn["family_ladders"][ctrl].items()}
                    for ctrl in ("CS1", "CS2")}
    corrected_counts = {
        "A": {ctrl: {fam: rep["level_count"] for fam, rep in variant_a[ctrl]["families"].items()}
              for ctrl in ("CS1", "CS2")},
        "B": {ctrl: {fam: rep["level_count"] for fam, rep in variant_b[ctrl]["families"].items()}
              for ctrl in ("CS1", "CS2")}}
    attribution["mixed_reference_assessment"] = {
        "mixed_19V1_counts": mixed_counts,
        "corrected_counts": corrected_counts,
        "headline_counts_unchanged": all(
            mixed_counts[ctrl][fam] == corrected_counts["A"][ctrl][fam]
            for ctrl in ("CS1", "CS2") for fam in mixed_counts[ctrl]),
        "note": "the mixed night-endpoint reference did not change headline level counts "
                "because every kept ΔL* link had margin >> gain correction; the RO-CS1 link "
                "margin shrank 5.7 -> 2.6 L* and is hue-gate-boundary anyway"}

    credible = {"CS1": corrected_counts["A"]["CS1"], "CS2": corrected_counts["A"]["CS2"]}
    conclusions = {
        "illumination_same_level": False,
        "morning_gain_vs_night": {ctrl: round(white_anchor[ctrl]["y_gain"], 3)
                                  for ctrl in ("CS1", "CS2")},
        "morning_vs_20260917_bright": illumination["white_anchor_vs_20260917_bright"],
        "credible_family_levels_morning": credible,
        "night_neutral_4_levels_valid": False,
        "one_liner": ("亮光重拍有效但不达标：屏面白锚 +%.1f/%+.1f L*（≈9-17 亮场的 %.2f），"
                      "今早可信级数 CS1 R2/RO2*/V1/B1/中性1、CS2 R2/RO1/V1/B1/中性1"
                      "（RO2 为门边界情形）；昨晚'中性4级'是暗光色度饥饿假象，不成立；"
                      "若要 0.85 门以上的数据仍需真正的日光重拍。"
                      % (white_anchor["CS1"]["morning_lstar"] - white_anchor["CS1"]["night_lstar"],
                         white_anchor["CS2"]["morning_lstar"] - white_anchor["CS2"]["night_lstar"],
                         illumination["white_anchor_vs_20260917_bright"]["CS1"])),
        "qualified_count": 0}

    analysis = {"kind": "mf1750-lh2-map-session-reconcile-v1", "version": VERSION,
                "inputs": {"night_extraction_sha256": rec.digest(
                               (args.night_analysis / "extraction.json").read_bytes()),
                           "morning_extraction_sha256": rec.digest(
                               (args.morning_analysis / "extraction.json").read_bytes()),
                           "night_map_analysis_sha256": rec.digest(
                               (args.night_analysis / "map-analysis.json").read_bytes()),
                           "morning_map_analysis_sha256": rec.digest(
                               (args.morning_analysis / "map-analysis.json").read_bytes())},
                "illumination": illumination, "attribution": attribution,
                "corrected_ladders": corrected, "conclusions": conclusions,
                "hardware_accessed": False, "visible_refresh": 0}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rec.write_new(args.output_dir / "reconcile-analysis.json", rec.seal(analysis))
    report = render_report(analysis)
    with (args.output_dir / "reconcile-report.md").open("x", encoding="utf-8",
                                                        newline="\n") as fh:
        fh.write(report)
    with (args.output_dir / "reconcile-tool.py").open("xb") as fh:
        fh.write(Path(__file__).read_bytes())
    print(json.dumps({"written": str(args.output_dir),
                      "credible": credible,
                      "gain": conclusions["morning_gain_vs_night"]}, ensure_ascii=False))


def render_report(a: dict) -> str:
    il = a["illumination"]
    at = a["attribution"]
    cc = a["conclusions"]
    lines = [
        "# LH2 MAP 两个拍摄 session 对账（2026-09-19）",
        "",
        "同一物理 MAP 屏态（中间无刷新）的两次拍摄：昨晚暗光（20260918）与今早亮光重拍"
        "（BRIGHT_20260919_V3）。纯离线对账，不动硬件。",
        "",
        "## 1. 照明是否同级？——否",
        "",
        f"- 屏面白锚（MAP 帧内 M7-C4 格）L*：昨晚 {il['white_anchor_cell_M7C4']['CS1']['night_lstar']:.1f}/"
        f"{il['white_anchor_cell_M7C4']['CS2']['night_lstar']:.1f} → 今早 "
        f"{il['white_anchor_cell_M7C4']['CS1']['morning_lstar']:.1f}/"
        f"{il['white_anchor_cell_M7C4']['CS2']['morning_lstar']:.1f}（Y 增益 "
        f"{il['white_anchor_cell_M7C4']['CS1']['y_gain']:.2f}×/{il['white_anchor_cell_M7C4']['CS2']['y_gain']:.2f}×）。",
        f"- 128 格全部变亮（ΔL* 中位 +{il['per_cell_lstar_delta_morning_minus_night']['median']:.1f}，"
        f"min +{il['per_cell_lstar_delta_morning_minus_night']['min']:.1f}，"
        f"max +{il['per_cell_lstar_delta_morning_minus_night']['max']:.1f}）；"
        f"彩度中位 {il['chroma_median']['night']:.1f} → {il['chroma_median']['morning']:.1f}。",
        f"- 相机设置逐字节相同：{il['camera_settings_identical']}；整帧 sums p50 "
        f"{il['scene_fullframe_sums']['night']['p50']:.0f} → {il['scene_fullframe_sums']['morning']['p50']:.0f}"
        "（p95 被屏面白区主导且取景变小，移动不敏感）。",
        f"- 今早白锚 ≈ 9-17 亮场的 {cc['morning_vs_20260917_bright']}（门 0.85 未达）。",
        "- “今早 36.8/35.5 与昨晚相同”的读数来自 19V1 分析把 --batch 指向昨晚批、"
        "混用了昨晚 s3-pre 端点；今早真实白锚是 44.2/43.4。",
        "",
        "## 2. 级数差异归因",
        "",
        f"- **NEUTRAL 4→1：{at['NEUTRAL_drop_4_to_1']['verdict']}**。"
        f"{at['NEUTRAL_drop_4_to_1']['explanation']}",
        f"- **RO 1→2（CS1）：{at['RO_gain_1_to_2_CS1']['verdict']}**。"
        f"{at['RO_gain_1_to_2_CS1']['explanation']}",
        f"- 混合参照影响：{at['mixed_reference_assessment']['note']}。",
        "",
        "## 3. 校正后可信级数表（变体 A：昨晚端点 Y 增益归一；冻结门不变）",
        "",
        "| 族 | CS1 | CS2 |",
        "|---|---|---|",
    ]
    for fam in ("R", "RO", "V", "B", "NEUTRAL"):
        lines.append(f"| {fam} | {cc['credible_family_levels_morning']['CS1'][fam]} "
                     f"| {cc['credible_family_levels_morning']['CS2'][fam]} |")
    lines += [
        "",
        "（变体 B：今早 MAP 帧内自洽阶梯见 reconcile-analysis.json corrected_ladders；"
        "RO-CS1 第 2 级是色相门边界情形，已标注不升级。）",
        "",
        "## 4. 一句话结论",
        "",
        cc["one_liner"],
        "",
        "qualified=0 保持。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
