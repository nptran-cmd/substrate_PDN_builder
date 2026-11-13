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

import csv
import json
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


def run_stage1_prelearn(
    stackup_file: Optional[str] = None,
    design_rule_files: Optional[List[str]] = None,
    padstack_library_folder: Optional[str] = None,
    mcm_path: Optional[str] = None,
    run_headless_mcm_learner: bool = False,
    output_index_path: str = "agent04_pdn_architect/reports/pdn_knowledge_index.json",
) -> Dict[str, Any]:
    """Execute Stage 1 Pre-Learn indexing across Stackup, Design Rules, and Padstack Library."""
    zones: Dict[str, List[str]] = {k: list(v) for k, v in DEFAULT_HFC_ZONES.items()}
    rules: Dict[str, Any] = dict(DEFAULT_DESIGN_RULES)
    pad_map: Dict[str, List[str]] = scan_padstack_folder(padstack_library_folder)
    mcm_learned_summary: Dict[str, Any] = {
        "layers_from_mcm": [],
        "symbols_from_mcm": [],
        "bga_pins_sampled": 0,
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

    if run_headless_mcm_learner and mcm_path and Path(mcm_path).exists():
        agent_dir = Path(__file__).resolve().parent.parent
        script_dir = agent_dir / "scripts"
        reports_dir = agent_dir / "reports"
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
        scr_path = runner.create_scr_file(
            skill_loads=skill_loads,
            skill_calls=['pdnDispatchBatchJob("PADSTACK_LEARN" "FALSE")'],
            output_scr_path=reports_dir / "pdn_prelearn.scr",
        )
        runner.run(
            mcm_path=Path(mcm_path).resolve(),
            scr_path=scr_path,
            working_dir=reports_dir,
            bypass_lock_readonly=True,
        )
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

    out_p = Path(output_index_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(knowledge_index, indent=2), encoding="utf-8")
    return knowledge_index
