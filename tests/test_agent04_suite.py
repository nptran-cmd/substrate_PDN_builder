"""
Unit & Integration Test Suite for Agent 04 (`pdn_architect`).

Verifies:
  1. Stage 1 Pre-Learn multi-format stackup & design rule indexing (6 zones,
     via stack depth, PTH density/pitch, 4FCO eDTC KOZ/Guard Metal, LSC rules).
  2. Stage 2 5-Zone PDN Synthesis (Above-BU VDD/VSS ratio, 4FCO eDTC landing vias
     & Guard Metal, Core PTH density solver & 5-point PPvia diamond/star clines,
     Below-BU Mirror vs 4-5 Via BGA Cluster, BASE LSC pocket learning).
  3. Stage 3 Sandbox SVG ("VSG") Export & XML validation of all 6 SVG files.
  4. Stage 4 Pipe-delimited recipe file (pdn_import_recipe.txt) generation & schema.
"""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from agent04_pdn_architect.cad_cli.pdn_prelearn import classify_layer_into_zone, run_stage1_prelearn
from agent04_pdn_architect.cad_cli.pdn_svg_sandbox import run_stage2_3_sandbox_and_recipe, solve_pth_pitch


class TestAgent04PDNArchitect(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(__file__).resolve().parent.parent.parent
        self.out_dir = self.workspace / "agent04_pdn_architect"
        self.reports_dir = self.out_dir / "reports"
        self.idx_path = self.reports_dir / "pdn_knowledge_index.json"
        self.svg_dir = self.out_dir / "svg_sandbox"
        self.recipe_path = self.reports_dir / "pdn_import_recipe.txt"

    def test_01_stage1_prelearn_stackup_and_design_rules(self) -> None:
        """Verify 6-zone layer classification and CSV design rule indexing."""
        self.assertEqual(classify_layer_into_zone("SURFACE"), "ABOVE_BU")
        self.assertEqual(classify_layer_into_zone("12F"), "ABOVE_BU")
        self.assertEqual(classify_layer_into_zone("4FCO"), "ABOVE_PP")
        self.assertEqual(classify_layer_into_zone("2FCI"), "CORE")
        self.assertEqual(classify_layer_into_zone("3BCI"), "BELOW_PP")
        self.assertEqual(classify_layer_into_zone("5B"), "BELOW_BU")
        self.assertEqual(classify_layer_into_zone("BASE"), "BASE")

        dr_files = [
            str(self.workspace / "specs_and_docs/design_rules/Via Rules_gid_107930080.csv"),
            str(self.workspace / "specs_and_docs/design_rules/eDTC DR_gid_1708488908.csv"),
            str(self.workspace / "specs_and_docs/design_rules/BGALSC Rules_gid_2099350359.csv"),
            str(self.workspace / "specs_and_docs/design_rules/Substrate Design Rules_gid_1425021083.csv"),
        ]
        idx = run_stage1_prelearn(
            stackup_file=dr_files[3],
            design_rule_files=dr_files,
            output_index_path=str(self.idx_path),
        )
        self.assertEqual(idx["status"], "SUCCESS")
        self.assertTrue(self.idx_path.exists())
        rules = idx["design_rules"]
        self.assertEqual(rules["max_stacked_via_bu"], 7)
        self.assertEqual(rules["max_stacked_via_on_pth"], 5)
        self.assertAlmostEqual(rules["pth_density_ids_per_mm2"], 8.0)
        self.assertAlmostEqual(rules["pth_density_ods_per_mm2"], 3.5)
        self.assertAlmostEqual(rules["edtc_cavity_koz_um"], 300.0)
        self.assertAlmostEqual(rules["edtc_guard_metal_width_um"], 150.0)
        self.assertFalse(rules["edtc_allow_lsc_under_dtc"])

    def test_02_pth_density_pitch_solver(self) -> None:
        """Verify Core PTH pitch solver satisfies IDS (<=8/mm²) and ODS (<=3.5/mm²)."""
        dx_ids, dy_ids, ach_ids = solve_pth_pitch(8.0, 432.5, 216.5)
        dx_ods, dy_ods, ach_ods = solve_pth_pitch(3.5, 432.5, 216.5)
        self.assertGreater(dx_ids, 350.0)
        self.assertGreater(dy_ids, 100.0)
        self.assertLessEqual(ach_ids, 8.0)
        self.assertLessEqual(ach_ods, 3.5)
        self.assertGreater(dx_ods, dx_ids)

    def test_03_stage2_3_sandbox_svgs_and_stage4_recipe(self) -> None:
        """Verify 5-Zone synthesis, XML-valid SVG export, and pipe-delimited recipe file."""
        idx = run_stage1_prelearn(output_index_path=str(self.idx_path))
        res = run_stage2_3_sandbox_and_recipe(
            knowledge_index=idx,
            target_refdes=["U1"],
            target_nets=["VDDC0", "VSS", "VDDSRAM"],
            vdd_vss_via_ratio=1.2,
            below_bu_mode="BGA_CLUSTER_4_5",
            vias_per_cluster=5,
            svg_sandbox_dir=str(self.svg_dir),
            recipe_output_path=str(self.recipe_path),
        )
        self.assertEqual(res["status"], "SUCCESS")
        metrics = res["zone_metrics"]
        self.assertGreater(metrics["zone1_above_bu_vias"], 100)
        self.assertGreaterEqual(metrics["zone1_achieved_vdd_vss_ratio"], 1.15)
        self.assertEqual(metrics["zone2_edtc_symbols_found"], 2)
        self.assertEqual(metrics["zone2_guard_metal_rings"], 4)
        self.assertGreater(metrics["zone3_core_pth_count"], 50)
        self.assertEqual(metrics["zone4_vias_per_cluster"], 5)
        self.assertGreater(metrics["zone5_lsc_placed"], 0)

        # Verify all 6 SVG files exist and pass XML ElementTree parsing
        self.assertEqual(len(res["svg_sandbox_files"]), 6)
        for svg_f in res["svg_sandbox_files"]:
            p = Path(svg_f)
            self.assertTrue(p.exists(), f"Missing SVG file: {p}")
            root = ET.fromstring(p.read_text(encoding="utf-8"))
            self.assertTrue(root.tag.endswith("svg"))

        # Verify Stage 4 pipe-delimited recipe file
        self.assertTrue(self.recipe_path.exists())
        lines = [ln for ln in self.recipe_path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        rec_types = {ln.split("|")[0] for ln in lines}
        self.assertIn("PLANE_POLARITY", rec_types)
        self.assertIn("VIA", rec_types)
        self.assertIn("CLINE", rec_types)
        self.assertIn("EDTC_GUARD", rec_types)
        self.assertIn("KOZ", rec_types)
        self.assertIn("LSC_SYM", rec_types)

    def test_04_stage1_hfc_to_docs_prepared_input_files(self) -> None:
        """Verify all Stage 1 prepared input datasets extracted from HFC_TO_docs (.mcm, Library, Symbols, Designrule)."""
        s1_dir = self.out_dir / "stage1_inputs"
        expected_files = [
            "bga_map.csv",
            "bump_map.csv",
            "bump_package_net_summary.csv",
            "die_bridge_refdes_summary.csv",
            "edtc_symbols.csv",
            "edtc_pin_map.csv",
            "lsc_placed_map.csv",
            "lsc_symbol_library.csv",
            "refdes_inventory.csv",
            "stackup_53layers.csv",
            "stackup_zones.json",
            "padstack_library_index.csv",
            "design_rules_table.csv",
            "design_rules_indexed.json",
            "stage1_master_manifest.json",
        ]
        for fname in expected_files:
            fpath = s1_dir / fname
            self.assertTrue(fpath.exists(), f"Missing Stage 1 input file: {fpath}")
            self.assertGreater(fpath.stat().st_size, 100, f"Empty Stage 1 input file: {fpath}")

    def test_05_surface_layer1_parameterized_router_and_skill(self) -> None:
        """Verify Layer 1 (SURFACE) parameterized M:N ratio & V/H/BOTH strapping router and SKILL script."""
        from agent04_pdn_architect.cad_cli.surface_layer1_router import (
            load_u7_surface_vdd_vss_bumps,
            synthesize_surface_routing,
        )

        ws = self.out_dir.parent
        vdd_pts, vss_pts = load_u7_surface_vdd_vss_bumps(ws)
        self.assertEqual(len(vdd_pts), 7584)
        self.assertEqual(len(vss_pts), 7962)

        for ratio_s in ("FULL", "4:2", "5:2", "3:1"):
            for dir_s in ("VERTICAL", "HORIZONTAL", "BOTH"):
                plan = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str=ratio_s, direction=dir_s)
                # 100% of bumps must be either via'd or strapped (0 floating bumps)
                self.assertEqual(len(plan["vdd_vias"]) + len(plan["vdd_unviad"]), 7584)
                self.assertEqual(len(plan["vss_vias"]) + len(plan["vss_unviad"]), 7962)
                self.assertGreaterEqual(plan["min_drc_clearance_um"], 40.0)

        il_path = self.out_dir / "scripts" / "surface_bump_router_batch.il"
        skill_md = self.out_dir / "skills" / "surface_layer1_routing" / "SKILL.md"
        self.assertTrue(il_path.exists())
        self.assertTrue(skill_md.exists())

    def test_06_pth_4fco_4bco_router_and_skill(self) -> None:
        """Verify 4FCO<->4BCO PTH & Prepreg Via-Stack router across densities 5..8 PTH/mm² and all 3 patterns."""
        from agent04_pdn_architect.cad_cli.pth_4fco_4bco_router import synthesize_pth_4fco_to_4bco

        for pat in ("STAGGERED", "ORTHOGONAL_90DEG_VERTICAL", "ORTHOGONAL_90DEG_HORIZONTAL"):
            for d_val in (5.0, 6.0, 7.0, 8.0):
                pl = synthesize_pth_4fco_to_4bco(
                    target_density_per_mm2=d_val,
                    pattern=pat,
                    stack_mode="1_OR_2_STACK_BY_LAYER_NET",
                )
                self.assertEqual(pl["pattern"], pat)
                self.assertTrue(pl["pitch_solver"]["drc_pitch_pass"])
                self.assertGreaterEqual(pl["pitch_solver"]["same_net_pitch_um"], 270.0)
                self.assertGreaterEqual(pl["pitch_solver"]["diff_net_pitch_um"], 432.5)
                self.assertTrue(pl["drc_verification"]["Zero_DRC_Violations"])
                self.assertEqual(pl["pths_inside_edtc_koz"], 0)
                self.assertGreater(pl["edtc_koz_excluded_sites"], 200)
                self.assertEqual(pl["vdd_pp_stack_depth"], {"top_above_core": 1, "bot_below_core": 2})
                self.assertEqual(pl["vss_pp_stack_depth"], {"top_above_core": 2, "bot_below_core": 1})

        il_path = self.out_dir / "scripts" / "pth_4fco_4bco_router_batch.il"
        skill_md = self.out_dir / "skills" / "pth_4fco_4bco_routing" / "SKILL.md"
        self.assertTrue(il_path.exists())
        self.assertTrue(skill_md.exists())

    def test_07_base_lsc_bga_router_and_skill(self) -> None:
        """Verify Step 3 (BASE/BOTTOM Layer) empty-BGA pocket learning, 0201 LSC maximization, and 3 BGA via cluster options."""
        from agent04_pdn_architect.cad_cli.base_lsc_bga_router import (
            get_bga_via_offsets,
            synthesize_base_pockets_lscs_and_bga_vias,
        )

        ws = self.out_dir.parent
        # Verify 175.0 um SRO-to-SRO rule (254 caps) across all 3 BGA via options
        expected_bga_vias = {
            "OPTION1_4VIA_SQUARE_2X2": 3476,
            "OPTION2_5VIA_QUINCUNX": 4345,
            "OPTION3_6VIA_HEX_RING": 5214,
        }
        for opt_key, exp_bga_cnt in expected_bga_vias.items():
            self.assertGreaterEqual(len(get_bga_via_offsets(opt_key)), 4)
            pl = synthesize_base_pockets_lscs_and_bga_vias(
                workspace=ws,
                bga_via_option=opt_key,
                sro_to_sro_min_um=175.0,
            )
            self.assertEqual(pl["pockets_count"], 8)
            self.assertEqual(pl["maximized_total_lscs"], 254)
            self.assertGreater(pl["maximized_total_lscs"], pl["golden_total_lscs"])
            self.assertEqual(pl["total_lsc_pad_vias_12b_to_base"], 254 * 6)
            self.assertEqual(pl["total_bga_vias_12b_to_base"], exp_bga_cnt)
            self.assertTrue(pl["drc_verification"]["Zero_SRO_Violations"])
            self.assertGreaterEqual(pl["drc_verification"]["min_measured_lsc_sro_to_lsc_sro_um"], 175.0)
            self.assertGreaterEqual(pl["drc_verification"]["min_measured_bga_sro_to_lsc_sro_um"], 500.0)

        # Verify 250.0 um SRO-to-SRO rule (195 caps vs 161 golden)
        pl_250 = synthesize_base_pockets_lscs_and_bga_vias(
            workspace=ws,
            bga_via_option="OPTION2_5VIA_QUINCUNX",
            sro_to_sro_min_um=250.0,
        )
        self.assertEqual(pl_250["maximized_total_lscs"], 195)
        self.assertTrue(pl_250["drc_verification"]["Zero_SRO_Violations"])
        self.assertGreaterEqual(pl_250["drc_verification"]["min_measured_lsc_sro_to_lsc_sro_um"], 250.0)

        il_path = self.out_dir / "scripts" / "base_lsc_bga_router_batch.il"
        skill_md = self.out_dir / "skills" / "base_lsc_bga_routing" / "SKILL.md"
        self.assertTrue(il_path.exists())
        self.assertTrue(skill_md.exists())

    def test_08_full_27layer_apd_master_exporter_and_skill(self) -> None:
        """Verify Stage 4 full 27-layer APD master exporter (every via, trace, LSC symbol, plane) and SKILL implementer."""
        from agent04_pdn_architect.cad_cli.apd_27layer_master_exporter import (
            export_full_27layer_apd_implementation,
        )

        manifest = export_full_27layer_apd_implementation(
            surface_ratio="FULL",
            surface_direction="VERTICAL",
            pth_density_per_mm2=7.0,
            pth_pattern="STAGGERED",
            bga_cluster_a_option="OPTION1_4VIA_SQUARE_2X2",
            lsc_sro_rule_um=175.0,
        )
        self.assertEqual(manifest["status"], "READY_FOR_APD_IMPLEMENTATION")
        self.assertTrue(manifest["drc_and_no_overlap_verification"]["Zero_DRC_and_Overlap_Violations"])
        self.assertTrue(manifest["drc_and_no_overlap_verification"]["Zero_Dangling_Vias"])
        self.assertEqual(manifest["drc_and_no_overlap_verification"]["dangling_via_columns_count"], 0)
        self.assertGreaterEqual(manifest["drc_and_no_overlap_verification"]["top_l09_min_7stack_to_2stack_edge_um"], 18.0)
        self.assertGreaterEqual(manifest["drc_and_no_overlap_verification"]["bottom_l20_bga_cluster_a_to_b_edge_um"], 40.0)
        self.assertGreaterEqual(manifest["drc_and_no_overlap_verification"]["bottom_l20_lsc_outer_to_inner_bar_edge_um"], 30.0)
        self.assertEqual(manifest["object_totals"]["total_0201_lsc_symbols_on_base"], 254)
        self.assertEqual(manifest["object_totals"]["total_copper_planes_l03_to_l26"], 24)
        self.assertGreater(manifest["object_totals"]["total_via_instances_all_layers"], 150000)

        for key, fpath_str in manifest["exported_files"].items():
            fpath = Path(fpath_str)
            self.assertTrue(fpath.exists(), f"Missing exported APD file ({key}): {fpath}")
            self.assertGreater(fpath.stat().st_size, 50)

        il_path = self.out_dir / "scripts" / "full_27layer_apd_implementer_batch.il"
        skill_md = self.out_dir / "skills" / "full_27layer_apd_implementation" / "SKILL.md"
        self.assertTrue(il_path.exists())
        self.assertTrue(skill_md.exists())

    def test_09_vdduc0_base_cavity_rule_and_svg(self) -> None:
        """Verify VDDUC0-only BASE LSC placement meeting both Substrate Design Rules and Mechanical Recess Cavity Rules."""
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.cad_cli.vdduc0_base_cavity_lsc_svg_generator import (
            synthesize_and_render_vdduc0_cavity_svg,
        )

        ws = self.out_dir.parent
        res_250 = synthesize_and_render_vdduc0_cavity_svg(ws, sro_to_sro_min_um=250.0)
        self.assertTrue(res_250["Zero_DRC_and_Cavity_Violations"])
        self.assertEqual(res_250["total_vdduc0_lscs"], 90)
        self.assertEqual(res_250["pocket_6_count"], 45)
        self.assertEqual(res_250["pocket_7_count"], 45)
        self.assertGreaterEqual(res_250["min_bga_sro_to_cavity_um"], 250.0)
        self.assertGreaterEqual(res_250["min_lsc_sro_to_cavity_um"], 225.0)
        self.assertGreaterEqual(res_250["min_bga_sro_to_lsc_sro_um"], 500.0)
        self.assertGreaterEqual(res_250["min_lsc_sro_to_lsc_sro_um"], 250.0)
        self.assertGreaterEqual(res_250["cavity_to_cavity_web_um"], 508.0)
        svg_250 = Path(res_250["svg_path"])
        self.assertTrue(svg_250.exists())
        ET.fromstring(svg_250.read_bytes())

        res_175 = synthesize_and_render_vdduc0_cavity_svg(ws, sro_to_sro_min_um=175.0)
        self.assertTrue(res_175["Zero_DRC_and_Cavity_Violations"])
        self.assertEqual(res_175["total_vdduc0_lscs"], 114)
        self.assertEqual(res_175["pruned_corner_count_total"], 4)
        self.assertGreaterEqual(res_175["min_lsc_sro_to_cavity_um"], 225.0)
        svg_175 = Path(res_175["svg_path"])
        self.assertTrue(svg_175.exists())
        ET.fromstring(svg_175.read_bytes())

    def test_10_vdduc_vddch_and_vddc_vddram_routing_flow_skills(self) -> None:
        """Verify both all-layer PDN domain routing flow skills (VDDUC/VDDCH and LDA VDDC/VDDRAM) and their templates/TODOs."""
        import json

        skills_root = self.out_dir / "skills"
        vdduc_dir = skills_root / "vdduc_vddch_routing_flow"
        vddc_dir = skills_root / "vddc_vddram_routing_flow"

        for req_path in (
            vdduc_dir / "SKILL.md",
            vdduc_dir / "TEMPLATE.md",
            vdduc_dir / "TODO.md",
            vdduc_dir / "templates" / "vdduc_vddch_all_layer_template.il",
            vddc_dir / "SKILL.md",
            vddc_dir / "TEMPLATE.md",
            vddc_dir / "TODO.md",
            vddc_dir / "templates" / "vddc_vddram_all_layer_template.il",
            vddc_dir / "references" / "lda_vddc0_sram0_learned_profile.json",
        ):
            self.assertTrue(req_path.exists(), f"Missing skill file: {req_path}")
            self.assertGreater(req_path.stat().st_size, 200, f"Skill file unexpectedly small: {req_path}")

        learned = json.loads((vddc_dir / "references" / "lda_vddc0_sram0_learned_profile.json").read_text(encoding="utf-8"))
        self.assertIn("U9", learned["lda_instances"])
        self.assertEqual(learned["u9_reference_learned_metrics"]["surface_c4_bumps"]["VDDC0"]["bumps"], 10664)
        self.assertEqual(learned["u9_reference_learned_metrics"]["surface_c4_bumps"]["VDD_0P8_SRAM_CC0"]["bumps"], 1007)
        self.assertEqual(learned["u9_reference_learned_metrics"]["edtc_4fco_sharing"]["total_edtc_count_for_u9"], 6)

    def test_11_hbm_vdd_routing_flow_skill(self) -> None:
        """Verify HBM (U13 / U13..U24) multi-rail VDD* + VPP* + VSS routing flow skill, template, TODO, and learned profile."""
        import json

        hbm_dir = self.out_dir / "skills" / "hbm_vdd_routing_flow"
        for req_path in (
            hbm_dir / "SKILL.md",
            hbm_dir / "TEMPLATE.md",
            hbm_dir / "TODO.md",
            hbm_dir / "templates" / "hbm_vdd_all_layer_template.il",
            hbm_dir / "references" / "hbm_u13_learned_profile.json",
        ):
            self.assertTrue(req_path.exists(), f"Missing HBM skill file: {req_path}")
            self.assertGreater(req_path.stat().st_size, 300, f"HBM skill file unexpectedly small: {req_path}")

        hbm_learned = json.loads((hbm_dir / "references" / "hbm_u13_learned_profile.json").read_text(encoding="utf-8"))
        self.assertEqual(hbm_learned["total_hbm_sites"], 12)
        self.assertIn("U13", hbm_learned["hbm_12site_channel_map"])
        u13_m = hbm_learned["u13_mem5_reference_learned_metrics"]
        self.assertEqual(u13_m["surface_dual_zone_escape"]["VDDQ_0P85_HBM_MEM5"]["u13_bumps"], 3717)
        self.assertEqual(u13_m["surface_dual_zone_escape"]["VDDC_1P0_HBM_MEM5"]["u13_bumps"], 2627)
        self.assertEqual(u13_m["surface_dual_zone_escape"]["VDDQL5"]["u13_bumps"], 1476)
        self.assertEqual(u13_m["surface_dual_zone_escape"]["VPP_1P8_HBM_MEM5"]["u13_bumps"], 774)
        self.assertEqual(u13_m["base_bga_lsc_and_recess_cavity"]["pocket_a_west_of_u41"]["lscs_inside_u41_emib_shadow"], 0)
        self.assertEqual(u13_m["base_bga_lsc_and_recess_cavity"]["pocket_b_north_of_u41"]["lscs_inside_u41_emib_shadow"], 0)

    def test_12_mcp_tools_recess_cavity_and_skill_scripts_integrity(self) -> None:
        """Verify MCP tool wrappers, pure 1D dy=0/dx=0 straps, Recess Cavity pocket metadata, and all 18 SKILL .il scripts."""
        import json
        import re
        from agent04_pdn_architect.cad_cli.base_lsc_bga_router import synthesize_base_pockets_lscs_and_bga_vias
        from agent04_pdn_architect.cad_cli.mcp.pdn_architect_tool import prelearn_pdn_inputs_tool
        from agent04_pdn_architect.cad_cli.surface_layer1_router import (
            load_u7_surface_vdd_vss_bumps,
            synthesize_surface_routing,
        )

        # 1. MCP Stage 1 wrapper
        idx = prelearn_pdn_inputs_tool(output_index_path=str(self.idx_path))
        self.assertEqual(idx["status"], "SUCCESS")

        # 2. Pure 1D dy=0 (HORIZONTAL) & dx=0 (VERTICAL) check on 3:1 SURFACE routing
        ws = self.out_dir.parent
        vdd_pts, vss_pts = load_u7_surface_vdd_vss_bumps(ws)
        p_h = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="3:1", direction="HORIZONTAL", cell_period=3)
        self.assertEqual(sum(1 for s in p_h["vdd_clines"] + p_h["vss_clines"] if abs(s[3] - s[1]) > 0.05), 0)
        p_v = synthesize_surface_routing(vdd_pts, vss_pts, ratio_str="3:1", direction="VERTICAL", cell_period=3)
        self.assertEqual(sum(1 for s in p_v["vdd_clines"] + p_v["vss_clines"] if abs(s[2] - s[0]) > 0.05), 0)

        # 3. BASE router enforce_cavity_rule=True metadata propagation
        pl_cav = synthesize_base_pockets_lscs_and_bga_vias(
            workspace=ws,
            bga_via_option="OPTION3_6VIA_HEX_RING",
            sro_to_sro_min_um=250.0,
            enforce_cavity_rule=True,
        )
        self.assertTrue(pl_cav["drc_verification"]["Zero_SRO_Violations"])
        for pck in pl_cav["pocket_breakdown"]:
            if pck["maximized_lsc_count"] > 0:
                self.assertIsNotNone(pck["cavity_info"])
                self.assertGreaterEqual(pck["min_lsc_sro_to_cavity_um"], 225.0)

        # 4. Balanced parentheses & quotes across all 18 SKILL .il scripts + fenced JSON blocks in TEMPLATE.md
        il_files = [f for f in sorted(self.out_dir.rglob("*.il")) if "MCM_test" not in f.parts]
        self.assertGreaterEqual(len(il_files), 18)
        for il_f in il_files:
            txt = il_f.read_text(encoding="utf-8")
            depth, in_str, esc, i, n = 0, False, False, 0, len(txt)
            while i < n:
                ch = txt[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == ";":
                        while i < n and txt[i] != "\n":
                            i += 1
                        continue
                    elif ch == '"':
                        in_str = True
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        self.assertGreaterEqual(depth, 0, f"Unmatched ')' in {il_f}")
                i += 1
            self.assertFalse(in_str, f"Unclosed string in {il_f}")
            self.assertEqual(depth, 0, f"Unbalanced '(' depth={depth} in {il_f}")

        for md_f in sorted(self.out_dir.rglob("TEMPLATE.md")):
            for m in re.finditer(r"```json\s*(.*?)```", md_f.read_text(encoding="utf-8"), flags=re.DOTALL):
                json.loads(m.group(1))

    def test_13_lsc_pin_net_assigner_cli_and_csv_map(self) -> None:
        """Verify standalone headless LSC Pin Net Assigner (MAP_FILE, AUTO_FROM_LAYOUT, REGION_RULE, MCP tool)."""
        import tempfile
        from agent04_pdn_architect.cad_cli.lsc_pin_net_assigner import (
            assign_lsc_pin_nets,
            build_lsc_pin_map_from_csv,
            export_lsc_pin_map_file,
        )
        from agent04_pdn_architect.cad_cli.mcp.pdn_architect_tool import assign_lsc_pin_nets_tool

        with tempfile.TemporaryDirectory() as tmpd:
            tp = Path(tmpd)
            lsc_csv = self.out_dir / "stage1_inputs" / "lsc_placed_map.csv"
            map_out, row_cnt = build_lsc_pin_map_from_csv(
                csv_path=lsc_csv,
                output_map_path=tp / "u13_lsc_map.txt",
                refdes_filter=["C203", "C204", "C208"],
            )
            self.assertEqual(row_cnt, 3)
            self.assertTrue(map_out.exists())
            txt = map_out.read_text(encoding="utf-8")
            self.assertIn("LSC_PIN_MAP|C203|", txt)
            self.assertIn("VDDC_1P0_HBM_MEM5", txt)
            self.assertIn("VDDQ_0P85_HBM_MEM5", txt)

            custom_map = export_lsc_pin_map_file(
                [{"refdes": "C_TEST_01", "pin1_net": "VDDUC0", "pin2_net": "VSS", "x": 20000.0, "y": 10000.0, "rot": 90.0}],
                tp / "custom_map.txt",
                create_if_missing=True,
            )
            dry_res = assign_lsc_pin_nets(
                mode="MAP_FILE",
                map_file=str(custom_map),
                out_dir=str(tp / "job"),
                dry_run=True,
            )
            self.assertEqual(dry_res["status"], "DRY_RUN_READY")
            self.assertEqual(dry_res["mapped_rows_count"], 1)
            self.assertTrue(Path(dry_res["scr_file"]).exists())

            mcp_dry = assign_lsc_pin_nets_tool(
                mode="REGION_RULE",
                vdd_net="VDDUC0",
                vss_net="VSS",
                region_bbox_um=[19500.0, 4900.0, 24500.0, 27500.0],
                dry_run=True,
            )
            self.assertEqual(mcp_dry["status"], "DRY_RUN_READY")

            from agent04_pdn_architect.cad_cli.lsc_pin_net_assigner import (
                place_vdduc0_lscs_with_pin_nets_to_new_mcm,
            )
            vdduc0_dry = place_vdduc0_lscs_with_pin_nets_to_new_mcm(dry_run=True)
            self.assertEqual(vdduc0_dry["status"], "DRY_RUN_READY")
            self.assertEqual(vdduc0_dry["mapped_rows_count"], 90)
            recipe_lines = [
                ln for ln in Path(vdduc0_dry["map_file"]).read_text(encoding="utf-8").splitlines()
                if ln.startswith("LSC_PIN_MAP|")
            ]
            rots = [float(ln.split("|")[6]) for ln in recipe_lines]
            self.assertEqual(rots.count(0.0), 42)
            self.assertEqual(rots.count(180.0), 42)
            self.assertEqual(rots.count(90.0), 6)

    def test_14_step1_step2_u9_u13_multirail_and_hbm(self) -> None:
        """Verify Step 1 (multi_rail_plane_polygon_splitter) + Step 2 (emib_csb_and_hbm_surface_router) on U9 & U13."""
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.cad_cli.mcp.pdn_architect_tool import synthesize_multi_rail_u9_u13_tool

        res = synthesize_multi_rail_u9_u13_tool(dry_run=True)
        self.assertEqual(res["status"], "DRY_RUN_READY")
        self.assertTrue(res["zero_via_overlap_audit"]["zero_via_overlap_pass"])
        self.assertEqual(res["zero_via_overlap_audit"]["duplicate_same_span_count"], 0)
        self.assertEqual(res["zero_via_overlap_audit"]["non_concentric_pad_overlap_count"], 0)
        self.assertEqual(res["zero_via_overlap_audit"]["concentric_diff_net_short_count"], 0)
        self.assertEqual(res["u9_metrics"]["edtc_pins_landed"], 864)
        self.assertEqual(res["u13_metrics"]["edtc_pins_landed"], 72)
        self.assertEqual(res["u13_metrics"]["top_and_csb_escape"]["u41_csb_vss_1stack"], 1855)
        self.assertEqual(
            res["u13_metrics"]["top_and_csb_escape"]["u41_csb_pwr_1stack"]
            + res["u13_metrics"]["top_and_csb_escape"]["u41_csb_pwr_2stack"],
            1199,
        )
        self.assertEqual(res["u13_metrics"]["top_and_csb_escape"]["u41_csb_9f_vddql_escapes"], 588)
        for mid_sp in ("9F:8F", "8F:7F", "7F:6F", "6F:5F", "5B:6B", "6B:7B", "7B:8B", "8B:9B"):
            self.assertGreaterEqual(res["u9_metrics"]["vss_span_counts"][mid_sp], 3000)
            self.assertGreaterEqual(res["u13_metrics"]["vss_span_counts"][mid_sp], 1000)
        self.assertGreater(res["u13_metrics"]["surface_gang_bars"], 300)
        self.assertGreater(res["u13_metrics"]["top_and_csb_escape"]["u13_west_drop_columns"], 1000)

        # Verify Dynamic Power/VSS shapes vs Static Guard Band metal + Recess KOZ recipe lines
        rec_lines = Path(res["recipe_file"]).read_text(encoding="utf-8").splitlines()
        poly_lines = [ln for ln in rec_lines if ln.startswith("POLY_SHAPE|")]
        dyn_lines = [ln for ln in poly_lines if "|DYNAMIC|" in ln]
        guard_lines = [ln for ln in poly_lines if "|STATIC_GUARD|" in ln]
        cav_lines = [ln for ln in rec_lines if ln.startswith("POLY_CAVITY|") or ln.startswith("CAVITY|")]
        lsc_place_lines = [ln for ln in rec_lines if ln.startswith("LSC_PLACE|")]
        self.assertGreater(len(dyn_lines), 540)
        self.assertEqual(len(guard_lines), 19)  # 3 EMIB 10F Guard Rings (U35,U45,U41) + 16 eDTC 4FCO/4BCO Guard Bands (8x2)
        self.assertTrue(all("__ISOLATED__" in ln for ln in guard_lines))
        self.assertEqual(len(cav_lines), 8)
        self.assertTrue(all(ln.startswith("POLY_CAVITY|") for ln in cav_lines))
        self.assertGreaterEqual(len(lsc_place_lines), 225)

        # Verify real multi-family eDTC silicon die & KOZ dimensions (018=144p, 017=48p, 016=24p)
        import csv as _csv
        from agent04_pdn_architect.cad_cli.multi_rail_polygon_engine import compute_real_edtc_profiles
        s1 = self.out_dir / "stage1_inputs"
        with (s1 / "edtc_pin_map.csv").open("r", encoding="utf-8") as f:
            epins = list(_csv.DictReader(f))
        with (s1 / "edtc_symbols.csv").open("r", encoding="utf-8") as f:
            esyms = list(_csv.DictReader(f))
        profs = compute_real_edtc_profiles(epins, esyms, ["C2215", "C2258", "C2257"])
        w_018 = round(profs["C2215"].inner_core_koz_bbox[2] - profs["C2215"].inner_core_koz_bbox[0], 1)
        h_018 = round(profs["C2215"].inner_core_koz_bbox[3] - profs["C2215"].inner_core_koz_bbox[1], 1)
        w_017 = round(profs["C2258"].inner_core_koz_bbox[2] - profs["C2258"].inner_core_koz_bbox[0], 1)
        h_017 = round(profs["C2258"].inner_core_koz_bbox[3] - profs["C2258"].inner_core_koz_bbox[1], 1)
        w_016 = round(profs["C2257"].inner_core_koz_bbox[2] - profs["C2257"].inner_core_koz_bbox[0], 1)
        h_016 = round(profs["C2257"].inner_core_koz_bbox[3] - profs["C2257"].inner_core_koz_bbox[1], 1)
        self.assertEqual((w_018, h_018), (3270.0, 5960.0))
        self.assertEqual((w_017, h_017), (2050.0, 4240.0))
        self.assertEqual((w_016, h_016), (2080.0, 2580.0))

        for svg_key in ("u9_svg", "u13_svg"):
            svg_p = Path(res[svg_key])
            self.assertTrue(svg_p.exists())
            ET.fromstring(svg_p.read_bytes())

        for sk_name in ("multi_rail_plane_polygon_splitter", "emib_csb_and_hbm_surface_router"):
            self.assertTrue((self.out_dir / "skills" / sk_name / "SKILL.md").exists())

    def test_15_u9_surface_3to1_vertical_jog_and_svg(self) -> None:
        """Verify U9 (LDA: VDDC0 + VDD_0P8_SRAM_CC0 + VSS) 3:1 partial-VIP + vertical C/S-jog SURFACE routing & SVG."""
        import csv as _csv
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.cad_cli.u9_vddc_sram_surface_3to1_jog_router import (
            render_u9_surface_3to1_inspection_svg,
            route_u9_vddc0_sram0_vss_3to1_vertical_jog,
        )

        u9_csv = self.out_dir / "stage1_inputs" / "u9_full_pins.csv"
        with u9_csv.open("r", encoding="utf-8") as fh:
            u9_pins = list(_csv.DictReader(fh))

        res = route_u9_vddc0_sram0_vss_3to1_vertical_jog(u9_pins, ratio_str="3:1", trace_width_um=15.0, min_gap_um=15.0)
        self.assertTrue(res.drc_audit["drc_pass"])
        self.assertEqual(res.drc_audit["pad_to_trace_violation_count"], 0)
        self.assertEqual(res.drc_audit["trace_to_trace_violation_count"], 0)
        self.assertEqual(res.drc_audit["vips_inside_emib_157_koz"], 0)
        self.assertEqual(res.drc_audit["unconnected_c4_bumps_total"], 0)
        self.assertGreaterEqual(res.drc_audit["min_pad_to_trace_gap_um"], 15.0)
        self.assertGreaterEqual(res.drc_audit["min_trace_to_trace_gap_um"], 15.0)

        per_net = res.stats["per_net"]
        # Neither VDDC0 nor VDD_0P8_SRAM_CC0 nor VSS uses 100% full via-on-bump:
        self.assertTrue(68.0 <= per_net["VDDC0"]["vip_pct"] <= 78.0)
        self.assertTrue(68.0 <= per_net["VDD_0P8_SRAM_CC0"]["vip_pct"] <= 78.0)
        self.assertTrue(22.0 <= per_net["VSS"]["vip_pct"] <= 30.0)
        self.assertGreater(per_net["VDD_0P8_SRAM_CC0"]["vertical_c_jogs"], 200)
        self.assertGreater(per_net["VDDC0"]["vertical_c_jogs"], 2000)
        self.assertGreater(per_net["VSS"]["vertical_c_jogs"], 7000)

        svg_path = self.out_dir / "pdn_sandbox" / "mockup_U9_SURFACE_VDDC0_SRAM0_3to1_VerticalJog.svg"
        render_u9_surface_3to1_inspection_svg(res, svg_path)
        self.assertTrue(svg_path.exists())
        ET.fromstring(svg_path.read_bytes())

    def test_16_curved_nonrect_recess_and_lsc_placement(self) -> None:
        """Verify curved BGA-following non-rectangular recess (Inverted-T, L-shape, staggered) & 180-deg LSC placement."""
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine import run_curved_recess_demo_and_audit

        res = run_curved_recess_demo_and_audit(self.workspace)
        self.assertTrue(res["all_drc_pass"])
        pks = res["pockets"]
        self.assertGreaterEqual(pks["U9_CAV_5_NW_TShape"]["placed_lsc_count"], 25)
        self.assertGreaterEqual(pks["U2_VDDCH0_NE_LShape"]["placed_lsc_count"], 31)
        self.assertGreaterEqual(pks["U13_CAV_1_Staggered_PocketA"]["placed_lsc_count"], 27)
        self.assertEqual(pks["U9_CAV_1_East_CoPocket"]["placed_lsc_count"], 51)
        for pk_metrics in pks.values():
            self.assertTrue(pk_metrics["drc_pass"])
            self.assertGreaterEqual(pk_metrics["min_bga_sro_to_cav_um"], 250.0)
            self.assertGreaterEqual(pk_metrics["min_bga_cu_to_cav_um"], 178.0)
            self.assertGreaterEqual(pk_metrics["min_lsc_sro_to_cav_um"], 225.0)
            self.assertGreaterEqual(pk_metrics["min_lsc_sro_to_sro_um"], 250.0)
            self.assertEqual(pk_metrics["emib_shadow_violations"], 0)

        svg_p = Path(res["svg_path"])
        self.assertTrue(svg_p.exists())
        ET.fromstring(svg_p.read_bytes())

    def test_17_all_3_tasks_curved_recess_and_lsc(self) -> None:
        """Verify curved BGA-following recess (POLY_CAVITY) & 180-deg LSC placement applied across all 3 PDN tasks."""
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.cad_cli.curved_recess_and_lsc_engine import (
            synthesize_all_3_tasks_curved_recess_and_lscs,
        )

        rep = synthesize_all_3_tasks_curved_recess_and_lscs(self.workspace)
        self.assertTrue(rep["all_3_tasks_drc_pass"])
        self.assertEqual(rep["total_pockets_synthesized"], 12)  # 4 Task1 + 6 Task2 + 2 Task3

        # Task 1: U7 VDDUC0 (43 + 43 with R=508um corner fillets) + U2 VDDCH0 (36 + 32) = 154 LSCs
        self.assertGreaterEqual(rep["task1_vdduc_vddch"]["total_lscs"], 152)
        # Task 2: U9 VDDC0 + VDD_0P8_SRAM_CC0 (6 pockets = 196 LSCs, incl. 40 SRAM0)
        self.assertEqual(rep["task2_vddc_sram"]["total_lscs"], 196)
        self.assertGreaterEqual(rep["task2_vddc_sram"]["lsc_by_rail"].get("VDD_0P8_SRAM_CC0", 0), 36)
        # Task 3: U13 HBM4E Pocket A (VDDC+VDDQ) + Pocket B (VDDQL5) >= 33 LSCs
        self.assertGreaterEqual(rep["task3_hbm_4rail"]["total_lscs"], 33)
        self.assertEqual(rep["task3_hbm_4rail"]["lsc_by_rail"].get("VDDQL5", 0), 6)

        for tkey in ("task1_vdduc_vddch", "task2_vddc_sram", "task3_hbm_4rail"):
            svg_p = Path(rep[tkey]["svg_path"])
            rec_p = Path(rep[tkey]["recipe_path"])
            self.assertTrue(svg_p.exists())
            self.assertTrue(rec_p.exists())
            ET.fromstring(svg_p.read_bytes())
            self.assertIn("POLY_CAVITY|", rec_p.read_text(encoding="utf-8"))

    def test_18_designer_27layer_templates_all_3_tasks(self) -> None:
        """Verify designer-editable 27-layer JSON templates, DRC validator, and full 3-task compiler."""
        import copy
        import json
        import xml.etree.ElementTree as ET
        from agent04_pdn_architect.templates.pdn_27layer_template_runner import (
            compile_all_3_task_templates,
            implement_sandbox_to_mcm_with_confirmation,
            validate_27layer_template_config,
        )

        tpl_dir = self.out_dir / "templates"
        for fname in (
            "task1_vdduc_vddch_27layer_template.json",
            "task2_vddc_sram_27layer_template.json",
            "task3_hbm_4rail_27layer_template.json",
        ):
            cfg = json.loads((tpl_dir / fname).read_text(encoding="utf-8"))
            self.assertEqual(len(cfg["stackup_all_27_layers"]), 27)
            self.assertEqual(validate_27layer_template_config(cfg), [])

            # Verify validator catches unsafe edits (e.g. overwriting PDN_test.mcm or BU split < 50um)
            bad_cfg = copy.deepcopy(cfg)
            bad_cfg["design_io"]["output_mcm_path"] = bad_cfg["design_io"]["source_mcm_readonly"]
            bad_cfg["stackup_all_27_layers"][2]["split_gap_um"] = 30.0
            errs = validate_27layer_template_config(bad_cfg)
            self.assertGreaterEqual(len(errs), 2)

        master = compile_all_3_task_templates(self.workspace)
        self.assertTrue(master["all_3_templates_valid_and_drc_clean"])
        for tk in ("task1", "task2", "task3"):
            t_res = master[tk]
            self.assertTrue(t_res["drc_all_pass"])
            self.assertEqual(len(t_res["layer_by_layer_27_inventory"]), 27)
            self.assertTrue(Path(t_res["master_recipe_path"]).exists())
            self.assertTrue(Path(t_res["apd_headless_launcher_bat"]).exists())
            gate_p = Path(t_res["confirmation_gate_json"])
            self.assertTrue(gate_p.exists())
            gate_obj = json.loads(gate_p.read_text(encoding="utf-8"))
            self.assertEqual(gate_obj["gate_status"], "READY_FOR_FINAL_HUMAN_CONFIRMATION")
            ET.fromstring(Path(t_res["stackup_summary_svg"]).read_bytes())
            ET.fromstring(Path(t_res["base_curved_recess_svg"]).read_bytes())

        # Verify Final Confirmation Gate strictly blocks .mcm implementation without confirmation token!
        t2_cfg = tpl_dir / "task2_vddc_sram_27layer_template.json"
        with self.assertRaises(RuntimeError) as ctx:
            implement_sandbox_to_mcm_with_confirmation(
                t2_cfg,
                workspace=self.workspace,
                confirm_token="",
                interactive=False,
                dry_run_preflight_only=True,
            )
        self.assertIn("FINAL_CONFIRMATION_REQUIRED", str(ctx.exception))

        preflight = implement_sandbox_to_mcm_with_confirmation(
            t2_cfg,
            workspace=self.workspace,
            confirm_token="YES_IMPLEMENT_MCM",
            interactive=False,
            dry_run_preflight_only=True,
        )
        self.assertEqual(preflight["status"], "CONFIRMED_PREFLIGHT_DRY_RUN")
        self.assertTrue(Path(preflight["scr_path"]).exists())


if __name__ == "__main__":
    unittest.main()
