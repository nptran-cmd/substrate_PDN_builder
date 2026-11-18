"""Curated Substrate AI Design Studio catalog — 1. PDN builder (A-to-Z Functions) & SVG discovery."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any, Dict, List


PROMPT_CATEGORIES: List[Dict[str, str]] = [
    {"id": "core_vddc_sram", "label": "1. Core (VDDC/SRAM)"},
    {"id": "uncore_vdduc", "label": "2. Uncore (VDDUC)"},
    {"id": "chiplet_vddch", "label": "3. Chiplet (VDDCH)"},
    {"id": "hbm", "label": "4. HBM"},
    {"id": "pdn_builder", "label": "5. Full A-Z & Stage 1"},
]


_RAIL_GROUP_CARD_SPECS: List[Dict[str, str]] = [
    {
        "cat": "core_vddc_sram",
        "rg": "core",
        "prefix": "core",
        "label": "Core (VDDC/SRAM)",
        "flow_skill": "vddc_vddram_routing_flow",
        "die_ref": "U9/U12/U88/U10 LDA (VDDC0 + VDD_0P8_SRAM_CC0 + VSS)",
        "default_ratio": "3:1",
        "default_dir": "VERTICAL",
    },
    {
        "cat": "uncore_vdduc",
        "rg": "uncore",
        "prefix": "uncore",
        "label": "Uncore (VDDUC)",
        "flow_skill": "uncore_vdduc_routing_flow",
        "die_ref": "U7/U5/U8/U6 LDB (VDDUC0..3 + VSS)",
        "default_ratio": "4:2",
        "default_dir": "VERTICAL",
    },
    {
        "cat": "chiplet_vddch",
        "rg": "chiplet",
        "prefix": "chiplet",
        "label": "Chiplet (VDDCH)",
        "flow_skill": "chiplet_vddch_routing_flow",
        "die_ref": "U2/U4/U3/U1 LDC (VDDCH0..3 + VSS)",
        "default_ratio": "5:2",
        "default_dir": "HORIZONTAL",
    },
    {
        "cat": "hbm",
        "rg": "hbm",
        "prefix": "hbm",
        "label": "HBM",
        "flow_skill": "hbm_vdd_routing_flow",
        "die_ref": "U13..U24 HBM4E + U41..U52 (VDDQ/VDDC/VDDQL/VPP + VSS)",
        "default_ratio": "FULL",
        "default_dir": "BOTH",
    },
]


def _build_8step_cards_for_rail_groups() -> List[Dict[str, Any]]:
    """Build ordered Step 0 (MCM Stage 1 Extract) + Steps 1..8 interactive skill cards for Core, Uncore, Chiplet, and HBM."""
    cards: List[Dict[str, Any]] = []
    for sp in _RAIL_GROUP_CARD_SPECS:
        rg = sp["rg"]
        cat = sp["cat"]
        flow_sk = sp["flow_skill"]
        die_ref = sp["die_ref"]
        dr = sp["default_ratio"]
        dd = sp["default_dir"]
        step_defs = [
            {
                "num": "0",
                "agent": "STAGE 1 / MCM EXTRACT",
                "title": "0. Extract Data from .mcm (Stage 1 -> Working Folder)",
                "summary": f"Extract BGA, bumps, eDTC, LSC, stackup, design rules & padstacks from <working_dir>/MCM_template/*.mcm into <working_dir>/stage1_inputs.",
                "layers": "Stackup & Rules",
                "svg": "stage1_inputs/stage1_data_summary.svg",
                "cmd": "python -m agent04_pdn_architect.cad_cli.stage1_input_builder",
                "prompt": (
                    "Run Stage 1 extraction (`python -m agent04_pdn_architect.cad_cli.stage1_input_builder`) against the original .mcm "
                    "inside `<working_dir>/MCM_template/` so all CSV/JSON datasets (bga_map.csv, bump_map.csv, edtc_symbols.csv, "
                    "lsc_placed_map.csv, stackup_53layers.csv, padstack_library_index.csv, stage1_master_manifest.json) "
                    f"and stage1_data_summary.svg are exported into `<working_dir>/stage1_inputs/` before running {die_ref} Steps 1-8."
                ),
            },
            {
                "num": "1",
                "agent": "STEP 1 / SURFACE",
                "title": "1. Step 1: Route on SURFACE (Ratio / FULL + Jog)",
                "summary": f"{die_ref}: FULL VIA or M:N VDD:VSS ratio with floating-bump jogging (0 floating bumps).",
                "layers": "SURFACE -> 12F",
                "svg": f"pdn_sandbox/{rg}_pdn_step1.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 1 --ratio {dr} --direction {dd}",
                "prompt": (
                    f"Use skills `step1_surface_bump_routing` and `{flow_sk}` for {die_ref}: "
                    f"route SURFACE with user ratio `{dr}` (or `FULL`, `4:2`, `5:2`, `3:1`) and strapping `{dd}` "
                    "(`VERTICAL`, `HORIZONTAL`, `BOTH`), jogging every floating bump to a via'd bump with 0 floating bumps."
                ),
            },
            {
                "num": "2",
                "agent": "STEP 2 / FRONTSIDE BU",
                "title": "2. Step 2: Transition Layer Routing (SURFACE -> 6F/7F)",
                "summary": f"{die_ref}: Stack same-net BU vias down to target layers (VDD=6F, VSS=7F; <= 7 BU stack).",
                "layers": "12F -> 6F/7F",
                "svg": f"pdn_sandbox/{rg}_pdn_step2.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 2 --vdd-top-layer 6F --vss-top-layer 7F --max-bu-stack 7",
                "prompt": (
                    f"Use skills `step2_frontside_bu_transition` and `{flow_sk}` for {die_ref}: "
                    "stack same-net BU vias downward from SURFACE to `--vdd-top-layer 6F` and `--vss-top-layer 7F`, "
                    "enforcing Max Stacked Via in BU <= 7 (<= 3 in EMIB HSIO void) and 0 pad overlap."
                ),
            },
            {
                "num": "3",
                "agent": "STEP 3 / CORE PTH",
                "title": "3. Step 3: Core PTH (4..11 PTH/mm2 + eDTC KOZ/Guard)",
                "summary": f"{die_ref}: Synthesize 4..11 PTH/mm2 (Staggered / 90deg V/H) with eDTC 300um KOZ + 150um Guard Metal.",
                "layers": "4FCO <-> 4BCO",
                "svg": f"pdn_sandbox/{rg}_pdn_step3.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 3 --pth-density 8.0 --pth-pattern STAGGERED --pkg-rule PKG0.8",
                "prompt": (
                    f"Use skills `step3_core_pth_routing` and `{flow_sk}` for {die_ref}: "
                    "route Core PTHs at `--pth-density` 4..11 PTH/mm2 (`--pkg-rule PKG0.8` for 4..9.01, `--pkg-rule PKG0.1` for 4..11) "
                    "in `STAGGERED`, `ORTHOGONAL_90DEG_VERTICAL`, or `ORTHOGONAL_90DEG_HORIZONTAL` obeying 700um eDTC KOZ + Guard Metal."
                ),
            },
            {
                "num": "4",
                "agent": "STEP 4 / PREPREG PP",
                "title": "4. Step 4: Route PP Patterns & Check Design Rule",
                "summary": f"{die_ref}: Route 1_VIA_CENTER, 2_VIA_ON_PTH, or 4_VIA_PER_PTH with Substrate DR verification.",
                "layers": "4FCO..2FCI / 2BCI..4BCO",
                "svg": f"pdn_sandbox/{rg}_pdn_step4.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 4 --pp-pattern 1_VIA_CENTER --pkg-rule PKG0.8",
                "prompt": (
                    f"Use skills `step4_prepreg_pp_routing` and `{flow_sk}` for {die_ref}: "
                    "compare Prepreg patterns `1_VIA_CENTER` (center aligned), `2_VIA_ON_PTH`, and `4_VIA_PER_PTH`, verifying against "
                    "Substrate Design Rules (Max vias/PTH pad = 1 [PKG0.1] / 2 [PKG0.8], PP-PP <= 45um, Core L/S >= 67.5um)."
                ),
            },
            {
                "num": "5",
                "agent": "STEP 5 / BGA VIAS",
                "title": "5. Step 5: BGA Vias (Opt 1-4 incl. Center ~0 Overlap)",
                "summary": f"{die_ref}: Route all Power + VSS BGAs with Opt 1..3 or Opt 4 (4 center vias +-45.5um, 0 overlap).",
                "layers": "12B <-> BASE",
                "svg": f"pdn_sandbox/{rg}_pdn_step5.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 5 --bga-pattern OPTION4_4VIA_CENTER_ZERO_OVERLAP",
                "prompt": (
                    f"Use skills `step5_bga_via_cluster_routing` and `{flow_sk}` for {die_ref}: "
                    "route 12B->BASE vias on ALL domain VDD + VSS BGA pads using Options 1..3 (`OPTION1_4VIA_SQUARE_2X2`, "
                    "`OPTION2_5VIA_QUINCUNX`, `OPTION3_6VIA_HEX_RING`) or Option 4 (`OPTION4_4VIA_CENTER_ZERO_OVERLAP`: "
                    "4 center vias at +-45.5um, 91um pitch, 0.0um pad overlap)."
                ),
            },
            {
                "num": "6",
                "agent": "STEP 6 / BASE LSC",
                "title": "6. Step 6: LSC Placement (DR + Curved Recess)",
                "summary": f"{die_ref}: Place 0201 LSCs strictly on CONDUCTOR/BASE meeting 180-deg + LSC_CAVITY recess rules.",
                "layers": "BASE + LSC_CAVITY",
                "svg": f"pdn_sandbox/{rg}_pdn_step6.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 6",
                "prompt": (
                    f"Use skills `step6_base_lsc_recess_placement` and `{flow_sk}` for {die_ref}: "
                    "place 0201 LSCs strictly on `CONDUCTOR/BASE` with Pin1=VDD/Pin2=VSS, 180-deg alternation, SRO clearance, "
                    "EMIB shadow KOZ, and curved BGA-following `LSC_CAVITY` recess (`R=508um`, BGA->Cav>=254um, LSC->Cav>=225um)."
                ),
            },
            {
                "num": "7",
                "agent": "STEP 7 / BACKSIDE BU",
                "title": "7. Step 7: Climb BGA/LSC Clusters to 6B/7B",
                "summary": f"{die_ref}: Stack BGA + LSC clusters from BASE up to transition layer below core (VDD=6B, VSS=7B).",
                "layers": "BASE -> 6B/7B",
                "svg": f"pdn_sandbox/{rg}_pdn_step7.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step 7 --bga-pattern OPTION4_4VIA_CENTER_ZERO_OVERLAP --vdd-bot-layer 6B --vss-bot-layer 7B",
                "prompt": (
                    f"Use skills `step7_backside_bu_transition` and `{flow_sk}` for {die_ref}: "
                    "climb every BGA cluster (including Option 4's 4 center ~0-overlap vias) and LSC pin via from BASE to "
                    "`--vdd-bot-layer 6B` (7 spans) / `--vss-bot-layer 7B` (6 spans) obeying <= 7 BU stack & 0 pad overlap."
                ),
            },
            {
                "num": "8",
                "agent": "STEP 8 / CORE BRIDGE",
                "title": "8. Step 8: Connect Transition <-> PP & Core (0 Overlap)",
                "summary": f"{die_ref}: Bridge 6F/7F & 6B/7B into PP/Core with 0 via overlap across all 27 conductor layers.",
                "layers": "All 27 Layers",
                "svg": f"pdn_sandbox/{rg}_pdn_all_8steps.svg",
                "cmd": f"python -m agent04_pdn_architect.cad_cli.pdn_8step_flow --rail-group {rg} --step all",
                "prompt": (
                    f"Use skills `step8_transition_pp_core_connection` and `{flow_sk}` for {die_ref}: "
                    "connect front (6F/7F->5F->4FCO) and back (6B/7B->5B->4BCO) transitions to PP & Core PTH layers and "
                    "verify full 27-layer zero via overlap via `audit_via_continuity_and_zero_overlap`."
                ),
            },
        ]
        for sd in step_defs:
            cards.append({
                "id": f"{sp['prefix']}_step{sd['num']}",
                "code": sd["num"],
                "agent": sd["agent"],
                "category": cat,
                "title": sd["title"],
                "summary": sd["summary"],
                "layers": sd["layers"],
                "default_svg": sd["svg"],
                "prompt": sd["prompt"],
                "cli_command": sd["cmd"],
            })
    return cards


# Complete 4 Rail Groups (8-Step Skills each) + Legacy A-to-Z Reference workflows
PROMPT_BUTTONS: List[Dict[str, Any]] = _build_8step_cards_for_rail_groups() + [
    {
        "id": "pdn_a_prelearn",
        "code": "A",
        "agent": "STAGE 1",
        "category": "pdn_builder",
        "title": "A. Stage 1 Data Export -> Working Folder",
        "summary": "Extract BGA, bumps, eDTC, LSC, stackup & padstacks from <working_dir>/MCM_template/*.mcm into <working_dir>/stage1_inputs.",
        "layers": "Stackup & Rules",
        "default_svg": "stage1_inputs/stage1_data_summary.svg",
        "prompt": (
            "Run Stage 1 extraction (`python -m agent04_pdn_architect.cad_cli.stage1_input_builder`) against the original .mcm "
            "inside `<working_dir>/MCM_template/` so all CSV/JSON datasets (bga_map.csv, bump_map.csv, edtc_symbols.csv, "
            "lsc_placed_map.csv, stackup_53layers.csv, padstack_library_index.csv, pdn_knowledge_index.json, "
            "stage1_master_manifest.json) and stage1_data_summary.svg are exported into <working_dir>/stage1_inputs/."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.stage1_input_builder",
    },
    {
        "id": "pdn_b_surface_l1",
        "code": "B",
        "agent": "LAYER 1",
        "category": "pdn_builder",
        "title": "B. Surface Layer 1 Bump-Via Ratio & Strapping",
        "summary": "Compare 100% VIA vs 4:2 / 5:2 / 3:1 VDD:VSS bump-via ratios and H/V/BOTH 24 um SURFACE straps.",
        "layers": "SURFACE -> 12F",
        "default_svg": "pdn_sandbox/mockup_L1_SURFACE_SideBySide_Full_vs_5to2.svg",
        "prompt": (
            "Use `surface_layer1_router.py` (`surface_layer1_routing`) on U7 (VDDUC0 and VSS) to compare "
            "100% Full VIA vs 5:2 VDD:VSS bump-via ratio with HORIZONTAL/VERTICAL/BOTH 24 um SURFACE strapping "
            "and export updated comparison SVGs."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.surface_layer1_router",
    },
    {
        "id": "pdn_c_vddc_sram",
        "code": "C",
        "agent": "COMPUTE DIE",
        "category": "pdn_builder",
        "title": "C. Co-Resident VDDC + VDDSRAM (U9, U12, U88, U10)",
        "summary": "Carve W/E SRAM islands (>=50/67.5 um gap), 10F SRAM bridge, and 3:1 SURFACE vertical jog straps.",
        "layers": "SURFACE -> BASE",
        "default_svg": "agent04_pdn_architect/reports/template_builds/task2_vddc_sram/Task2_U9_VDDC0_SRAM0_27Layer_Blueprint.svg",
        "prompt": (
            "Use `vddc_vddram_routing_flow` and `u9_vddc_sram_surface_3to1_jog_router.py` to synthesize the "
            "27-layer dual-rail PDN for U9 (VDDC0 + VDD_0P8_SRAM_CC0 + VSS) with 3:1 SURFACE jogs, 10F SRAM "
            "bridge backbone, eDTC keepouts, and updated SVG blueprint."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.u9_vddc_sram_surface_3to1_jog_router",
    },
    {
        "id": "pdn_d_core_pth_edtc",
        "code": "D",
        "agent": "CORE / eDTC",
        "category": "pdn_builder",
        "title": "D. Core PTH (4FCO<->4BCO) & eDTC KOZ Sweep",
        "summary": "Sweep 5..8 PTH/mm² (Staggered vs 90-deg H/V), 1/2-stack PP, and N24792 eDTC 300/150 um KOZ/Guard.",
        "layers": "6F..4FCO <-> 4BCO..6B",
        "default_svg": "pdn_sandbox/mockup_PTH_4FCO_4BCO_Density_5_6_7_8_Comparison.svg",
        "prompt": (
            "Use `pth_4fco_4bco_router.py` on U7 (VDDUC0 / VSS) to sweep Core PTH densities (5..8 PTH/mm²) "
            "across Staggered vs 90-deg Orthogonal H/V, apply 4FCO eDTC KOZ + 150 um Guard Metal, and refresh the SVG."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.pth_4fco_4bco_router",
    },
    {
        "id": "pdn_e_hbm_emib",
        "code": "E",
        "agent": "HBM4E / EMIB",
        "category": "pdn_builder",
        "title": "E. HBM4E 4-Rail + EMIB C0 + 10F CSB (U13..U24)",
        "summary": "West 84-90 um gang-bars, East EMIB C0 bridges, 10F CSB lateral 8F dogbones, and 4-rail inner strips.",
        "layers": "SURFACE..6F + C0",
        "default_svg": "agent04_pdn_architect/reports/template_builds/task3_hbm_4rail/Task3_U13_HBM_4Rail_27Layer_Blueprint.svg",
        "prompt": (
            "Use `hbm_vdd_routing_flow` and `hbm_surface_and_csb_router.py` to route U13 (MEM5: VDDQ, VDDC, VDDQL, "
            "VPP, HBMPHY, VSS) with West gang-bars, East EMIB C0 routing, and 10F CSB 8F dogbone escapes."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.hbm_surface_and_csb_router",
    },
    {
        "id": "pdn_f_vdduc_vddch",
        "code": "F",
        "agent": "LDB / LDC",
        "category": "pdn_builder",
        "title": "F. Single-Rail VDDUC* (U5..U8) & VDDCH* (U1..U4)",
        "summary": "Full 27-layer synthesis with 100% SURFACE VIA, 9F->5F/9B->5B stitch trunks, 4FCO eDTC & LSCs.",
        "layers": "All 27 Layers",
        "default_svg": "agent04_pdn_architect/reports/template_builds/task1_vdduc_vddch/Task1_VDDUC_VDDCH_BASE_Curved_Recess_LSC.svg",
        "prompt": (
            "Use `vdduc_vddch_routing_flow` to route U7 (VDDUC0 and VSS) and U2 (VDDCH0 and VSS) across all "
            "27 layers with 100% VIA, 4FCO eDTC stacks, unbroken 9F->5F / 9B->5B trunks, and 180-deg BASE LSCs."
        ),
        "cli_command": None,
    },
    {
        "id": "pdn_g_polygon_splitter",
        "code": "G",
        "agent": "PLANES",
        "category": "pdn_builder",
        "title": "G. Multi-Rail Co-Planar Polygon Splitter & Pruner",
        "summary": "24 inner Dynamic planes, Static 150 um EMIB/eDTC guard bands, and O(1) atomic via stack pruning.",
        "layers": "C0, 12F..12B",
        "default_svg": "agent04_pdn_architect/pdn_sandbox/mockup_Step1_Step2_U9_MultiRail.svg",
        "prompt": (
            "Use `multi_rail_polygon_engine.py` (`multi_rail_plane_polygon_splitter`) to generate inner-layer "
            "co-planar islands for U9 and U13 with Dynamic planes, Static 150 um guard bands, and atomic via pruning."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.multi_rail_polygon_engine",
    },
    {
        "id": "pdn_h_base_lsc_cavity",
        "code": "H",
        "agent": "BASE / LSC",
        "category": "pdn_builder",
        "title": "H. BASE (L27) Curved Recess Cavity & 180-deg 0201 LSC",
        "summary": "R=500 um filleted cavities, Pin 1=VDD / Pin 2=VSS, 180-deg polarity alternation & BGA 4/5/6-via clusters.",
        "layers": "10B -> BASE",
        "default_svg": "agent04_pdn_architect/reports/all_dies_all_rails/FullPackage_24Dies_BASE_Curved_Recess_LSC.svg",
        "prompt": (
            "Use `curved_recess_and_lsc_engine.py` and `base_lsc_bga_routing` to synthesize all BASE R=500 um curved "
            "recess cavities, place CONDUCTOR/BASE 0201 LSCs with 180-deg alternation (Pin 1=VDD*, Pin 2=VSS), "
            "and regenerate the BASE LSC inspection SVG."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine",
    },
    {
        "id": "pdn_i_overlap_audit",
        "code": "I",
        "agent": "AUDIT",
        "category": "pdn_builder",
        "title": "I. Zero-Via-Overlap (27 Layers) & Continuity Audit",
        "summary": "Verify 0 same-span duplicates, 0 non-concentric pad overlaps, and unbroken 9F->5F / 9B->5B trunks.",
        "layers": "27 Conductors",
        "default_svg": "agent04_pdn_architect/reports/all_dies_all_rails/FullPackage_24Dies_Domain_Audit_Summary.svg",
        "prompt": (
            "Run `audit_pdn_test_placement.py` and strict 27-layer zero-via-overlap + continuity checks on the "
            "active PDN build; report duplicate, pad-overlap, and 9F->5F / 9B->5B trunk results."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.audit_pdn_test_placement",
    },
    {
        "id": "pdn_j_full_package_sandbox",
        "code": "J",
        "agent": "FULL 24-DIE",
        "category": "pdn_builder",
        "title": "J. Full-Package 24-Die, 76-Rail 27-Layer PDN Sandbox",
        "summary": "Synthesize all 24 dies + 12 HBMs + EMIB + VSS in --sandbox-only mode and refresh Master Gate SVGs.",
        "layers": "SURFACE -> BASE",
        "default_svg": "agent04_pdn_architect/reports/all_dies_all_rails/FullPackage_24Dies_27Layer_Master_Overview.svg",
        "prompt": (
            "Run full-package 24-die 27-layer PDN synthesis (`full_package_all_dies_pdn.py --sandbox-only`), "
            "verify 0 via overlaps and continuity across all domains, and refresh the 3 Master Gate SVGs."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.full_package_all_dies_pdn --sandbox-only",
    },
    {
        "id": "pdn_k_quadrant_parallel",
        "code": "K",
        "agent": "QUADRANT",
        "category": "pdn_builder",
        "title": "K. Quadrant / Corner Subset Parallel .mcm Build",
        "summary": "Fast isolated corner build from master.tag (U1 VDDCH3, U5 VDDUC1, U12 VDDC1/SRAM1, U13 MEM5).",
        "layers": "All 27 Layers",
        "default_svg": "agent04_pdn_architect/reports/upper_left_corner/FullPackage_24Dies_27Layer_Master_Overview.svg",
        "prompt": (
            "Run `upper_left_corner_pdn.py` against active working folder `<working_dir>` (or `master.tag` in repo mode) "
            "for Upper-Left Corner U1 (VDDCH3), U5 (VDDUC1), U12 (VDDC1 + SRAM1), and U13 (MEM5) in sandbox first, "
            "exporting SVGs and reports into `<working_dir>` before preparing headless .mcm build."
        ),
        "cli_command": "python -m agent04_pdn_architect.cad_cli.upper_left_corner_pdn --hbm-dies U13 --sandbox-only",
    },
    {
        "id": "pdn_l_templates_and_qa",
        "code": "L",
        "agent": "STAGE 4 / QA",
        "category": "pdn_builder",
        "title": "L. Template Runner, Headless .mcm Build & 18-Test QA",
        "summary": "Compile JSON templates (`pdn_27layer_template_runner.py`), stream Stage 4 apd.exe import, or run 18 QA tests.",
        "layers": ".mcm Batch + QA",
        "default_svg": "agent04_pdn_architect/svg_sandbox/pdn_vertical_cross_section.svg",
        "prompt": (
            "Run `python -m unittest agent04_pdn_architect.tests.test_agent04_suite -v` or execute Stage 4 "
            "headless Cadence APD .mcm build (`--reuse-sandbox` or `pdn_27layer_template_runner.py`)."
        ),
        "cli_command": "python -m unittest agent04_pdn_architect.tests.test_agent04_suite -v",
    },
]


def _bounded_walk_files(
    root: Path,
    extensions: tuple[str, ...],
    max_depth: int = 3,
    exclude_dir_names: tuple[str, ...] = (),
) -> List[Path]:
    """Walk root up to max_depth skipping cache/VCS folders and optional excluded dirnames."""
    import os

    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}
    excluded_lower = {name.lower() for name in exclude_dir_names}
    root_resolved = root.resolve()
    root_depth = len(root_resolved.parts)
    matches: List[Path] = []
    if not root_resolved.is_dir():
        return matches
    for dirpath, dirnames, filenames in os.walk(root_resolved):
        cur = Path(dirpath)
        depth = len(cur.parts) - root_depth
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and not d.startswith(".") and d.lower() not in excluded_lower
        ]
        if depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            if fn.lower().endswith(extensions):
                matches.append(cur / fn)
    return matches


def find_mcm_template_dir(work_dir: Path | None) -> Path | None:
    """Locate the MCM_template subfolder inside work_dir (case-insensitive match)."""
    if not work_dir:
        return None
    wd = work_dir.resolve()
    if not wd.is_dir():
        return None
    exact = wd / "MCM_template"
    if exact.is_dir():
        return exact
    try:
        for entry in sorted(wd.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_dir() and entry.name.lower() == "mcm_template":
                return entry
    except OSError:
        return None
    return None


def discover_mcm_designs(workspace_root: Path, working_dir: Path | None = None) -> List[Dict[str, Any]]:
    """Find .mcm designs prioritizing <working_dir>/MCM_template/, then working_dir, then agent folders."""
    designs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    candidates: List[tuple[Path, str, bool]] = []

    wd_res = working_dir.resolve() if working_dir else None
    ws_res = workspace_root.resolve()
    tpl_dir = find_mcm_template_dir(wd_res) if wd_res else None

    if tpl_dir:
        for p in _bounded_walk_files(tpl_dir, (".mcm",), max_depth=3):
            candidates.append((p, "working_dir" if wd_res and wd_res != ws_res else "repo", True))

    if wd_res and wd_res != ws_res:
        for p in _bounded_walk_files(wd_res, (".mcm",), max_depth=3):
            in_tpl = bool(tpl_dir and tpl_dir.resolve() in p.resolve().parents)
            candidates.append((p, "working_dir", in_tpl))

    for base in (
        workspace_root / "agent04_pdn_architect" / "MCM_test",
        workspace_root / "agent08_serdes_da_gpio_routing" / "MCM_serdes_test",
        workspace_root / "mcm_designs",
    ):
        if base.exists():
            for p in base.rglob("*.mcm"):
                candidates.append((p, "repo", False))

    for p, source, is_tpl in candidates:
        try:
            abs_p = str(p.resolve())
            if abs_p in seen:
                continue
            seen.add(abs_p)
            st = p.stat()
            rel = (
                p.resolve().relative_to(wd_res).as_posix()
                if source == "working_dir" and wd_res
                else p.resolve().relative_to(ws_res).as_posix()
            )
            designs.append(
                {
                    "name": p.name,
                    "rel_path": rel,
                    "abs_path": abs_p,
                    "source": source,
                    "is_mcm_template": is_tpl,
                    "size_mb": round(st.st_size / (1024 * 1024), 1),
                    "mtime": int(st.st_mtime),
                }
            )
        except Exception:
            continue

    designs.sort(
        key=lambda d: (
            0 if d.get("is_mcm_template") else (1 if d["source"] == "working_dir" else 2),
            -d["mtime"],
        )
    )
    return designs


def _iter_agent_svg_files(workspace_root: Path) -> List[Path]:
    """Enumerate .svg files residing inside repo `agent*` and `pdn_sandbox` folders."""
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".mypy_cache", ".pytest_cache"}
    ws_res = workspace_root.resolve()
    found: List[Path] = []
    try:
        roots = [
            d for d in ws_res.iterdir()
            if d.is_dir() and (d.name.startswith("agent") or d.name == "pdn_sandbox")
        ]
    except OSError:
        return found
    for base in roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
            cur = Path(dirpath)
            for fn in filenames:
                if fn.lower().endswith(".svg"):
                    found.append(cur / fn)
    return found


def snapshot_agent_svgs(workspace_root: Path) -> Dict[str, int]:
    """Capture baseline `{abs_path: mtime_ns}` for existing agent repo SVGs before a working-dir session."""
    snap: Dict[str, int] = {}
    for p in _iter_agent_svg_files(workspace_root):
        try:
            snap[str(p.resolve())] = int(p.stat().st_mtime_ns)
        except OSError:
            continue
    return snap


def _is_complete_svg(path: Path) -> bool:
    """Confirm SVG file has closed `</svg` tag so an in-progress write is never moved prematurely."""
    try:
        sz = path.stat().st_size
        if sz <= 0:
            return False
        with path.open("rb") as fh:
            if sz > 1024:
                fh.seek(-1024, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="ignore").lower()
        return "</svg" in tail
    except OSError:
        return False


def relocate_agent_svgs_to_working_dir(
    workspace_root: Path,
    working_dir: Path,
    baseline_snapshot: Dict[str, int],
    since_ns: int,
) -> List[Dict[str, str]]:
    """
    When a custom Working Space Folder is active, ensure SVGs generated inside agent repo folders
    after `since_ns` are placed in `<working_dir>` (not left in `agent*` folders).
    Newly created SVGs are moved directly; modified baseline repo SVGs are copied without
    deleting pre-existing repo baselines.
    """
    ws_res = workspace_root.resolve()
    wd_res = working_dir.resolve()
    if wd_res == ws_res or not wd_res.is_dir() or since_ns <= 0:
        return []

    relocated: List[Dict[str, str]] = []
    for p in _iter_agent_svg_files(ws_res):
        try:
            p_res = p.resolve()
            abs_p = str(p_res)
            st = p_res.stat()
            mtime_ns = int(st.st_mtime_ns)
        except OSError:
            continue

        prev_mtime = baseline_snapshot.get(abs_p)
        is_new = prev_mtime is None
        if is_new:
            if mtime_ns < since_ns - 100_000_000:
                continue
        else:
            if mtime_ns <= prev_mtime or mtime_ns < since_ns - 100_000_000:
                continue

        if not _is_complete_svg(p_res):
            continue

        rel_ws = p_res.relative_to(ws_res)
        parts = rel_ws.parts
        dest_rel = Path(*parts[1:]) if (len(parts) > 1 and parts[0].startswith("agent")) else rel_ws
        dest = (wd_res / dest_rel).resolve()
        if not dest.is_relative_to(wd_res):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if is_new:
                shutil.move(str(p_res), str(dest))
                action = "moved"
            else:
                shutil.copy2(str(p_res), str(dest))
                baseline_snapshot[abs_p] = mtime_ns
                action = "copied"
            relocated.append(
                {
                    "action": action,
                    "name": p_res.name,
                    "from": rel_ws.as_posix(),
                    "to": f"work://{dest_rel.as_posix()}",
                }
            )
        except OSError:
            continue
    return relocated


def discover_pdn_svgs(workspace_root: Path, working_dir: Path | None = None) -> List[Dict[str, Any]]:
    """
    List .svg visualizations strictly from an active custom Working Space Folder
    (excluding MCM_template/). Returns empty list when no custom Working Folder is selected
    so agent repo baseline SVGs are never shown in the SVG viewer.
    """
    if not working_dir:
        return []
    wd_res = working_dir.resolve()
    if wd_res == workspace_root.resolve() or not wd_res.is_dir():
        return []

    svgs: List[Dict[str, Any]] = []
    seen_abs: set[str] = set()
    for p in _bounded_walk_files(wd_res, (".svg",), max_depth=6, exclude_dir_names=("mcm_template",)):
        try:
            abs_str = str(p.resolve())
            if abs_str in seen_abs:
                continue
            seen_abs.add(abs_str)
            st = p.stat()
            rel = p.resolve().relative_to(wd_res).as_posix()
            folder = p.resolve().parent.relative_to(wd_res).as_posix()
            svgs.append(
                {
                    "name": p.name,
                    "rel_path": f"work://{rel}",
                    "folder": folder,
                    "source": "working_dir",
                    "size_kb": round(st.st_size / 1024.0, 1),
                    "mtime": int(st.st_mtime),
                    "mtime_ns": int(st.st_mtime_ns),
                }
            )
        except Exception:
            continue

    svgs.sort(key=lambda item: item["mtime_ns"], reverse=True)
    return svgs
