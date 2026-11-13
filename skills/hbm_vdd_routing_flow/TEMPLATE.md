# `HBM` (`U13` / `U13..U24`) `VDD*` Routing Flow — Customizable JSON & Recipe Templates

> [!TIP]
> All 4 HBM power rails (`VDDQ_0P85_HBM_MEM*`, `VDDC_1P0_HBM_MEM*`, `VDDQL*`, `VPP_1P8_HBM_MEM*`), `SURFACE` West gang-stripe vs. East `C0` EMIB options, 27-layer strip/plane assignments, `4FCO` `eDTC`s, and `BASE` `6-via`/`4-via` BGA clusters + `LSC_CAVITY` Recess parameters are exposed below so you can customize or clone across `U13..U24` effortlessly.

## 1. HBM 4-Rail Configuration JSON Template (`hbm_vdd_config.json`)

```json
{
  "flow_name": "HBM4E_4RAIL_27LAYER_PDN_ROUTING_FLOW",
  "target_hbm_site": {
    "hbm_refdes": "U13",
    "hbm_symbol": "HBM4E_MICRON_NOMINAL_BC_A0",
    "channel_id": "5",
    "paired_lava_emib_refdes": "U41",
    "paired_lava_emib_symbol": "LAVA_BRIDGE_22_BC_A0",
    "paired_host_ldb_refdes": "U5",
    "rails": {
      "vddq":  "VDDQ_0P85_HBM_MEM5",
      "vddc":  "VDDC_1P0_HBM_MEM5",
      "vddql": "VDDQL5",
      "vpp":   "VPP_1P8_HBM_MEM5",
      "vss":   "VSS"
    },
    "kelvin_sense_pairs": [
      ["OBS_VDDQ_0P85_HBM_MEM5", "OBS_VDDQ_0P85_HBM_MEM5_VSS"],
      ["OBS_VDDC_1P0_HBM_MEM5", "OBS_VDDC_1P0_HBM_MEM5_VSS"],
      ["OBS_VDDQL5",             "OBS_VDDQL5_VSS"],
      ["OBS_VPP_1P8_HBM_MEM5",  "OBS_VPP_1P8_HBM_MEM5_VSS"],
      ["SNS_VDDC_1P0_HBM_MEM5", "SNS_VDDC_1P0_HBM_MEM5_VSS"],
      ["SNS_VDDQL5",             "SNS_VDDQL5_VSS"]
    ]
  },
  "zone1_dual_surface_escape_options": {
    "hbm_bump_padstack": "C21_7_DP_01A",
    "west_non_emib_mode": "HORIZONTAL_90UM_GANG_STRIPES_AND_35UM_STRAPS",
    "west_gang_stripe_height_um": 90.0,
    "west_strap_width_um": 35.0,
    "west_surface_to_12f_padstack": "V77_49_77_SURFACE_12F_01A",
    "west_vddc_to_vss_via_ratio": "LEARNED_OR_3_TO_1",
    "east_emib_hbm_to_c0_padstack": "VU30_19_60_SURFACE_C0_01B",
    "east_emib_ldb_to_c0_padstack": "VU30_19_39_SURFACE_C0_01B",
    "min_surface_drc_space_um": 18.0
  },
  "emib_bridge_design_rules": {
    "adjacent_emib_refdes": ["U41"],
    "c0_exclusivity_inside_bridge_only": true,
    "cavity_wall_to_emib_die_um": 75.0,
    "l12f_l11f_c4_pad_shape_to_cavity_min_um": 82.5,
    "l12f_l11f_total_koz_from_emib_die_um": 157.5,
    "l10f_no_plane_or_trace_under_emib_die": true,
    "l10f_isolated_guard_ring_width_um": 150.0,
    "l10f_c4_pad_shape_to_guard_ring_min_um": 50.0,
    "l10f_c4_pad_shape_to_csb_pad_min_um": 372.0,
    "csb_padstack": "C77_10F_DP_01A",
    "csb_max_stacked_via_below_10f": 2,
    "edtc_cavity_to_emib_cavity_min_um": 1000.0,
    "base_exclude_lsc_under_emib_die_shadow": true
  },
  "layer_plane_partition_map": {
    "12F":  { "mode": "DEDICATED_EMIB_VOIDED", "net": "VDDC_1P0_HBM_MEM5" },
    "11F":  { "mode": "DEDICATED_EMIB_VOIDED", "net": "VSS" },
    "10F":  { "mode": "DEDICATED_CSB_FLOOR",   "net": "VDDQ_0P85_HBM_MEM5", "csb_breakout_nets": ["VDDQL5", "VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VPP_1P8_HBM_MEM5", "VSS"] },
    "9F":   { "mode": "DEDICATED",             "net": "VSS" },
    "8F":   { "mode": "WEST_EAST_SPLIT",       "west_net": "VDDC_1P0_HBM_MEM5", "east_net": "VDDQ_0P85_HBM_MEM5", "split_x_um": -35858.0, "split_gap_um": 50.0 },
    "7F":   { "mode": "DEDICATED",             "net": "VSS" },
    "6F":   { "mode": "FOUR_RAIL_SPLIT",       "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5"], "split_gap_um": 50.0 },
    "5F":   { "mode": "DEDICATED",             "net": "VSS" },
    "4FCO": { "mode": "FOUR_RAIL_SPLIT_EDTC",  "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5"], "split_gap_um": 67.5 },
    "3FCI": { "mode": "DEDICATED",             "net": "VSS" },
    "2FCI": { "mode": "FOUR_STRIP_CORE",       "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDQ_0P85_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5"], "split_gap_um": 67.5 },
    "1FCI": { "mode": "VSS_WITH_VDDC_FINGERS", "net": "VSS", "finger_net": "VDDC_1P0_HBM_MEM5", "finger_width_um": 230.0 },
    "1BCI": { "mode": "VSS_WITH_VDDC_FINGERS", "net": "VSS", "finger_net": "VDDC_1P0_HBM_MEM5", "finger_width_um": 230.0 },
    "2BCI": { "mode": "FOUR_STRIP_CORE",       "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQ_0P85_HBM_MEM5", "VDDQL5"], "split_gap_um": 67.5 },
    "3BCI": { "mode": "DEDICATED",             "net": "VSS" },
    "4BCO": { "mode": "THREE_RAIL_SPLIT_PP",   "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5"], "split_gap_um": 67.5 },
    "5B":   { "mode": "DEDICATED_SOLID_UNDER_EDTC", "net": "VSS" },
    "6B":   { "mode": "THREE_RAIL_SPLIT",      "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQ_0P85_HBM_MEM5"], "split_gap_um": 50.0 },
    "7B":   { "mode": "DEDICATED",             "net": "VSS" },
    "8B":   { "mode": "THREE_RAIL_SPLIT",      "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5"], "split_gap_um": 50.0 },
    "9B":   { "mode": "DEDICATED",             "net": "VSS" },
    "10B":  { "mode": "TWO_RAIL_SPLIT",        "west_net": "VPP_1P8_HBM_MEM5", "main_net": "VDDQ_0P85_HBM_MEM5", "split_gap_um": 50.0 },
    "11B":  { "mode": "DEDICATED_SHIELD",      "net": "VSS" },
    "12B":  { "mode": "THREE_RAIL_SPLIT_GCP",  "strips_west_to_east": ["VPP_1P8_HBM_MEM5", "VDDC_1P0_HBM_MEM5", "VDDQL5"], "split_gap_um": 67.5 }
  },
  "zone2_edtc_4fco_options": {
    "vddc_48pin_edtc": { "refdes": "C2258", "symbol": "N24792-017_LIVE_BUG_4FCO_02A", "vddc_pins": 24, "vss_pins": 24 },
    "vddq_24pin_edtc": { "refdes": "C2257", "symbol": "N24792-016_LIVE_BUG_4FCO_02A", "vddq_pins": 12, "vss_pins": 12 },
    "concentric_pin_landing_offset_um": 0.0,
    "cavity_koz_um": 300.0,
    "guard_metal_width_um": 150.0,
    "core_metal_to_guard_space_um": 67.5,
    "block_all_routing_4fco_to_4bco_in_koz": true,
    "require_solid_5b_plane_under_edtc": true
  },
  "zone3_core_pth_pp_options": {
    "pp_via_mode": "CONCENTRIC_1VIA_PER_PTH",
    "pp_4fco_3fci_padstack": "V282_5_85_175_4FCO_3FCI_01A",
    "pp_3fci_2fci_padstack": "V175_85_175_3FCI_2FCI_01A",
    "power_pth_padstack": "V282_5_150_282_5_2FCI_2BCI_01B",
    "sense_pth_padstack": "V282_5_150_282_5_2FCI_2BCI_02A",
    "pp_2bci_3bci_padstack": "V282_5_85_175_2BCI_3BCI_01A",
    "pp_3bci_4bco_padstack": "V175_85_282_5_3BCI_4BCO_01A",
    "same_net_pth_min_pitch_um": 270.0,
    "diff_net_pth_min_pitch_um": 432.5
  },
  "zone5_base_bga_lsc_and_cavity": {
    "bga_padstack": "C560_35_01B",
    "vddq_bga_via_cluster": { "vias_per_bga": 6, "offsets_um": [[-45.0, -45.0], [-45.0, 45.0], [0.0, -123.0], [0.0, 123.0], [45.0, -45.0], [45.0, 45.0]] },
    "vddc_vddql_vpp_bga_via_cluster": { "vias_per_bga": 4, "offsets_um": [[-200.0, 0.0], [200.0, 0.0], [0.0, -200.0], [0.0, 200.0]] },
    "lsc_symbol": "SM0201_690X390X550_01A",
    "pocket_a_west_of_u41": { "vddc_lscs": 16, "vddq_lscs": 11 },
    "pocket_b_north_of_u41": { "vddql_lscs": 6 },
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

## 2. HBM Multi-Rail Pipe-Delimited Master Recipe Format (`*_HBM_APD_Master_Recipe.txt`)

Supports `SURFACE` fine-pitch bump gang-stripes (`SURFACE_STRIPE|`), multi-rail co-planar strips/islands (`PLANE|`, `PLANE_VOID|`, `PLANE_ISLAND|`), `R = 500 um` `LSC_CAVITY` + `Code D` `178 um` keepouts (`CAVITY_OUTLINE|`), co-pocket LSCs (`LSC_SYM|`), `VIA|`, and `CLINE|`:

```text
# 1. Horizontal SURFACE Gang-Stripe Bar Connecting C21_7_DP_01A HBM Bumps to V77_49_77 Vias (West of U41)
SURFACE_STRIPE|<net_name>|SURFACE|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 2. Outer Main Plane (`VDDQ_*`, `VDDC_*`, `VDDQL*`, `VPP_*`, or `VSS`)
PLANE|<net_name>|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 3. Void Inside Preceding PLANE (12F/11F/10F U41 EMIB/Guard/CSB KOZ, 4FCO..4BCO C2257/C2258 KOZ, or Split Cutout)
PLANE_VOID|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 4. Co-Planar Sub-Island / Strip Shape (`>= 50.0 um` BU / `>= 67.5 um` Core/PP/GCP split clearance)
PLANE_ISLAND|<sub_net_name>|<layer>|<x1_um>|<y1_um>|<x2_um>|<y2_um>

# 5. Rounded-Corner Mechanical Recess Cavity (`SUBSTRATE GEOMETRY/LSC_CAVITY`) + `178 um` `ROUTE KEEPOUT/BASE`
CAVITY_OUTLINE|<pocket_id>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<corner_r_um>|<ext_koz_um>

# 6. Mirrored 0201 LSC Component on BASE (`Pocket A`: `VDDC`+`VDDQ`; `Pocket B`: `VDDQL`)
LSC_SYM|<refdes>|<symbol_name>|<x_um>|<y_um>|<rotation_deg>|MIRROR_YES|<pin1_net>|<pin2_net>

# 7. Via Instance (`VU30_19_60`, `V77_49_77`, `V90_65_90`, `V282_5_85_175`, `V282_5_150_282_5`, etc.)
VIA|<net_name>|<padstack_name>|<start_layer>|<end_layer>|<x_um>|<y_um>|<zone_tag>

# 8. CLINE Segment (`SURFACE` 35um Straps, `12F` 18um OBS_* Sense, `10B` 16.5um SNS_* Sense, `12B` 90um Dogbones)
CLINE|<net_name>|<layer>|<width_um>|<x1_um>|<y1_um>|<x2_um>|<y2_um>|<zone_tag>
```
