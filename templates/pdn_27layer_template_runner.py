"""
Designer-Editable 27-Layer Full PDN Design Template Validator & Compiler CLI
for all 3 Substrate PDN Tasks (`L01 SURFACE` -> `L27 BASE`):
  - Task 1 (`TASK1_VDDUC_VDDCH`): `LDB` (`U7..U5` `VDDUC0..3`) & `LDC` (`U2..U1` `VDDCH0..3`)
  - Task 2 (`TASK2_VDDC_SRAM`)  : `LDA` (`U9, U12, U88, U10` `VDDC0..3` + `VDD_0P8_SRAM_CC0..3`)
  - Task 3 (`TASK3_HBM_4RAIL`)  : `HBM4E` (`U13..U24` + `U41..U52`: `VDDQ` + `VDDC` + `VDDQL` + `VPP`)

Usage:
  # STEP 3 (Mandatory SANDBOX first — zero .mcm mutation, generates SVGs + Confirmation Card):
  python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json --stage sandbox

  # STEP 4 + 5 (FINAL CONFIRMATION GATE -> Build New .mcm + Post-Route Connectivity Audit):
  python -m agent04_pdn_architect.templates.pdn_27layer_template_runner --config agent04_pdn_architect/templates/task2_vddc_sram_27layer_template.json --stage implement-mcm
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import shutil
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent04_pdn_architect.cad_cli.apd_27layer_master_exporter import (
    export_full_27layer_apd_implementation,
)
from agent04_pdn_architect.cad_cli.cadence_runner import CadenceBatchRunner
from agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine import (
    PlacedLscItem,
    export_curved_pockets_recipe_txt,
    render_curved_recess_inspection_svg,
    synthesize_curved_bga_recess_and_pack_lscs,
)
from agent04_pdn_architect.cad_cli.hbm_surface_and_csb_router import (
    connect_u9_sram0_10f_backbone,
    route_u13_emib_csb_and_c0_pins,
    route_u13_hbm_surface_and_10f_csb,
    route_u9_emib_csb_and_c0_pins,
    route_u9_lda_surface_and_emib,
)
from agent04_pdn_architect.cad_cli.multi_rail_polygon_engine import (
    BBox,
    CavityRecord,
    ClineRecord,
    FastXYClearanceGrid,
    MultiRailLayerOwnershipIndex,
    PolygonIsland,
    U13_DOMAIN_BBOX,
    U13_EDTC_BODIES,
    U41_EMIB_BBOX,
    U9_DOMAIN_BBOX,
    U9_EDTC_BODIES,
    U9_EMIB_BRIDGES,
    U9_SRAM0_SUB_ISLANDS_12B,
    ViaRecord,
    audit_via_continuity_and_zero_overlap,
    build_u13_hbm_27layer_polygons,
    build_u9_lda_27layer_polygons,
    compute_real_edtc_profiles,
    route_bottom_bga_and_lsc_with_atomic_pruning,
    synthesize_bu_9f_5f_and_9b_5b_stitch_arrays,
    synthesize_concentric_edtc_stacks,
    synthesize_multi_rail_core_pth_and_pp,
)
from agent04_pdn_architect.cad_cli.step1_step2_u9_u13_validator import (
    _hexagonal_6via_offsets,
    _octagonal_8via_offsets,
    _render_multirail_svg,
    write_master_recipe,
)
from agent04_pdn_architect.cad_cli.u9_vddc_sram_surface_3to1_jog_router import (
    render_u9_surface_3to1_inspection_svg,
    route_u9_vddc0_sram0_vss_3to1_vertical_jog,
)

CANONICAL_27_LAYERS: Tuple[str, ...] = (
    "SURFACE", "C0",
    "12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F",
    "4FCO", "3FCI", "2FCI", "1FCI", "1BCI", "2BCI", "3BCI", "4BCO",
    "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B",
    "BASE",
)

BU_LAYERS = {"12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F", "5B", "6B", "7B", "8B", "9B", "10B", "11B"}
CORE_PP_GCP_LAYERS = {"4FCO", "3FCI", "2FCI", "1FCI", "1BCI", "2BCI", "3BCI", "4BCO", "12B"}


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def validate_27layer_template_config(cfg: Dict[str, Any]) -> List[str]:
    """
    Validate a designer-edited 27-layer PDN JSON template for stackup completeness,
    safety invariants, and substrate DRC limits. Returns a list of error strings (empty == valid).
    """
    errors: List[str] = []
    task_id = cfg.get("task_id", "")
    if task_id not in ("TASK1_VDDUC_VDDCH", "TASK2_VDDC_SRAM", "TASK3_HBM_4RAIL"):
        errors.append(f"Unsupported task_id '{task_id}'. Expected TASK1_VDDUC_VDDCH, TASK2_VDDC_SRAM, or TASK3_HBM_4RAIL.")

    io_cfg = cfg.get("design_io", {})
    src_mcm = str(io_cfg.get("source_mcm_readonly", "")).strip()
    out_mcm = str(io_cfg.get("output_mcm_path", "")).strip()
    if not src_mcm or not out_mcm:
        errors.append("design_io.source_mcm_readonly and design_io.output_mcm_path must both be non-empty.")
    elif Path(src_mcm).name.lower() == Path(out_mcm).name.lower():
        errors.append("Safety violation: design_io.output_mcm_path must NEVER overwrite source_mcm_readonly (PDN_test.mcm).")

    layers = cfg.get("stackup_all_27_layers", [])
    if len(layers) != 27:
        errors.append(f"stackup_all_27_layers must define all 27 layers (found {len(layers)}).")
    else:
        actual_names = tuple(str(it.get("layer", "")).upper() for it in layers)
        if actual_names != CANONICAL_27_LAYERS:
            errors.append(
                f"stackup_all_27_layers order mismatch.\nExpected: {CANONICAL_27_LAYERS}\nActual  : {actual_names}"
            )
        for it in layers:
            lname = str(it.get("layer", "")).upper()
            gap = float(it.get("split_gap_um", 0.0))
            if lname in BU_LAYERS and gap < 50.0:
                errors.append(f"Layer {lname}: split_gap_um ({gap} um) < minimum BU split rule (50.0 um).")
            elif lname in CORE_PP_GCP_LAYERS and gap < 67.5:
                errors.append(f"Layer {lname}: split_gap_um ({gap} um) < minimum Core/PP/GCP split rule (67.5 um).")
            elif lname in ("SURFACE", "C0") and gap < 15.0:
                errors.append(f"Layer {lname}: split_gap_um ({gap} um) < minimum fine-line gap (15.0 um).")

    z_cfg = cfg.get("zone_routing_parameters", {})
    z4 = z_cfg.get("zone4_middle_bu_continuity_and_stack_limits", {})
    if int(z4.get("max_stacked_bu_vias", 7)) > 7:
        errors.append("zone4: max_stacked_bu_vias cannot exceed 7.")
    if int(z4.get("max_stacked_bu_vias_on_pth", 5)) > 5:
        errors.append("zone4: max_stacked_bu_vias_on_pth cannot exceed 5.")
    if not bool(z4.get("enforce_9f_to_5f_continuity", False)) or not bool(z4.get("enforce_9b_to_5b_continuity", False)):
        errors.append("zone4: enforce_9f_to_5f_continuity and enforce_9b_to_5b_continuity are mandatory.")
    if not bool(z4.get("zero_per_conductor_via_pad_overlap", False)):
        errors.append("zone4: zero_per_conductor_via_pad_overlap is mandatory.")

    z5 = z_cfg.get("zone5_base_bga_curved_recess_and_lsc", {})
    if not bool(z5.get("enforce_conductor_base_only", False)):
        errors.append("zone5: enforce_conductor_base_only must be true (0 LSCs allowed on SURFACE).")
    if not bool(z5.get("enforce_180deg_cap_to_cap_alternation", False)):
        errors.append("zone5: enforce_180deg_cap_to_cap_alternation must be true.")
    if float(z5.get("lsc_sro_to_sro_min_um", 250.0)) < 175.0:
        errors.append("zone5: lsc_sro_to_sro_min_um must be >= 175.0 um.")

    cr = z5.get("curved_recess_rules", {})
    if float(cr.get("mill_tool_radius_um", 508.0)) < 500.0:
        errors.append("curved_recess_rules: mill_tool_radius_um must be >= 500.0 um (Code K).")
    if float(cr.get("bga_sro_to_cavity_min_um", 254.0)) < 250.0:
        errors.append("curved_recess_rules: bga_sro_to_cavity_min_um must be >= 250.0 um (Code G/H).")
    if float(cr.get("ext_cu_to_cavity_koz_um", 178.0)) < 178.0:
        errors.append("curved_recess_rules: ext_cu_to_cavity_koz_um must be >= 178.0 um (Code D).")
    if float(cr.get("lsc_sro_to_cavity_min_um", 225.0)) < 225.0:
        errors.append("curved_recess_rules: lsc_sro_to_cavity_min_um must be >= 225.0 um (Slide 11).")

    return errors


def _write_apd_headless_bat(
    bat_path: Path,
    workspace: Path,
    src_mcm_rel: str,
    out_mcm_rel: str,
    recipe_path: Path,
    report_txt_path: Path,
) -> Path:
    il_script = (workspace / "agent04_pdn_architect" / "templates" / "apd_unified_27layer_template_importer.il").as_posix()
    src_mcm = (workspace / src_mcm_rel).resolve()
    out_mcm = (workspace / out_mcm_rel).resolve()
    replay_scr = bat_path.with_suffix(".scr")
    replay_scr.write_text(
        f'skill load("{il_script}")\n'
        f'skill pdnRunUnified27LayerTemplateBatch("{recipe_path.as_posix()}" "" "{report_txt_path.as_posix()}")\n'
        f"exit\n"
        f"fillin no\n",
        encoding="utf-8",
    )
    runner = CadenceBatchRunner()
    apd_bin = str(runner.apd_path) if runner.apd_path else r"C:\Cadence\SPB_25.1\tools\bin\apd.exe"
    bat_content = (
        "@echo off\n"
        "REM Auto-generated by pdn_27layer_template_runner.py — Never modifies source PDN_test.mcm!\n"
        f'copy /Y "{src_mcm}" "{out_mcm}"\n'
        f'if exist "{out_mcm}.lck" del /F /Q "{out_mcm}.lck"\n'
        f'"{apd_bin}" -product Allegro_Adv_Packaging_Plus -nographic "{out_mcm}" -s "{replay_scr}"\n'
    )
    bat_path.write_text(bat_content, encoding="utf-8")
    return bat_path


def _write_confirmation_gate_card(
    build_dir: Path,
    cfg: Dict[str, Any],
    summary: Dict[str, Any],
    workspace: Path,
) -> Path:
    inv = summary["layer_by_layer_27_inventory"]
    tot_planes = sum(r["copper_planes_or_islands"] for r in inv)
    tot_voids = sum(r["plane_voids"] for r in inv)
    tot_vias = sum(r["vias_starting_on_layer"] for r in inv)
    tot_clines = sum(r["cline_segments"] for r in inv)
    base_row = next((r for r in inv if r["layer"] == "BASE"), {})
    io_cfg = cfg["design_io"]
    gate = {
        "gate_status": "READY_FOR_FINAL_HUMAN_CONFIRMATION" if summary["drc_all_pass"] else "BLOCKED_SANDBOX_DRC_FAILED",
        "task_id": summary["task_id"],
        "flow_name": summary["flow_name"],
        "confirmation_token_required": "YES_IMPLEMENT_MCM",
        "sandbox_drc_all_pass": summary["drc_all_pass"],
        "safety_lock": {
            "source_mcm_readonly": str((workspace / io_cfg["source_mcm_readonly"]).resolve()),
            "output_mcm_target": str((workspace / io_cfg["output_mcm_path"]).resolve()),
            "source_mcm_will_remain_untouched": True,
        },
        "sandbox_object_summary": {
            "total_layers_configured": len(inv),
            "copper_planes_and_islands": tot_planes,
            "plane_voids_edtc_and_emib": tot_voids,
            "vias_all_26_spans": tot_vias,
            "cline_segments": tot_clines,
            "base_0201_lscs": base_row.get("base_lscs_placed", 0),
            "curved_recess_pockets": base_row.get("curved_recess_pockets", 0),
        },
        "visual_inspection_svgs": {
            k: summary[k]
            for k in ("stackup_summary_svg", "blueprint_27layer_svg", "surface_3to1_jog_svg", "base_curved_recess_svg")
            if k in summary and summary[k]
        },
        "master_recipe_txt": summary["master_recipe_path"],
        "next_command_after_review": (
            f"python -m agent04_pdn_architect.templates.pdn_27layer_template_runner "
            f"--config <your_template.json> --stage implement-mcm"
        ),
    }
    gate_path = build_dir / f"{cfg['task_id']}_Confirmation_Gate.json"
    gate_path.write_text(json.dumps(gate, indent=2), encoding="utf-8")
    return gate_path


def _build_27layer_inventory_table(
    stackup_spec: Sequence[Dict[str, Any]],
    planes_by_layer: Dict[str, int],
    voids_by_layer: Dict[str, int],
    vias_start_by_layer: Dict[str, int],
    vias_end_by_layer: Dict[str, int],
    clines_by_layer: Dict[str, int],
    base_lsc_count: int,
    base_cavity_count: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in stackup_spec:
        lyr = str(item["layer"]).upper()
        rows.append({
            "order": item["order"],
            "layer": lyr,
            "cu_um": item["cu_um"],
            "mode": item["mode"],
            "shape_type": item["shape_type"],
            "nets": item["nets"],
            "split_gap_um": item["split_gap_um"],
            "copper_planes_or_islands": planes_by_layer.get(lyr, 0),
            "plane_voids": voids_by_layer.get(lyr, 0),
            "vias_starting_on_layer": vias_start_by_layer.get(lyr, 0),
            "vias_ending_on_layer": vias_end_by_layer.get(lyr, 0),
            "cline_segments": clines_by_layer.get(lyr, 0),
            "base_lscs_placed": base_lsc_count if lyr == "BASE" else 0,
            "curved_recess_pockets": base_cavity_count if lyr == "BASE" else 0,
        })
    return rows


def _render_27layer_stackup_svg(
    svg_path: Path,
    title: str,
    inventory_rows: Sequence[Dict[str, Any]],
) -> Path:
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    W, H = 1680, 1080
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        '<rect width="100%" height="100%" fill="#0b1120"/>',
        f'<text x="32" y="42" fill="#f8fafc" font-family="Segoe UI, Arial" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        '<text x="32" y="66" fill="#38bdf8" font-family="Segoe UI, Arial" font-size="13">Designer-Editable 27-Layer Full PDN Stackup &amp; Synthesized Object Inventory (L01 SURFACE -&gt; L27 BASE)</text>',
    ]
    headers = [
        (32, "#"), (80, "Layer"), (165, "Cu(um)"), (240, "Shape Type"),
        (465, "Design Mode"), (745, "Nets"), (1090, "Planes"),
        (1175, "Voids"), (1255, "ViaStart"), (1350, "ViaEnd"),
        (1445, "CLINEs"), (1535, "LSC/Cav"),
    ]
    hy = 98
    out.append(f'<rect x="24" y="{hy-20}" width="{W-48}" height="28" rx="4" fill="#1e293b"/>')
    for hx, htxt in headers:
        out.append(f'<text x="{hx}" y="{hy}" fill="#fde047" font-family="Consolas, monospace" font-size="12" font-weight="bold">{html.escape(htxt)}</text>')

    row_h = 34
    for idx, r in enumerate(inventory_rows):
        ry = 130 + idx * row_h
        bg = "#111827" if idx % 2 == 0 else "#0f172a"
        if r["layer"] in ("SURFACE", "4FCO", "2FCI", "2BCI", "4BCO", "12B", "BASE"):
            bg = "#172554"
        out.append(f'<rect x="24" y="{ry-19}" width="{W-48}" height="{row_h-2}" rx="3" fill="{bg}" stroke="#1e293b" stroke-width="0.8"/>')
        nets_s = ",".join(r["nets"])
        if len(nets_s) > 38:
            nets_s = nets_s[:35] + "..."
        lsc_cav_s = f"{r['base_lscs_placed']}/{r['curved_recess_pockets']}" if r["layer"] == "BASE" else "-"
        cols = [
            (32, f"L{r['order']:02d}", "#94a3b8"),
            (80, r["layer"], "#f8fafc"),
            (165, f"{r['cu_um']:.1f}", "#cbd5e1"),
            (240, r["shape_type"][:24], "#38bdf8"),
            (465, r["mode"][:30], "#e2e8f0"),
            (745, nets_s, "#fdba74"),
            (1090, str(r["copper_planes_or_islands"]), "#4ade80"),
            (1175, str(r["plane_voids"]), "#facc15"),
            (1255, str(r["vias_starting_on_layer"]), "#7dd3fc"),
            (1350, str(r["vias_ending_on_layer"]), "#c084fc"),
            (1445, str(r["cline_segments"]), "#f472b6"),
            (1535, lsc_cav_s, "#2dd4bf"),
        ]
        for cx, ctxt, ccol in cols:
            out.append(f'<text x="{cx}" y="{ry}" fill="{ccol}" font-family="Consolas, monospace" font-size="12">{html.escape(ctxt)}</text>')

    out.append("</svg>")
    svg_txt = "\n".join(out)
    ET.fromstring(svg_txt.encode("utf-8"))
    svg_path.write_text(svg_txt, encoding="utf-8")
    return svg_path


def _compile_curved_pockets_from_seeds(
    lscs: Sequence[Dict[str, str]],
    bga_balls: Sequence[Dict[str, str]],
    target_nets: Sequence[str],
    prefix: str,
    ownership: MultiRailLayerOwnershipIndex | None,
    emib_boxes: Sequence[BBox],
    mill_r: float,
    bga_sro_min: float,
    ext_koz: float,
    lsc_sro_cav: float,
    lsc_sro_sro: float,
    inter_cav_web: float,
    lsc_sym: str,
) -> Tuple[List[CavityRecord], List[PlacedLscItem], List[str], List[ Any ]]:
    tset = set(target_nets)
    pts: List[Tuple[float, float, Dict[str, str]]] = []
    for r in lscs:
        if r["pin1_net"] in tset or r["pin2_net"] in tset:
            pts.append((float(r["x_um"]), float(r["y_um"]), r))
    if not pts:
        return [], [], [], []

    n = len(pts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if abs(pts[i][0] - pts[j][0]) <= 2100.0 and abs(pts[i][1] - pts[j][1]) <= 2100.0:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    groups: Dict[int, List[Tuple[float, float, Dict[str, str]]]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(pts[i])

    def _resolver(x_c: float, y_c: float, rot_deg: float) -> str | None:
        if ownership is None:
            return target_nets[0]
        tmp = PlacedLscItem("TMP", lsc_sym, x_c, y_c, rot_deg, target_nets[0], "VSS", "P")
        (p1x, p1y), _ = tmp.pin_coords
        if "VDD_0P8_SRAM_CC0" in tset:
            if any(sb[0] + 40.0 <= p1x <= sb[2] - 40.0 and sb[1] + 40.0 <= p1y <= sb[3] - 40.0 for sb in U9_SRAM0_SUB_ISLANDS_12B):
                if ownership.owner_at("10B", p1x, p1y, min_edge_margin_um=45.0) == "VDD_0P8_SRAM_CC0":
                    return "VDD_0P8_SRAM_CC0"
            own = ownership.owner_at("12B", p1x, p1y, min_edge_margin_um=45.0)
            return own if own in tset else None
        own12 = ownership.owner_at("12B", p1x, p1y, min_edge_margin_um=40.0)
        if own12 in tset:
            if "VDDQ_0P85_HBM_MEM5" in tset and -37950.0 <= p1x <= -36200.0 and 25000.0 <= p1y <= 31500.0:
                if ownership.owner_at("10B", p1x, p1y, min_edge_margin_um=45.0) == "VDDQ_0P85_HBM_MEM5":
                    return "VDDQ_0P85_HBM_MEM5"
            return own12
        own10 = ownership.owner_at("10B", p1x, p1y, min_edge_margin_um=45.0)
        return own10 if own10 in tset else None

    cavs: List[CavityRecord] = []
    placed_all: List[PlacedLscItem] = []
    del_refs: List[str] = []
    raw_results = []
    built_polys: List[List[Tuple[float, float]]] = []

    for idx, grp in enumerate(sorted(groups.values(), key=lambda g: -len(g)), start=1):
        pk_id = f"{prefix}_CAV_{idx}"
        ex_rows = [item[2] for item in grp]
        for r in ex_rows:
            if r.get("refdes"):
                del_refs.append(r["refdes"])
        res = synthesize_curved_bga_recess_and_pack_lscs(
            pocket_id=pk_id,
            seed_points=[(it[0], it[1]) for it in grp],
            bga_balls=bga_balls,
            default_vdd_net=target_nets[0],
            rail_resolver_fn=_resolver,
            existing_pocket_lscs=ex_rows,
            emib_shadow_boxes=emib_boxes,
            other_cavity_polys=built_polys,
            mill_radius_um=mill_r,
            bga_sro_to_cav_um=bga_sro_min,
            ext_koz_um=ext_koz,
            lsc_sro_to_cav_um=lsc_sro_cav,
            sro_to_sro_um=lsc_sro_sro,
            symbol_name=lsc_sym,
            refdes_prefix=f"C_{prefix}_P{idx}",
            grid_step_um=20.0,
        )
        raw_results.append(res)
        if res.cavity_poly:
            built_polys.append(res.cavity_poly)
            xs = [p[0] for p in res.cavity_poly]
            ys = [p[1] for p in res.cavity_poly]
            cavs.append(
                CavityRecord(
                    pocket_id=pk_id,
                    x1=round(min(xs), 2),
                    y1=round(min(ys), 2),
                    x2=round(max(xs), 2),
                    y2=round(max(ys), 2),
                    corner_r_um=mill_r,
                    ext_koz_um=ext_koz,
                    lsc_safe_in_um=lsc_sro_cav,
                    cavity_poly=res.cavity_poly,
                    outer_koz_poly=res.outer_koz_poly,
                    inner_safe_poly=res.inner_safe_poly,
                )
            )
        placed_all.extend(res.placed_lscs)

    return cavs, placed_all, del_refs, raw_results


def _compile_task1(cfg: Dict[str, Any], ws: Path) -> Dict[str, Any]:
    io_cfg = cfg["design_io"]
    build_dir = ws / io_cfg["output_build_dir"]
    build_dir.mkdir(parents=True, exist_ok=True)
    z_cfg = cfg["zone_routing_parameters"]
    z1 = z_cfg["zone1_surface_escape"]
    z3 = z_cfg["zone3_edtc_and_core_pth"]
    z5 = z_cfg["zone5_base_bga_curved_recess_and_lsc"]
    cr = z5["curved_recess_rules"]

    # 1. Run parameterized 27-layer U7 exporter
    u7_manifest = export_full_27layer_apd_implementation(
        surface_ratio=str(z1["surface_vip_ratio"]),
        surface_direction=str(z1["strap_direction"]),
        pth_density_per_mm2=float(z3["core_pth_density_per_mm2"]),
        pth_pattern=str(z3["core_pth_pattern"]),
        bga_cluster_a_option=str(z5["bga_cluster_a_7stack_option"]),
        lsc_sro_rule_um=float(z5.get("exporter_u7_lsc_sro_rule_um", 175.0)),
    )

    # 2. Synthesize curved BGA-following recesses & 180-deg LSCs for U7 (VDDUC0) + U2 (VDDCH0)
    bga_balls = _read_csv_rows(ws / io_cfg["bga_map_csv"])
    t1_specs = [
        ("U7_VDDUC0_CoreSouth", [(21980.0, 9500.0), (21980.0, 6200.0), (21980.0, 12800.0)], "VDDUC0"),
        ("U7_VDDUC0_CoreNorth", [(21980.0, 22700.0), (21980.0, 19300.0), (21980.0, 26000.0)], "VDDUC0"),
        ("U2_VDDCH0_North1",    [(10580.0, 37400.0), (8000.0, 37400.0), (13200.0, 37400.0)], "VDDCH0"),
        ("U2_VDDCH0_North2_L",  [(19800.0, 37400.0), (17600.0, 36400.0), (22500.0, 37800.0)], "VDDCH0"),
    ]
    t1_raw = []
    t1_built: List[List[Tuple[float, float]]] = []
    for pk_id, seeds, vnet in t1_specs:
        res = synthesize_curved_bga_recess_and_pack_lscs(
            pocket_id=pk_id,
            seed_points=seeds,
            bga_balls=bga_balls,
            default_vdd_net=vnet,
            other_cavity_polys=t1_built,
            mill_radius_um=float(cr["mill_tool_radius_um"]),
            bga_sro_to_cav_um=float(cr["bga_sro_to_cavity_min_um"]),
            ext_koz_um=float(cr["ext_cu_to_cavity_koz_um"]),
            lsc_sro_to_cav_um=float(cr["lsc_sro_to_cavity_min_um"]),
            sro_to_sro_um=float(z5["lsc_sro_to_sro_min_um"]),
            symbol_name=str(z5["lsc_symbol_name"]),
            refdes_prefix=f"C_{pk_id}",
            grid_step_um=20.0,
        )
        t1_raw.append(res)
        if res.cavity_poly:
            t1_built.append(res.cavity_poly)

    # Copy U7 master recipe + append U2 curved pockets & LSCs into unified Task 1 Master Recipe
    u7_rec_txt = Path(u7_manifest["exported_files"]["master_skill_recipe_txt"]).read_text(encoding="utf-8")
    u2_extra_lines: List[str] = ["# --- U2 VDDCH0 Curved Recess & 180-deg BASE LSCs ---"]
    for res in t1_raw[2:]:
        c_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in res.cavity_poly)
        k_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in res.outer_koz_poly)
        s_str = ";".join(f"{x:.2f},{y:.2f}" for x, y in res.inner_safe_poly)
        u2_extra_lines.append(f"POLY_CAVITY|{res.pocket_id}|{c_str}|{k_str}|{s_str}")
        for cap in res.placed_lscs:
            u2_extra_lines.append(
                f"LSC_PLACE|{cap.refdes}|{cap.symbol_name}|{cap.x:.3f}|{cap.y:.3f}|{cap.rot_deg:.1f}|{cap.pin1_net}|{cap.pin2_net}"
            )

    master_recipe = build_dir / "Task1_VDDUC_VDDCH_27Layer_Master_Recipe.txt"
    master_recipe.write_text(u7_rec_txt + "\n" + "\n".join(u2_extra_lines) + "\n", encoding="utf-8")

    # Build 27-layer inventory from U7 exported CSVs + U2 additions
    planes_by_l: Counter[str] = Counter()
    voids_by_l: Counter[str] = Counter()
    vstart_by_l: Counter[str] = Counter()
    vend_by_l: Counter[str] = Counter()
    clines_by_l: Counter[str] = Counter()

    for row in _read_csv_rows(Path(u7_manifest["exported_files"]["all_planes_csv"])):
        lyr = row["layer"].upper()
        planes_by_l[lyr] += 1
        if str(row.get("has_edtc_voids", "")).lower() == "true":
            voids_by_l[lyr] += 5
    for row in _read_csv_rows(Path(u7_manifest["exported_files"]["all_vias_csv"])):
        vstart_by_l[row["start_layer"].upper()] += 1
        vend_by_l[row["end_layer"].upper()] += 1
    for row in _read_csv_rows(Path(u7_manifest["exported_files"]["all_traces_clines_csv"])):
        clines_by_l[row["layer"].upper()] += 1

    total_lscs = int(u7_manifest["object_totals"]["total_0201_lsc_symbols_on_base"]) + sum(len(r.placed_lscs) for r in t1_raw[2:])
    inv_rows = _build_27layer_inventory_table(
        cfg["stackup_all_27_layers"],
        planes_by_l, voids_by_l, vstart_by_l, vend_by_l, clines_by_l,
        base_lsc_count=total_lscs,
        base_cavity_count=8 + 2,
    )

    base_svg = build_dir / "Task1_VDDUC_VDDCH_BASE_Curved_Recess_LSC.svg"
    render_curved_recess_inspection_svg(
        t1_raw,
        base_svg,
        header_title="Task 1 Template Build — Curved BGA-Following Recess & 180-deg BASE LSCs (VDDUC0 + VDDCH0)",
    )
    stack_svg = build_dir / "Task1_VDDUC_VDDCH_27Layer_Stackup_Summary.svg"
    _render_27layer_stackup_svg(stack_svg, "Task 1 (VDDUC* & VDDCH*) — Full 27-Layer PDN Template Build", inv_rows)

    bat_path = _write_apd_headless_bat(
        build_dir / "Task1_VDDUC_VDDCH_run_apd_headless.bat",
        ws,
        io_cfg["source_mcm_readonly"],
        io_cfg["output_mcm_path"],
        master_recipe,
        build_dir / "Task1_apd_import_report.txt",
    )

    summary = {
        "task_id": cfg["task_id"],
        "flow_name": cfg["flow_name"],
        "validation_passed": True,
        "drc_all_pass": bool(u7_manifest["drc_and_no_overlap_verification"]["Zero_DRC_and_Overlap_Violations"])
                        and all(bool(r.drc_metrics["drc_pass"]) for r in t1_raw),
        "source_mcm_readonly": str((ws / io_cfg["source_mcm_readonly"]).resolve()),
        "output_mcm_path": str((ws / io_cfg["output_mcm_path"]).resolve()),
        "master_recipe_path": str(master_recipe),
        "stackup_summary_svg": str(stack_svg),
        "base_curved_recess_svg": str(base_svg),
        "apd_headless_launcher_bat": str(bat_path),
        "apd_import_report_txt": str(build_dir / "Task1_apd_import_report.txt"),
        "layer_by_layer_27_inventory": inv_rows,
    }
    summary["confirmation_gate_json"] = str(_write_confirmation_gate_card(build_dir, cfg, summary, ws))
    (build_dir / "Task1_VDDUC_VDDCH_27Layer_Layer_By_Layer_Summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def _compile_task2(cfg: Dict[str, Any], ws: Path) -> Dict[str, Any]:
    io_cfg = cfg["design_io"]
    build_dir = ws / io_cfg["output_build_dir"]
    build_dir.mkdir(parents=True, exist_ok=True)
    z_cfg = cfg["zone_routing_parameters"]
    z1 = z_cfg["zone1_surface_escape"]
    z3 = z_cfg["zone3_edtc_and_core_pth"]
    z4 = z_cfg["zone4_middle_bu_continuity_and_stack_limits"]
    z5 = z_cfg["zone5_base_bga_curved_recess_and_lsc"]
    cr = z5["curved_recess_rules"]

    edtc_pins = _read_csv_rows(ws / io_cfg["edtc_pin_map_csv"])
    edtc_syms = _read_csv_rows(ws / io_cfg["edtc_symbols_csv"])
    bga_balls = _read_csv_rows(ws / io_cfg["bga_map_csv"])
    lsc_caps  = _read_csv_rows(ws / io_cfg["lsc_placed_map_csv"])
    u9_pins   = _read_csv_rows(ws / io_cfg["u9_pins_csv"])

    u9_edtc_profs = compute_real_edtc_profiles(edtc_pins, edtc_syms, list(U9_EDTC_BODIES.keys()))
    grid = FastXYClearanceGrid(cell_um=250.0)
    u9_polys = build_u9_lda_27layer_polygons(edtc_profiles=u9_edtc_profs)
    u9_own = MultiRailLayerOwnershipIndex(u9_polys)
    u9_vias: List[ViaRecord] = []
    u9_clines: List[ClineRecord] = []

    synthesize_concentric_edtc_stacks(
        edtc_pins=edtc_pins,
        target_refdes=list(U9_EDTC_BODIES.keys()),
        allowed_nets=("VDDC0", "VDD_0P8_SRAM_CC0", "VSS"),
        ownership=u9_own,
        vias_out=u9_vias,
        grid=grid,
    )
    route_u9_emib_csb_and_c0_pins(u9_pins=u9_pins, ownership=u9_own, vias_out=u9_vias, grid=grid)

    synthesize_multi_rail_core_pth_and_pp(
        domain_bbox=U9_DOMAIN_BBOX,
        power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
        ownership=u9_own,
        edtc_bodies=U9_EDTC_BODIES,
        emib_boxes=U9_EMIB_BRIDGES,
        vias_out=u9_vias,
        grid=grid,
        pth_pitch_x_um=float(z3["core_pth_pitch_x_um"]),
        pth_pitch_y_um=float(z3["core_pth_pitch_y_um"]),
        tag_prefix="U9",
        edtc_profiles=u9_edtc_profs,
    )

    u9_cavs, u9_placed_lscs, u9_del_lscs, u9_raw_cavs = _compile_curved_pockets_from_seeds(
        lscs=lsc_caps,
        bga_balls=bga_balls,
        target_nets=("VDDC0", "VDD_0P8_SRAM_CC0"),
        prefix="U9",
        ownership=u9_own,
        emib_boxes=list(U9_EMIB_BRIDGES.values()),
        mill_r=float(cr["mill_tool_radius_um"]),
        bga_sro_min=float(cr["bga_sro_to_cavity_min_um"]),
        ext_koz=float(cr["ext_cu_to_cavity_koz_um"]),
        lsc_sro_cav=float(cr["lsc_sro_to_cavity_min_um"]),
        lsc_sro_sro=float(z5["lsc_sro_to_sro_min_um"]),
        inter_cav_web=float(cr["inter_cavity_min_web_um"]),
        lsc_sym=str(z5["lsc_symbol_name"]),
    )

    oct8 = _octagonal_8via_offsets(float(z5["vdd_bga_octagon_radius_um"]))
    vh = float(z5["vss_bga_half_span_um"])
    route_bottom_bga_and_lsc_with_atomic_pruning(
        bga_balls=bga_balls,
        lsc_caps=[it.to_cap_dict() for it in u9_placed_lscs],
        target_power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
        vss_bbox=tuple(cfg["target_domains"]["primary_lda_domain"]["domain_bbox_um"]),  # type: ignore[arg-type]
        ownership=u9_own,
        bga_offsets_by_rail={"VDDC0": oct8, "VDD_0P8_SRAM_CC0": oct8, "VSS": [(-vh, -vh), (vh, -vh), (-vh, vh), (vh, vh)]},
        vias_out=u9_vias,
        grid=grid,
        tag_prefix="U9_BOT",
    )

    surf_mode = str(z1["surface_routing_mode"]).upper()
    surf_svg_path = ""
    if surf_mode == "PARTIAL_3_TO_1_VERTICAL_C_S_JOG":
        # Route SRAM0 3:1 vertical jog first, then 9F->5F/9B->5B stitch, then VDDC0+VSS 3:1 vertical jog!
        jog_sram = route_u9_vddc0_sram0_vss_3to1_vertical_jog(
            u9_pins=u9_pins,
            ownership=u9_own,
            vias_out=u9_vias,
            clines_out=u9_clines,
            grid=grid,
            ratio_str=str(z1["vdd_to_vss_vip_ratio"]),
            trace_width_um=float(z1["vertical_jog_trace_width_um"]),
            min_gap_um=15.0,
            emib_already_routed=True,
            only_nets=("VDD_0P8_SRAM_CC0",),
        )
        synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(
            domain_bbox=U9_DOMAIN_BBOX,
            power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
            ownership=u9_own,
            vias_out=u9_vias,
            grid=grid,
            pitch_um=float(z4["middle_bu_stitch_pitch_um"]),
            tag_prefix="U9_MID",
        )
        jog_full = route_u9_vddc0_sram0_vss_3to1_vertical_jog(
            u9_pins=u9_pins,
            ownership=u9_own,
            vias_out=u9_vias,
            clines_out=u9_clines,
            grid=grid,
            ratio_str=str(z1["vdd_to_vss_vip_ratio"]),
            trace_width_um=float(z1["vertical_jog_trace_width_um"]),
            min_gap_um=15.0,
            emib_already_routed=True,
            only_nets=("VDDC0", "VSS"),
        )
        _ = jog_sram, jog_full
        # Also render full 3-net surface 3:1 vertical jog inspection SVG
        standalone_jog = route_u9_vddc0_sram0_vss_3to1_vertical_jog(
            u9_pins=u9_pins,
            ratio_str=str(z1["vdd_to_vss_vip_ratio"]),
            trace_width_um=float(z1["vertical_jog_trace_width_um"]),
            min_gap_um=15.0,
        )
        s_svg = build_dir / "Task2_U9_SURFACE_3to1_VerticalJog.svg"
        render_u9_surface_3to1_inspection_svg(standalone_jog, s_svg)
        surf_svg_path = str(s_svg)
    else:
        ratio_use = "1:0" if surf_mode == "FULL_VIP" else str(z1["vdd_to_vss_vip_ratio"])
        shared_obs = FastXYClearanceGrid(cell_um=160.0)
        route_u9_lda_surface_and_emib(
            u9_pins=u9_pins, ownership=u9_own, vias_out=u9_vias, clines_out=u9_clines,
            grid=grid, vddc_vss_ratio=ratio_use, emib_already_routed=True,
            only_nets=("VDD_0P8_SRAM_CC0",), shared_bump_obs=shared_obs,
        )
        synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(
            domain_bbox=U9_DOMAIN_BBOX, power_rails=("VDDC0", "VDD_0P8_SRAM_CC0"),
            ownership=u9_own, vias_out=u9_vias, grid=grid,
            pitch_um=float(z4["middle_bu_stitch_pitch_um"]), tag_prefix="U9_MID",
        )
        route_u9_lda_surface_and_emib(
            u9_pins=u9_pins, ownership=u9_own, vias_out=u9_vias, clines_out=u9_clines,
            grid=grid, vddc_vss_ratio=ratio_use, emib_already_routed=True,
            only_nets=("VDDC0", "VSS"), shared_bump_obs=shared_obs,
        )

    connect_u9_sram0_10f_backbone(u9_own, u9_vias, u9_clines, grid)
    via_audit = audit_via_continuity_and_zero_overlap(u9_vias)

    master_recipe = build_dir / "Task2_U9_VDDC0_SRAM0_27Layer_Master_Recipe.txt"
    write_master_recipe(
        master_recipe,
        u9_polys,
        u9_cavs,
        u9_vias,
        u9_clines,
        placed_lscs=u9_placed_lscs,
        delete_lsc_refdes=u9_del_lscs,
    )

    planes_by_l = Counter(p.layer.upper() for p in u9_polys)
    voids_by_l: Counter[str] = Counter()
    for p in u9_polys:
        voids_by_l[p.layer.upper()] += len(p.voids)
    vstart_by_l = Counter(v.start_layer.upper() for v in u9_vias)
    vend_by_l = Counter(v.end_layer.upper() for v in u9_vias)
    clines_by_l = Counter(c.layer.upper() for c in u9_clines)

    inv_rows = _build_27layer_inventory_table(
        cfg["stackup_all_27_layers"],
        planes_by_l, voids_by_l, vstart_by_l, vend_by_l, clines_by_l,
        base_lsc_count=len(u9_placed_lscs),
        base_cavity_count=len(u9_cavs),
    )

    bp_svg = _render_multirail_svg(
        build_dir / "Task2_U9_VDDC0_SRAM0_27Layer_Blueprint.svg",
        "Task 2 Template Build — U9 (LDA: VDDC0 + VDD_0P8_SRAM_CC0 + VSS) Full 27-Layer PDN",
        U9_DOMAIN_BBOX,
        u9_polys,
        u9_vias,
        u9_cavs,
        {"VDDC0": "#ef4444", "VDD_0P8_SRAM_CC0": "#a855f7", "VSS": "#38bdf8", "__ISOLATED__": "#facc15"},
    )
    base_svg = build_dir / "Task2_U9_VDDC0_SRAM0_BASE_Curved_Recess_LSC.svg"
    render_curved_recess_inspection_svg(
        u9_raw_cavs,
        base_svg,
        header_title="Task 2 Template Build — U9 Curved BGA-Following Recesses & 196 Co-Pocket 180-deg LSCs",
    )
    stack_svg = _render_27layer_stackup_svg(
        build_dir / "Task2_U9_VDDC0_SRAM0_27Layer_Stackup_Summary.svg",
        "Task 2 (LDA VDDC0 + SRAM_CC0) — Full 27-Layer PDN Template Build",
        inv_rows,
    )
    bat_path = _write_apd_headless_bat(
        build_dir / "Task2_U9_VDDC0_SRAM0_run_apd_headless.bat",
        ws,
        io_cfg["source_mcm_readonly"],
        io_cfg["output_mcm_path"],
        master_recipe,
        build_dir / "Task2_apd_import_report.txt",
    )

    summary = {
        "task_id": cfg["task_id"],
        "flow_name": cfg["flow_name"],
        "validation_passed": True,
        "drc_all_pass": (
            bool(via_audit["zero_via_overlap_pass"])
            and all(via_audit["vss_span_counts"].get(sp, 0) > 0 for sp in ("9F:8F", "8F:7F", "7F:6F", "6F:5F", "5B:6B", "6B:7B", "7B:8B", "8B:9B"))
            and all(bool(r.drc_metrics["drc_pass"]) for r in u9_raw_cavs)
        ),
        "source_mcm_readonly": str((ws / io_cfg["source_mcm_readonly"]).resolve()),
        "output_mcm_path": str((ws / io_cfg["output_mcm_path"]).resolve()),
        "via_continuity_and_zero_overlap_audit": via_audit,
        "master_recipe_path": str(master_recipe),
        "blueprint_27layer_svg": str(bp_svg),
        "stackup_summary_svg": str(stack_svg),
        "base_curved_recess_svg": str(base_svg),
        "surface_3to1_jog_svg": surf_svg_path,
        "apd_headless_launcher_bat": str(bat_path),
        "apd_import_report_txt": str(build_dir / "Task2_apd_import_report.txt"),
        "layer_by_layer_27_inventory": inv_rows,
    }
    summary["confirmation_gate_json"] = str(_write_confirmation_gate_card(build_dir, cfg, summary, ws))
    (build_dir / "Task2_U9_VDDC0_SRAM0_27Layer_Layer_By_Layer_Summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def _compile_task3(cfg: Dict[str, Any], ws: Path) -> Dict[str, Any]:
    io_cfg = cfg["design_io"]
    build_dir = ws / io_cfg["output_build_dir"]
    build_dir.mkdir(parents=True, exist_ok=True)
    z_cfg = cfg["zone_routing_parameters"]
    z3 = z_cfg["zone3_compact_edtc_and_4strip_core_pth"]
    z4 = z_cfg["zone4_middle_bu_continuity_and_stack_limits"]
    z5 = z_cfg["zone5_base_bga_curved_recess_and_lsc"]
    cr = z5["curved_recess_rules"]

    edtc_pins = _read_csv_rows(ws / io_cfg["edtc_pin_map_csv"])
    edtc_syms = _read_csv_rows(ws / io_cfg["edtc_symbols_csv"])
    bga_balls = _read_csv_rows(ws / io_cfg["bga_map_csv"])
    lsc_caps  = _read_csv_rows(ws / io_cfg["lsc_placed_map_csv"])
    u13_pins  = _read_csv_rows(ws / io_cfg["u13_u41_u5_pins_csv"])

    rails = cfg["target_domains"]["primary_hbm_site"]["rails"]
    pwr_rails = (rails["vddq"], rails["vddc"], rails["vddql"], rails["vpp"])

    u13_edtc_profs = compute_real_edtc_profiles(edtc_pins, edtc_syms, list(U13_EDTC_BODIES.keys()))
    grid = FastXYClearanceGrid(cell_um=250.0)
    u13_polys = build_u13_hbm_27layer_polygons(edtc_profiles=u13_edtc_profs)
    u13_own_box = [MultiRailLayerOwnershipIndex(u13_polys)]
    u13_vias: List[ViaRecord] = []
    u13_clines: List[ClineRecord] = []
    u13_gang_bars: List[PolygonIsland] = []

    synthesize_concentric_edtc_stacks(
        edtc_pins=edtc_pins,
        target_refdes=list(U13_EDTC_BODIES.keys()),
        allowed_nets=(*pwr_rails, "VSS"),
        ownership=u13_own_box[0],
        vias_out=u13_vias,
        grid=grid,
    )
    route_u13_emib_csb_and_c0_pins(
        u13_u41_u5_pins=u13_pins,
        u13_polys=u13_polys,
        ownership_ref=u13_own_box,
        vias_out=u13_vias,
        clines_out=u13_clines,
        grid=grid,
    )
    u13_own = u13_own_box[0]
    synthesize_multi_rail_core_pth_and_pp(
        domain_bbox=U13_DOMAIN_BBOX,
        power_rails=pwr_rails,
        ownership=u13_own,
        edtc_bodies=U13_EDTC_BODIES,
        emib_boxes={"U41": U41_EMIB_BBOX},
        vias_out=u13_vias,
        grid=grid,
        pth_pitch_x_um=float(z3["core_pth_pitch_x_um"]),
        pth_pitch_y_um=float(z3["core_pth_pitch_y_um"]),
        tag_prefix="U13",
        edtc_profiles=u13_edtc_profs,
    )

    u13_cavs, u13_placed_lscs, u13_del_lscs, u13_raw_cavs = _compile_curved_pockets_from_seeds(
        lscs=lsc_caps,
        bga_balls=bga_balls,
        target_nets=pwr_rails,
        prefix="U13",
        ownership=u13_own,
        emib_boxes=(U41_EMIB_BBOX,),
        mill_r=float(cr["mill_tool_radius_um"]),
        bga_sro_min=float(cr["bga_sro_to_cavity_min_um"]),
        ext_koz=float(cr["ext_cu_to_cavity_koz_um"]),
        lsc_sro_cav=float(cr["lsc_sro_to_cavity_min_um"]),
        lsc_sro_sro=float(z5["lsc_sro_to_sro_min_um"]),
        inter_cav_web=float(cr["inter_cavity_min_web_um"]),
        lsc_sym=str(z5["lsc_symbol_name"]),
    )

    hex6 = _hexagonal_6via_offsets(float(z5["vddq_bga_hex_radius_um"]))
    dr = float(z5["vddc_vddql_vpp_bga_diamond_radius_um"])
    diam4 = [(-dr, 0.0), (dr, 0.0), (0.0, -dr), (0.0, dr)]
    vh = float(z5["vss_bga_half_span_um"])
    route_bottom_bga_and_lsc_with_atomic_pruning(
        bga_balls=bga_balls,
        lsc_caps=[it.to_cap_dict() for it in u13_placed_lscs],
        target_power_rails=pwr_rails,
        vss_bbox=tuple(cfg["target_domains"]["primary_hbm_site"]["domain_bbox_um"]),  # type: ignore[arg-type]
        ownership=u13_own,
        bga_offsets_by_rail={
            rails["vddq"]: hex6,
            rails["vddc"]: diam4,
            rails["vddql"]: diam4,
            rails["vpp"]: diam4,
            "VSS": [(-vh, -vh), (vh, -vh), (-vh, vh), (vh, vh)],
        },
        vias_out=u13_vias,
        grid=grid,
        tag_prefix="U13_BOT",
    )

    route_u13_hbm_surface_and_10f_csb(
        u13_u41_u5_pins=u13_pins,
        ownership=u13_own,
        surface_gang_islands_out=u13_gang_bars,
        vias_out=u13_vias,
        clines_out=u13_clines,
        grid=grid,
        u13_polys=u13_polys,
        emib_already_routed=True,
    )
    synthesize_bu_9f_5f_and_9b_5b_stitch_arrays(
        domain_bbox=U13_DOMAIN_BBOX,
        power_rails=pwr_rails,
        ownership=u13_own,
        vias_out=u13_vias,
        grid=grid,
        pitch_um=float(z4["middle_bu_stitch_pitch_um"]),
        tag_prefix="U13_MID",
    )

    all_polys = list(u13_polys) + list(u13_gang_bars)
    via_audit = audit_via_continuity_and_zero_overlap(u13_vias)

    master_recipe = build_dir / "Task3_U13_HBM_4Rail_27Layer_Master_Recipe.txt"
    write_master_recipe(
        master_recipe,
        all_polys,
        u13_cavs,
        u13_vias,
        u13_clines,
        placed_lscs=u13_placed_lscs,
        delete_lsc_refdes=u13_del_lscs,
    )

    planes_by_l = Counter(p.layer.upper() for p in all_polys)
    voids_by_l: Counter[str] = Counter()
    for p in all_polys:
        voids_by_l[p.layer.upper()] += len(p.voids)
    vstart_by_l = Counter(v.start_layer.upper() for v in u13_vias)
    vend_by_l = Counter(v.end_layer.upper() for v in u13_vias)
    clines_by_l = Counter(c.layer.upper() for c in u13_clines)

    inv_rows = _build_27layer_inventory_table(
        cfg["stackup_all_27_layers"],
        planes_by_l, voids_by_l, vstart_by_l, vend_by_l, clines_by_l,
        base_lsc_count=len(u13_placed_lscs),
        base_cavity_count=len(u13_cavs),
    )

    bp_svg = _render_multirail_svg(
        build_dir / "Task3_U13_HBM_4Rail_27Layer_Blueprint.svg",
        "Task 3 Template Build — U13 + U41 (HBM4E 4-Rail + VSS) Full 27-Layer PDN",
        U13_DOMAIN_BBOX,
        all_polys,
        u13_vias,
        u13_cavs,
        {
            rails["vddq"]: "#10b981",
            rails["vddc"]: "#ef4444",
            rails["vddql"]: "#f59e0b",
            rails["vpp"]: "#a855f7",
            "VSS": "#38bdf8",
            "__ISOLATED__": "#facc15",
        },
    )
    base_svg = build_dir / "Task3_U13_HBM_4Rail_BASE_Curved_Recess_LSC.svg"
    render_curved_recess_inspection_svg(
        u13_raw_cavs,
        base_svg,
        header_title="Task 3 Template Build — U13 + U41 Curved Recesses & 36 Co-Pocket 180-deg LSCs",
    )
    stack_svg = _render_27layer_stackup_svg(
        build_dir / "Task3_U13_HBM_4Rail_27Layer_Stackup_Summary.svg",
        "Task 3 (HBM4E 4-Rail + EMIB) — Full 27-Layer PDN Template Build",
        inv_rows,
    )
    bat_path = _write_apd_headless_bat(
        build_dir / "Task3_U13_HBM_4Rail_run_apd_headless.bat",
        ws,
        io_cfg["source_mcm_readonly"],
        io_cfg["output_mcm_path"],
        master_recipe,
        build_dir / "Task3_apd_import_report.txt",
    )

    summary = {
        "task_id": cfg["task_id"],
        "flow_name": cfg["flow_name"],
        "validation_passed": True,
        "drc_all_pass": (
            bool(via_audit["zero_via_overlap_pass"])
            and all(via_audit["vss_span_counts"].get(sp, 0) > 0 for sp in ("9F:8F", "8F:7F", "7F:6F", "6F:5F", "5B:6B", "6B:7B", "7B:8B", "8B:9B"))
            and all(bool(r.drc_metrics["drc_pass"]) for r in u13_raw_cavs)
        ),
        "source_mcm_readonly": str((ws / io_cfg["source_mcm_readonly"]).resolve()),
        "output_mcm_path": str((ws / io_cfg["output_mcm_path"]).resolve()),
        "via_continuity_and_zero_overlap_audit": via_audit,
        "master_recipe_path": str(master_recipe),
        "blueprint_27layer_svg": str(bp_svg),
        "stackup_summary_svg": str(stack_svg),
        "base_curved_recess_svg": str(base_svg),
        "apd_headless_launcher_bat": str(bat_path),
        "apd_import_report_txt": str(build_dir / "Task3_apd_import_report.txt"),
        "layer_by_layer_27_inventory": inv_rows,
    }
    summary["confirmation_gate_json"] = str(_write_confirmation_gate_card(build_dir, cfg, summary, ws))
    (build_dir / "Task3_U13_HBM_4Rail_27Layer_Layer_By_Layer_Summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def compile_27layer_template(config_path: Path, workspace: Path | None = None) -> Dict[str, Any]:
    """Validate and compile a single 27-layer PDN JSON template into full APD deliverables."""
    ws = workspace or Path(__file__).resolve().parent.parent.parent
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    errors = validate_27layer_template_config(cfg)
    if errors:
        raise ValueError(f"Template validation failed for {config_path}:\n  - " + "\n  - ".join(errors))

    task_id = cfg["task_id"]
    if task_id == "TASK1_VDDUC_VDDCH":
        return _compile_task1(cfg, ws)
    if task_id == "TASK2_VDDC_SRAM":
        return _compile_task2(cfg, ws)
    if task_id == "TASK3_HBM_4RAIL":
        return _compile_task3(cfg, ws)
    raise ValueError(f"Unhandled task_id: {task_id}")


def compile_all_3_task_templates(workspace: Path | None = None) -> Dict[str, Any]:
    """Validate and compile all 3 designer-editable 27-layer PDN templates end-to-end."""
    t0 = time.perf_counter()
    ws = workspace or Path(__file__).resolve().parent.parent.parent
    tpl_dir = ws / "agent04_pdn_architect" / "templates"
    r1 = compile_27layer_template(tpl_dir / "task1_vdduc_vddch_27layer_template.json", ws)
    r2 = compile_27layer_template(tpl_dir / "task2_vddc_sram_27layer_template.json", ws)
    r3 = compile_27layer_template(tpl_dir / "task3_hbm_4rail_27layer_template.json", ws)
    master = {
        "runtime_sec": round(time.perf_counter() - t0, 2),
        "all_3_templates_valid_and_drc_clean": bool(r1["drc_all_pass"] and r2["drc_all_pass"] and r3["drc_all_pass"]),
        "task1": r1,
        "task2": r2,
        "task3": r3,
    }
    out_master = ws / "agent04_pdn_architect" / "reports" / "template_builds" / "all_3_tasks_template_build_audit.json"
    out_master.parent.mkdir(parents=True, exist_ok=True)
    out_master.write_text(json.dumps(master, indent=2), encoding="utf-8")
    return master


def implement_sandbox_to_mcm_with_confirmation(
    config_path: Path,
    workspace: Path | None = None,
    confirm_token: str = "",
    interactive: bool = True,
    dry_run_preflight_only: bool = False,
    timeout_sec: int = 1200,
) -> Dict[str, Any]:
    """
    Execute Stage 4 (Final Human Confirmation Gate) + Stage 5 (Headless Cadence APD .mcm Build
    & Post-Route Connectivity Audit) from a verified Sandbox build.
    """
    ws = workspace or Path(__file__).resolve().parent.parent.parent
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    summary = compile_27layer_template(config_path, ws)
    if not summary["drc_all_pass"]:
        raise RuntimeError(
            f"SANDBOX_DRC_BLOCKED: Refusing to implement {cfg['task_id']} into .mcm because Sandbox DRC failed!"
        )

    gate_path = Path(summary["confirmation_gate_json"])
    gate_data = json.loads(gate_path.read_text(encoding="utf-8"))
    src_mcm = Path(summary["source_mcm_readonly"]).resolve()
    out_mcm = Path(summary["output_mcm_path"]).resolve()
    if src_mcm == out_mcm:
        raise RuntimeError("SAFETY_LOCK: output_mcm_path matches source_mcm_readonly; refusing overwrite.")

    # Enforce explicit final human confirmation BEFORE any .mcm file is copied or modified
    approved = (confirm_token == "YES_IMPLEMENT_MCM")
    if not approved:
        if not interactive:
            raise RuntimeError(
                "FINAL_CONFIRMATION_REQUIRED: Review the Sandbox SVGs and Confirmation Gate JSON "
                f"({gate_path}), then pass --confirm-token YES_IMPLEMENT_MCM or run interactively."
            )
        print("\n" + "=" * 78)
        print(f"FINAL CONFIRMATION GATE — {summary['task_id']} ({summary['flow_name']})")
        print("=" * 78)
        print(json.dumps(gate_data, indent=2))
        print("=" * 78)
        user_reply = input("Have you inspected the Sandbox SVGs? Type 'YES_IMPLEMENT_MCM' to build the new .mcm: ").strip()
        if user_reply != "YES_IMPLEMENT_MCM":
            return {
                "status": "ABORTED_BY_USER",
                "task_id": summary["task_id"],
                "confirmation_gate_json": str(gate_path),
                "mcm_modified": False,
            }

    build_dir = ws / cfg["design_io"]["output_build_dir"]
    il_script = (ws / "agent04_pdn_architect" / "templates" / "apd_unified_27layer_template_importer.il").as_posix()
    recipe_path = Path(summary["master_recipe_path"])
    report_txt = Path(summary["apd_import_report_txt"])
    scr_path = Path(summary["apd_headless_launcher_bat"]).with_suffix(".scr")
    scr_path.write_text(
        f'skill load("{il_script}")\n'
        f'skill pdnRunUnified27LayerTemplateBatch("{recipe_path.as_posix()}" "" "{report_txt.as_posix()}")\n'
        f"exit\n"
        f"fillin no\n",
        encoding="utf-8",
    )

    if dry_run_preflight_only:
        audit_preflight = {
            "status": "CONFIRMED_PREFLIGHT_DRY_RUN",
            "task_id": summary["task_id"],
            "confirmed": True,
            "source_mcm_readonly": str(src_mcm),
            "output_mcm_target": str(out_mcm),
            "scr_path": str(scr_path),
            "report_txt_expected": str(report_txt),
        }
        (build_dir / f"{cfg['task_id']}_MCM_Implementation_Audit.json").write_text(
            json.dumps(audit_preflight, indent=2), encoding="utf-8"
        )
        return audit_preflight

    out_mcm.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_mcm, out_mcm)
    lck = out_mcm.with_name(out_mcm.name + ".lck")
    if lck.exists():
        lck.unlink()

    if report_txt.exists():
        report_txt.unlink()

    runner = CadenceBatchRunner(default_timeout=timeout_sec)
    run_res = runner.run(
        mcm_path=out_mcm,
        scr_path=scr_path,
        working_dir=build_dir,
        timeout=timeout_sec,
        bypass_lock_readonly=False,
    )

    kv: Dict[str, str] = {}
    if report_txt.exists():
        for ln in report_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                kv[k.strip()] = v.strip()

    audit = {
        "status": kv.get("STATUS", "SUCCESS" if run_res.success else "ERROR"),
        "task_id": summary["task_id"],
        "source_mcm_readonly": str(src_mcm),
        "output_mcm_path": str(out_mcm),
        "duration_sec": run_res.duration_sec,
        "apd_report": kv,
    }
    (build_dir / f"{cfg['task_id']}_MCM_Implementation_Audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile & Implement Designer-Editable 27-Layer Full PDN Templates")
    parser.add_argument("--config", type=str, default="", help="Path to a task*_27layer_template.json file")
    parser.add_argument("--all-3-tasks", action="store_true", help="Validate & compile all 3 task templates in Sandbox mode")
    parser.add_argument(
        "--stage",
        type=str,
        default="sandbox",
        choices=["sandbox", "implement-mcm"],
        help="Execution stage: 'sandbox' (zero .mcm mutation, generates SVGs & Confirmation Gate) or 'implement-mcm' (builds new .mcm after confirmation)",
    )
    parser.add_argument("--confirm-token", type=str, default="", help="Pass YES_IMPLEMENT_MCM to confirm .mcm implementation in non-interactive mode")
    parser.add_argument("--non-interactive", action="store_true", help="Fail unless --confirm-token YES_IMPLEMENT_MCM is supplied")
    args = parser.parse_args()

    if args.stage == "implement-mcm":
        if not args.config:
            raise SystemExit("ERROR: --stage implement-mcm requires --config <task*_27layer_template.json>")
        res_mcm = implement_sandbox_to_mcm_with_confirmation(
            Path(args.config).resolve(),
            confirm_token=args.confirm_token,
            interactive=not args.non_interactive,
        )
        print(json.dumps(res_mcm, indent=2))
    elif args.all_3_tasks or not args.config:
        res_all = compile_all_3_task_templates()
        print(json.dumps({
            "stage": "SANDBOX_COMPLETE_AWAITING_CONFIRMATION",
            "runtime_sec": res_all["runtime_sec"],
            "all_3_templates_valid_and_drc_clean": res_all["all_3_templates_valid_and_drc_clean"],
            "task1_gate": res_all["task1"]["confirmation_gate_json"],
            "task2_gate": res_all["task2"]["confirmation_gate_json"],
            "task3_gate": res_all["task3"]["confirmation_gate_json"],
        }, indent=2))
    else:
        res_one = compile_27layer_template(Path(args.config).resolve())
        print(json.dumps({
            "stage": "SANDBOX_COMPLETE_AWAITING_CONFIRMATION",
            "task_id": res_one["task_id"],
            "drc_all_pass": res_one["drc_all_pass"],
            "confirmation_gate_json": res_one["confirmation_gate_json"],
            "master_recipe_path": res_one["master_recipe_path"],
            "stackup_summary_svg": res_one["stackup_summary_svg"],
            "base_curved_recess_svg": res_one["base_curved_recess_svg"],
        }, indent=2))
