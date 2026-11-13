"""
MCP Tool Definitions for Agent 04 (`pdn_architect`).

Exposes:
  1. prelearn_pdn_inputs       (Stage 1: Stackup + Design Rules + Padstack Library Learner)
  2. run_pdn_svg_sandbox       (Stage 2 & 3: 5-Zone Synthesis + SVG Visual Sandbox + Recipe TXT)
  3. import_pdn_recipe_to_mcm  (Stage 4: Stream pdn_import_recipe.txt into .mcm via headless apd.exe)
  4. execute_full_pdn_4stage   (End-to-End Stages 1 -> 4)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..lsc_pin_net_assigner import assign_lsc_pin_nets
from ..pdn_architect import (
    run_full_4stage_pdn_flow,
    run_stage4_import_recipe_to_mcm,
)
from ..pdn_prelearn import run_stage1_prelearn
from ..pdn_svg_sandbox import run_stage2_3_sandbox_and_recipe
from ..step1_step2_u9_u13_validator import synthesize_and_validate_step1_step2_u9_u13


def prelearn_pdn_inputs_tool(
    stackup_file: Optional[str] = "specs_and_docs/design_rules/Substrate Design Rules_gid_1425021083.csv",
    design_rule_files: Optional[List[str]] = None,
    padstack_library_folder: Optional[str] = None,
    mcm_path: Optional[str] = None,
    run_headless_mcm_learner: bool = False,
    output_index_path: str = "agent04_pdn_architect/reports/pdn_knowledge_index.json",
) -> Dict[str, Any]:
    """Stage 1 MCP Tool: Index Stackup, Design Rules (.xlsx/.csv/.pdf), and Padstack Library."""
    return run_stage1_prelearn(
        stackup_file=stackup_file,
        design_rule_files=design_rule_files,
        padstack_library_folder=padstack_library_folder,
        mcm_path=mcm_path,
        run_headless_mcm_learner=run_headless_mcm_learner,
        output_index_path=output_index_path,
    )


def run_pdn_svg_sandbox_tool(
    knowledge_index: Dict[str, Any],
    target_refdes: Optional[List[str]] = None,
    target_nets: Optional[List[str]] = None,
    layer_polarity_map: Optional[Dict[str, str]] = None,
    vdd_vss_via_ratio: float = 1.2,
    below_bu_mode: str = "BGA_CLUSTER_4_5",
    vias_per_cluster: int = 5,
    lsc_cap_type: str = "0201",
    svg_sandbox_dir: str = "agent04_pdn_architect/svg_sandbox",
    recipe_output_path: str = "agent04_pdn_architect/reports/pdn_import_recipe.txt",
) -> Dict[str, Any]:
    """Stage 2 & 3 MCP Tool: Synthesize 5 PDN zones, export 6 XML-validated SVGs, and write pdn_import_recipe.txt."""
    return run_stage2_3_sandbox_and_recipe(
        knowledge_index=knowledge_index,
        target_refdes=target_refdes,
        target_nets=target_nets,
        layer_polarity_map=layer_polarity_map,
        vdd_vss_via_ratio=vdd_vss_via_ratio,
        below_bu_mode=below_bu_mode,
        vias_per_cluster=vias_per_cluster,
        lsc_cap_type=lsc_cap_type,
        svg_sandbox_dir=svg_sandbox_dir,
        recipe_output_path=recipe_output_path,
    )


def import_pdn_recipe_to_mcm_tool(
    mcm_path: str,
    recipe_file: str = "agent04_pdn_architect/reports/pdn_import_recipe.txt",
    save_design: bool = False,
) -> Dict[str, Any]:
    """Stage 4 MCP Tool: Stream pipe-delimited pdn_import_recipe.txt into .mcm via headless apd.exe."""
    return run_stage4_import_recipe_to_mcm(
        mcm_path=mcm_path,
        recipe_file=recipe_file,
        save_design=save_design,
    )


def execute_full_pdn_4stage_tool(
    mcm_path: Optional[str] = None,
    target_refdes: Optional[List[str]] = None,
    target_nets: Optional[List[str]] = None,
    vdd_vss_via_ratio: float = 1.2,
    below_bu_mode: str = "BGA_CLUSTER_4_5",
    vias_per_cluster: int = 5,
    run_mcm_import: bool = False,
    save_design: bool = False,
) -> Dict[str, Any]:
    """End-to-End 4-Stage MCP Tool for Agent 04 (`pdn_architect`)."""
    return run_full_4stage_pdn_flow(
        mcm_path=mcm_path,
        target_refdes=target_refdes,
        target_nets=target_nets,
        vdd_vss_via_ratio=vdd_vss_via_ratio,
        below_bu_mode=below_bu_mode,
        vias_per_cluster=vias_per_cluster,
        run_mcm_import=run_mcm_import,
        save_design=save_design,
    )


def assign_lsc_pin_nets_tool(
    mcm_path: Optional[str] = None,
    mode: str = "AUTO_FROM_LAYOUT",
    map_file: Optional[str] = None,
    source_csv: Optional[str] = None,
    vdd_net: str = "VDDUC0",
    vss_net: str = "VSS",
    region_bbox_um: Optional[List[float]] = None,
    create_if_missing: bool = False,
    save_design: bool = False,
    out_mcm_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """MCP Tool: Assign or remap Pin 1 (VDD*) and Pin 2 (VSS) net names on BASE LSC symbols in .mcm."""
    bbox_tuple = (
        (float(region_bbox_um[0]), float(region_bbox_um[1]), float(region_bbox_um[2]), float(region_bbox_um[3]))
        if region_bbox_um and len(region_bbox_um) == 4
        else None
    )
    return assign_lsc_pin_nets(
        mcm_path=mcm_path,
        mode=mode,
        map_file=map_file,
        source_csv=source_csv,
        region_bbox_um=bbox_tuple,
        vdd_net=vdd_net,
        vss_net=vss_net,
        create_if_missing=create_if_missing,
        save_design=save_design,
        out_mcm_path=out_mcm_path,
        dry_run=dry_run,
    )


def synthesize_multi_rail_u9_u13_tool(
    base_mcm_path: str = "agent04_pdn_architect/MCM_test/PDN_test.mcm",
    out_mcm_path: str = "agent04_pdn_architect/MCM_test/PDN_test_Step1_Step2_U9_U13_DynPlanes_RealEDTC_RecessKOZ.mcm",
    vddc_vss_ratio: str = "3:1",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """MCP Tool: Synthesize Step 1 (multi-rail polygons) + Step 2 (HBM gang-bars & EMIB/CSB) for U9 & U13."""
    return synthesize_and_validate_step1_step2_u9_u13(
        base_mcm_path=base_mcm_path,
        out_mcm_path=out_mcm_path,
        vddc_vss_ratio=vddc_vss_ratio,
        dry_run=dry_run,
    )
