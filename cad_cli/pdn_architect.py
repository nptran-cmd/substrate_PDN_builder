"""
Agent 04 (PDN Architect) — 4-Stage CLI & Headless Cadence Orchestrator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cadence_runner import CadenceBatchRunner
from .pdn_prelearn import run_stage1_prelearn
from .pdn_svg_sandbox import run_stage2_3_sandbox_and_recipe


def _parse_kv_report(report_file: Path) -> Dict[str, str]:
    res: Dict[str, str] = {}
    if not report_file.exists():
        return res
    for line in report_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            res[k.strip()] = v.strip()
    return res


def run_stage4_import_recipe_to_mcm(
    mcm_path: str,
    recipe_file: str = "agent04_pdn_architect/reports/pdn_import_recipe.txt",
    save_design: bool = False,
) -> Dict[str, Any]:
    """Execute Stage 4: Stream pipe-delimited pdn_import_recipe.txt into .mcm via headless apd.exe."""
    mcm_abs = Path(mcm_path).resolve()
    recipe_abs = Path(recipe_file).resolve()
    if not recipe_abs.exists():
        raise FileNotFoundError(f"Recipe file does not exist: {recipe_abs}")

    agent_dir = Path(__file__).resolve().parent.parent
    script_dir = agent_dir / "scripts"
    reports_dir = agent_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_txt = reports_dir / "pdn_report.txt"
    summary_txt = reports_dir / "pdn_import_summary.txt"

    skill_loads = [
        script_dir / "pdn_core_batch.il",
        script_dir / "padstack_learner_batch.il",
        script_dir / "pdn_above_bu_batch.il",
        script_dir / "edtc_pdn_guard_batch.il",
        script_dir / "PTH_and_PPvia_batch.il",
        script_dir / "pdn_below_bu_batch.il",
        script_dir / "lsc_pocket_placer_batch.il",
        script_dir / "pdn_import_from_txt_batch.il",
        script_dir / "pdn_Pipeline_batch.il",
    ]
    save_str = "TRUE" if save_design else "FALSE"

    runner = CadenceBatchRunner()
    scr_path = runner.create_scr_file(
        skill_loads=skill_loads,
        skill_calls=[f'pdnDispatchBatchJob("STAGE4_IMPORT_RECIPE" "{save_str}")'],
        output_scr_path=reports_dir / f"{mcm_abs.stem}_stage4_import.scr",
    )
    run_res = runner.run(
        mcm_path=mcm_abs,
        scr_path=scr_path,
        working_dir=reports_dir,
        bypass_lock_readonly=not save_design,
    )

    kv = _parse_kv_report(report_txt)
    return {
        "status": kv.get("STATUS", "SUCCESS" if run_res.success else "ERROR"),
        "stage": "STAGE4_TXT_IMPORT",
        "mcm_path": str(mcm_abs),
        "recipe_file": str(recipe_abs),
        "vias_imported": int(kv.get("VIAS_IMPORTED", "0")),
        "clines_imported": int(kv.get("CLINES_IMPORTED", "0")),
        "edtc_guard_rings_imported": int(kv.get("EDTC_GUARD_RINGS_IMPORTED", "0")),
        "koz_shapes_imported": int(kv.get("KOZ_SHAPES_IMPORTED", "0")),
        "lsc_symbols_imported": int(kv.get("LSC_SYMBOLS_IMPORTED", "0")),
        "duration_sec": run_res.duration_sec,
        "report": kv,
    }


def run_full_4stage_pdn_flow(
    mcm_path: Optional[str] = None,
    stackup_file: Optional[str] = "specs_and_docs/design_rules/Substrate Design Rules_gid_1425021083.csv",
    design_rule_files: Optional[List[str]] = None,
    padstack_library_folder: Optional[str] = None,
    target_refdes: Optional[List[str]] = None,
    target_nets: Optional[List[str]] = None,
    vdd_vss_via_ratio: float = 1.2,
    below_bu_mode: str = "BGA_CLUSTER_4_5",
    vias_per_cluster: int = 5,
    lsc_cap_type: str = "0201",
    run_mcm_import: bool = False,
    save_design: bool = False,
    output_dir: str = "agent04_pdn_architect",
) -> Dict[str, Any]:
    """Run all 4 stages of Agent 04 (Pre-Learn -> 5-Zone Synthesis -> SVG Sandbox -> .mcm Recipe Import)."""
    out_base = Path(output_dir)
    reports_dir = out_base / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    if design_rule_files is None:
        design_rule_files = [
            "specs_and_docs/design_rules/Via Rules_gid_107930080.csv",
            "specs_and_docs/design_rules/eDTC DR_gid_1708488908.csv",
            "specs_and_docs/design_rules/BGALSC Rules_gid_2099350359.csv",
            "specs_and_docs/design_rules/Substrate Design Rules_gid_1425021083.csv",
        ]

    idx_path = str(reports_dir / "pdn_knowledge_index.json")
    s1_res = run_stage1_prelearn(
        stackup_file=stackup_file,
        design_rule_files=design_rule_files,
        padstack_library_folder=padstack_library_folder,
        mcm_path=mcm_path,
        run_headless_mcm_learner=bool(run_mcm_import and mcm_path),
        output_index_path=idx_path,
    )

    recipe_path = str(reports_dir / "pdn_import_recipe.txt")
    svg_dir = str(out_base / "svg_sandbox")
    s23_res = run_stage2_3_sandbox_and_recipe(
        knowledge_index=s1_res,
        target_refdes=target_refdes,
        target_nets=target_nets,
        vdd_vss_via_ratio=vdd_vss_via_ratio,
        below_bu_mode=below_bu_mode,
        vias_per_cluster=vias_per_cluster,
        lsc_cap_type=lsc_cap_type,
        svg_sandbox_dir=svg_dir,
        recipe_output_path=recipe_path,
    )

    s4_res: Optional[Dict[str, Any]] = None
    if run_mcm_import and mcm_path:
        s4_res = run_stage4_import_recipe_to_mcm(
            mcm_path=mcm_path,
            recipe_file=recipe_path,
            save_design=save_design,
        )

    return {
        "status": "SUCCESS",
        "stage1_prelearn": s1_res,
        "stage2_3_sandbox": s23_res,
        "stage4_mcm_import": s4_res,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 04 (PDN Architect) 4-Stage CLI")
    parser.add_argument("--mcm", type=str, default=None, help="Path to target .mcm file")
    parser.add_argument("--refdes", type=str, default="U1", help="Comma-separated RefDes list (e.g., U1,U2)")
    parser.add_argument("--nets", type=str, default="VDDC0,VSS,VDDSRAM", help="Comma-separated PDN nets")
    parser.add_argument("--ratio", type=float, default=1.2, help="Target VDD/VSS via ratio on Above-BU")
    parser.add_argument(
        "--below-bu-mode",
        type=str,
        default="BGA_CLUSTER_4_5",
        choices=["MIRROR_ABOVE_BU", "BGA_CLUSTER_4_5"],
        help="Below-BU routing strategy",
    )
    parser.add_argument("--cluster-vias", type=int, default=5, choices=[4, 5], help="Vias per BGA cluster (4 or 5)")
    parser.add_argument("--import-mcm", action="store_true", help="Run Stage 4 headless .mcm import")
    parser.add_argument("--save", action="store_true", help="Save .mcm after Stage 4 import")
    args = parser.parse_args()

    res = run_full_4stage_pdn_flow(
        mcm_path=args.mcm,
        target_refdes=[r.strip() for r in args.refdes.split(",") if r.strip()],
        target_nets=[n.strip() for n in args.nets.split(",") if n.strip()],
        vdd_vss_via_ratio=args.ratio,
        below_bu_mode=args.below_bu_mode,
        vias_per_cluster=args.cluster_vias,
        run_mcm_import=args.import_mcm,
        save_design=args.save,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
