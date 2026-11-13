# `VDDC*` & `VDDRAM` (`LDA` Die) Routing Flow — Customizable JSON & Recipe Templates

> [!TIP]
> Every layer assignment, `SURFACE` ratio/strap direction, `PTH` concentric vs. dual-PP spider-web mode, and `BASE` `8-via` vs. `4/5/6-via` BGA cluster option below is parameterized so you can modify it before generating SVGs or `.mcm` recipes.

## 1. Multi-Rail Domain Configuration JSON Template (`vddc_vddram_config.json`)

```json
{
  "flow_name": "VDDC_VDDRAM_27LAYER_DUAL_RAIL_PDN_FLOW",
  "target_lda_die": {
    "refdes": "U9",
    "symbol_name": "HUTTON_HILL_LDA_BC_A0",
    "primary_vdd_net": "VDDC0",
    "secondary_sram_net": "VDD_0P8_SRAM_CC0",
    "vss_net": "VSS",
    "kelvin_sense_pairs": [
      ["OBS_VDD_0P8_SRAM_CC0_0", "OBS_VDD_0P8_SRAM_CC0_0_VSS"],
      ["OBS_VDD_0P8_SRAM_CC0_1", "OBS_VDD_0P8_SRAM_CC0_1_VSS"],
      ["SNS_VDD_0P8_SRAM_CC0",   "SNS_VDD_0P8_SRAM_CC0_VSS"]
    ]
  },
  "zone1_surface_options": {
    "vddc_to_vss_via_ratio": "FULL",
    "sram_via_mode": "FULL_3STACK_TO_10F",
    "floating_bump_strap_direction": "HORIZONTAL",
    "vddc_strap_width_um": 24.0,
    "vss_strap_width_um": 24.0,
    "surface_to_12f_padstack": "V77_49_77_SURFACE_12F_01A",
    "emib_vss_surface_to_c0_padstack": "VU30_19_35_SURFACE_C0_01B"
  },
  "emib_bridge_design_rules": {
    "adjacent_emib_refdes": ["U25", "U29", "U32", "U28", "U39"],
    "c0_exclusivity_inside_bridge_only": true,
    "cavity_wall_to_emib_die_um": 75.0,
    "l12f_l11f_c4_pad_shape_to_cavity_min_um": 82.5,
    "l12f_l11f_total_koz_from_emib_die_um": 157.5,
    "l10f_no_plane_or_trace_under_emib_die": true,
    "l10f_isolated_guard_ring_width_um": 150.0,
    "l10f_c4_pad_shape_to_guard_ring_min_um": 50.0,
    "l10f_c4_pad_shape_to_csb_pad_min_um": 372.0,
    "csb_pad_diameter_um": 77.0,
    "csb_min_pitch_um": 130.0,
    "csb_max_stacked_via_below_10f": 2,
    "edtc_cavity_to_emib_cavity_min_um": 1000.0,
    "base_exclude_lsc_under_emib_die_shadow": true
  },
  "layer_plane_partition_map": {
    "12F":  { "mode": "DEDICATED", "net": "VDDC0" },
    "11F":  { "mode": "DEDICATED", "net": "VSS" },
    "10F":  { "mode": "DEDICATED_WITH_WINDOW", "primary_net": "VDD_0P8_SRAM_CC0", "carved_windows": [{ "net": "VDDC0", "bbox_um": [3113.1, 17504.9, 6593.4, 30400.8], "split_gap_um": 50.0 }] },
    "9F":   { "mode": "DEDICATED", "net": "VSS" },
    "8F":   { "mode": "DEDICATED", "net": "VDDC0" },
    "7F":   { "mode": "DEDICATED", "net": "VSS" },
    "6F":   { "mode": "COPLANAR_SPLIT", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 50.0 },
    "5F":   { "mode": "DEDICATED", "net": "VSS" },
    "4FCO": { "mode": "COPLANAR_SPLIT_EDTC", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 67.5 },
    "3FCI": { "mode": "DEDICATED", "net": "VSS" },
    "2FCI": { "mode": "COPLANAR_SPLIT_CORE", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 67.5 },
    "1FCI": { "mode": "VSS_WITH_POWER_FINGERS", "net": "VSS", "finger_width_um": 350.0 },
    "1BCI": { "mode": "VSS_WITH_POWER_FINGERS", "net": "VSS", "finger_width_um": 350.0 },
    "2BCI": { "mode": "COPLANAR_SPLIT_CORE", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 67.5 },
    "3BCI": { "mode": "DEDICATED", "net": "VSS" },
    "4BCO": { "mode": "COPLANAR_SPLIT_PP", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 67.5 },
    "5B":   { "mode": "DEDICATED_SOLID_UNDER_EDTC", "net": "VSS" },
    "6B":   { "mode": "COPLANAR_SPLIT", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 50.0 },
    "7B":   { "mode": "DEDICATED", "net": "VSS" },
    "8B":   { "mode": "COPLANAR_SPLIT", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 50.0 },
    "9B":   { "mode": "DEDICATED", "net": "VSS" },
    "10B":  { "mode": "DEDICATED", "net": "VDD_0P8_SRAM_CC0" },
    "11B":  { "mode": "DEDICATED_SHIELD", "net": "VSS" },
    "12B":  { "mode": "COPLANAR_SPLIT_GCP", "main_net": "VDDC0", "sub_islands_net": "VDD_0P8_SRAM_CC0", "split_gap_um": 67.5 }
  },
  "zone2_shared_edtc_4fco_options": {
    "pure_vddc_edtcs": ["C2215", "C2217", "C2219", "C2220"],
    "shared_vddc_sram_edtcs": ["C2216", "C2218"],
    "concentric_pin_landing_offset_um": 0.0,
    "cavity_koz_um": 300.0,
    "guard_metal_width_um": 150.0,
    "core_metal_to_guard_space_um": 67.5,
    "block_all_routing_4fco_to_4bco_in_koz": true
  },
  "zone3_core_pth_pp_options": {
    "pp_via_mode": "CONCENTRIC_1VIA_OR_HYBRID_2VIA_SPIDER",
    "target_pth_density_per_mm2": 7.0,
    "pth_grid_pattern": "STAGGERED",
    "power_pth_padstack": "V282_5_150_282_5_2FCI_2BCI_01B",
    "sense_pth_padstack": "V282_5_150_282_5_2FCI_2BCI_02A",
    "spider_strap_width_um": 175.0
  },
  "zone4_backside_bu_options": {
    "use_high_current_10b_12b_uvia": true,
    "uvia_10b_11b_padstack": "V83_55_83_10B_11B_01A",
    "uvia_11b_12b_padstack": "V83_55_83_11B_12B_01A",
    "enforce_atomic_2via_spatial_net_matching": true,
    "allow_dangling_vias": false
  },
  "zone5_base_bga_lsc_and_cavity": {
    "bga_via_cluster_option": "OPTION4_8VIA_OCTAGON_R195",
    "bga_via_offsets_um": [[-195.0, 0.0], [195.0, 0.0], [0.0, -195.0], [0.0, 195.0], [-137.9, -137.9], [-137.9, 137.9], [137.9, -137.9], [137.9, 137.9]],
    "lsc_symbol": "SM0201_690X390X550_01A",
    "lsc_sro_to_sro_min_um": 250.0,
    "bga_sro_to_lsc_sro_min_um": 500.0,
    "allow_co_pocket_vddc_and_sram_lscs": true,
    "enforce_recess_cavity_rule": true,
    "exclude_lsc_under_emib_die_shadow": true,
    "bga_sro_to_cavity_min_um": 250.0,
    "smd1_smo_to_cavity_min_um": 254.0,
    "smd8_smo_to_cavity_min_um": 330.2,
    "lsc_sro_to_cavity_min_um": 225.0,
    "cavity_corner_radius_um": 500.0,
    "cavity_min_xy_um": 1016.0,
    "cavity_to_cavity_min_web_um": 508.0,
    "sm_min_web_um": 76.0,
    "base_ext_cu_signal_to_cavity_koz_um": 178.0,
    "inner_cu_signal_to_cavity_koz_um": 203.0
  }
}
```

---

## 2. Multi-Rail Pipe-Delimited Master Recipe Format (`*_LDA_APD_Master_Recipe.txt`)

Extends the single-rail recipe with **`PLANE_ISLAND|`** and **`PLANE_VOID|`** so `12F/11F/10F` EMIB Cavity / Guard-Ring / `CSB` keepouts, `4FCO..4BCO` `eDTC` KOZs, and carved `VDD_0P8_SRAM_CCx` sub-islands sit cleanly inside `VDDCx` main planes with exact `50.0 / 67.5 um` split clearances:

```text
# 1. Outer Main Plane (`VDDC0`, `VDD_0P8_SRAM_CC0`, or `VSS`)
PLANE|<net_name>|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 2. Void Inside Immediately Preceding PLANE (for 12F/11F/10F EMIB KOZ, 4FCO..4BCO eDTC KOZ, OR Co-Planar SRAM Cutout!)
PLANE_VOID|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 3. Carved Co-Planar Sub-Island Shape (Placed inside the expanded PLANE_VOID cutout with >=50/67.5um gap)
PLANE_ISLAND|<sub_net_name>|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 4. Rounded-Corner Mechanical Recess Cavity + Code D 178um BASE Signal/Cu KOZ
CAVITY_OUTLINE|<pocket_id>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<corner_r_um>|<ext_koz_um>

# 5. Co-Pocket Mirrored 0201 LSC Symbol (`pin1_net` = `VDDCx` or `VDD_0P8_SRAM_CCx`, `pin2_net` = `VSS`)
LSC_SYM|<refdes>|<symbol_name>|<x_um>|<y_um>|<rotation_deg>|MIRROR_YES|<pin1_net>|<pin2_net>

# 6. Via Instance (`V77_49_77`, `V90_65_90`, `V90_65_121`, `V175_85_175`, `V282_5_150_282_5`, `V83_55_83`, etc.)
VIA|<net_name>|<padstack_name>|<start_layer>|<end_layer>|<x_um>|<y_um>|<zone_tag>

# 7. CLINE Segment (`SURFACE` Straps, `3FCI/3BCI` 175um Spider Straps, `1FCI/1BCI` 350um Fingers, `7B/9B/11B` 90um Busbars)
CLINE|<net_name>|<layer>|<width_um>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<zone_tag>
```
