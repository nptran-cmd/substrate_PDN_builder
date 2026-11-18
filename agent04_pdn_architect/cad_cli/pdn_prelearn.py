"""
Stage 1: Pre-Learn & Multi-Format Data Indexing Engine for Agent 04 (PDN Architect).

Supports ingesting:
1. Stackup files (.xlsx, .csv, .pdf) -> Classifies layers into 6 structural zones:
   ABOVE_BU, ABOVE_PP (including 4FCO eDTC), CORE, BELOW_PP, BELOW_BU, BASE.
2. Design Rule files (.xlsx, .csv, .pdf) -> Indexes stacked via limits (BU vs PP-on-PTH),
   PTH density (8/mm² IDS, 3.5/mm² ODS) & pitch (432.5um diff, 216.5-270um same),
   4FCO eDTC rules (90_65_90 via, 1/pad, <=2 stack, 300um KOZ, 150um Guard Metal),
   and BASE LSC pocket rules (175um LSC-to-LSC, 500um BGA SRO KOZ, no LSC under eDTC).
3. Padstack Input Library Folder (.pad files) + optional headless .mcm learner
   (padstack_learner_batch.il) -> Maps padstacks to layer spans and categories.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cadence_runner import CadenceBatchRunner


DEFAULT_HFC_ZONES: Dict[str, List[str]] = {
    "ABOVE_BU": ["SURFACE", "C0", "12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F"],
    "ABOVE_PP": ["4FCO", "3FCI"],
    "CORE": ["2FCI", "1FCI", "1BCI", "2BCI"],
    "BELOW_PP": ["3BCI", "4BCO"],
    "BELOW_BU": ["5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B"],
    "BASE": ["BASE"],
}

DEFAULT_DESIGN_RULES: Dict[str, Any] = {
    "max_stacked_via_bu": 7,
    "max_stacked_via_bu_hsio_front": 3,
    "max_stacked_via_bu_hsio_back": 6,
    "max_stacked_via_on_pth": 5,
    "max_stacked_via_on_shape_pp": 9,
    "max_pp_vias_per_pth_pad": 2,
    "core_thickness_um": 1570.0,
    "pth_drill_um": 150.0,
    "pth_outer_pad_um": 282.5,
    "pth_inner_pad_um": 365.0,
    "pth_min_pitch_diff_net_um": 432.5,
    "pth_min_pitch_same_net_um": 216.5,
    "pth_density_ids_per_mm2": 8.0,
    "pth_density_ods_per_mm2": 3.5,
    "edtc_layer": "4FCO",
    "edtc_pad_min_size_um": 200.0,
    "edtc_pad_spacing_um": 50.0,
    "edtc_via_padstack": "V90_65_90_01A_L09_L10",
    "edtc_via_drill_um": 65.0,
    "edtc_via_pad_um": 90.0,
    "edtc_max_stacked_via": 2,
    "edtc_vias_per_pad": 1,
    "edtc_cavity_koz_um": 300.0,
    "edtc_cavity_to_cavity_spacing_um": 1600.0,
    "edtc_body_to_body_min_spacing_um": 2200.0,
    "edtc_guard_to_guard_outer_spacing_um": 1300.0,
    "edtc_inner_core_metal_to_cavity_spacing_um": 150.0,
    "edtc_fiducial_to_fiducial_center_spacing_um": 10000.0,
    "edtc_to_die_cavity_koz_um": 1000.0,
    "edtc_to_emib_cavity_koz_um": 1000.0,
    "edtc_guard_metal_width_um": 150.0,
    "edtc_allow_core_metal_inside_cavity": False,
    "edtc_allow_holes_in_guard_metal": False,
    "edtc_require_solid_plane_first_backside_bu": True,
    "edtc_allow_lsc_under_dtc": False,
    "lsc_0201_body_um": [600.0, 300.0],
    "lsc_0204_body_um": [500.0, 1000.0],
    "lsc_to_lsc_spacing_um": 175.0,
    "lsc_sro_to_bga_sro_spacing_um": 500.0,
}

DEFAULT_PADSTACK_MAP: Dict[str, List[str]] = {
    "CORE_PTH": ["V282_5_150_282_5_01A_2FCI_2BCI", "pth_282p5_150d"],
    "PP_VIA": [
        "V282_5_85_175_01A_L11_L12",
        "V175_85_282_5_01A_L12_L13",
        "V282_5_85_175_01A_L16_L17",
        "V175_85_282_5_01A_L17_L18",
    ],
    "BU_TO_PP_VIA": ["V90_65_121_01A_L10_L11", "V121_65_90_01A_L18_L19"],
    "BU_UVIA": ["V90_65_90_01A_L09_L10", "V90_65_90_01A_L19_L20"],
    "EDTC_VIA": ["V90_65_90_01A_L09_L10"],
    "BGA_PAD": ["c560_35_01a", "BGA"],
}


def classify_layer_into_zone(layer_name: str) -> str:
    """Classify a substrate conductor layer name into one of the 6 structural PDN zones."""
    u = layer_name.strip().upper()
    if u in {"BASE", "BOTTOM", "BOT"} or "BGA" in u:
        return "BASE"
    if u in {"SURFACE", "TOP", "C0"}:
        return "ABOVE_BU"
    if u in {"4FCO", "3FCI"} or "FCO" in u or ("3F" in u and "CI" in u):
        return "ABOVE_PP"
    if u in {"2FCI", "1FCI", "1BCI", "2BCI"} or u.startswith(("1F", "2F", "1B", "2B")):
        return "CORE"
    if u in {"3BCI", "4BCO"} or "BCO" in u or ("3B" in u and "CI" in u):
        return "BELOW_PP"
    if re.match(r"^\d+F$", u):
        return "ABOVE_BU"
    if re.match(r"^\d+B$", u):
        return "BELOW_BU"
    return "ABOVE_BU"


def read_tabular_lines_from_any_format(file_path: str | Path) -> List[List[str]]:
    """Read rows from .csv, .xlsx/.xls, or .pdf files into a unified list of string rows."""
    p = Path(file_path)
    if not p.exists():
        return []
    ext = p.suffix.lower()
    rows: List[List[str]] = []

    if ext in {".csv", ".txt"}:
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for r in reader:
                if any(cell.strip() for cell in r):
                    rows.append([cell.strip() for cell in r])
        return rows

    if ext in {".xlsx", ".xls"}:
        try:
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                for r in ws.iter_rows(values_only=True):
                    str_row = [str(c).strip() if c is not None else "" for c in r]
                    if any(str_row):
                        rows.append(str_row)
            wb.close()
            return rows
        except Exception:
            return rows

    if ext == ".pdf":
        try:
            import pypdf  # type: ignore

            reader = pypdf.PdfReader(str(p))
            for page in reader.pages:
                txt = page.extract_text() or ""
                for line in txt.splitlines():
                    tokens = [t.strip() for t in re.split(r"\s{2,}|\|", line) if t.strip()]
                    if tokens:
                        rows.append(tokens)
            return rows
        except Exception:
            return rows

    return rows


def parse_design_rules_from_rows(rows: List[List[str]], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Extract quantitative design rules from CSV/XLSX/PDF rows."""
    updated = dict(rules)
    for r in rows:
        joined = " | ".join(r)
        u = joined.upper()
        if "STACKED VIA" in u and "LANDING ON PTH" in u and "THROUGH PP" in u and "ALL" in u:
            nums = [int(x) for x in re.findall(r"\b(\d+)\b", joined) if 1 <= int(x) <= 15]
            if nums:
                updated["max_stacked_via_on_pth"] = nums[-1]
        elif "STACKED VIA" in u and "IN BU" in u and "ALL" in u:
            nums = [int(x) for x in re.findall(r"\b(\d+)\b", joined) if 1 <= int(x) <= 15]
            if nums:
                updated["max_stacked_via_bu"] = nums[-1]
        elif "TARGET PTH DENSITY" in u:
            m_ids = re.search(r"(\d+(?:\.\d+)?)\s*PTH/MM2\s*\(IDS\)", u)
            m_ods = re.search(r"(\d+(?:\.\d+)?)\s*PTH/MM2\s*\(ODS\)", u)
            if m_ids:
                updated["pth_density_ids_per_mm2"] = float(m_ids.group(1))
            if m_ods:
                updated["pth_density_ods_per_mm2"] = float(m_ods.group(1))
        elif "MIN PTH PITCH" in u and "DIFFERENT NET" in u:
            floats = [float(x) for x in re.findall(r"\b(\d{3}(?:\.\d+)?)\b", joined)]
            if floats:
                updated["pth_min_pitch_diff_net_um"] = floats[0]
        elif "DTC EDGE TO DTC CAVITY EDGE" in u:
            nums = [float(x) for x in re.findall(r"\b(\d{2,4}(?:\.\d+)?)\b", joined) if float(x) >= 100]
            if nums:
                updated["edtc_cavity_koz_um"] = nums[0]
        elif "MIN GUARD METAL WIDTH" in u and "DTC CAVITY" in u:
            nums = [float(x) for x in re.findall(r"\b(\d{2,4}(?:\.\d+)?)\b", joined) if float(x) >= 50]
            if nums:
                updated["edtc_guard_metal_width_um"] = nums[-1]
        elif "LSC NOT ALLOWED UNDER DTC" in u:
            updated["edtc_allow_lsc_under_dtc"] = False
        elif "LSC SRO EDGE TO BGA SRO EDGE" in u:
            nums = [float(x) for x in re.findall(r"\b(\d{3,4}(?:\.\d+)?)\b", joined)]
            if nums:
                updated["lsc_sro_to_bga_sro_spacing_um"] = nums[0]
    return updated


def scan_padstack_folder(padstack_folder: Optional[str | Path]) -> Dict[str, List[str]]:
    """Scan a user-provided folder of .pad files and classify padstacks by layer/role."""
    pad_map: Dict[str, List[str]] = {k: list(v) for k, v in DEFAULT_PADSTACK_MAP.items()}
    if not padstack_folder:
        return pad_map
    p = Path(padstack_folder)
    if not p.exists() or not p.is_dir():
        return pad_map

    for pad_file in sorted(p.glob("*.pad")):
        stem = pad_file.stem
        u = stem.upper()
        if "PTH" in u or ("2FCI" in u and "2BCI" in u) or "150" in u:
            if stem not in pad_map["CORE_PTH"]:
                pad_map["CORE_PTH"].append(stem)
        elif "175" in u or "L11_L12" in u or "L12_L13" in u or "L16_L17" in u or "L17_L18" in u:
            if stem not in pad_map["PP_VIA"]:
                pad_map["PP_VIA"].append(stem)
        elif "121" in u or "L10_L11" in u or "L18_L19" in u:
            if stem not in pad_map["BU_TO_PP_VIA"]:
                pad_map["BU_TO_PP_VIA"].append(stem)
        elif "560" in u or "BGA" in u:
            if stem not in pad_map["BGA_PAD"]:
                pad_map["BGA_PAD"].append(stem)
        else:
            if stem not in pad_map["BU_UVIA"]:
                pad_map["BU_UVIA"].append(stem)
    return pad_map


def find_mcm_template_dir(work_dir: Path) -> Optional[Path]:
    """Locate the MCM_template subfolder inside work_dir (case-insensitive match)."""
    wd = work_dir.resolve()
    if not wd.is_dir():
        return None
    exact = wd / "MCM_template"
    if exact.is_dir():
        return exact
    for entry in sorted(wd.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_dir() and entry.name.lower() == "mcm_template":
            return entry
    return None


def _pick_newest_mcm(paths: List[Path]) -> Optional[Path]:
    valid = [p for p in paths if p.is_file() and p.suffix.lower() == ".mcm"]
    if not valid:
        return None
    valid.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return valid[0]


def _read_master_tag_mcm(folder: Path) -> Optional[Path]:
    master_tag = folder / "master.tag"
    if not master_tag.is_file():
        return None
    for raw_ln in master_tag.read_text(encoding="utf-8", errors="ignore").splitlines():
        cand_name = raw_ln.strip()
        if cand_name.lower().endswith(".mcm"):
            cand = folder / cand_name
            if cand.is_file():
                return cand
    return None


def resolve_mcm_in_work_dir(work_dir: Path) -> Optional[Path]:
    """Find the original .mcm template in work_dir, prioritizing <work_dir>/MCM_template/ first."""
    wd = work_dir.resolve()
    if not wd.is_dir():
        return None

    # 1. Prioritize <work_dir>/MCM_template/ (origin template folder, never confused with built outputs)
    tpl_dir = find_mcm_template_dir(wd)
    if tpl_dir:
        tagged = _read_master_tag_mcm(tpl_dir)
        if tagged:
            return tagged
        direct_tpl = _pick_newest_mcm(list(tpl_dir.glob("*.mcm")))
        if direct_tpl:
            return direct_tpl
        nested_tpl = _pick_newest_mcm(list(tpl_dir.glob("*/*.mcm")))
        if nested_tpl:
            return nested_tpl

    # 2. Check master.tag or direct .mcm in work_dir root
    tagged_root = _read_master_tag_mcm(wd)
    if tagged_root:
        return tagged_root
    direct = _pick_newest_mcm(list(wd.glob("*.mcm")))
    if direct:
        return direct

    # 3. Fallback one level down
    return _pick_newest_mcm(list(wd.glob("*/*.mcm")))


def run_stage1_prelearn(
    stackup_file: Optional[str] = None,
    design_rule_files: Optional[List[str]] = None,
    padstack_library_folder: Optional[str] = None,
    mcm_path: Optional[str] = None,
    run_headless_mcm_learner: bool = False,
    output_index_path: str = "agent04_pdn_architect/reports/pdn_knowledge_index.json",
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Stage 1 Pre-Learn indexing across Stackup, Design Rules, and Padstack Library."""
    try:
        from agent04_pdn_architect.cad_cli.pdn_paths import resolve_active_work_dir
    except ImportError:
        from pdn_paths import resolve_active_work_dir  # type: ignore

    agent_dir = Path(__file__).resolve().parent.parent
    repo_root = agent_dir.parent

    eff_wd, is_custom_wd = resolve_active_work_dir(work_dir)
    if not is_custom_wd and not work_dir and not os.environ.get("SUBSTRATE_WORK_DIR", "").strip():
        eff_wd = None

    if output_index_path == "agent04_pdn_architect/reports/pdn_knowledge_index.json" and is_custom_wd and eff_wd:
        output_index_path = str(eff_wd / "stage1_inputs" / "pdn_knowledge_index.json")

    if not mcm_path and eff_wd:
        found_mcm = resolve_mcm_in_work_dir(eff_wd)
        if found_mcm:
            mcm_path = str(found_mcm)

    zones: Dict[str, List[str]] = {k: list(v) for k, v in DEFAULT_HFC_ZONES.items()}
    rules: Dict[str, Any] = dict(DEFAULT_DESIGN_RULES)
    pad_map: Dict[str, List[str]] = scan_padstack_folder(padstack_library_folder)
    mcm_learned_summary: Dict[str, Any] = {
        "layers_from_mcm": [],
        "symbols_from_mcm": [],
        "bga_pins_sampled": 0,
        "source_mcm": mcm_path or "",
        "working_dir": str(eff_wd) if eff_wd else str(repo_root),
    }

    if stackup_file and Path(stackup_file).exists():
        stk_rows = read_tabular_lines_from_any_format(stackup_file)
        rules = parse_design_rules_from_rows(stk_rows, rules)
        extracted_layers: Dict[str, List[str]] = {k: [] for k in DEFAULT_HFC_ZONES}
        for r in stk_rows:
            for cell in r:
                c = cell.strip().upper()
                if c in {
                    "SURFACE", "C0", "12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F",
                    "4FCO", "3FCI", "2FCI", "1FCI", "1BCI", "2BCI", "3BCI", "4BCO",
                    "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B", "BASE",
                }:
                    z = classify_layer_into_zone(c)
                    if c not in extracted_layers[z]:
                        extracted_layers[z].append(c)
        for z_key, z_list in extracted_layers.items():
            if z_list:
                zones[z_key] = z_list

    if design_rule_files:
        for dr_file in design_rule_files:
            if Path(dr_file).exists():
                dr_rows = read_tabular_lines_from_any_format(dr_file)
                rules = parse_design_rules_from_rows(dr_rows, rules)

    out_p = Path(output_index_path)

    if run_headless_mcm_learner and mcm_path and Path(mcm_path).exists():
        script_dir = agent_dir / "scripts"
        reports_dir = (eff_wd / "stage1_inputs") if is_custom_wd and eff_wd else (agent_dir / "reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        learned_txt = reports_dir / "pdn_mcm_learned.txt"
        report_txt = reports_dir / "pdn_prelearn_report.txt"
        summary_txt = reports_dir / "pdn_prelearn_summary.txt"

        skill_loads = [
            script_dir / "pdn_core_batch.il",
            script_dir / "padstack_learner_batch.il",
            script_dir / "pdn_Pipeline_batch.il",
        ]
        runner = CadenceBatchRunner()
        reports_dir_skill = runner.to_skill_path(reports_dir)
        scr_path = runner.create_scr_file(
            skill_loads=skill_loads,
            skill_calls=[
                f'axlSetVariable("PDN_CWD" "{reports_dir_skill}")',
                'pdnDispatchBatchJob("PADSTACK_LEARN" "FALSE")',
            ],
            output_scr_path=reports_dir / "pdn_prelearn.scr",
        )
        prev_pdn_cwd = os.environ.get("PDN_CWD")
        os.environ["PDN_CWD"] = reports_dir_skill
        try:
            runner.run(
                mcm_path=Path(mcm_path).resolve(),
                scr_path=scr_path,
                working_dir=reports_dir,
                bypass_lock_readonly=True,
            )
        finally:
            if prev_pdn_cwd is None:
                os.environ.pop("PDN_CWD", None)
            else:
                os.environ["PDN_CWD"] = prev_pdn_cwd
        if learned_txt.exists():
            with learned_txt.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("|")
                    rec = parts[0]
                    if rec == "STACKUP_LAYER" and len(parts) >= 3:
                        mcm_learned_summary["layers_from_mcm"].append(parts[2].strip())
                    elif rec == "PADSTACK" and len(parts) >= 3:
                        ps_name, cat = parts[1].strip(), parts[2].strip()
                        if cat in pad_map and ps_name not in pad_map[cat]:
                            pad_map[cat].insert(0, ps_name)
                    elif rec == "SYMBOL" and len(parts) >= 8:
                        mcm_learned_summary["symbols_from_mcm"].append({
                            "refdes": parts[1],
                            "symbol_name": parts[2],
                            "layer": parts[3],
                            "bbox": [float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])],
                        })
                    elif rec == "BGA_PIN":
                        mcm_learned_summary["bga_pins_sampled"] += 1

    knowledge_index: Dict[str, Any] = {
        "status": "SUCCESS",
        "stage": "STAGE1_PRELEARN",
        "stackup_zones": zones,
        "edtc_layer": rules["edtc_layer"],
        "design_rules": rules,
        "padstack_library_map": pad_map,
        "mcm_learned_summary": mcm_learned_summary,
    }

    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(knowledge_index, indent=2), encoding="utf-8")
    return knowledge_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1 Pre-Learn & Multi-Format Data Indexing Engine")
    parser.add_argument("--work-dir", default=None, help="Target project working folder (defaults to SUBSTRATE_WORK_DIR)")
    parser.add_argument("--mcm", default=None, help="Path to target .mcm template (auto-detected from work-dir if omitted)")
    parser.add_argument("--out-index", default="agent04_pdn_architect/reports/pdn_knowledge_index.json")
    parser.add_argument("--stackup-file", default=None)
    parser.add_argument("--design-rule", action="append", default=None)
    parser.add_argument("--padstack-dir", default=None)
    parser.add_argument("--run-apd", action="store_true", help="Run headless apd.exe PADSTACK_LEARN extractor")
    args = parser.parse_args()

    res = run_stage1_prelearn(
        stackup_file=args.stackup_file,
        design_rule_files=args.design_rule,
        padstack_library_folder=args.padstack_dir,
        mcm_path=args.mcm,
        run_headless_mcm_learner=args.run_apd,
        output_index_path=args.out_index,
        work_dir=args.work_dir,
    )
    print(json.dumps({"status": res["status"], "source_mcm": res["mcm_learned_summary"].get("source_mcm"), "working_dir": res["mcm_learned_summary"].get("working_dir")}, indent=2))


if __name__ == "__main__":
    main()
