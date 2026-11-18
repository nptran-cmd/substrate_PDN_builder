"""Unit tests for the 8-Step PDN Engine, PTH 4..11/mm2, PP DRC Audit, and BGA Option 4."""

import os
import tempfile
import unittest
from pathlib import Path

from agent04_pdn_architect.cad_cli.base_lsc_bga_router import get_bga_via_offsets
from agent04_pdn_architect.cad_cli.pdn_8step_flow import run_pdn_8step_flow
from agent04_pdn_architect.cad_cli.pth_4fco_4bco_router import (
    get_pp_pattern_offsets_and_drc,
    synthesize_pth_4fco_to_4bco,
)


class Pdn8StepEngineTests(unittest.TestCase):
    def test_pth_density_4_to_11_pkg01_zero_drc(self) -> None:
        for d in (4.0, 5.0, 8.0, 9.0, 10.0, 11.0):
            for pat in ("STAGGERED", "ORTHOGONAL_90DEG_VERTICAL", "ORTHOGONAL_90DEG_HORIZONTAL"):
                plan = synthesize_pth_4fco_to_4bco(d, pattern=pat, pkg_rule="PKG0.1")
                self.assertTrue(plan["drc_verification"]["Zero_DRC_Violations"], (d, pat))
                self.assertAlmostEqual(plan["target_density_per_mm2"], d, places=1)
                self.assertEqual(plan["pths_inside_edtc_koz"], 0)

    def test_prepreg_1via_2via_4via_design_rule_audit(self) -> None:
        d1_08 = get_pp_pattern_offsets_and_drc("1_VIA_CENTER", "STAGGERED", "PKG0.8", 442.8)
        self.assertTrue(d1_08["drc_pass"])
        self.assertEqual(d1_08["status"], "PASS")

        d2_08 = get_pp_pattern_offsets_and_drc("2_VIA_ON_PTH", "ORTHOGONAL_90DEG_VERTICAL", "PKG0.8", 440.0)
        self.assertTrue(d2_08["count_rule_pass"])
        self.assertTrue(d2_08["pp_overlap_rule_pass"])
        self.assertTrue(d2_08["diff_space_pass"])

        d2_01 = get_pp_pattern_offsets_and_drc("2_VIA_ON_PTH", "STAGGERED", "PKG0.1", 360.0)
        self.assertFalse(d2_01["count_rule_pass"])
        self.assertEqual(d2_01["status"], "FAIL_DR_VIOLATION")

        d4_08 = get_pp_pattern_offsets_and_drc("4_VIA_PER_PTH", "STAGGERED", "PKG0.8", 442.8)
        self.assertFalse(d4_08["count_rule_pass"])
        self.assertEqual(d4_08["vias_per_pth"], 4)
        self.assertEqual(d4_08["status"], "FAIL_DR_VIOLATION")

    def test_bga_option4_center_zero_overlap_offsets(self) -> None:
        offs = get_bga_via_offsets("OPTION4_4VIA_CENTER_ZERO_OVERLAP")
        self.assertEqual(len(offs), 4)
        self.assertEqual(offs, [(-45.5, -45.5), (45.5, -45.5), (-45.5, 45.5), (45.5, 45.5)])
        # Pairwise center-to-center distance >= 90.0 um (2 * 45.0um V90 pad radius -> 0.0 um overlap)
        dists = [
            ((offs[i][0] - offs[j][0]) ** 2 + (offs[i][1] - offs[j][1]) ** 2) ** 0.5
            for i in range(4)
            for j in range(i + 1, 4)
        ]
        self.assertGreaterEqual(min(dists), 90.0)

    def _seed_synthetic_uncore_stage1_if_missing(self, work_dir: Path) -> None:
        """Provide a minimal synthetic Stage-1 BGA/bump grid when repo stage1_inputs CSVs are excluded (e.g. GitHub clone)."""
        repo_s1 = Path(__file__).resolve().parents[2] / "agent04_pdn_architect" / "stage1_inputs"
        if (repo_s1 / "bga_map.csv").is_file() and (repo_s1 / "bump_map.csv").is_file():
            return
        s1_dir = work_dir / "stage1_inputs"
        s1_dir.mkdir(parents=True, exist_ok=True)
        bga_rows = ["pin_number,net_name,x_um,y_um,padstack_name"]
        idx = 1
        for x in range(16000, 29001, 1000):
            for y in range(0, 31001, 1000):
                in_s_pocket = 20500 <= x <= 23500 and 5500 <= y <= 10500
                in_n_pocket = 20500 <= x <= 23500 and 18500 <= y <= 23500
                if in_s_pocket or in_n_pocket:
                    continue
                net = "VDDUC0" if ((x // 1000 + y // 1000) % 2 == 0) else "VSS"
                bga_rows.append(f"B{idx},{net},{float(x)},{float(y)},C560_35_01A")
                idx += 1
        (s1_dir / "bga_map.csv").write_text("\n".join(bga_rows) + "\n", encoding="utf-8")

        bump_rows = ["refdes,pin_number,net_name,x_um,y_um,padstack_name"]
        b_idx = 1
        for ix, x in enumerate(range(17000, 22000, 290)):
            for iy, y in enumerate(range(2000, 8000, 290)):
                net = "VDDUC0" if ((ix + iy) % 2 == 0) else "VSS"
                bump_rows.append(f"U7,P{b_idx},{net},{float(x)},{float(y)},C35_21_DP_01A")
                b_idx += 1
        (s1_dir / "bump_map.csv").write_text("\n".join(bump_rows) + "\n", encoding="utf-8")

    def test_8step_flow_uncore_and_working_dir_svg_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._seed_synthetic_uncore_stage1_if_missing(Path(tmp))
            old_wd = os.environ.get("SUBSTRATE_WORK_DIR")
            os.environ["SUBSTRATE_WORK_DIR"] = tmp
            try:
                res = run_pdn_8step_flow(
                    rail_group="uncore",
                    step="all",
                    ratio="4:2",
                    direction="VERTICAL",
                    pth_density=10.0,
                    pkg_rule="PKG0.1",
                    pp_pattern="1_VIA_CENTER",
                    bga_pattern="OPTION4_4VIA_CENTER_ZERO_OVERLAP",
                )
            finally:
                if old_wd is None:
                    os.environ.pop("SUBSTRATE_WORK_DIR", None)
                else:
                    os.environ["SUBSTRATE_WORK_DIR"] = old_wd

            self.assertTrue(res["overall_drc_pass"], res)
            st = res["steps"]
            self.assertEqual(st["step1"]["unconnected_floating_bumps"], 0)
            self.assertEqual(st["step2"]["vdd_target_layer"], "6F")
            self.assertEqual(st["step2"]["vss_target_layer"], "7F")
            self.assertLessEqual(st["step2"]["vdd_bu_stack_depth"], 7)
            self.assertTrue(st["step3"]["drc_verification"]["Zero_DRC_Violations"])
            self.assertEqual(st["step5"]["max_intra_cluster_pad_overlap_um"], 0.0)
            self.assertGreater(st["step7"]["vdd_clusters_climbed"], 0)
            self.assertGreater(st["step7"]["vss_clusters_climbed"], 0)
            self.assertEqual(st["step7"]["vdd_target_layer"], "6B")
            self.assertEqual(st["step7"]["vss_target_layer"], "7B")
            self.assertTrue(st["step8"]["all_27layers_zero_overlap_pass"])
            svg_p = Path(res["svg_file"]).resolve()
            self.assertTrue(svg_p.is_file())
            self.assertTrue(svg_p.is_relative_to(Path(tmp).resolve()))


if __name__ == "__main__":
    unittest.main()
