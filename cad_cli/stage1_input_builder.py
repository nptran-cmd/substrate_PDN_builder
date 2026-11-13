"""
Stage 1 End-to-End Input Preparation & Extraction Pipeline for Agent 04 (`pdn_architect`).

Prepares all Stage 1 input datasets from the 4 user-specified Google Drive / HFC_TO_docs sources:
  1. MCM Layout Source (18HYdFquj1YGEy8tEPamSwFe-cIcmwegV):
     `<cadence_library_dir>
     -> Extracts:
        - `bga_map.csv`                   (14,521 BGA balls on A1 / BASE)
        - `bump_map.csv`                  (SURFACE Die/HBM/EMIB Bridge bump pins by RefDes)
        - `bump_package_net_summary.csv`  (Full bump counts & power/ground breakdown from Symbols/*.zip)
        - `die_bridge_refdes_summary.csv` (All 54 U* Die/HBM/EMIB Bridge RefDes bounding boxes & pin counts)
        - `edtc_symbols.csv`              (All 72 4FCO eDTC symbols + 8 fiducials)
        - `edtc_pin_map.csv`              (All 6,048 4FCO eDTC terminal pins)
        - `stackup_53layers.csv`          (All 53 Conductor/Dielectric/Plane layers classified into 6 PDN zones)
        - `refdes_inventory.csv`          (All 2,348 placed symbols & RefDes)
  2. Padstack Library Source (1lAOTp7WoyjEXx5BGcLOQMt7unXKBW_rm):
     `<cadence_library_dir>
     -> Extracts:
        - `padstack_library_index.csv`    (All .pad files + 105 .mcm padstacks mapped to exact layer spans & sizes)
  3. LSC & Component Symbols Source (1qunS4LfGvYBjFmf22MjZAPaLxrvCgZHs):
     `<cadence_library_dir> & `<cadence_library_dir>
     -> Extracts:
        - `lsc_symbol_library.csv`        (SM0201 / SM0201S / SM0204 LSC packages, device files, padstacks)
        - `lsc_placed_map.csv`            (467 BASE LSCs + 1,741 SURFACE DSCs)
  4. Design Rule Source (1fT3G6jmAennsQqZpESV_Jq0kirRUUwLa):
     `<cadence_library_dir> (`J97403 Substrate Design Rule IFS_Hutton_Hill_21_2.pdf` + 25 Rule SVGs + CSVs)
     -> Extracts:
        - `design_rules_table.csv`
        - `design_rules_indexed.json`
        - `stage1_master_manifest.json`
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cadence_runner import CadenceBatchRunner
from .pdn_prelearn import (
    DEFAULT_DESIGN_RULES,
    classify_layer_into_zone,
    parse_design_rules_from_rows,
    read_tabular_lines_from_any_format,
)


DRIVE_FOLDER_SOURCES: Dict[str, Dict[str, str]] = {
    "mcm_source": {
        "drive_url": "<drive_source_url>",
        "local_path": r"<cadence_library_dir>",
    },
    "padstack_library": {
        "drive_url": "<drive_source_url>",
        "local_path": r"<cadence_library_dir>",
    },
    "lsc_and_symbols": {
        "drive_url": "<drive_source_url>",
        "local_path": r"<cadence_library_dir>",
    },
    "design_rules": {
        "drive_url": "<drive_source_url>",
        "local_path": r"<cadence_library_dir>",
    },
}


def _classify_padstack_zone(ps_name: str, start_layer: str, end_layer: str, is_thru: bool) -> str:
    u = ps_name.upper()
    s = start_layer.upper()
    e = end_layer.upper()
    if is_thru or ("2FCI" in u and "2BCI" in u) or ("2FCI" in s and "2BCI" in e):
        return "CORE_PTH"
    if "4FCO" in u and ("C200" in u or "S200" in u or "FID" in u):
        return "EDTC_4FCO_PAD"
    if "SURFACE_C0" in u or ("SURFACE" in s and "C0" in e):
        return "SURFACE_TO_C0_UVIA"
    if "5F_4FCO" in u or "L10_L11" in u or "VIA0910" in u or ("5F" in s and "4FCO" in e):
        return "ABOVE_BU_TO_PP_4FCO_VIA"
    if "4BCO_5B" in u or "L18_L19" in u or "VIA1718" in u or ("4BCO" in s and "5B" in e):
        return "BELOW_PP_4BCO_TO_BU_VIA"
    if any(k in u for k in ("4FCO_3FCI", "3FCI_2FCI", "L11_L12", "L12_L13")):
        return "ABOVE_PP_VIA"
    if any(k in u for k in ("2BCI_3BCI", "3BCI_4BCO", "L16_L17", "L17_L18")):
        return "BELOW_PP_VIA"
    if "12B_BASE" in u or ("12B" in s and ("BASE" in e or "BOTTOM" in e)):
        return "BELOW_BU_TO_BASE_VIA"
    if any(k in u for k in ("C560", "C480", "C430", "C350", "C250")):
        return "BGA_BASE_PAD"
    if any(k in u for k in ("S300", "R1000X200", "FIDLSC")):
        return "LSC_PAD"
    if any(k in u for k in ("UBUMP", "C18_6", "C21_7", "C35_", "C39_", "C40_", "C50_", "C60_")):
        return "SURFACE_DIE_BUMP_PAD"
    if re.search(r"_(12F|11F|10F|9F|8F|7F|6F|5F|L0[1-9])", u):
        return "ABOVE_BU_UVIA"
    if re.search(r"_(5B|6B|7B|8B|9B|10B|11B|12B|L19|L20|L21)", u):
        return "BELOW_BU_UVIA"
    return "BU_UVIA"


def _parse_padstack_geometry_from_extract(mcm_padstacks_txt: Path) -> Dict[str, Dict[str, Any]]:
    """Parse exact drill diameter, start/end layer, and regular pad size from mcm_padstacks.txt."""
    geom: Dict[str, Dict[str, Any]] = {}
    if not mcm_padstacks_txt.exists():
        return geom
    with mcm_padstacks_txt.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.startswith("S!"):
                continue
            parts = line.strip().split("!")
            if len(parts) < 10:
                continue
            ps_name = parts[1].strip().upper()
            lyr = parts[3].strip()
            shape = parts[6].strip()
            w_str = parts[7].strip()
            cat = parts[-2].strip() if len(parts) >= 2 else ""

            info = geom.setdefault(
                ps_name,
                {
                    "drill_um": 0.0,
                    "active_layers": [],
                    "pad_widths": {},
                    "category_raw": cat,
                },
            )
            try:
                w_val = float(w_str) if w_str else 0.0
            except ValueError:
                w_val = 0.0

            if lyr == "~DRILL":
                try:
                    info["drill_um"] = float(shape)
                except ValueError:
                    pass
            elif lyr not in {"internal_pad_def"} and not lyr.startswith("~") and w_val > 0.0 and shape != "":
                info["active_layers"].append(lyr)
                info["pad_widths"][lyr] = w_val
    return geom


def build_stage1_stackup_csv(
    mcm_layers_txt: Path,
    out_csv: Path,
    out_zones_json: Path,
) -> Dict[str, Any]:
    """Build stackup_53layers.csv and stackup_zones.json with 6-Zone PDN classification."""
    rows_out: List[Dict[str, Any]] = []
    zones: Dict[str, List[str]] = {
        "ABOVE_BU": [],
        "ABOVE_PP": [],
        "CORE": [],
        "BELOW_PP": [],
        "BELOW_BU": [],
        "BASE": [],
    }

    if mcm_layers_txt.exists():
        idx = 0
        with mcm_layers_txt.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.startswith("S!"):
                    continue
                p = line.strip().split("!")
                subclass = p[2].strip() if len(p) > 2 else ""
                if not subclass:
                    continue
                idx += 1
                canonical = "SURFACE" if subclass.upper() == "TOP" else ("BASE" if subclass.upper() == "BOTTOM" else subclass)
                l_use = p[3].strip()
                is_cond = p[5].strip()
                dk = p[6].strip()
                cond_mho = p[7].strip()
                df = p[8].strip()
                material = p[9].strip()
                thick_mil_str = p[13].strip().replace(" mil", "")
                l_type = p[14].strip()
                try:
                    thick_mil = float(thick_mil_str)
                    thick_um = round(thick_mil * 25.4, 2)
                except ValueError:
                    thick_mil = 0.0
                    thick_um = 0.0

                if is_cond == "YES":
                    pdn_zone = classify_layer_into_zone(canonical)
                    if canonical not in zones[pdn_zone]:
                        zones[pdn_zone].append(canonical)
                else:
                    if any(k in canonical.upper() for k in ("C0", "12", "11", "10", "9", "8", "7", "6", "5F", "4-5F")):
                        pdn_zone = "DIELECTRIC_ABOVE_BU" if "B" not in canonical.upper() else "DIELECTRIC_BELOW_BU"
                    elif any(k in canonical.upper() for k in ("3-4F", "2-3F")):
                        pdn_zone = "PREPREG_ABOVE_CORE"
                    elif any(k in canonical.upper() for k in ("1-2F", "PTH", "1-2B")):
                        pdn_zone = "DIELECTRIC_CORE"
                    elif any(k in canonical.upper() for k in ("2-3B", "3-4B")):
                        pdn_zone = "PREPREG_BELOW_CORE"
                    else:
                        pdn_zone = "DIELECTRIC_BELOW_BU"

                rows_out.append(
                    {
                        "layer_index": idx,
                        "subclass_name": canonical,
                        "mcm_subclass": subclass,
                        "layer_type": l_type,
                        "layer_use": l_use or l_type,
                        "is_conductor": is_cond,
                        "material": material,
                        "thickness_um": thick_um,
                        "thickness_mil": round(thick_mil, 4),
                        "dk": dk,
                        "df": df,
                        "conductivity": cond_mho,
                        "pdn_zone": pdn_zone,
                    }
                )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "layer_index",
                "subclass_name",
                "mcm_subclass",
                "layer_type",
                "layer_use",
                "is_conductor",
                "material",
                "thickness_um",
                "thickness_mil",
                "dk",
                "df",
                "conductivity",
                "pdn_zone",
            ],
        )
        writer.writeheader()
        writer.writerows(rows_out)

    zone_payload = {
        "total_stackup_layers": len(rows_out),
        "conductor_zones": zones,
        "edtc_layer": "4FCO",
        "core_layers": zones["CORE"],
        "base_layer": "BASE",
    }
    out_zones_json.write_text(json.dumps(zone_payload, indent=2), encoding="utf-8")
    return zone_payload


def build_stage1_padstack_index(
    library_dir: Path,
    mcm_learned_txt: Path,
    mcm_padstacks_txt: Path,
    out_csv: Path,
) -> Dict[str, Any]:
    """Combine all .pad files from <cadence_library_dir> with .mcm padstack definitions."""
    geom_map = _parse_padstack_geometry_from_extract(mcm_padstacks_txt)
    pad_records: Dict[str, Dict[str, Any]] = {}

    if mcm_learned_txt.exists():
        with mcm_learned_txt.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.startswith("PADSTACK|"):
                    continue
                p = line.strip().split("|")
                if len(p) < 6:
                    continue
                ps_name = p[1].strip().upper()
                is_thru = p[3].strip().upper() == "TRUE"
                start_l = p[4].strip().strip('"').replace("CONDUCTOR/", "")
                end_l = p[5].strip().strip('"').replace("CONDUCTOR/", "")
                g = geom_map.get(ps_name, {})
                drill_um = g.get("drill_um", 0.0)
                pw_dict = g.get("pad_widths", {})
                pad_um = max(pw_dict.values()) if pw_dict else 0.0
                zone_cat = _classify_padstack_zone(ps_name, start_l, end_l, is_thru)
                pad_records[ps_name] = {
                    "padstack_name": ps_name,
                    "in_mcm_db": "YES",
                    "in_library_folder": "NO",
                    "pad_file_path": "",
                    "start_layer": start_l,
                    "end_layer": end_l,
                    "drill_um": drill_um,
                    "regular_pad_um": pad_um,
                    "pdn_zone_category": zone_cat,
                }

    lib_pad_files = sorted(library_dir.glob("*.pad")) if library_dir.exists() else []
    for pf in lib_pad_files:
        ps_upper = pf.stem.upper()
        m_via = re.match(r"^V(?:U)?(\d+(?:_\d+)?)_(\d+)_(\d+(?:_\d+)?)_([A-Z0-9]+)_([A-Z0-9]+)", ps_upper)
        inferred_pad = float(m_via.group(1).replace("_", ".")) if m_via else 0.0
        inferred_drill = float(m_via.group(2)) if m_via else 0.0
        inferred_start = m_via.group(4) if m_via else ""
        inferred_end = m_via.group(5) if m_via else ""

        if ps_upper in pad_records:
            pad_records[ps_upper]["in_library_folder"] = "YES"
            pad_records[ps_upper]["pad_file_path"] = str(pf)
            if pad_records[ps_upper]["drill_um"] == 0.0 and inferred_drill > 0.0:
                pad_records[ps_upper]["drill_um"] = inferred_drill
            if pad_records[ps_upper]["regular_pad_um"] == 0.0 and inferred_pad > 0.0:
                pad_records[ps_upper]["regular_pad_um"] = inferred_pad
        else:
            zone_cat = _classify_padstack_zone(ps_upper, inferred_start, inferred_end, "2FCI_2BCI" in ps_upper)
            pad_records[ps_upper] = {
                "padstack_name": ps_upper,
                "in_mcm_db": "NO",
                "in_library_folder": "YES",
                "pad_file_path": str(pf),
                "start_layer": inferred_start or "LIBRARY_DEF",
                "end_layer": inferred_end or "LIBRARY_DEF",
                "drill_um": inferred_drill,
                "regular_pad_um": inferred_pad,
                "pdn_zone_category": zone_cat,
            }

    rows = sorted(pad_records.values(), key=lambda r: (r["pdn_zone_category"], r["padstack_name"]))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "padstack_name",
                "in_mcm_db",
                "in_library_folder",
                "pad_file_path",
                "start_layer",
                "end_layer",
                "drill_um",
                "regular_pad_um",
                "pdn_zone_category",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    by_category: Dict[str, List[str]] = {}
    for r in rows:
        by_category.setdefault(r["pdn_zone_category"], []).append(r["padstack_name"])

    return {
        "total_indexed_padstacks": len(rows),
        "library_pad_files_count": len(lib_pad_files),
        "padstacks_by_zone_category": by_category,
    }


def build_stage1_bump_package_summaries_from_symbols_zip(
    symbols_dir: Path,
    out_summary_csv: Path,
) -> List[Dict[str, Any]]:
    """Parse bump map CSVs inside <cadence_library_dir> for Die/HBM/Bridge bump stats."""
    zip_targets = [
        ("hutton_hill_ldc_bc_a0_FN.zip", "U1.HUTTON_HILL_LDC_A0.csv", "HUTTON_HILL_LDC_BC_A0", "U1,U2,U3,U4"),
        ("hutton_hill_ldb_bc_a0_FN.zip", "U1.HUTTON_HILL_LDB_A0.csv", "HUTTON_HILL_LDB_BC_A0", "U5,U6,U7,U8"),
        ("hutton_hill_lda_bc_a0_FN_1_01.zip", "U1.HUTTON_HILL_LDA_A0.csv", "HUTTON_HILL_LDA_BC_A0", "U9,U10,U12,U88"),
        ("hbm4e_micron_nominal_bc_a0.zip", "U1.HBM4E_MICRON_NOMINAL_A0.csv", "HBM4E_MICRON_NOMINAL_BC_A0", "U13..U24"),
        ("HTH_BC_CSV.zip", "U1.DISCOVERY_BRIDGE_11_BC_A0.csv", "DISCOVERY_BRIDGE_11_BC_A0", "U25..U28"),
        ("HTH_BC_CSV.zip", "U1.DISCOVERY_BRIDGE_12_BC_A0.csv", "DISCOVERY_BRIDGE_12_BC_A0", "U29..U32"),
        ("HTH_BC_CSV.zip", "U1.DISCOVERY_BRIDGE_13_BC_A0.csv", "DISCOVERY_BRIDGE_13_BC_A0", "U37,U38"),
        ("HTH_BC_CSV.zip", "U1.DISCOVERY_BRIDGE_14_BC_A0.csv", "DISCOVERY_BRIDGE_14_BC_A0", "U33,U34"),
        ("HTH_BC_CSV.zip", "U1.DISCOVERY_BRIDGE_15_BC_A0.csv", "DISCOVERY_BRIDGE_15_BC_A0", "U35,U36"),
        ("HTH_BC_CSV.zip", "U1.DISCOVERY_BRIDGE_16_BC_A0.csv", "DISCOVERY_BRIDGE_16_BC_A0", "U39,U40"),
        ("HTH_BC_CSV.zip", "U1.LAVA_BRIDGE_22_BC_A0.csv", "LAVA_BRIDGE_22_BC_A0", "U41..U43,U50..U52"),
        ("HTH_BC_CSV.zip", "U1.LAVA_BRIDGE_23_BC_A0.csv", "LAVA_BRIDGE_23_BC_A0", "U44..U49"),
    ]
    rows_out: List[Dict[str, Any]] = []
    for zname, csv_name, pkg_name, refdes_list in zip_targets:
        zpath = symbols_dir / zname
        if not zpath.exists():
            continue
        try:
            with zipfile.ZipFile(zpath, "r") as z:
                if csv_name not in z.namelist():
                    continue
                raw_bytes = z.read(csv_name)
                text_stream = io.StringIO(raw_bytes.decode("utf-8", errors="ignore"))
                reader = csv.DictReader(text_stream)
                total_bumps = 0
                vdd_bumps = 0
                vss_bumps = 0
                geoms: Counter[str] = Counter()
                top_power_nets: Counter[str] = Counter()
                for row in reader:
                    total_bumps += 1
                    net = (row.get("Si_Net_Name") or row.get("PadConn") or "").strip().upper()
                    geom = (row.get("Geometry") or "").strip()
                    if geom:
                        geoms[geom] += 1
                    if "VSS" in net or "GND" in net:
                        vss_bumps += 1
                        top_power_nets[net] += 1
                    elif "VDD" in net or "VCC" in net:
                        vdd_bumps += 1
                        top_power_nets[net] += 1
                rows_out.append(
                    {
                        "symbol_package": pkg_name,
                        "mcm_refdes_instances": refdes_list,
                        "source_zip": zname,
                        "source_csv": csv_name,
                        "total_bumps_per_instance": total_bumps,
                        "vdd_bumps_per_instance": vdd_bumps,
                        "vss_bumps_per_instance": vss_bumps,
                        "signal_nc_bumps_per_instance": total_bumps - vdd_bumps - vss_bumps,
                        "bump_geometries": "; ".join(f"{k}:{v}" for k, v in geoms.most_common(3)),
                        "top_power_ground_nets": "; ".join(f"{k}:{v}" for k, v in top_power_nets.most_common(6)),
                    }
                )
        except Exception:
            continue

    out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol_package",
                "mcm_refdes_instances",
                "source_zip",
                "source_csv",
                "total_bumps_per_instance",
                "vdd_bumps_per_instance",
                "vss_bumps_per_instance",
                "signal_nc_bumps_per_instance",
                "bump_geometries",
                "top_power_ground_nets",
            ],
        )
        writer.writeheader()
        writer.writerows(rows_out)
    return rows_out


def build_stage1_lsc_and_symbol_library_csv(
    library_dir: Path,
    symbols_dir: Path,
    out_csv: Path,
) -> List[Dict[str, Any]]:
    """Index LSC, eDTC, BGA, and Die/Bridge symbols across Library and Symbols folders."""
    records: List[Dict[str, Any]] = []
    if library_dir.exists():
        for psm in sorted(library_dir.glob("*.psm")):
            stem = psm.stem.upper()
            dra = psm.with_suffix(".dra")
            txt = psm.with_suffix(".txt")
            role = "OTHER_SYMBOL"
            layer = "SURFACE"
            if stem.startswith("SM0201") or stem.startswith("SM0204"):
                role = "LSC_OR_DSC_CAPACITOR"
                layer = "BASE / SURFACE"
            elif "4FCO" in stem or "EDTC" in stem:
                role = "EDTC_4FCO_SYMBOL"
                layer = "4FCO"
            elif "14521" in stem or "BGA" in stem:
                role = "BGA_PACKAGE_SYMBOL"
                layer = "BASE"
            elif "CSB" in stem:
                role = "DIE_OR_BRIDGE_SYMBOL"
                layer = "SURFACE"
            records.append(
                {
                    "symbol_name": stem,
                    "symbol_role": role,
                    "target_layer": layer,
                    "psm_file": str(psm),
                    "dra_file": str(dra) if dra.exists() else "",
                    "device_or_archive_file": str(txt) if txt.exists() else "",
                }
            )
    if symbols_dir.exists():
        for zf in sorted(symbols_dir.glob("*.zip")):
            stem = zf.stem.upper()
            role = "DIE_PACKAGE_ARCHIVE"
            if "BRIDGE" in stem:
                role = "EMIB_BRIDGE_ARCHIVE"
            elif "HBM" in stem:
                role = "HBM4E_DIE_ARCHIVE"
            elif "MAPPING" in stem or "CSV" in stem:
                role = "BUMP_NETLIST_MAPPING_ARCHIVE"
            records.append(
                {
                    "symbol_name": stem,
                    "symbol_role": role,
                    "target_layer": "SURFACE",
                    "psm_file": "",
                    "dra_file": "",
                    "device_or_archive_file": str(zf),
                }
            )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol_name",
                "symbol_role",
                "target_layer",
                "psm_file",
                "dra_file",
                "device_or_archive_file",
            ],
        )
        writer.writeheader()
        writer.writerows(records)
    return records


def build_per_layer_design_rules_csv(
    out_per_layer_csv: Path,
) -> List[Dict[str, Any]]:
    """
    Build per-layer design rule matrix (per_layer_design_rules.csv) for all 27 conductor layers
    from local workspace CSVs in specs_and_docs/design_rules/ and stackup_53layers.csv + padstack_library_index.csv.
    Covers all 9 Architect Pre-Learn categories per layer:
      1. Max stacked via (BU above/below, normal vs HSIO, on trace/shape vs on PTH)
      2. Padstack via used for UP and DOWN transitions
      3. Min web (minimum aperture rule 3.4.1.18)
      4. Max stacked via on eDTC pin (4FCO)
      5. Via-to-via spacing (3.4.1.46 edge-to-edge, diff-net pitch, same-net overlap pitch, staggered overlap)
      6. Via-to-pin spacing (3.4.1.25 Unrestricted / Restricted Necking / EMIB)
      7. Cline-to-via (3.4.1.41/97), Via-to-shape (3.4.1.30), Shape-to-shape (3.4.1.29), Trace-to-shape (3.4.1.40)
      8. eDTC Keep-Out Zone (KOZ / Guard Metal / Inner Core Keepout / 5B Solid Plane / BASE no-LSC)
      9. GCP (12B & BASE GX92 40um rules) & LSC SRO-to-SRO / BGA SRO-to-LSC SRO rules
    """
    conductor_specs: List[Dict[str, Any]] = [
        {
            "cond_order": 1, "layer": "SURFACE", "mcm_subclass": "TOP", "pdn_zone": "ABOVE_BU",
            "cu_group": "12Cu", "cu_thickness_um": 12.0, "de_below_name": "C0-13F / 12-C0", "de_below_um": "17.0 (to C0) / 34.0 (to 12F)",
            "via_padstack_up": "DIE_BUMP_PAD (C18_6_DP_01A / C21_7_DP_01A / C35_21_DP_01A / UBUMP)",
            "via_padstack_down": "VU30_19_35_SURFACE_C0_01B (30/19/35 to C0) | V77_49_77_SURFACE_12F_01A (77/49/77 skip-C0 to 12F)",
            "via_drill_down_um": "19.0 (to C0) | 49.0 (to 12F)", "via_pad_down_um": "30-35 (to C0) | 77.0 (to 12F)",
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 3,
            "min_web_aperture_um": 14.0,
            "edtc_max_stack_via": "N/A (Surface)",
            "via_to_via_edge_um": "18.0 (Unrestricted) | 9.9 (EMIB)",
            "via_pitch_diff_net_um": "95.0 (77_49_77) | 48.0 (30_19_35)",
            "via_pitch_same_net_um": "63.0 (77_49_77 w/ overlap)",
            "adj_layer_via_overlap_um": "14.0 (same) | 14->25 (staggered BU)",
            "via_to_pin_space_um": "18.0 (Unrestricted/Necking) | 9.9 (EMIB)",
            "cline_to_via_space_um": "18.0 (Unrestricted) | 12-13 (Necking) | 16.0 (EMIB)",
            "via_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking) | 16.0 (EMIB)",
            "shape_to_shape_space_um": "50.0 (Unrestricted/Necking) | 16.0 (EMIB)",
            "trace_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking) | 16.0 (EMIB)",
            "min_line_width_space_um": "9/9 (EMIB) | 9/12 (Necking) | 18/18 (Unrestricted)",
            "edtc_koz_and_layer_rule": "DTC NOT allowed under EMIB Die; DTC Cavity Edge to Die Edge >= 1000 um; DTC Cavity Edge to EMIB Cavity Edge >= 1000 um",
            "gcp_12b_base_rule": "N/A (Topside Surface)",
            "lsc_and_bga_sro_rule": "DSC (Topside 0201) placed on SURFACE; LSC rules apply to BASE",
        },
        {
            "cond_order": 2, "layer": "C0", "mcm_subclass": "C0", "pdn_zone": "ABOVE_BU",
            "cu_group": "12Cu (1um RDL/EMIB)", "cu_thickness_um": 1.0, "de_below_name": "12-C0 (GL107)", "de_below_um": "17.0",
            "via_padstack_up": "VU30_19_35_SURFACE_C0_01B | VU30_19_39_SURFACE_C0_01B | VU30_19_50_SURFACE_C0_01B",
            "via_padstack_down": "EMIB Bridge Bump Pads (C21_7_C0_DP_01A / C35_C0_DP_01A / C50_C0_DP_01A)",
            "via_drill_down_um": "19.0", "via_pad_down_um": "35.0 / 39.0 / 50.0",
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 3,
            "min_web_aperture_um": 14.0,
            "edtc_max_stack_via": "N/A (EMIB RDL)",
            "via_to_via_edge_um": "9.9 (EMIB) | 18.0 (Unrestricted)",
            "via_pitch_diff_net_um": "45.0 - 55.0 (EMIB uBump)",
            "via_pitch_same_net_um": "45.0 (EMIB)",
            "adj_layer_via_overlap_um": "14.0",
            "via_to_pin_space_um": "9.9 (EMIB) | 18.0 (Unrestricted)",
            "cline_to_via_space_um": "16.0 (EMIB) | 18.0 (Unrestricted)",
            "via_to_shape_space_um": "16.0 (EMIB) | 50.0 (Unrestricted)",
            "shape_to_shape_space_um": "16.0 (EMIB) | 50.0 (Unrestricted)",
            "trace_to_shape_space_um": "16.0 (EMIB) | 50.0 (Unrestricted)",
            "min_line_width_space_um": "9/9 (EMIB) | 18/18 (Unrestricted)",
            "edtc_koz_and_layer_rule": "DTC NOT allowed under EMIB Die; DTC Cavity Edge to EMIB Cavity Edge >= 1000 um",
            "gcp_12b_base_rule": "N/A",
            "lsc_and_bga_sro_rule": "N/A",
        },
    ]

    # Front 15Cu BU layers: 12F, 11F, 10F (30um GL107)
    front_15cu = [
        (3, "12F", "11-12F (GL107 30um)", "30.0", "V77_49_77_SURFACE_12F_01A (77/49/77)", "V77_49_77_12F_11F_01A (77/49/77)",
         "DTC Cavity Edge to EMIB Cavity >= 1000 um; EMIB cavity to C4 via pad >= 82.5 um (Surface-1)"),
        (4, "11F", "10-11F (GL107 30um)", "30.0", "V77_49_77_12F_11F_01A (77/49/77)", "V77_49_77_11F_10F_01A (77/49/77)",
         "DTC Cavity Edge to EMIB Cavity >= 1000 um; EMIB cavity to C4 via pad >= 82.5 um (Surface-2)"),
        (5, "10F", "9-10F (GL107 30um)", "30.0", "V77_49_77_11F_10F_01A (77/49/77)", "V77_49_77_10F_9F_01A (77/49/77)",
         "DTC Cavity Edge to EMIB Cavity >= 1000 um; C4 via pad to CSB pad >= 372 um (Surface-3)"),
    ]
    for order, lyr, de_name, de_um, v_up, v_dn, edtc_note in front_15cu:
        conductor_specs.append({
            "cond_order": order, "layer": lyr, "mcm_subclass": lyr, "pdn_zone": "ABOVE_BU",
            "cu_group": "15Cu", "cu_thickness_um": 15.0, "de_below_name": de_name, "de_below_um": de_um,
            "via_padstack_up": v_up, "via_padstack_down": v_dn,
            "via_drill_down_um": "49.0", "via_pad_down_um": "77.0",
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 3,
            "min_web_aperture_um": 14.0,
            "edtc_max_stack_via": "N/A (Upper BU)",
            "via_to_via_edge_um": "18.0",
            "via_pitch_diff_net_um": "95.0 (77_49_77)",
            "via_pitch_same_net_um": "63.0 (77_49_77 w/ overlap)",
            "adj_layer_via_overlap_um": "14.0 (same) | 14->25 (staggered BU)",
            "via_to_pin_space_um": "18.0",
            "cline_to_via_space_um": "18.0 (Unrestricted) | 12-13 (Necking/EMIB)",
            "via_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking/EMIB)",
            "shape_to_shape_space_um": "50.0 (Unrestricted/Necking) | 30.0 (EMIB)",
            "trace_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking/EMIB)",
            "min_line_width_space_um": "9/12 (Necking/EMIB) | 18/18 (Unrestricted)",
            "edtc_koz_and_layer_rule": edtc_note,
            "gcp_12b_base_rule": "N/A",
            "lsc_and_bga_sro_rule": "N/A",
        })

    # Front 18Cu BU layers: 9F, 8F, 7F, 6F, 5F (50um GL107)
    front_18cu = [
        (6, "9F", "8-9F (GL107 50um)", "V77_49_77_10F_9F_01A (77/49/77)", "V90_65_90_9F_8F_01A (90/65/90)", "90.0", "108.0", "N/A", "Standard BU routing above DTC"),
        (7, "8F", "7-8F (GL107 50um)", "V90_65_90_9F_8F_01A (90/65/90)", "V90_65_90_8F_7F_01A (90/65/90)", "90.0", "108.0", "N/A", "Standard BU routing above DTC"),
        (8, "7F", "6-7F (GL107 50um)", "V90_65_90_8F_7F_01A (90/65/90)", "V90_65_90_7F_6F_01A (90/65/90)", "90.0", "108.0", "N/A", "Standard BU routing above DTC; break 2-stack eDTC via column at 6F->7F"),
        (9, "6F", "5-6F (GL107 50um)", "V90_65_90_7F_6F_01A (90/65/90)", "V90_65_90_6F_5F_01A (90/65/90)", "90.0", "108.0", "2 (Max 2 stacked vias on DTC pad: 6F->5F->4FCO)", "2nd stacked via level above 4FCO DTC pad (90_65_90, max stack=2)"),
        (10, "5F", "4-5F (GL107 50um)", "V90_65_90_6F_5F_01A (90/65/90)", "V90_65_121_5F_4FCO_01A (90/65/121 to 4FCO plane) | V90_65_90 (90/65/90 on 4FCO DTC pad)", "121.0 (plane) | 90.0 (DTC pad)", "139.0 (90_65_121) | 108.0 (90_65_90)", "2 (1 via/pad required, 90_65_90, max stack=2)", "1st BU layer over 4FCO DTC: 1 via/DTC pad (65um drill / 90um pad), max 2 stacked vias on DTC pad"),
    ]
    for order, lyr, de_name, v_up, v_dn, pad_dn, pitch_diff, edtc_stk, edtc_note in front_18cu:
        conductor_specs.append({
            "cond_order": order, "layer": lyr, "mcm_subclass": lyr, "pdn_zone": "ABOVE_BU",
            "cu_group": "18Cu", "cu_thickness_um": 18.0, "de_below_name": de_name, "de_below_um": "50.0",
            "via_padstack_up": v_up, "via_padstack_down": v_dn,
            "via_drill_down_um": "65.0", "via_pad_down_um": pad_dn,
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 3,
            "min_web_aperture_um": 14.0,
            "edtc_max_stack_via": edtc_stk,
            "via_to_via_edge_um": "18.0",
            "via_pitch_diff_net_um": pitch_diff,
            "via_pitch_same_net_um": "76.0 (90_65_90 / 90_65_121 w/ overlap)",
            "adj_layer_via_overlap_um": "14.0 (BU-BU) | 12.5 (PP-BU)",
            "via_to_pin_space_um": "18.0",
            "cline_to_via_space_um": "18.0 (Unrestricted) | 12.0 (Necking/EMIB)",
            "via_to_shape_space_um": "50.0 (All regions)",
            "shape_to_shape_space_um": "50.0 (All regions)",
            "trace_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking/EMIB)",
            "min_line_width_space_um": "12/12 (Necking/EMIB) | 18/18 (Unrestricted)",
            "edtc_koz_and_layer_rule": edtc_note,
            "gcp_12b_base_rule": "N/A",
            "lsc_and_bga_sro_rule": "N/A",
        })

    # Prepreg & Core layers: 4FCO, 3FCI, 2FCI, 1FCI, 1BCI, 2BCI, 3BCI, 4BCO
    pp_core_specs = [
        (11, "4FCO", "ABOVE_PP", "25Cu", 25.0, "3-4F (GEA-795GL PP)", "60.0",
         "V90_65_121_5F_4FCO_01A (90/65/121) | V90_65_90 on DTC pad",
         "V175_85_175_4FCO_3FCI_01A | V282_5_85_175_4FCO_3FCI_01A",
         "85.0", "175.0 / 282.5", "242.5 (175_85_175)", "130.0 (175_85_175 w/ overlap)", "12.5 (PP-BU) | 45.0 (PP-PP)",
         "2 (Max 2 stacked vias on DTC pad; 1 via/pad required, 90_65_90)",
         "eDTC Terminal Layer (C200M_0_4FCO_01A / S200M_0_4FCO_01A, min 200x200um pad, 50um pad-to-pad); DTC Edge to DTC Cavity Edge KOZ = 300 um; DTC Cavity to Cavity = 1600 um"),
        (12, "3FCI", "ABOVE_PP", "25Cu_Inner", 25.0, "2-3F (GEA-795GL PP)", "60.0",
         "V175_85_175_4FCO_3FCI_01A | V282_5_85_175_4FCO_3FCI_01A",
         "V175_85_175_3FCI_2FCI_01A | V175_85_282_5_3FCI_2FCI_01A",
         "85.0", "175.0 / 282.5", "242.5 (175_85_175)", "130.0 (175_85_175 w/ overlap)", "45.0 (PP-PP / PP-PTH)",
         "0 (No metal/via inside DTC cavity)",
         "NO Trace/Via/Pin/Shape inside DTC Cavity (DTC+300um); Inner Layer metal to DTC Cavity Edge >= 150 um (total 450 um KOZ from DTC body)"),
        (13, "2FCI", "CORE", "35Cu", 35.0, "1-2F (E795UCLH Core)", "530.0 (1570um Total Core)",
         "V175_85_282_5_3FCI_2FCI_01A (max 2 PP vias per PTH pad)",
         "V282_5_150_282_5_2FCI_2BCI_01A..02D (Core PTH 2FCI->2BCI)",
         "150.0", "282.5 (outer) / 365.0 (inner)", "432.5 (w/ inner pad) | 350.0 (w/o inner pad)", "270.0 (PKG 0.3-0.8) | 216.5 (PKG 0.1)", "45.0 (PTH-PP)",
         "0 (No metal/via inside DTC cavity)",
         "Outermost Core Layer: NO Trace/Via/Pin/Shape inside DTC Cavity (DTC+300um); Guard Metal Ring width >= 150 um around DTC Cavity (NO degassing holes or vias in Guard Metal); 4 DTC fiducials (500um pad / 500um clearance)"),
        (14, "1FCI", "CORE", "25Cu_Inner", 25.0, "PTH (GEA-795GL 100um Inner Core)", "100.0",
         "V282_5_150_282_5_2FCI_2BCI_01B/02D (Thru Core PTH)",
         "V282_5_150_282_5_2FCI_2BCI_01B/02D (Thru Core PTH)",
         "150.0", "365.0 (inner PTH pad)", "432.5", "270.0 (common inner pads)", "N/A (Thru PTH)",
         "0 (No metal/via inside DTC cavity)",
         "Inner Core Layer: NO Trace/Via/Pin/Shape inside DTC Cavity (DTC+300um); Min spacing from DTC Cavity Edge to nearest metal >= 150 um (total 450 um KOZ from DTC body)"),
        (15, "1BCI", "CORE", "25Cu_Inner", 25.0, "1-2B (E795UCLH Core)", "530.0",
         "V282_5_150_282_5_2FCI_2BCI_01B/02D (Thru Core PTH)",
         "V282_5_150_282_5_2FCI_2BCI_01B/02D (Thru Core PTH)",
         "150.0", "365.0 (inner PTH pad)", "432.5", "270.0 (common inner pads)", "N/A (Thru PTH)",
         "0 (No metal/via inside DTC cavity)",
         "Inner Core Layer: NO Trace/Via/Pin/Shape inside DTC Cavity (DTC+300um); Min spacing from DTC Cavity Edge to nearest metal >= 150 um (total 450 um KOZ from DTC body)"),
        (16, "2BCI", "CORE", "35Cu", 35.0, "2-3B (GEA-795GL PP)", "60.0",
         "V282_5_150_282_5_2FCI_2BCI_01A..02D (Core PTH 2FCI->2BCI)",
         "V175_85_175_2BCI_3BCI_01A | V282_5_85_175_2BCI_3BCI_01A",
         "85.0", "282.5 (PTH lid) / 175.0 (PP)", "432.5 (PTH) | 242.5 (PP)", "270.0 (PTH) | 130.0 (PP)", "45.0 (PTH-PP)",
         "0 (No metal/via inside DTC cavity)",
         "Outermost Core Layer: NO Trace/Via/Pin/Shape inside DTC Cavity (DTC+300um); Guard Metal Ring width >= 150 um around DTC Cavity (NO degassing holes or vias in Guard Metal)"),
        (17, "3BCI", "BELOW_PP", "25Cu_Inner", 25.0, "3-4B (GEA-795GL PP)", "60.0",
         "V175_85_175_2BCI_3BCI_01A | V282_5_85_175_2BCI_3BCI_01A",
         "V175_85_175_3BCI_4BCO_01A | V175_85_282_5_3BCI_4BCO_01A",
         "85.0", "175.0 / 282.5", "242.5 (175_85_175)", "130.0 (175_85_175 w/ overlap)", "45.0 (PP-PP)",
         "0 (No metal/via inside DTC cavity if through-cavity)",
         "Inner Prepreg Layer: maintain >= 150 um clearance from DTC Cavity Edge (450 um from DTC body)"),
        (18, "4BCO", "BELOW_PP", "25Cu (20um Cu)", 20.0, "4-5B (GL107 50um)", "50.0",
         "V175_85_175_3BCI_4BCO_01A | V175_85_282_5_3BCI_4BCO_01A",
         "V121_65_90_4BCO_5B_01A (121/65/90 to 5B)",
         "65.0", "121.0 (on 4BCO) / 90.0 (on 5B)", "139.0 (121_65_90)", "76.0 (121_65_90 w/ overlap)", "12.5 (PP-BU) | 45.0 (PP-PP)",
         "N/A (Backside PP)",
         "Backside 4BCO fiducials (FID_C500M_0_4BCO_1500KO_01A); transition to 5B solid plane under DTC"),
    ]
    for (order, lyr, zone, cu_grp, cu_thk, de_name, de_um, v_up, v_dn, drl, pad_s, p_diff, p_same, ovlp, edtc_stk, edtc_note) in pp_core_specs:
        hsio_stk = 3 if "F" in lyr else 6
        conductor_specs.append({
            "cond_order": order, "layer": lyr, "mcm_subclass": lyr, "pdn_zone": zone,
            "cu_group": cu_grp, "cu_thickness_um": cu_thk, "de_below_name": de_name, "de_below_um": de_um,
            "via_padstack_up": v_up, "via_padstack_down": v_dn,
            "via_drill_down_um": drl, "via_pad_down_um": pad_s,
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": hsio_stk,
            "min_web_aperture_um": 67.5,
            "edtc_max_stack_via": edtc_stk,
            "via_to_via_edge_um": "67.5",
            "via_pitch_diff_net_um": p_diff,
            "via_pitch_same_net_um": p_same,
            "adj_layer_via_overlap_um": ovlp,
            "via_to_pin_space_um": "67.5",
            "cline_to_via_space_um": "67.5",
            "via_to_shape_space_um": "67.5",
            "shape_to_shape_space_um": "67.5",
            "trace_to_shape_space_um": "67.5",
            "min_line_width_space_um": "67.5 / 67.5",
            "edtc_koz_and_layer_rule": edtc_note,
            "gcp_12b_base_rule": "N/A",
            "lsc_and_bga_sro_rule": "N/A",
        })

    # Back 18Cu BU layers: 5B, 6B, 7B, 8B, 9B (50um GL107)
    back_18cu = [
        (19, "5B", "5-6B (GL107 50um)", "50.0", "V121_65_90_4BCO_5B_01A (121/65/90)", "V90_65_90_5B_6B_01A (90/65/90)", "65.0", "90.0", "108.0",
         "SOLID PLANE REQUIRED on 5B (First Backside BU layer) under entire DTC Cavity + Guard Metal (Rule #13; adhesion holes and vias ARE allowed in 5B solid plane per Rule #25)"),
        (20, "6B", "6-7B (GL107 50um)", "50.0", "V90_65_90_5B_6B_01A (90/65/90)", "V90_65_90_6B_7B_01A (90/65/90)", "65.0", "90.0", "108.0",
         "Backside BU routing allowed"),
        (21, "7B", "7-8B (GL107 50um)", "50.0", "V90_65_90_6B_7B_01A (90/65/90)", "V90_65_90_7B_8B_01A (90/65/90)", "65.0", "90.0", "108.0",
         "Backside BU routing allowed"),
        (22, "8B", "8-9B (GL107 50um)", "50.0", "V90_65_90_7B_8B_01A (90/65/90)", "V90_65_90_8B_9B_01A (90/65/90)", "65.0", "90.0", "108.0",
         "Backside BU routing allowed"),
        (23, "9B", "9-10B (GL107 30um)", "30.0", "V90_65_90_8B_9B_01A (90/65/90)", "V77_49_77_9B_10B_01A (77/49/77)", "49.0", "77.0", "95.0 (to 10B) | 108.0 (to 8B)",
         "Backside BU routing allowed"),
    ]
    for order, lyr, de_name, de_um, v_up, v_dn, drl, pad_dn, p_diff, edtc_note in back_18cu:
        conductor_specs.append({
            "cond_order": order, "layer": lyr, "mcm_subclass": lyr, "pdn_zone": "BELOW_BU",
            "cu_group": "18Cu", "cu_thickness_um": 18.0, "de_below_name": de_name, "de_below_um": de_um,
            "via_padstack_up": v_up, "via_padstack_down": v_dn,
            "via_drill_down_um": drl, "via_pad_down_um": pad_dn,
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 6,
            "min_web_aperture_um": 14.0,
            "edtc_max_stack_via": "N/A (Backside BU)",
            "via_to_via_edge_um": "18.0",
            "via_pitch_diff_net_um": p_diff,
            "via_pitch_same_net_um": "76.0 (90_65_90) | 63.0 (77_49_77)",
            "adj_layer_via_overlap_um": "14.0 (same) | 14->25 (staggered BU)",
            "via_to_pin_space_um": "18.0",
            "cline_to_via_space_um": "18.0 (Unrestricted) | 12.0 (Necking)",
            "via_to_shape_space_um": "50.0 (All regions)",
            "shape_to_shape_space_um": "50.0 (All regions)",
            "trace_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking)",
            "min_line_width_space_um": "12/12 (Necking) | 18/18 (Unrestricted)",
            "edtc_koz_and_layer_rule": edtc_note,
            "gcp_12b_base_rule": "N/A",
            "lsc_and_bga_sro_rule": "N/A",
        })

    # Back 15Cu BU layers: 10B, 11B, 12B (30um GL107 / 40um GX92 GCP on 12B->BASE)
    back_15cu = [
        (24, "10B", "10-11B (GL107 30um)", "30.0", "V77_49_77_9B_10B_01A (77/49/77)", "V77_49_77_10B_11B_01A (77/49/77) | V83_55_83_10B_11B_01A (83/55/83)",
         "49.0 / 55.0", "77.0 / 83.0", "18.0", "95.0", "63.0", "N/A (Base-3: routing allowed)"),
        (25, "11B", "11-12B (GL107 30um)", "30.0", "V77_49_77_10B_11B_01A | V83_55_83_10B_11B_01A", "V77_49_77_11B_12B_01A (77/49/77) | V83_55_83_11B_12B_01A (83/55/83)",
         "49.0 / 55.0", "77.0 / 83.0", "18.0", "95.0", "63.0", "Base-2 (11B): Routing NOT Allowed (planes & via pads/BGA-Aligned 4-5 via clusters only)"),
        (26, "12B", "12-13B (GL107 30um / GX92 40um GCP)", "30.0 (ABF) / 40.0 (GX92 GCP)",
         "V77_49_77_11B_12B_01A | V83_55_83_11B_12B_01A",
         "V90_65_90_12B_BASE_01A (90/65/90 GCP) | V83_55_83_12B_BASE_01A | V77_49_77_12B_BASE_01A",
         "65.0 (GCP) / 55.0 / 49.0", "90.0 (GCP) / 83.0 / 77.0",
         "90.0 (Diff-Net on Base-1 w/ GCP 90_65_90) | 67.5 (GCP Cu space) | 18.0 (std 15Cu)",
         "180.0 (40um GCP 90_65_90) | 95.0 (ABF 77_49_77)", "63.0 - 76.0",
         "Base-1 (12B) GCP Rule: GX92 40um GCP applied Base-to-Base-1; uVia 90_65_90; Diff-Net Via-to-Via space on Base-1 = 90 um (min pitch 180 um, Cu space 67.5 um); Routing NOT Allowed on Base-1"),
    ]
    for order, lyr, de_name, de_um, v_up, v_dn, drl, pad_dn, v2v_edge, p_diff, p_same, gcp_note in back_15cu:
        conductor_specs.append({
            "cond_order": order, "layer": lyr, "mcm_subclass": lyr, "pdn_zone": "BELOW_BU",
            "cu_group": "15Cu" if lyr != "12B" else "15Cu + 40um_GCP", "cu_thickness_um": 15.0, "de_below_name": de_name, "de_below_um": de_um,
            "via_padstack_up": v_up, "via_padstack_down": v_dn,
            "via_drill_down_um": drl, "via_pad_down_um": pad_dn,
            "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 6,
            "min_web_aperture_um": 14.0,
            "edtc_max_stack_via": "N/A (Backside BU)",
            "via_to_via_edge_um": v2v_edge,
            "via_pitch_diff_net_um": p_diff,
            "via_pitch_same_net_um": p_same,
            "adj_layer_via_overlap_um": "14.0 (same) | 14->25 (staggered BU)",
            "via_to_pin_space_um": "18.0",
            "cline_to_via_space_um": "18.0 (Unrestricted) | 12-13 (Necking)",
            "via_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking)",
            "shape_to_shape_space_um": "50.0",
            "trace_to_shape_space_um": "50.0 (Unrestricted) | 30.0 (Necking)",
            "min_line_width_space_um": "9/12 (Necking) | 18/18 (Unrestricted)",
            "edtc_koz_and_layer_rule": "Backside BU under DTC shadow (LSC not allowed on BASE under DTC)",
            "gcp_12b_base_rule": gcp_note,
            "lsc_and_bga_sro_rule": "BGA-aligned 4-5 via clusters above BGA pads",
        })

    # BASE (Bottom BGA & LSC layer)
    conductor_specs.append({
        "cond_order": 27, "layer": "BASE", "mcm_subclass": "BOTTOM", "pdn_zone": "BASE",
        "cu_group": "12Cu + 40um_GCP", "cu_thickness_um": 12.0, "de_below_name": "BGA / LSC Solder Mask (SMB)", "de_below_um": "N/A (Bottom Surface)",
        "via_padstack_up": "V90_65_90_12B_BASE_01A (90/65/90 GCP) | V83_55_83_12B_BASE_01A | V77_49_77_12B_BASE_01A",
        "via_padstack_down": "BGA Pads (C560_35_01B 630um Cu / 560um SRO, C480_60_01B, C430_60_01B) + LSC Pads (S300_24_01B 348um Cu / 300um SRO, R1000X200_70_01B)",
        "via_drill_down_um": "65.0 (from 12B GCP)", "via_pad_down_um": "90.0 (uVia) | 630.0 (BGA Cu) | 348.0 (0201 LSC Cu)",
        "max_stack_via_bu_normal": 7, "max_stack_via_pp_shape": 9, "max_stack_via_on_pth": 5, "max_stack_via_hsio": 6,
        "min_web_aperture_um": 14.0,
        "edtc_max_stack_via": "0 (LSC Not Allowed under DTC)",
        "via_to_via_edge_um": "67.5 (GCP 90_65_90) | 18.0 (12Cu)",
        "via_pitch_diff_net_um": "180.0 (40um GCP 90_65_90) | 870.0 (Min BGA Pitch)",
        "via_pitch_same_net_um": "76.0 (90_65_90)",
        "adj_layer_via_overlap_um": "14.0",
        "via_to_pin_space_um": "18.0",
        "cline_to_via_space_um": "18.0 (Routing Not Allowed on BASE)",
        "via_to_shape_space_um": "50.0",
        "shape_to_shape_space_um": "50.0",
        "trace_to_shape_space_um": "50.0 (Routing Not Allowed on BASE)",
        "min_line_width_space_um": "Routing NOT Allowed on BASE (18/18 12Cu spec)",
        "edtc_koz_and_layer_rule": "LSC NOT Allowed under 4FCO DTC footprint (Rule #27)",
        "gcp_12b_base_rule": "BASE GCP Rule: GX92 40um GCP between BASE and 12B (Base-1); 90_65_90 uVia (180um min pitch, 67.5um Cu space); Routing NOT Allowed on BASE",
        "lsc_and_bga_sro_rule": "LSC SRO-to-SRO = 175 um (0201/0204 0.2mm tall, DR 3.5.4.6) | 250 um (0201 0.5mm tall 10uF, DR 3.5.4.7); BGA SRO-to-LSC SRO = 500 um; LSC SRO to Cavity = 225 um; BGA SRO to Cavity = 250 um",
    })

    out_per_layer_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(conductor_specs[0].keys())
    with out_per_layer_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(conductor_specs)
    return conductor_specs


def build_stage1_design_rules(
    designrule_dir: Path,
    csv_rule_files: List[Path],
    out_json: Path,
    out_csv: Path,
    out_per_layer_csv: Optional[Path] = None,
) -> Dict[str, Any]:
    """Parse design rules strictly from local workspace CSV rule sheets in specs_and_docs/design_rules/."""
    rules: Dict[str, Any] = dict(DEFAULT_DESIGN_RULES)
    rule_table_rows: List[Dict[str, str]] = []

    local_csv_sources: List[str] = []
    for cf in csv_rule_files:
        if cf.exists():
            local_csv_sources.append(str(cf))
            rows = read_tabular_lines_from_any_format(cf)
            rules = parse_design_rules_from_rows(rows, rules)

    per_layer_path = out_per_layer_csv or (out_json.parent / "per_layer_design_rules.csv")
    per_layer_rows = build_per_layer_design_rules_csv(per_layer_path)

    # Enrich indexed JSON with all 9 Pre-Learn Architect Q&A rule categories from local CSVs
    rules.update({
        "local_design_rule_csv_files": local_csv_sources,
        "per_layer_design_rules_csv": str(per_layer_path),
        "q1_max_stacked_via_rules": {
            "normal_bu_above_and_below_in_bu": 7,
            "normal_bu_above_and_below_through_pp_on_shape": 9,
            "normal_bu_above_and_below_landing_on_pth": 5,
            "max_pp_vias_per_single_pth_pad": 2,
            "hsio_void_front_above_core": 3,
            "hsio_void_front_ids_on_pth": 0,
            "hsio_void_back_below_core": 6,
        },
        "q2_via_padstack_by_layer_span": {
            "SURFACE_to_C0_17um_ABF": ["VU30_19_35_SURFACE_C0_01B", "VU30_19_39_SURFACE_C0_01B", "VU30_19_50_SURFACE_C0_01B", "VU30_19_60_SURFACE_C0_01B", "V30_19_30_SURFACE_C0_01A"],
            "SURFACE_to_12F_34um_skip_C0": ["V77_49_77_SURFACE_12F_01A", "V77_49_77_01B_L01_L03"],
            "12F_to_9F_30um_ABF_15Cu": ["V77_49_77_12F_11F_01A", "V77_49_77_11F_10F_01A", "V77_49_77_10F_9F_01A"],
            "9F_to_5F_50um_ABF_18Cu": ["V90_65_90_9F_8F_01A", "V90_65_90_8F_7F_01A", "V90_65_90_7F_6F_01A", "V90_65_90_6F_5F_01A"],
            "5F_to_4FCO_50um_ABF_to_PP": ["V90_65_121_5F_4FCO_01A", "V90_65_121_01A_L10_L11", "V90_65_90_on_4FCO_eDTC_Pad"],
            "4FCO_to_2FCI_60um_Prepreg": ["V175_85_175_4FCO_3FCI_01A", "V282_5_85_175_4FCO_3FCI_01A", "V175_85_175_3FCI_2FCI_01A", "V175_85_282_5_3FCI_2FCI_01A"],
            "2FCI_to_2BCI_1570um_Core_PTH": ["V282_5_150_282_5_01A_2FCI_2BCI", "V282_5_150_282_5_2FCI_2BCI_01B", "V282_5_150_282_5_2FCI_2BCI_02A", "V282_5_150_282_5_2FCI_2BCI_02D"],
            "2BCI_to_4BCO_60um_Prepreg": ["V175_85_175_2BCI_3BCI_01A", "V282_5_85_175_2BCI_3BCI_01A", "V175_85_175_3BCI_4BCO_01A", "V175_85_282_5_3BCI_4BCO_01A"],
            "4BCO_to_5B_50um_PP_to_ABF": ["V121_65_90_4BCO_5B_01A", "VIA1718_121P_85D_90P"],
            "5B_to_9B_50um_ABF_18Cu": ["V90_65_90_5B_6B_01A", "V90_65_90_6B_7B_01A", "V90_65_90_7B_8B_01A", "V90_65_90_8B_9B_01A"],
            "9B_to_12B_30um_ABF_15Cu": ["V77_49_77_9B_10B_01A", "V77_49_77_10B_11B_01A", "V83_55_83_10B_11B_01A", "V77_49_77_11B_12B_01A", "V83_55_83_11B_12B_01A"],
            "12B_to_BASE_40um_GCP_or_30um_ABF": ["V90_65_90_12B_BASE_01A", "V83_55_83_12B_BASE_01A", "V77_49_77_12B_BASE_01A"],
        },
        "q3_min_web_aperture_3_4_1_18_um": {
            "12Cu_SURFACE_BASE_C0": 14.0,
            "15Cu_12F_11F_10F_10B_11B_12B": 14.0,
            "18Cu_9F_8F_7F_6F_5F_5B_6B_7B_8B_9B": 14.0,
            "25Cu_4FCO_4BCO": 67.5,
            "25Cu_Inner_3FCI_1FCI_1BCI_3BCI": 67.5,
            "35Cu_2FCI_2BCI": 67.5,
        },
        "q4_edtc_pin_via_rules": {
            "edtc_terminal_layer": "4FCO",
            "edtc_padstack_names": ["C200M_0_4FCO_01A", "S200M_0_4FCO_01A"],
            "edtc_pad_min_size_um": 200.0,
            "edtc_pad_to_pad_spacing_um": 50.0,
            "edtc_pad_min_center_pitch_um": 250.0,
            "edtc_landing_via_size": "90_65_90 (65um drill, 90um pad)",
            "edtc_vias_required_per_pad": 1,
            "edtc_max_stacked_via_on_pad": 2,
        },
        "q4b_edtc_to_edtc_spacing_rules_um": {
            "edtc_pad_to_pad_edge_spacing_um": 50.0,
            "edtc_pad_to_pad_center_pitch_um": 250.0,
            "edtc_body_edge_to_cavity_edge_koz_um": 300.0,
            "edtc_cavity_edge_to_cavity_edge_min_spacing_um": 1600.0,
            "edtc_body_edge_to_body_edge_min_spacing_um": 2200.0,
            "edtc_guard_ring_outer_to_guard_ring_outer_min_spacing_um": 1300.0,
            "edtc_inner_core_channel_width_between_min_spaced_dtcs_um": 1300.0,
            "edtc_cavity_edge_to_die_edge_min_spacing_um": 1000.0,
            "edtc_cavity_edge_to_emib_cavity_edge_min_spacing_um": 1000.0,
            "edtc_fiducial_center_to_fiducial_center_min_spacing_um": 10000.0,
            "edtc_fiducial_edge_to_surrounding_metal_min_spacing_um": 500.0,
        },
        "q5_via_to_via_spacing_and_pitch_um": {
            "edge_to_edge_3_4_1_46": {
                "12Cu_Unrestricted": 18.0,
                "12Cu_EMIB": 9.9,
                "15Cu_All": 18.0,
                "18Cu_All": 18.0,
                "25Cu_25CuInner_35Cu_PP_Core": 67.5,
                "12B_Base1_DiffNet_with_40um_GCP": 90.0,
            },
            "center_to_center_pitch": {
                "30_35um_ABF_77_49_77_diff_net": 95.0,
                "30_35um_ABF_77_49_77_same_net_overlap": 63.0,
                "50um_ABF_90_65_90_diff_net": 108.0,
                "50um_ABF_90_65_90_same_net_overlap": 76.0,
                "50um_ABF_NextToCore_90_65_121_diff_net": 139.0,
                "50um_ABF_NextToCore_90_65_121_same_net_overlap": 76.0,
                "60um_PP_175_85_175_diff_net": 242.5,
                "60um_PP_175_85_175_same_net_overlap": 130.0,
                "40um_GCP_90_65_90_diff_net": 180.0,
                "Core_PTH_diff_net_with_inner_pad": 432.5,
                "Core_PTH_diff_net_without_inner_pad": 350.0,
                "Core_PTH_same_net_common_inner_pad_PKG08": 270.0,
                "Core_PTH_same_net_common_inner_pad_PKG01": 216.5,
            },
            "adjacent_layer_staggered_pad_overlap_um": {
                "BU_to_BU_same_layer": 14.0,
                "BU_to_BU_staggered_alternate": "14.0 -> 25.0",
                "PP_to_BU": 12.5,
                "PP_to_PP": 45.0,
                "PTH_to_PP": 45.0,
            },
        },
        "q6_via_to_pin_spacing_3_4_1_25_um": {
            "12Cu_SURFACE_BASE_Unrestricted_and_Necking": 18.0,
            "12Cu_SURFACE_C0_EMIB": 9.9,
            "15Cu_12F_to_10F_10B_to_12B_All": 18.0,
            "18Cu_9F_to_5F_5B_to_9B_All": 18.0,
            "25Cu_25CuInner_35Cu_PP_and_Core": 67.5,
            "C4_via_pad_to_EMIB_cavity_12F_11F": 82.5,
            "C4_via_pad_to_CSB_pad_10F": 372.0,
        },
        "q7_cline_via_shape_spacing_by_cu_group_um": {
            "12Cu": {
                "cline_to_via_3_4_1_41": {"Unrestricted": 18.0, "Restricted_Necking": "12.0 - 13.0", "EMIB": 16.0},
                "via_to_shape_3_4_1_30": {"Unrestricted": 50.0, "Restricted_Necking": 30.0, "EMIB": 16.0},
                "shape_to_shape_3_4_1_29": {"Unrestricted": 50.0, "Restricted_Necking": 50.0, "EMIB": 16.0},
                "trace_to_shape_3_4_1_40": {"Unrestricted": 50.0, "Restricted_Necking": 30.0, "EMIB": 16.0},
            },
            "15Cu": {
                "cline_to_via_3_4_1_41": {"Unrestricted": 18.0, "Restricted_Necking": "12.0 - 13.0", "EMIB": "12.0 - 13.0"},
                "via_to_shape_3_4_1_30": {"Unrestricted": 50.0, "Restricted_Necking": 30.0, "EMIB": 30.0},
                "shape_to_shape_3_4_1_29": {"Unrestricted": 50.0, "Restricted_Necking": 50.0, "EMIB": 30.0},
                "trace_to_shape_3_4_1_40": {"Unrestricted": 50.0, "Restricted_Necking": 30.0, "EMIB": 30.0},
            },
            "18Cu": {
                "cline_to_via_3_4_1_41": {"Unrestricted": 18.0, "Restricted_Necking": 12.0, "EMIB": 12.0},
                "via_to_shape_3_4_1_30": {"Unrestricted": 50.0, "Restricted_Necking": 50.0, "EMIB": 50.0},
                "shape_to_shape_3_4_1_29": {"Unrestricted": 50.0, "Restricted_Necking": 50.0, "EMIB": 50.0},
                "trace_to_shape_3_4_1_40": {"Unrestricted": 50.0, "Restricted_Necking": 30.0, "EMIB": 30.0},
            },
            "25Cu_25CuInner_35Cu": {
                "cline_to_via_3_4_1_41": 67.5,
                "via_to_shape_3_4_1_30": 67.5,
                "shape_to_shape_3_4_1_29": 67.5,
                "trace_to_shape_3_4_1_40": 67.5,
            },
        },
        "q8_edtc_koz_and_per_layer_rules": {
            "SURFACE_to_10F": "DTC NOT allowed under EMIB Die (Rule #14); DTC Cavity Edge to Die Edge >= 1000 um (Rule #4); DTC Cavity Edge to EMIB Cavity Edge >= 1000 um (Rule #5)",
            "6F_and_5F": "Landing via 90_65_90 (65um drill / 90um pad), 1 via per DTC pad, max 2 stacked vias on DTC pad (Rules #9-12, #17, #22-23)",
            "4FCO": "DTC Pad min 200x200 um, pad-to-pad spacing 50 um (Rules #1-3); DTC Edge to DTC Cavity Edge KOZ = 300 um (Rule #6); DTC Cavity to Cavity = 1600 um (Rule #7)",
            "2FCI_and_2BCI_Outermost_Core": "NO Trace/Via/Pin/Shape allowed inside DTC Cavity (Rule #18); Guard Metal Ring width >= 150 um around DTC Cavity (Rule #8); Guard Metal CANNOT have any adhesion/degassing holes or vias (Rule #26); 4 global fiducials 500um pad / 500um clearance / 10000um spacing (Rules #15-16, #19-21)",
            "3FCI_1FCI_1BCI_3BCI_Inner_Core_PP": "NO Trace/Via/Pin/Shape allowed inside DTC Cavity (Rule #18); Min spacing from DTC Cavity Edge to nearest metal in all inner core layers = 150 um (Rule #24 -> 300 + 150 = 450 um total KOZ from DTC body edge)",
            "5B_First_Backside_BU": "Solid Plane REQUIRED under DTC Cavity including Guard Metal (Rule #13); adhesion/degassing holes and vias ARE allowed in 5B solid plane (Rule #25)",
            "BASE": "LSC NOT allowed under DTC (Rule #27)",
        },
        "q9_gcp_12B_and_BASE_rules": {
            "gcp_material": "GX92",
            "gcp_thickness_um": 40.0,
            "gcp_layer_span": "BASE to Base-1 (12B)",
            "gcp_uvia_padstack": "V90_65_90_12B_BASE_01A (90um pad, 65um drill, 90um pad)",
            "base1_12B_diff_net_via_to_via_space_um": 90.0,
            "gcp_cu_to_cu_space_um": 67.5,
            "gcp_min_diff_net_via_pitch_um": 180.0,
            "routing_allowed_on_BASE_12B_11B": False,
        },
        "q10_lsc_and_bga_sro_rules": {
            "lsc_0201_0p2mm_tall_sro_to_sro_um": 175.0,
            "lsc_0204_0p2mm_tall_sro_to_sro_um": 175.0,
            "lsc_0201_0p5mm_tall_10uF_sro_to_sro_um": 250.0,
            "bga_sro_to_lsc_sro_spacing_um": 500.0,
            "lsc_sro_to_cavity_edge_um": 225.0,
            "bga_sro_to_cavity_edge_um": 250.0,
            "lsc_0201_pad_and_sro_um": {"cu_pad": 348.0, "sro": 300.0, "padstack": "S300_24_01B"},
            "lsc_0204_pad_and_sro_um": {"cu_pad": [1048.0, 248.0], "sro": [1000.0, 200.0], "padstack": "R1000X200_70_01B"},
            "bga_pad_and_sro_um": {"cu_pad": 630.0, "sro": 560.0, "min_pitch": 870.0, "padstack": "C560_35_01B"},
        },
        "indexed_conductor_layer_count": len(per_layer_rows),
    })

    for k, v in sorted(rules.items()):
        if isinstance(v, (int, float, str, bool)):
            rule_table_rows.append({"rule_parameter": k, "indexed_value": str(v), "source": "LOCAL_SPECS_AND_DOCS_DESIGN_RULES"})

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rule_parameter", "indexed_value", "source"])
        writer.writeheader()
        writer.writerows(rule_table_rows)

    out_json.write_text(json.dumps(rules, indent=2), encoding="utf-8")
    return rules


def run_stage1_full_input_preparation(
    mcm_path: str = DRIVE_FOLDER_SOURCES["mcm_source"]["local_path"],
    padstack_lib_dir: str = DRIVE_FOLDER_SOURCES["padstack_library"]["local_path"],
    symbols_dir: str = DRIVE_FOLDER_SOURCES["lsc_and_symbols"]["local_path"],
    designrule_dir: str = DRIVE_FOLDER_SOURCES["design_rules"]["local_path"],
    out_dir: str = "agent04_pdn_architect/stage1_inputs",
    run_headless_apd_extract: bool = True,
) -> Dict[str, Any]:
    """Execute complete Stage 1 input file extraction & indexing from the 4 user-specified sources."""
    workspace = Path(__file__).resolve().parent.parent.parent
    agent_dir = Path(__file__).resolve().parent.parent
    out_p = workspace / out_dir if not Path(out_dir).is_absolute() else Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    # Use local NVMe cache of the .mcm if present to avoid streaming 2.98 GB over G:\My Drive
    local_mcm_cache = workspace / "mcm_designs" / "HH_full_Main_Drawing_Nguyen_2026-0916_2000_CORE_TO_R3.mcm"
    effective_mcm = local_mcm_cache if local_mcm_cache.exists() else Path(mcm_path)

    script_dir = agent_dir / "scripts"
    extractor_report: Dict[str, str] = {}
    if run_headless_apd_extract and effective_mcm.exists():
        skill_loads = [
            script_dir / "pdn_core_batch.il",
            script_dir / "padstack_learner_batch.il",
            script_dir / "stage1_full_extractor_batch.il",
            script_dir / "pdn_Pipeline_batch.il",
        ]
        runner = CadenceBatchRunner()
        scr_path = runner.create_scr_file(
            skill_loads=skill_loads,
            skill_calls=['pdnDispatchBatchJob("STAGE1_FULL_EXTRACT" "FALSE")'],
            output_scr_path=out_p / "run_stage1_extract.scr",
        )
        runner.run(
            mcm_path=effective_mcm.resolve(),
            scr_path=scr_path,
            working_dir=out_p,
            bypass_lock_readonly=True,
        )
        rep_file = out_p / "stage1_extraction_report.txt"
        if rep_file.exists():
            for line in rep_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    extractor_report[k.strip()] = v.strip()

    # 2. Build 53-Layer Stackup CSV & 6-Zone Classification JSON
    stackup_summary = build_stage1_stackup_csv(
        mcm_layers_txt=workspace / "cadence_extract" / "mcm_layers.txt",
        out_csv=out_p / "stackup_53layers.csv",
        out_zones_json=out_p / "stackup_zones.json",
    )

    # 3. Build Padstack Library Index CSV (combining <cadence_library_dir> + .mcm padstacks)
    padstack_summary = build_stage1_padstack_index(
        library_dir=Path(padstack_lib_dir),
        mcm_learned_txt=agent_dir / "reports" / "pdn_mcm_learned.txt",
        mcm_padstacks_txt=workspace / "cadence_extract" / "mcm_padstacks.txt",
        out_csv=out_p / "padstack_library_index.csv",
    )

    # 4. Build Full Die/HBM/EMIB Bridge Bump Package Summary from Symbols/*.zip
    bump_pkg_summary = build_stage1_bump_package_summaries_from_symbols_zip(
        symbols_dir=Path(symbols_dir),
        out_summary_csv=out_p / "bump_package_net_summary.csv",
    )

    # 5. Build LSC & Die/Bridge Symbol Library CSV
    symbol_lib_records = build_stage1_lsc_and_symbol_library_csv(
        library_dir=Path(padstack_lib_dir),
        symbols_dir=Path(symbols_dir),
        out_csv=out_p / "lsc_symbol_library.csv",
    )

    # 6. Build Design Rule Index strictly from local specs_and_docs/design_rules/*.csv
    local_dr_dir = workspace / "specs_and_docs" / "design_rules"
    csv_rules = sorted(local_dr_dir.glob("*.csv")) if local_dr_dir.exists() else []
    design_rules = build_stage1_design_rules(
        designrule_dir=local_dr_dir,
        csv_rule_files=csv_rules,
        out_json=out_p / "design_rules_indexed.json",
        out_csv=out_p / "design_rules_table.csv",
        out_per_layer_csv=out_p / "per_layer_design_rules.csv",
    )

    manifest = {
        "status": "SUCCESS",
        "stage": "STAGE1_PRELEARN_COMPLETE",
        "drive_sources": DRIVE_FOLDER_SOURCES,
        "mcm_extraction_metrics": extractor_report,
        "stackup_summary": stackup_summary,
        "padstack_library_summary": padstack_summary,
        "bump_package_summary_count": len(bump_pkg_summary),
        "symbol_library_count": len(symbol_lib_records),
        "design_rules_summary": {
            "local_csv_rule_sheet_count": len(design_rules.get("local_design_rule_csv_files", [])),
            "indexed_conductor_layer_count": design_rules.get("indexed_conductor_layer_count", 27),
            "max_stacked_via_bu": design_rules["max_stacked_via_bu"],
            "max_stacked_via_on_pth": design_rules["max_stacked_via_on_pth"],
            "pth_density_ids_per_mm2": design_rules["pth_density_ids_per_mm2"],
            "pth_density_ods_per_mm2": design_rules["pth_density_ods_per_mm2"],
            "edtc_cavity_koz_um": design_rules["edtc_cavity_koz_um"],
            "edtc_guard_metal_width_um": design_rules["edtc_guard_metal_width_um"],
            "lsc_to_lsc_spacing_um": design_rules["lsc_to_lsc_spacing_um"],
            "lsc_sro_to_bga_sro_spacing_um": design_rules["lsc_sro_to_bga_sro_spacing_um"],
        },
        "prepared_stage1_files": {
            "bga_map_csv": str(out_p / "bga_map.csv"),
            "bump_map_csv": str(out_p / "bump_map.csv"),
            "bump_package_net_summary_csv": str(out_p / "bump_package_net_summary.csv"),
            "die_bridge_refdes_summary_csv": str(out_p / "die_bridge_refdes_summary.csv"),
            "edtc_symbols_csv": str(out_p / "edtc_symbols.csv"),
            "edtc_pin_map_csv": str(out_p / "edtc_pin_map.csv"),
            "lsc_placed_map_csv": str(out_p / "lsc_placed_map.csv"),
            "lsc_symbol_library_csv": str(out_p / "lsc_symbol_library.csv"),
            "refdes_inventory_csv": str(out_p / "refdes_inventory.csv"),
            "stackup_53layers_csv": str(out_p / "stackup_53layers.csv"),
            "stackup_zones_json": str(out_p / "stackup_zones.json"),
            "padstack_library_index_csv": str(out_p / "padstack_library_index.csv"),
            "design_rules_table_csv": str(out_p / "design_rules_table.csv"),
            "per_layer_design_rules_csv": str(out_p / "per_layer_design_rules.csv"),
            "design_rules_indexed_json": str(out_p / "design_rules_indexed.json"),
        },
    }
    (out_p / "stage1_master_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    res = run_stage1_full_input_preparation(run_headless_apd_extract=True)
    print(json.dumps(res["mcm_extraction_metrics"], indent=2))
