# `VDDUC` & `VDDCH` Routing Flow — Configuration & Recipe Templates

## 1. Domain Configuration JSON Template (`vdduc_vddch_config.json`)

```json
{
  "flow_name": "VDDUC_VDDCH_27LAYER_PDN_FLOW",
  "target_die": {
    "refdes": "U7",
    "symbol_name": "HUTTON_HILL_LDB_BC_A0",
    "vdd_net": "VDDUC0",
    "vss_net": "VSS"
  },
  "zone1_surface_options": {
    "vdd_to_vss_via_ratio": "3:1",
    "cell_period": 3,
    "floating_bump_strap_direction": "HORIZONTAL",
    "strap_width_um": 24.0,
    "surface_via_padstack": "V77_49_77_SURFACE_12F_01A",
    "emib_ubump_via_padstack": "VU30_19_35_SURFACE_C0_01B",
    "min_cline_to_pad_drc_um": 18.0
  },
  "emib_bridge_design_rules": {
    "adjacent_emib_refdes": ["U28", "U32", "U35", "U38", "U47", "U48", "U49"],
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
  "zone2_edtc_4fco_options": {
    "edtc_refdes_list": ["C2238", "C2239", "C2209", "C2210", "C2211"],
    "concentric_pin_landing_offset_um": 0.0,
    "max_stacked_vias_on_edtc_pin": 2,
    "cavity_koz_um": 300.0,
    "guard_metal_width_um": 150.0,
    "core_metal_to_guard_space_um": 67.5,
    "block_all_routing_4fco_to_4bco_in_koz": true,
    "require_solid_5b_plane_under_edtc": true
  },
  "zone3_core_pth_pp_options": {
    "target_pth_density_per_mm2": 7.0,
    "pth_grid_pattern": "STAGGERED",
    "vdd_pth_padstack": "V282_5_150_282_5_2FCI_2BCI_01B",
    "vss_pth_padstack": "V282_5_150_282_5_2FCI_2BCI_02A",
    "concentric_pp_on_pth_offset_um": 0.0,
    "same_net_pth_min_pitch_um": 270.0,
    "diff_net_pth_min_pitch_um": 432.5
  },
  "zone1b_4_bu_stack_pruning": {
    "vdd_plane_layers": ["12F", "10F", "8F", "6F", "4FCO", "2FCI", "2BCI", "4BCO", "6B", "8B", "10B", "12B"],
    "vss_plane_layers": ["11F", "9F", "7F", "5F", "3FCI", "1FCI", "1BCI", "3BCI", "5B", "7B", "9B", "11B"],
    "enforce_atomic_2via_net_matched_pruning": true,
    "allow_dangling_vias": false
  },
  "zone5_base_lsc_and_recess_cavity": {
    "lsc_symbol": "SM0201_690X390X550_01A",
    "lsc_sro_to_sro_min_um": 250.0,
    "bga_sro_to_lsc_sro_min_um": 500.0,
    "enforce_recess_cavity_rule": true,
    "bga_sro_to_cavity_min_um": 250.0,
    "lsc_sro_to_cavity_min_um": 225.0,
    "cavity_corner_radius_um": 500.0,
    "cavity_min_xy_um": 1016.0,
    "cavity_to_cavity_min_web_um": 508.0,
    "base_ext_cu_signal_to_cavity_koz_um": 178.0,
    "inner_cu_signal_to_cavity_koz_um": 203.0,
    "lsc_uvia_padstack": "V90_65_90_12B_BASE_01A",
    "lsc_vias_per_cap": 6,
    "bga_via_cluster_option": "OPTION3_6VIA_HEX_RING"
  }
}
```

---

## 2. Pipe-Delimited Master Recipe Record Specification (`*_APD_Master_Recipe.txt`)

Following the workspace rule (*Python parses large CSVs and outputs a flat pipe-delimited text file loaded into SKILL `makeTable` with zero stack overflow*), the SKILL template consumes 6 deterministic record types:

```text
# 1. Copper Plane Shape (Closed Filled Shape on CONDUCTOR/<layer>, isFilled = t)
PLANE|<net_name>|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 2. Plane Void Cutout (Closed Void inside immediately preceding PLANE for 4FCO..4BCO eDTC KOZ)
PLANE_VOID|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 3. Bottom (BASE) Mirrored 0201 LSC Component Placement + Pin Net Re-Mapping
LSC_SYM|<refdes>|<symbol_name>|<x_um>|<y_um>|<rotation_deg>|MIRROR_YES|<pin1_net>|<pin2_net>

# 4. Mechanical Recess Cavity Outline & BASE Copper/Signal Keepout Halo
CAVITY_OUTLINE|<pocket_id>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<corner_r_um>|<ext_koz_um>

# 5. Via Instance (Exact .mcm Padstack & Start/End Layer Span)
VIA|<net_name>|<padstack_name>|<start_layer>|<end_layer>|<x_um>|<y_um>|<zone_tag>

# 6. CLINE Strap Segment (SURFACE M:N Horizontal/Vertical Straps or Inner Busbars)
CLINE|<net_name>|<layer>|<width_um>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<zone_tag>
```
