# Agent 04 (`pdn_architect`) — Input / Output JSON & Recipe Contract

## 1. Stage 1 (`Pre-Learn`) Request Schema

```json
{
  "stage": "STAGE1_PRELEARN",
  "stackup_file": "specs_and_docs/design_rules/Substrate Design Rules_gid_1425021083.csv",
  "design_rule_files": [
    "specs_and_docs/design_rules/Via Rules_gid_107930080.csv",
    "specs_and_docs/design_rules/eDTC DR_gid_1708488908.csv",
    "specs_and_docs/design_rules/BGALSC Rules_gid_2099350359.csv",
    "specs_and_docs/design_rules/Substrate Design Rules_gid_1425021083.csv"
  ],
  "padstack_library_folder": "input_files/padstacks",
  "mcm_path": "input_files/HH_Nguyen_2026-1023_1900_TO_v8.mcm",
  "output_index_path": "agent04_pdn_architect/pdn_knowledge_index.json"
}
```

## 2. Stage 1 (`Pre-Learn`) Output Schema (`pdn_knowledge_index.json`)

```json
{
  "status": "SUCCESS",
  "stage": "STAGE1_PRELEARN",
  "stackup_zones": {
    "ABOVE_BU": ["SURFACE", "C0", "12F", "11F", "10F", "9F", "8F", "7F", "6F", "5F"],
    "ABOVE_PP": ["4FCO", "3FCI"],
    "CORE": ["2FCI", "1FCI", "1BCI", "2BCI"],
    "BELOW_PP": ["3BCI", "4BCO"],
    "BELOW_BU": ["5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B"],
    "BASE": ["BASE"]
  },
  "edtc_layer": "4FCO",
  "design_rules": {
    "max_stacked_via_bu": 7,
    "max_stacked_via_on_pth": 5,
    "max_pp_vias_per_pth_pad": 2,
    "pth_density_ids_per_mm2": 8.0,
    "pth_density_ods_per_mm2": 3.5,
    "pth_min_pitch_diff_net_um": 432.5,
    "pth_min_pitch_same_net_um": 216.5,
    "edtc_via_padstack": "V90_65_90",
    "edtc_max_stacked_via": 2,
    "edtc_vias_per_pad": 1,
    "edtc_cavity_koz_um": 300.0,
    "edtc_guard_metal_width_um": 150.0,
    "edtc_allow_lsc_under_dtc": false,
    "lsc_to_lsc_spacing_um": 175.0,
    "lsc_sro_to_bga_sro_spacing_um": 500.0
  },
  "padstack_library_map": {
    "CORE_PTH": ["V282_5_150_282_5_01A_2FCI_2BCI"],
    "PP_VIA": ["V282_5_85_175_01A_L11_L12", "V175_85_282_5_01A_L12_L13", "V282_5_85_175_01A_L16_L17", "V175_85_282_5_01A_L17_L18"],
    "BU_TO_PP_VIA": ["V90_65_121_01A_L10_L11", "V121_65_90_01A_L18_L19"],
    "BU_UVIA": ["V90_65_90_01A_L09_L10", "V90_65_90_01A_L19_L20"],
    "EDTC_VIA": ["V90_65_90_01A_L09_L10"],
    "BGA_PAD": ["c560_35_01a"]
  }
}
```

---

## 3. Stage 2 & Stage 3 (`Synthesize + SVG Visual Sandbox`) Request Schema

```json
{
  "stage": "STAGE2_3_SANDBOX_SYNTHESIS",
  "knowledge_index_path": "agent04_pdn_architect/pdn_knowledge_index.json",
  "target_refdes": ["U1"],
  "target_nets": ["VDDC0", "VSS", "VDDSRAM"],
  "layer_polarity_map": {
    "12F": "VSS",
    "11F": "VDDC0",
    "10F": "VSS",
    "9F": "VDDC0",
    "8F": "VSS",
    "7F": "VDDSRAM",
    "6F": "VSS",
    "5F": "VDDC0",
    "4FCO": "EDTC_MIXED",
    "3FCI": "VDDC0",
    "2FCI": "VSS",
    "1FCI": "VDDC0",
    "1BCI": "VSS",
    "2BCI": "VDDC0",
    "3BCI": "VSS",
    "4BCO": "VDDC0",
    "5B": "VSS",
    "6B": "VDDC0",
    "7B": "VSS",
    "8B": "VDDC0",
    "9B": "VSS",
    "10B": "VDDC0",
    "11B": "VSS",
    "12B": "VDDC0"
  },
  "above_bu_strategy": {
    "stack_mode": "STACKED_WITH_AUTO_STAGGER",
    "max_stack_layers": 7,
    "vdd_vss_via_ratio": 1.2
  },
  "edtc_4fco_strategy": {
    "enabled": true,
    "cavity_koz_um": 300.0,
    "guard_metal_width_um": 150.0,
    "max_stacked_via_on_pad": 2,
    "vias_per_pad": 1
  },
  "core_pth_strategy": {
    "case_mode": "CASE2",
    "ids_density_per_mm2": 8.0,
    "ods_density_per_mm2": 3.5,
    "max_stacked_on_pth": 5,
    "pp_vias_per_pth": 2
  },
  "below_bu_strategy": {
    "mode": "BGA_CLUSTER_4_5",
    "vias_per_cluster": 5,
    "bga_cluster_profile": "GOOGLE_VER3"
  },
  "base_lsc_strategy": {
    "enabled": true,
    "cap_type": "0201",
    "exclude_edtc_shadow": true
  },
  "svg_sandbox_dir": "agent04_pdn_architect/svg_sandbox",
  "recipe_output_path": "agent04_pdn_architect/pdn_import_recipe.txt"
}
```

---

## 4. Stage 3 & Stage 4 Output Schema

```json
{
  "status": "SUCCESS",
  "stage": "STAGE3_4_COMPLETE",
  "target_refdes": ["U1"],
  "target_nets": ["VDDC0", "VSS", "VDDSRAM"],
  "zone_metrics": {
    "zone1_above_bu_vias": 1420,
    "zone1_actual_vdd_vss_ratio": 1.19,
    "zone2_edtc_symbols_found": 2,
    "zone2_edtc_landing_vias": 128,
    "zone2_guard_metal_rings": 2,
    "zone3_core_pth_count": 812,
    "zone3_ids_achieved_density_per_mm2": 7.98,
    "zone3_ods_achieved_density_per_mm2": 3.48,
    "zone3_pp_vias_placed": 3248,
    "zone3_diamond_star_clines": 1624,
    "zone4_below_bu_strategy": "BGA_CLUSTER_4_5",
    "zone4_below_bu_cluster_vias": 2150,
    "zone5_base_empty_pockets": 4,
    "zone5_lsc_placed": 24
  },
  "svg_sandbox_files": [
    "agent04_pdn_architect/svg_sandbox/pdn_vertical_cross_section.svg",
    "agent04_pdn_architect/svg_sandbox/zone1_above_bu_routing.svg",
    "agent04_pdn_architect/svg_sandbox/zone2_4fco_edtc_guard.svg",
    "agent04_pdn_architect/svg_sandbox/zone3_core_pth_ppvia.svg",
    "agent04_pdn_architect/svg_sandbox/zone4_below_bu_clusters.svg",
    "agent04_pdn_architect/svg_sandbox/zone5_base_lsc_pockets.svg"
  ],
  "recipe_file": "agent04_pdn_architect/pdn_import_recipe.txt",
  "mcm_import_status": "IMPORTED_OK"
}
```
