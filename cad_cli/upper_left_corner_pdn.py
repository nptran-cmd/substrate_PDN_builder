"""
Upper-Left Corner Multi-Domain 27-Layer PDN Synthesizer & Fast Headless APD Builder
===================================================================================
Reads `agent04_pdn_architect/MCM_test/master.tag` (resolving `PDN_test.mcm`),
synthesizes the Upper-Left Corner domains:
  1. `U1`  (`VDDCH3`)
  2. `U5`  (`VDDUC1`)
  3. `U12` (`VDDC1` + `VDD_0P8_SRAM_CC1`)
  4. `U13` (`MEM5` Upper-Left Corner HBM rails:
            `VDDQ_0P85_HBM_MEM5`, `VDDC_1P0_HBM_MEM5`, `VDDQL5`,
            `VPP_1P8_HBM_MEM5`, `VDD_0P75_HBMPHY_UC5`, plus `EMIB U41` & `U98`)
     (configurable via `--hbm-dies`, e.g., `U13` or `U13,U14,U15`)

Reorders the recipe so `VIA` and `CLINE` execute BEFORE `POLY_SHAPE`, and uses
`apd_fast_27layer_template_importer.il` (`axlShapeChangeDynamicType(shpObj t nil)`
followed by a single batch `axlShapeDynamicUpdate(nil t)`) so the `.mcm` build
runs in parallel in its own isolated directory without interfering with any other
running `.mcm` build.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import agent04_pdn_architect.cad_cli.full_package_all_dies_pdn as fp

MASTER_TAG_PATH = fp.WORKSPACE / "agent04_pdn_architect" / "MCM_test" / "master.tag"
DEFAULT_OUT_DIR = fp.WORKSPACE / "agent04_pdn_architect" / "reports" / "upper_left_corner"
DEFAULT_OUT_MCM = (
    fp.WORKSPACE
    / "agent04_pdn_architect"
    / "MCM_test"
    / "PDN_test_UpperLeft_VDDCH3_VDDUC1_VDDC1_SRAM1_HBM.mcm"
)
FAST_SKILL_IMPORTER = (
    fp.WORKSPACE
    / "agent04_pdn_architect"
    / "templates"
    / "apd_unified_27layer_template_importer.il"
)


def resolve_source_mcm_from_master_tag(tag_path: Path = MASTER_TAG_PATH) -> Path:
    mcm_name = tag_path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    src_mcm = tag_path.parent / mcm_name
    lck_path = Path(str(src_mcm) + ".lck")
    baseline_mcm = tag_path.parent / "PDN_test.mcm"
    if lck_path.exists() and baseline_mcm.is_file():
        return baseline_mcm
    if not src_mcm.is_file():
        if baseline_mcm.is_file():
            return baseline_mcm
        raise FileNotFoundError(f"Source MCM resolved from {tag_path} not found: {src_mcm}")
    return src_mcm


def reorder_recipe_vias_clines_before_polygons(recipe_path: Path, fast_recipe_path: Path) -> Dict[str, int]:
    """
    Reorders a generated 27-layer master recipe so:
      1. POLY_CAVITY
      2. LSC_DELETE
      3. LSC_PLACE
      4. VIA
      5. CLINE
      6. POLY_SHAPE / POLY_VOID / POLY_CLOSE (in exact original sequence)
    ensuring Cadence APD creates all vias and clines when 0 dynamic shapes exist in the DB.
    """
    cav_lines: List[str] = []
    lsc_del_lines: List[str] = []
    lsc_place_lines: List[str] = []
    via_lines: List[str] = []
    cline_lines: List[str] = []
    poly_lines: List[str] = []
    static_cnt = 0
    dyn_cnt = 0

    with recipe_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cmd = line.split("|", 1)[0].strip()
            if cmd == "POLY_CAVITY":
                cav_lines.append(line)
            elif cmd == "LSC_DELETE":
                lsc_del_lines.append(line)
            elif cmd == "LSC_PLACE":
                lsc_place_lines.append(line)
            elif cmd == "VIA":
                via_lines.append(line)
            elif cmd == "CLINE":
                cline_lines.append(line)
            elif cmd in ("POLY_SHAPE", "POLY_VOID", "POLY_CLOSE"):
                poly_lines.append(line)
                if cmd == "POLY_SHAPE":
                    parts = line.split("|")
                    if len(parts) > 3 and parts[3].strip() == "DYNAMIC":
                        dyn_cnt += 1
                    else:
                        static_cnt += 1

    with fast_recipe_path.open("w", encoding="utf-8") as out:
        out.write("# Upper-Left Corner 27-Layer Fast-Ordered Master Recipe\n")
        out.write("# Order: POLY_CAVITY -> LSC_DELETE -> LSC_PLACE -> VIA -> CLINE -> POLY_SHAPE\n")
        for l in cav_lines:
            out.write(l + "\n")
        for l in lsc_del_lines:
            out.write(l + "\n")
        for l in lsc_place_lines:
            out.write(l + "\n")
        for l in via_lines:
            out.write(l + "\n")
        for l in cline_lines:
            out.write(l + "\n")
        for l in poly_lines:
            out.write(l + "\n")

    return {
        "cavities": len(cav_lines),
        "lsc_delete": len(lsc_del_lines),
        "lsc_place": len(lsc_place_lines),
        "vias": len(via_lines),
        "clines": len(cline_lines),
        "static_polygons": static_cnt,
        "dynamic_polygons": dyn_cnt,
    }


def run_upper_left_corner_pdn(
    out_dir: Path = DEFAULT_OUT_DIR,
    out_mcm: Path = DEFAULT_OUT_MCM,
    lda_dies: Tuple[str, ...] = ("U12",),
    ldb_dies: Tuple[str, ...] = ("U5",),
    ldc_dies: Tuple[str, ...] = ("U1",),
    hbm_dies: Tuple[str, ...] = ("U13",),
    sandbox_only: bool = False,
    reuse_sandbox: bool = False,
    timeout_sec: int = 1800,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    src_mcm = resolve_source_mcm_from_master_tag()
    fast_recipe_path = out_dir / "UpperLeft_Fast_27Layer_Master_Recipe.txt"
    sandbox_json = out_dir / "AllDies_AllRails_Sandbox_Audit.json"

    if not reuse_sandbox or not fast_recipe_path.is_file():
        orig_lda = list(fp.LDA_SITES)
        orig_ldb = list(fp.LDB_SITES)
        orig_ldc = list(fp.LDC_SITES)
        orig_hbm = list(fp.HBM_SITES)
        try:
            fp.LDA_SITES = [s for s in orig_lda if s["refdes"] in set(lda_dies)]
            fp.LDB_SITES = [s for s in orig_ldb if s["refdes"] in set(ldb_dies)]
            fp.LDC_SITES = [s for s in orig_ldc if s["refdes"] in set(ldc_dies)]
            fp.HBM_SITES = [s for s in orig_hbm if s["hbm"] in set(hbm_dies)]

            audit = fp.synthesize_full_package_all_dies(
                pins_csv=fp.DEFAULT_PINS_CSV,
                out_dir=out_dir,
                dry_run_only=True,
                out_mcm_path=out_mcm,
                timeout_sec=timeout_sec,
            )
        finally:
            fp.LDA_SITES = orig_lda
            fp.LDB_SITES = orig_ldb
            fp.LDC_SITES = orig_ldc
            fp.HBM_SITES = orig_hbm

        raw_recipe = Path(audit["recipe_file"])
        fast_counts = reorder_recipe_vias_clines_before_polygons(raw_recipe, fast_recipe_path)
        audit["fast_recipe_file"] = str(fast_recipe_path)
        audit["fast_recipe_counts"] = fast_counts
        audit["source_mcm_from_master_tag"] = str(src_mcm)
        audit["target_mcm"] = str(out_mcm)
        sandbox_json.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    else:
        audit = json.loads(sandbox_json.read_text(encoding="utf-8"))

    if sandbox_only:
        return audit

    # Execute Fast Headless Cadence APD 25.1 Build in isolated directory
    t_apd0 = time.perf_counter()
    out_mcm.parent.mkdir(parents=True, exist_ok=True)
    work_mcm = out_dir / out_mcm.name
    for p_lck in (Path(str(work_mcm) + ".lck"), Path(str(out_mcm) + ".lck")):
        if p_lck.exists():
            p_lck.unlink()
    shutil.copy2(src_mcm, work_mcm)

    report_path = out_dir / "UpperLeft_apd_import_report.txt"
    prog_path = out_dir / "UpperLeft_apd_import_report.txt.progress"
    for p in (report_path, prog_path):
        if p.exists():
            p.unlink()

    skill_posix = FAST_SKILL_IMPORTER.resolve().as_posix()
    recipe_posix = fast_recipe_path.resolve().as_posix()
    report_posix = report_path.resolve().as_posix()

    scr_path = out_dir / "run_upper_left_corner.scr"
    scr_path.write_text(
        f'skill load("{skill_posix}")\n'
        f'skill pdnRunUnified27LayerTemplateBatch("{recipe_posix}" "" "{report_posix}")\n'
        f"exit\nfillin no\n",
        encoding="utf-8",
    )

    runner = fp.CadenceBatchRunner(default_timeout=timeout_sec)
    apd_res = runner.run(
        mcm_path=work_mcm,
        scr_path=scr_path,
        working_dir=out_dir,
        timeout=timeout_sec,
        bypass_lock_readonly=False,
    )
    if work_mcm.is_file():
        shutil.copy2(work_mcm, out_mcm)
        try:
            work_mcm.unlink()
        except OSError:
            pass

    parsed_report: Dict[str, str] = {}
    if report_path.is_file():
        for line in report_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                parsed_report[k.strip()] = v.strip()

    audit["apd_execution"] = {
        "success": bool(getattr(apd_res, "success", False)) and parsed_report.get("STATUS") == "SUCCESS",
        "returncode": getattr(apd_res, "exit_code", None),
        "duration_sec": round(time.perf_counter() - t_apd0, 2),
        "output_mcm": str(out_mcm),
        "output_mcm_size_bytes": out_mcm.stat().st_size if out_mcm.is_file() else 0,
        "report_path": str(report_path),
        "parsed_report": parsed_report,
    }
    build_json = out_dir / "UpperLeft_MCM_Build_Audit.json"
    build_json.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Upper-Left Corner 27-Layer PDN MCM.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-mcm", type=Path, default=DEFAULT_OUT_MCM)
    parser.add_argument(
        "--hbm-dies",
        type=str,
        default="U13",
        help="Comma-separated upper-left HBM dies to include (default: U13 [MEM5]; or U13,U14,U15).",
    )
    parser.add_argument("--sandbox-only", action="store_true")
    parser.add_argument("--reuse-sandbox", action="store_true")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    hbm_dies = tuple(x.strip() for x in args.hbm_dies.split(",") if x.strip())
    res = run_upper_left_corner_pdn(
        out_dir=args.out_dir,
        out_mcm=args.out_mcm,
        hbm_dies=hbm_dies,
        sandbox_only=args.sandbox_only,
        reuse_sandbox=args.reuse_sandbox,
        timeout_sec=args.timeout,
    )
    print(
        json.dumps(
            {
                "status": res.get("status"),
                "source_mcm_from_master_tag": res.get("source_mcm_from_master_tag"),
                "target_mcm": res.get("target_mcm"),
                "totals": res.get("totals"),
                "fast_recipe_counts": res.get("fast_recipe_counts"),
                "zero_via_overlap_pass": res.get("zero_via_overlap_audit", {}).get("zero_via_overlap_pass"),
                "polygon_clearance_pass": res.get("polygon_clearance_audit", {}).get("polygon_clearance_pass"),
                "apd_execution": res.get("apd_execution"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
